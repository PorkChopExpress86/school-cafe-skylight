"""Behavior tests for the deep Week Menu interface."""

from __future__ import annotations

from datetime import date

from lunch_planner.persistence import database as db
from lunch_planner.school_menu.school_cafe_adapter import DayMenu, MenuItem, SchoolCafeConfig
from lunch_planner.school_menu.week_menu import WeekMenu

REFERENCE = date(2026, 8, 24)
CONFIG = SchoolCafeConfig("school-1")


class _Source:
    def __init__(self, config=CONFIG) -> None:
        self.current_config = config
        self.fetches = 0
        self.error: Exception | None = None

    def config(self):
        return self.current_config

    def fetch_week(self, _config, reference):
        self.fetches += 1
        if self.error is not None:
            raise self.error
        return [DayMenu(reference, [MenuItem("CHEESE PIZZA", "LUNCH ENTREE")])]


def test_week_menu_reports_an_unconfigured_source_without_fetching() -> None:
    source = _Source(config=None)

    result = WeekMenu(source).read(REFERENCE)

    assert result.days is None
    assert result.source_config is None
    assert result.error == "SCHOOL_ID not set in .env"
    assert source.fetches == 0


def test_week_menu_contains_source_errors() -> None:
    source = _Source()
    source.error = RuntimeError("offline")

    result = WeekMenu(source).read(REFERENCE)

    assert result.days is None
    assert result.error == "RuntimeError: offline"


def test_week_menu_expires_source_weeks_through_its_interface(tmp_path) -> None:
    db_path = tmp_path / "week-menu.db"
    db.init_db(db_path)
    now = 10.0
    source = _Source()
    week_menu = WeekMenu(source, clock=lambda: now)

    first = week_menu.read(REFERENCE, db_path)
    second = week_menu.read(REFERENCE, db_path)
    now = 911.0
    third = week_menu.read(REFERENCE, db_path)

    assert first.days == second.days == third.days
    assert source.fetches == 2


def test_display_overrides_update_a_cached_week_without_refetching(tmp_path) -> None:
    db_path = tmp_path / "week-menu.db"
    db.init_db(db_path)
    source = _Source()
    week_menu = WeekMenu(source)

    first = week_menu.read(REFERENCE, db_path)
    db.set_menu_override("CHEESE PIZZA", "Pizza Friday", db_path)
    overridden = week_menu.read(REFERENCE, db_path)
    db.clear_menu_override("CHEESE PIZZA", db_path)
    cleared = week_menu.read(REFERENCE, db_path)

    assert first.days is not None
    assert overridden.days is not None
    assert cleared.days is not None
    assert first.days[0].items[0].description == "Cheese Pizza"
    assert overridden.days[0].items[0].description == "Pizza Friday"
    assert cleared.days[0].items[0].description == "Cheese Pizza"
    assert source.fetches == 1
