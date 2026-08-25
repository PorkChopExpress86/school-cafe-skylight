"""Tests for one deep, offline Menu Sync attempt."""

from __future__ import annotations

from datetime import date

import db
import menu_sync
from school_menu import DayMenu, MenuItem, SchoolCafeConfig


def test_sync_collects_all_remote_weeks_before_the_single_persistence_phase(monkeypatch, tmp_path):
    events: list[str] = []

    def fetch(_config: SchoolCafeConfig, week_start: date) -> list[DayMenu]:
        events.append(f"fetch:{week_start.isoformat()}")
        return [DayMenu(week_start, [MenuItem("CHEESE PIZZA", "LUNCH ENTREE")])]

    def store(weeks, db_path):
        events.append("store")
        assert db_path == tmp_path / "sync.db"
        assert len(weeks) == menu_sync.SYNC_WEEKS
        return sum(len(items) for _, items in weeks)

    monkeypatch.setattr(menu_sync, "get_weekly_items", fetch)
    monkeypatch.setattr(menu_sync.db, "store_menu_items", store)
    monkeypatch.setattr(menu_sync.db, "log_sync_attempt", lambda _path, _result: None)

    result = menu_sync.sync_menu(
        SchoolCafeConfig("123"), reference=date(2026, 8, 12), db_path=tmp_path / "sync.db"
    )

    assert result.succeeded is True
    assert events == [
        "fetch:2026-08-10",
        "fetch:2026-08-17",
        "fetch:2026-08-24",
        "fetch:2026-08-31",
        "store",
    ]


def test_store_menu_items_persists_every_week_in_one_call(tmp_path):
    db_path = tmp_path / "sync.db"
    stored = db.store_menu_items(
        [
            (date(2026, 8, 10), [(date(2026, 8, 10), "CHEESE PIZZA", "LUNCH ENTREE")]),
            (date(2026, 8, 17), [(date(2026, 8, 17), "HOT DOG", "LUNCH ENTREE")]),
        ],
        db_path,
    )

    assert stored == 2
    assert [(item["week_start"], item["description"]) for item in db.fetch_menu_items(db_path)] == [
        ("2026-08-10", "CHEESE PIZZA"),
        ("2026-08-17", "HOT DOG"),
    ]
