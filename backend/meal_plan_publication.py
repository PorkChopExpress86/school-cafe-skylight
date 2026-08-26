"""Deep module for publishing local Selections to a Skylight meal plan."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Protocol

import db
from publication_outcome import (
    DatePublicationOutcome,
    DatePublicationStatus,
    KidPublicationOutcome,
    PublicationResult,
)

_publication_lock = Lock()
_active_publications: set[tuple[str, str]] = set()


@dataclass(frozen=True)
class SkylightRecipe:
    """Recipe fields the publication workflow owns after adapter translation."""

    id: str
    summary: str


@dataclass(frozen=True)
class SkylightSitting:
    """Sitting fields the publication workflow owns after adapter translation."""

    id: str
    meal_recipe_id: str


class SkylightAdapter(Protocol):
    """External seam used by Meal-plan Publication."""

    def resolve_lunch_category_id(self) -> str | None: ...

    def list_recipes(self) -> list[SkylightRecipe]: ...

    def list_lunch_sittings(self, menu_date: str, lunch_id: str) -> list[SkylightSitting]: ...

    def delete_sitting(self, sitting_id: str, menu_date: str) -> None: ...

    def create_recipe(self, summary: str, description: str, lunch_id: str) -> SkylightRecipe: ...

    def create_sitting(self, menu_date: str, lunch_id: str, recipe_id: str) -> SkylightSitting: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class _SelectionSnapshot:
    kid_id: int
    kid_name: str
    kid_prefix: str
    menu_date: str
    stored_selection: str
    selection: str
    sent_sitting_id: str | None


class MealPlanPublisher:
    """Publish one frozen Selection snapshot through one Skylight adapter session."""

    def __init__(self, db_path: Path, adapter_factory: Callable[[], SkylightAdapter]) -> None:
        self._db_path = db_path
        self._adapter_factory = adapter_factory

    def publish(self, dates: Sequence[date]) -> PublicationResult:
        requested_dates = list(dict.fromkeys(dates))
        claimed_dates, busy_dates = self._claim_dates(requested_dates)
        outcomes_by_date = {
            value.isoformat(): DatePublicationOutcome(
                menu_date=value.isoformat(),
                status="busy",
                kid_outcomes=[],
                phase="concurrency",
                message="Meal-plan Publication is already in progress for this date.",
            )
            for value in busy_dates
        }
        if not claimed_dates:
            return PublicationResult([outcomes_by_date[value.isoformat()] for value in requested_dates])

        try:
            snapshots = self._snapshot(claimed_dates)
            try:
                adapter = self._adapter_factory()
            except Exception as exc:  # noqa: BLE001
                outcomes_by_date.update(
                    {
                        menu_date: DatePublicationOutcome(
                            menu_date=menu_date,
                            status="blocked",
                            kid_outcomes=[],
                            phase="connection",
                            message=f"Could not connect to Skylight: {exc}",
                        )
                        for menu_date in snapshots
                    }
                )
                return PublicationResult([outcomes_by_date[value.isoformat()] for value in requested_dates])
            try:
                try:
                    lunch_id = adapter.resolve_lunch_category_id()
                    lunch_error = None
                except Exception as exc:  # noqa: BLE001
                    lunch_id = None
                    lunch_error = f"Could not discover Skylight meal categories: {exc}"
                if lunch_id is None:
                    outcomes_by_date.update(
                        {
                            menu_date: DatePublicationOutcome(
                                menu_date=menu_date,
                                status="blocked",
                                kid_outcomes=[],
                                phase="discovery",
                                message=(
                                    lunch_error or "Could not find a 'Lunch' meal category on this Skylight frame."
                                ),
                            )
                            for menu_date in snapshots
                        }
                    )
                else:
                    try:
                        all_recipes = adapter.list_recipes()
                    except Exception as exc:  # noqa: BLE001
                        outcomes_by_date.update(
                            {
                                menu_date: DatePublicationOutcome(
                                    menu_date=menu_date,
                                    status="blocked",
                                    kid_outcomes=[],
                                    phase="discovery",
                                    message=f"Could not discover Skylight recipes: {exc}",
                                )
                                for menu_date in snapshots
                            }
                        )
                    else:
                        recipes = {recipe.summary.strip(): recipe for recipe in all_recipes}
                        recipes_by_id = {recipe.id: recipe for recipe in all_recipes}
                        outcomes_by_date.update(
                            {
                                menu_date: self._publish_date(
                                    adapter,
                                    lunch_id,
                                    menu_date,
                                    rows,
                                    recipes,
                                    recipes_by_id,
                                )
                                for menu_date, rows in snapshots.items()
                            }
                        )
            finally:
                adapter.close()
            return PublicationResult([outcomes_by_date[value.isoformat()] for value in requested_dates])
        finally:
            self._release_dates(claimed_dates)

    def _claim_dates(self, dates: Sequence[date]) -> tuple[list[date], list[date]]:
        db_key = str(self._db_path.resolve())
        claimed: list[date] = []
        busy: list[date] = []
        with _publication_lock:
            for value in dates:
                key = (db_key, value.isoformat())
                if key in _active_publications:
                    busy.append(value)
                else:
                    _active_publications.add(key)
                    claimed.append(value)
        return claimed, busy

    def _release_dates(self, dates: Sequence[date]) -> None:
        db_key = str(self._db_path.resolve())
        with _publication_lock:
            for value in dates:
                _active_publications.discard((db_key, value.isoformat()))

    def _snapshot(self, dates: Sequence[date]) -> dict[str, list[_SelectionSnapshot]]:
        menu_dates = list(dict.fromkeys(value.isoformat() for value in dates))
        snapshots: dict[str, list[_SelectionSnapshot]] = {}
        overrides = db.fetch_all_overrides(self._db_path)
        with db.get_db(self._db_path) as conn:
            kids = conn.execute("SELECT id, name, prefix FROM kids ORDER BY id").fetchall()
            for menu_date in menu_dates:
                for kid in kids:
                    conn.execute(
                        """
                        INSERT INTO selections (kid_id, menu_date, selection, sent_at, sent_sitting_id)
                        VALUES (?, ?, ?, NULL, NULL)
                        ON CONFLICT(kid_id, menu_date) DO NOTHING
                        """,
                        (kid["id"], menu_date, db.MAKE_AT_HOME),
                    )
                rows = conn.execute(
                    """
                    SELECT s.kid_id, s.selection, s.sent_sitting_id,
                           k.name AS kid_name, k.prefix AS kid_prefix
                    FROM selections s
                    JOIN kids k ON k.id = s.kid_id
                    WHERE s.menu_date = ?
                    ORDER BY k.id
                    """,
                    (menu_date,),
                ).fetchall()
                snapshots[menu_date] = [
                    _SelectionSnapshot(
                        kid_id=row["kid_id"],
                        kid_name=row["kid_name"],
                        kid_prefix=(row["kid_prefix"] or db._derive_kid_prefix(row["kid_name"])).strip(),
                        menu_date=menu_date,
                        stored_selection=row["selection"],
                        selection=db.resolve_display_text(row["selection"], overrides),
                        sent_sitting_id=row["sent_sitting_id"],
                    )
                    for row in rows
                ]
            conn.commit()
        return snapshots

    def _publish_date(
        self,
        adapter: SkylightAdapter,
        lunch_id: str,
        menu_date: str,
        snapshots: list[_SelectionSnapshot],
        recipes: dict[str, SkylightRecipe],
        recipes_by_id: dict[str, SkylightRecipe],
    ) -> DatePublicationOutcome:
        owned_prefixes = tuple(f"{snapshot.kid_prefix} " for snapshot in snapshots)
        owned_ids = {snapshot.sent_sitting_id for snapshot in snapshots if snapshot.sent_sitting_id}
        owned_sittings = []
        try:
            lunch_sittings = adapter.list_lunch_sittings(menu_date, lunch_id)
        except Exception as exc:  # noqa: BLE001
            return DatePublicationOutcome(
                menu_date=menu_date,
                status="blocked",
                kid_outcomes=[],
                phase="discovery",
                message=f"Could not discover existing Skylight sittings: {exc}",
            )
        for sitting in lunch_sittings:
            recipe = recipes_by_id.get(sitting.meal_recipe_id)
            summary = recipe.summary.strip() if recipe is not None else ""
            if sitting.id in owned_ids or summary.startswith(owned_prefixes):
                owned_sittings.append(sitting)
        deleted_sitting_ids: list[str] = []
        for sitting in owned_sittings:
            sitting_id = sitting.id
            try:
                adapter.delete_sitting(sitting_id, menu_date)
                deleted_sitting_ids.append(sitting_id)
            except Exception as exc:  # noqa: BLE001
                try:
                    self._clear_removed_sitting_state(menu_date, deleted_sitting_ids)
                except Exception as persistence_exc:  # noqa: BLE001
                    return DatePublicationOutcome(
                        menu_date=menu_date,
                        status="partial",
                        kid_outcomes=[],
                        deleted=len(deleted_sitting_ids),
                        phase="persistence",
                        message=(
                            f"Could not remove an Owned Skylight Sitting: {exc}; "
                            f"could not persist successful removals: {persistence_exc}"
                        ),
                    )
                return DatePublicationOutcome(
                    menu_date=menu_date,
                    status="blocked",
                    kid_outcomes=[],
                    deleted=len(deleted_sitting_ids),
                    phase="removal",
                    message=f"Could not remove an Owned Skylight Sitting: {exc}",
                )

        kid_outcomes: list[KidPublicationOutcome] = []
        for snapshot in snapshots:
            if snapshot.selection == db.MAKE_AT_HOME:
                kid_outcomes.append(
                    KidPublicationOutcome(
                        kid_id=snapshot.kid_id,
                        kid_name=snapshot.kid_name,
                        selection=snapshot.selection,
                        status="make_at_home",
                    )
                )
                continue

            summary = f"{snapshot.kid_prefix} {snapshot.selection}"
            recipe = recipes.get(summary)
            if recipe is None:
                try:
                    recipe = adapter.create_recipe(
                        summary,
                        f"{snapshot.selection} (from school menu)",
                        lunch_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    kid_outcomes.append(
                        KidPublicationOutcome(
                            kid_id=snapshot.kid_id,
                            kid_name=snapshot.kid_name,
                            selection=snapshot.selection,
                            status="failed",
                            phase="recipe_creation",
                            message=str(exc),
                        )
                    )
                    continue
                recipes[summary] = recipe
                recipes_by_id[recipe.id] = recipe
            try:
                sitting = adapter.create_sitting(menu_date, lunch_id, recipe.id)
            except Exception as exc:  # noqa: BLE001
                kid_outcomes.append(
                    KidPublicationOutcome(
                        kid_id=snapshot.kid_id,
                        kid_name=snapshot.kid_name,
                        selection=snapshot.selection,
                        status="failed",
                        phase="sitting_creation",
                        message=str(exc),
                    )
                )
                continue
            kid_outcomes.append(
                KidPublicationOutcome(
                    kid_id=snapshot.kid_id,
                    kid_name=snapshot.kid_name,
                    selection=snapshot.selection,
                    status="published",
                    sitting_id=sitting.id,
                )
            )

        try:
            persisted_kid_ids = self._persist(menu_date, kid_outcomes, snapshots)
        except Exception as exc:  # noqa: BLE001
            return DatePublicationOutcome(
                menu_date=menu_date,
                status="partial",
                kid_outcomes=kid_outcomes,
                deleted=len(deleted_sitting_ids),
                phase="persistence",
                message=f"persistence({menu_date}): {exc}",
            )
        changed_kid_ids = {outcome.kid_id for outcome in kid_outcomes} - persisted_kid_ids
        if changed_kid_ids:
            kid_outcomes = [
                replace(
                    outcome,
                    status="failed",
                    phase="concurrency",
                    message="Selection changed while publication was in progress; it remains unpublished.",
                )
                if outcome.kid_id in changed_kid_ids
                else outcome
                for outcome in kid_outcomes
            ]
        status: DatePublicationStatus = (
            "published" if all(outcome.status != "failed" for outcome in kid_outcomes) else "partial"
        )
        return DatePublicationOutcome(
            menu_date=menu_date,
            status=status,
            kid_outcomes=kid_outcomes,
            deleted=len(deleted_sitting_ids),
        )

    def _clear_removed_sitting_state(self, menu_date: str, sitting_ids: list[str]) -> None:
        """Clear sent state for removals that Skylight already confirmed."""
        if not sitting_ids:
            return
        with db.get_db(self._db_path) as conn:
            conn.executemany(
                """
                UPDATE selections
                SET sent_at = NULL, sent_sitting_id = NULL
                WHERE menu_date = ? AND sent_sitting_id = ?
                """,
                ((menu_date, sitting_id) for sitting_id in sitting_ids),
            )
            conn.commit()

    def _persist(
        self,
        menu_date: str,
        outcomes: list[KidPublicationOutcome],
        snapshots: list[_SelectionSnapshot],
    ) -> set[int]:
        snapshots_by_kid = {snapshot.kid_id: snapshot for snapshot in snapshots}
        persisted_kid_ids: set[int] = set()
        now = datetime.now().isoformat(timespec="seconds")
        with db.get_db(self._db_path) as conn:
            for outcome in outcomes:
                snapshot = snapshots_by_kid[outcome.kid_id]
                sent_at = now if outcome.status == "published" else None
                updated = conn.execute(
                    """
                    UPDATE selections
                    SET sent_at = ?, sent_sitting_id = ?
                    WHERE kid_id = ? AND menu_date = ?
                      AND selection = ? AND sent_sitting_id IS ?
                    """,
                    (
                        sent_at,
                        outcome.sitting_id,
                        outcome.kid_id,
                        menu_date,
                        snapshot.stored_selection,
                        snapshot.sent_sitting_id,
                    ),
                )
                if updated.rowcount:
                    persisted_kid_ids.add(outcome.kid_id)
                if outcome.status == "published" and updated.rowcount:
                    db.log_history(
                        conn,
                        outcome.kid_name,
                        menu_date,
                        outcome.selection,
                        "Sent to Skylight",
                    )
            conn.commit()
        return persisted_kid_ids
