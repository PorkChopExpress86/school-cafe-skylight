"""Behavior tests for the deterministic automated menu-sync policy."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import db
from menu_sync import SyncResult
from menu_sync_schedule import MenuSyncSchedule
from school_menu import SchoolCafeConfig

SUNDAY_AT_THREE = datetime(2026, 8, 30, 3, 5)


def _successful_result(now: datetime) -> SyncResult:
    return SyncResult(
        attempted_at=now,
        succeeded=True,
        weeks_fetched=4,
        items_stored=12,
        error=None,
        weeks_covered=["2026-08-31"],
    )


def test_schedule_returns_not_due_without_loading_configuration(tmp_path):
    schedule = MenuSyncSchedule(tmp_path / "schedule.db", load_config=lambda: (_ for _ in ()).throw(AssertionError()))

    outcome = schedule.run_if_due(datetime(2026, 8, 31, 3, 0))

    assert outcome.status == "not_due"


def test_schedule_skips_a_day_that_already_has_an_attempt(tmp_path):
    db_path = tmp_path / "schedule.db"
    db.init_db(db_path)
    db.log_sync_attempt(db_path, _successful_result(SUNDAY_AT_THREE))
    schedule = MenuSyncSchedule(db_path, load_config=lambda: (_ for _ in ()).throw(AssertionError()))

    outcome = schedule.run_if_due(SUNDAY_AT_THREE)

    assert outcome.status == "already_attempted"


def test_schedule_reports_missing_configuration(tmp_path):
    db_path = tmp_path / "schedule.db"
    db.init_db(db_path)
    schedule = MenuSyncSchedule(db_path, load_config=lambda: None)

    outcome = schedule.run_if_due(SUNDAY_AT_THREE)

    assert outcome.status == "not_configured"


def test_schedule_converts_aware_instants_to_central_time(tmp_path):
    db_path = tmp_path / "schedule.db"
    db.init_db(db_path)
    schedule = MenuSyncSchedule(db_path, load_config=lambda: None)

    outcome = schedule.run_if_due(datetime(2026, 8, 30, 8, 5, tzinfo=UTC))

    assert outcome.status == "not_configured"


def test_schedule_syncs_once_when_due(tmp_path):
    db_path = tmp_path / "schedule.db"
    db.init_db(db_path)
    config = SchoolCafeConfig(school_id="123")
    calls: list[tuple[SchoolCafeConfig, Path]] = []

    def perform_sync(received_config: SchoolCafeConfig, received_db_path: Path) -> SyncResult:
        calls.append((received_config, received_db_path))
        return _successful_result(SUNDAY_AT_THREE)

    schedule = MenuSyncSchedule(db_path, load_config=lambda: config, perform_sync=perform_sync)

    outcome = schedule.run_if_due(SUNDAY_AT_THREE)

    assert outcome.status == "synced"
    assert outcome.sync_result == _successful_result(SUNDAY_AT_THREE)
    assert calls == [(config, db_path)]


def test_schedule_reports_a_failed_sync(tmp_path):
    db_path = tmp_path / "schedule.db"
    db.init_db(db_path)

    def fail_sync(_config: SchoolCafeConfig, _db_path: Path) -> SyncResult:
        raise RuntimeError("offline")

    schedule = MenuSyncSchedule(
        db_path,
        load_config=lambda: SchoolCafeConfig(school_id="123"),
        perform_sync=fail_sync,
    )

    outcome = schedule.run_if_due(SUNDAY_AT_THREE)

    assert outcome.status == "failed"
    assert "offline" in outcome.message
