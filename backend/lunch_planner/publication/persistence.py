"""Meal-plan Publication-owned SQLite operations."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from lunch_planner.menu_catalog.display_read import MenuItemDisplayRead
from lunch_planner.persistence.connection import get_db
from lunch_planner.planner.models import MAKE_AT_HOME, derive_kid_prefix
from lunch_planner.planner.persistence import log_history
from lunch_planner.publication.models import FrozenSelection, KidPublicationOutcome


def read_frozen_selections(db_path: Path, dates: Sequence[date]) -> dict[str, list[FrozenSelection]]:
    """Capture requested Selections and create missing Make at Home defaults."""
    menu_dates = list(dict.fromkeys(value.isoformat() for value in dates))
    snapshots: dict[str, list[FrozenSelection]] = {}
    display = MenuItemDisplayRead.read(db_path, passthrough=(MAKE_AT_HOME,))
    with get_db(db_path) as conn:
        kids = conn.execute("SELECT id, name, prefix FROM kids ORDER BY id").fetchall()
        for menu_date in menu_dates:
            for kid in kids:
                conn.execute(
                    """
                    INSERT INTO selections (kid_id, menu_date, selection, sent_at, sent_sitting_id)
                    VALUES (?, ?, ?, NULL, NULL)
                    ON CONFLICT(kid_id, menu_date) DO NOTHING
                    """,
                    (kid["id"], menu_date, MAKE_AT_HOME),
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
                FrozenSelection(
                    kid_id=row["kid_id"],
                    kid_name=row["kid_name"],
                    kid_prefix=(row["kid_prefix"] or derive_kid_prefix(row["kid_name"])).strip(),
                    menu_date=menu_date,
                    stored_selection=row["selection"],
                    selection=display.display(row["selection"]),
                    sent_sitting_id=row["sent_sitting_id"],
                )
                for row in rows
            ]
        conn.commit()
    return snapshots


def clear_removed_sitting_state(db_path: Path, menu_date: str, sitting_ids: Sequence[str]) -> None:
    """Clear publication state for Owned Skylight Sittings already removed."""
    if not sitting_ids:
        return
    with get_db(db_path) as conn:
        conn.executemany(
            """
            UPDATE selections
            SET sent_at = NULL, sent_sitting_id = NULL
            WHERE menu_date = ? AND sent_sitting_id = ?
            """,
            ((menu_date, sitting_id) for sitting_id in sitting_ids),
        )
        conn.commit()


def record_publication_state(
    db_path: Path,
    menu_date: str,
    outcomes: Sequence[KidPublicationOutcome],
    snapshots: Sequence[FrozenSelection],
) -> set[int]:
    """Persist outcomes only when their frozen Selections are still current."""
    snapshots_by_kid = {snapshot.kid_id: snapshot for snapshot in snapshots}
    persisted_kid_ids: set[int] = set()
    now = datetime.now().isoformat(timespec="seconds")
    with get_db(db_path) as conn:
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
                log_history(conn, outcome.kid_name, menu_date, outcome.selection, "Sent to Skylight")
        conn.commit()
    return persisted_kid_ids
