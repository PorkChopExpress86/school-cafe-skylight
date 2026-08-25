"""Read the Menu Catalog used to administer the planner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import db
import menu_service


@dataclass(frozen=True)
class MenuCatalogReadback:
    """Source-unique Menu items and the recent catalog refresh history."""

    items: list[dict]
    attempts: list[dict]
    last_success: dict | None

    @classmethod
    def read(cls, db_path: Path, attempt_limit: int = 50) -> MenuCatalogReadback:
        """Read ordered, Display Text-resolved catalog administration state."""
        items = menu_service.apply_overrides_to_items(
            db.fetch_unique_menu_items(db_path), db.fetch_all_overrides(db_path)
        )
        items.sort(key=lambda item: (item["display_description"], item["description"]))
        attempts = db.fetch_recent_sync_attempts(db_path, limit=attempt_limit)
        return cls(
            items=[
                {
                    "description": item["description"],
                    "category": item["category"],
                    "display_description": item["display_description"],
                }
                for item in items
            ],
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
