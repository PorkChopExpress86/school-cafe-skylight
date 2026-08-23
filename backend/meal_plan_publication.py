"""Deep module for publishing local Selections to a Skylight meal plan."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

import db

_publication_lock = Lock()
_active_publications: set[tuple[str, str]] = set()


class SkylightAdapter(Protocol):
    """External seam used by Meal-plan Publication."""

    def resolve_lunch_category_id(self) -> str | None: ...

    def list_recipes(self) -> list[Any]: ...

    def list_lunch_sittings(self, menu_date: str, lunch_id: str) -> list[Any]: ...

    def delete_sitting(self, sitting_id: str, menu_date: str) -> None: ...

    def create_recipe(self, summary: str, description: str, lunch_id: str) -> Any: ...

    def create_sitting(self, menu_date: str, lunch_id: str, recipe_id: str) -> Any: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class KidPublicationOutcome:
    kid_id: int
    kid_name: str
    selection: str
    status: str
    sitting_id: str | None = None
    phase: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class DatePublicationOutcome:
    menu_date: str
    status: str
    kid_outcomes: list[KidPublicationOutcome]
    deleted: int = 0
    phase: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class PublicationResult:
    date_outcomes: list[DatePublicationOutcome]

    @property
    def ok(self) -> bool:
        return all(outcome.status == "published" for outcome in self.date_outcomes)


@dataclass(frozen=True)
class _SelectionSnapshot:
    kid_id: int
    kid_name: str
    kid_prefix: str
    menu_date: str
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
                        recipes = {(recipe.summary or "").strip(): recipe for recipe in all_recipes}
                        recipes_by_id = {str(recipe.id): recipe for recipe in all_recipes}
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
        recipes: dict[str, Any],
        recipes_by_id: dict[str, Any],
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
            recipe = recipes_by_id.get(str(sitting.meal_recipe_id))
            summary = (recipe.summary or "").strip() if recipe is not None else ""
            if str(sitting.id) in owned_ids or summary.startswith(owned_prefixes):
                owned_sittings.append(sitting)
        deleted = 0
        for sitting in owned_sittings:
            try:
                adapter.delete_sitting(str(sitting.id), menu_date)
                deleted += 1
            except Exception as exc:  # noqa: BLE001
                return DatePublicationOutcome(
                    menu_date=menu_date,
                    status="blocked",
                    kid_outcomes=[],
                    deleted=deleted,
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
                recipes_by_id[str(recipe.id)] = recipe
            try:
                sitting = adapter.create_sitting(menu_date, lunch_id, str(recipe.id))
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
                    sitting_id=str(sitting.id),
                )
            )

        try:
            self._persist(menu_date, kid_outcomes)
        except Exception as exc:  # noqa: BLE001
            return DatePublicationOutcome(
                menu_date=menu_date,
                status="partial",
                kid_outcomes=kid_outcomes,
                deleted=deleted,
                phase="persistence",
                message=f"persistence({menu_date}): {exc}",
            )
        status = "published" if all(outcome.status != "failed" for outcome in kid_outcomes) else "partial"
        return DatePublicationOutcome(
            menu_date=menu_date,
            status=status,
            kid_outcomes=kid_outcomes,
            deleted=deleted,
        )

    def _persist(self, menu_date: str, outcomes: list[KidPublicationOutcome]) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with db.get_db(self._db_path) as conn:
            for outcome in outcomes:
                sent_at = now if outcome.status == "published" else None
                conn.execute(
                    """
                    UPDATE selections
                    SET sent_at = ?, sent_sitting_id = ?
                    WHERE kid_id = ? AND menu_date = ?
                    """,
                    (sent_at, outcome.sitting_id, outcome.kid_id, menu_date),
                )
                if outcome.status == "published":
                    db.log_history(
                        conn,
                        outcome.kid_name,
                        menu_date,
                        outcome.selection,
                        "Sent to Skylight",
                    )
            conn.commit()
