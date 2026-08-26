"""Read the Menu Catalog used to administer the planner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lunch_planner.menu_catalog.display import MenuItemDisplay
from lunch_planner.persistence import database as db


@dataclass(frozen=True)
class MenuCatalogReadback:
    """Source-unique Menu items and the recent catalog refresh history."""

    items: list[dict]
    attempts: list[dict]
    last_success: dict | None

    @classmethod
    def read(cls, db_path: Path, attempt_limit: int = 50) -> MenuCatalogReadback:
        """Read ordered, Display Text-resolved catalog administration state."""
        items = _assemble_catalog(db.fetch_unique_menu_items(db_path), db.fetch_all_overrides(db_path))
        attempts = db.fetch_recent_sync_attempts(db_path, limit=attempt_limit)
        return cls(
            items=items,
            attempts=attempts,
            last_success=next((attempt for attempt in attempts if attempt["succeeded"]), None),
        )

    def as_payload(self) -> dict:
        """Return the established Menu Catalog response shape."""
        return {
            "items": self.items,
            "attempts": self.attempts,
            "last_success": self.last_success,
        }


def _assemble_catalog(items: list[dict], overrides: dict[str, str]) -> list[dict]:
    display = MenuItemDisplay(overrides)
    displayed = [
        {
            "description": item["description"],
            "category": item["category"],
            "display_description": display.display(item["description"]),
        }
        for item in items
    ]
    return sorted(displayed, key=lambda item: (item["display_description"], item["description"]))
