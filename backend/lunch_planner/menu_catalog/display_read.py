"""Read the current Display Text rule from the Menu Catalog."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from lunch_planner.menu_catalog.display import MenuItemDisplay
from lunch_planner.menu_catalog.persistence import fetch_all_overrides


@dataclass(frozen=True)
class MenuItemDisplayRead:
    """The current persisted Display Overrides behind the pure display rule."""

    _display: MenuItemDisplay

    @classmethod
    def read(
        cls,
        db_path: Path | None = None,
        *,
        passthrough: Iterable[str] = (),
    ) -> MenuItemDisplayRead:
        """Read current overrides once and return a reusable Display Text resolver."""
        return cls(MenuItemDisplay(fetch_all_overrides(db_path), passthrough=passthrough))

    def display(self, text: str) -> str:
        """Resolve one stored description using the current Display Text rule."""
        return self._display.display(text)
