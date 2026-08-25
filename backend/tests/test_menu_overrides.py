"""Tests for menu-item display overrides through their owning modules."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import db
import menu_service
from db import clear_menu_override, fetch_all_overrides, set_menu_override
from menu_service import apply_overrides_to_items, apply_overrides_to_week
from school_menu import DayMenu, MenuItem, SchoolCafeConfig


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A throwaway SQLite DB for override tests."""
    return tmp_path / "test.db"


class TestOverrideStorage:
    def test_set_and_fetch_override(self, db_path):
        set_menu_override("Cheese Pizza", "Cheese Pizza (Veggie)", db_path)
        overrides = fetch_all_overrides(db_path)
        assert overrides == {"Cheese Pizza": "Cheese Pizza (Veggie)"}

    def test_update_existing_override(self, db_path):
        set_menu_override("Hot Dog", "Hot Dog (Beef)", db_path)
        set_menu_override("Hot Dog", "Hot Dog (Turkey)", db_path)
        overrides = fetch_all_overrides(db_path)
        assert overrides == {"Hot Dog": "Hot Dog (Turkey)"}

    def test_clear_override(self, db_path):
        set_menu_override("Hot Dog", "Hot Dog (Beef)", db_path)
        clear_menu_override("Hot Dog", db_path)
        assert fetch_all_overrides(db_path) == {}

    def test_empty_replacement_clears(self, db_path):
        set_menu_override("Hot Dog", "Hot Dog (Beef)", db_path)
        set_menu_override("Hot Dog", "   ", db_path)
        assert fetch_all_overrides(db_path) == {}

    def test_overrides_persist_across_connections(self, db_path):
        set_menu_override("Cheese Pizza", "Cheese Pizza (Veggie)", db_path)
        # New connection (simulated by a fresh fetch) still sees it.
        overrides = fetch_all_overrides(db_path)
        assert overrides["Cheese Pizza"] == "Cheese Pizza (Veggie)"


class TestOverrideApplication:
    def test_apply_to_items_dicts(self):
        items = [
            {"description": "Cheese Pizza", "menu_date": "2026-08-12"},
            {"description": "Hot Dog", "menu_date": "2026-08-12"},
        ]
        overrides = {"Cheese Pizza": "Cheese Pizza (Veggie)"}
        out = apply_overrides_to_items(items, overrides)
        assert out[0]["display_description"] == "Cheese Pizza (Veggie)"
        assert out[1]["display_description"] == "Hot Dog"
        # Input not mutated.
        assert "display_description" not in items[0]

    def test_apply_to_week(self):
        week = [
            DayMenu(
                date=__import__("datetime").date(2026, 8, 12),
                items=[
                    MenuItem("Cheese Pizza", "LUNCH ENTREE"),
                    MenuItem("Hot Dog", "LUNCH ENTREE"),
                ],
            )
        ]
        overrides = {"Cheese Pizza": "Cheese Pizza (Veggie)"}
        out = apply_overrides_to_week(week, overrides)
        assert out[0].items[0].description == "Cheese Pizza (Veggie)"
        assert out[0].items[1].description == "Hot Dog"
        # Original week untouched.
        assert week[0].items[0].description == "Cheese Pizza"

    def test_no_overrides_returns_same_week(self):
        week = [
            DayMenu(
                date=__import__("datetime").date(2026, 8, 12),
                items=[MenuItem("Cheese Pizza", "LUNCH ENTREE")],
            )
        ]
        out = apply_overrides_to_week(week, {})
        assert out[0].items[0].description == "Cheese Pizza"


class TestCachedWeekDisplayText:
    def test_set_and_clear_override_update_a_cached_week_without_refetching(self, monkeypatch, db_path):
        db.init_db(db_path)
        config = SchoolCafeConfig("test", "Lunch", "Lunch", "02")
        source_week = [
            DayMenu(
                date=date(2026, 8, 24),
                items=[MenuItem("CHEESE PIZZA", "LUNCH ENTREE")],
            )
        ]
        fetches = 0

        def fetch_source_week(_config, _reference):
            nonlocal fetches
            fetches += 1
            return source_week

        monkeypatch.setattr(menu_service, "school_config", lambda: config)
        monkeypatch.setattr(menu_service, "get_weekly_items", fetch_source_week)
        monkeypatch.setattr(menu_service, "_week_cache", {})

        first, error = menu_service.fetch_week(date(2026, 8, 24), db_path)
        assert error is None
        assert first[0].items[0].description == "Cheese Pizza"

        set_menu_override("CHEESE PIZZA", "Pizza Friday", db_path)
        overridden, error = menu_service.fetch_week(date(2026, 8, 24), db_path)
        assert error is None
        assert overridden[0].items[0].description == "Pizza Friday"

        clear_menu_override("CHEESE PIZZA", db_path)
        cleared, error = menu_service.fetch_week(date(2026, 8, 24), db_path)
        assert error is None
        assert cleared[0].items[0].description == "Cheese Pizza"
        assert fetches == 1
