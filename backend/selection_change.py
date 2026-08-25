"""One deep Selection Change module with refreshed Planner Readback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import db
from planner_readback import PlannerReadback


class UnknownKidError(Exception):
    """Raised when a Selection Change names no current Kid."""


@dataclass(frozen=True)
class SelectionChangeResult:
    """A completed Selection Change and its refreshed planner state."""

    kid_id: int
    menu_date: str
    selection: str
    sent_at: str | None
    readback: PlannerReadback


class SelectionChange:
    """Replace one Selection, clear publication, record history, and read back state."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def apply(self, kid_id: int, menu_date: str, selection: str) -> SelectionChangeResult:
        """Apply one validated Selection Change using the current Display Text rule."""
        overrides = db.fetch_all_overrides(self._db_path)
        display_selection = db.resolve_display_text(selection, overrides)
        with db.get_db(self._db_path) as conn:
            kid = conn.execute("SELECT name FROM kids WHERE id = ?", (kid_id,)).fetchone()
            if kid is None:
                raise UnknownKidError(kid_id)
            conn.execute(
                """
                INSERT INTO selections (kid_id, menu_date, selection, sent_at, sent_sitting_id)
                VALUES (?, ?, ?, NULL, NULL)
                ON CONFLICT(kid_id, menu_date) DO UPDATE
                    SET selection = excluded.selection,
                        sent_at = NULL,
                        sent_sitting_id = NULL
                """,
                (kid_id, menu_date, display_selection),
            )
            db.log_history(conn, kid["name"], menu_date, display_selection, "Selected")
            conn.commit()

        readback = PlannerReadback.read(self._db_path, [menu_date])
        return SelectionChangeResult(kid_id, menu_date, display_selection, None, readback)
