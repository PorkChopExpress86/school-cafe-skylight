"""One deep Selection Change module with refreshed Planner Readback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lunch_planner.menu_catalog.display_read import MenuItemDisplayRead
from lunch_planner.planner import persistence as db
from lunch_planner.planner.models import MAKE_AT_HOME
from lunch_planner.planner.readback import PlannerReadback


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
        display = MenuItemDisplayRead.read(self._db_path, passthrough=(MAKE_AT_HOME,))
        display_selection = display.display(selection)
        if not db.persist_selection_change(self._db_path, kid_id, menu_date, display_selection):
            raise UnknownKidError(kid_id)

        readback = PlannerReadback.read(self._db_path, [menu_date])
        return SelectionChangeResult(kid_id, menu_date, display_selection, None, readback)
