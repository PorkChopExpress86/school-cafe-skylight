"""Behavior tests for the deep Menu Catalog Refresh interface."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import database_support as db

from lunch_planner.menu_catalog import refresh as menu_catalog_refresh
from lunch_planner.menu_catalog.refresh import MenuCatalogRefresh, MenuCatalogRefreshResult
from lunch_planner.school_menu.school_cafe_adapter import DayMenu, MenuItem, SchoolCafeConfig
from tools import menu_refresh as menu_sync

REFERENCE = date(2026, 8, 12)
SUNDAY_AT_THREE = datetime(2026, 8, 30, 3, 5)
CONFIG = SchoolCafeConfig("school-1")


class _Source:
    def __init__(self, config=CONFIG) -> None:
        self.current_config = config
        self.fetches: list[date] = []
        self.error: Exception | None = None

    def config(self):
        return self.current_config

    def fetch_week(self, _config, reference):
        self.fetches.append(reference)
        if self.error is not None:
            raise self.error
        return [DayMenu(reference, [MenuItem("CHEESE PIZZA", "LUNCH ENTREE")])]


def test_refresh_collects_all_weeks_before_one_store_and_one_log(monkeypatch, tmp_path) -> None:
    events: list[str] = []
    source = _Source()

    def store(weeks, db_path):
        events.append("store")
        assert db_path == tmp_path / "catalog.db"
        assert len(weeks) == menu_catalog_refresh.REFRESH_WEEKS
        return sum(len(items) for _, items in weeks)

    def log(_db_path, result):
        events.append(f"log:{result.status}")

    monkeypatch.setattr(menu_catalog_refresh.db, "store_menu_items", store)
    monkeypatch.setattr(menu_catalog_refresh.db, "log_sync_attempt", log)

    result = MenuCatalogRefresh(tmp_path / "catalog.db", source).refresh(REFERENCE)

    assert result.status == "refreshed"
    assert result.succeeded is True
    assert source.fetches == [
        date(2026, 8, 10),
        date(2026, 8, 17),
        date(2026, 8, 24),
        date(2026, 8, 31),
    ]
    assert events == ["store", "log:refreshed"]


def test_failed_refresh_returns_and_logs_one_typed_outcome(monkeypatch, tmp_path) -> None:
    source = _Source()
    source.error = RuntimeError("offline")
    logged: list[MenuCatalogRefreshResult] = []
    monkeypatch.setattr(menu_catalog_refresh.db, "log_sync_attempt", lambda _path, result: logged.append(result))

    result = MenuCatalogRefresh(tmp_path / "catalog.db", source).refresh(REFERENCE)

    assert result.status == "failed"
    assert result.error == "RuntimeError: offline"
    assert logged == [result]


def test_unconfigured_refresh_is_not_an_attempt(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        menu_catalog_refresh.db,
        "log_sync_attempt",
        lambda _path, _result: (_ for _ in ()).throw(AssertionError("must not log")),
    )

    result = MenuCatalogRefresh(tmp_path / "catalog.db", _Source(config=None)).refresh(REFERENCE)

    assert result.status == "not_configured"
    assert result.succeeded is False


def test_schedule_returns_not_due_without_loading_the_source(tmp_path) -> None:
    source = _Source()
    refresh = MenuCatalogRefresh(tmp_path / "catalog.db", source)

    result = refresh.run_if_due(datetime(2026, 8, 31, 3, 0))

    assert result.status == "not_due"
    assert source.fetches == []


def test_schedule_skips_a_day_that_already_has_an_attempt(tmp_path) -> None:
    db_path = tmp_path / "catalog.db"
    db.init_db(db_path)
    db.log_sync_attempt(
        db_path,
        MenuCatalogRefreshResult(SUNDAY_AT_THREE, "refreshed", "done", weeks_fetched=4),
    )

    result = MenuCatalogRefresh(db_path, _Source()).run_if_due(SUNDAY_AT_THREE)

    assert result.status == "already_attempted"


def test_schedule_converts_aware_instants_to_central_time(tmp_path) -> None:
    db_path = tmp_path / "catalog.db"
    db.init_db(db_path)

    result = MenuCatalogRefresh(db_path, _Source(config=None)).run_if_due(datetime(2026, 8, 30, 8, 5, tzinfo=UTC))

    assert result.status == "not_configured"


def test_schedule_runs_the_same_refresh_workflow_when_due(tmp_path) -> None:
    db_path = tmp_path / "catalog.db"
    db.init_db(db_path)
    source = _Source()

    result = MenuCatalogRefresh(db_path, source).run_if_due(SUNDAY_AT_THREE)

    assert result.status == "refreshed"
    assert len(source.fetches) == menu_catalog_refresh.REFRESH_WEEKS
    assert len(db.fetch_recent_sync_attempts(db_path)) == 1


def test_schedule_reports_failed_outcomes_and_stops_on_cancellation(monkeypatch, tmp_path) -> None:
    refresh = MenuCatalogRefresh(tmp_path / "catalog.db", _Source())
    failures: list[str] = []
    sleeps = 0

    async def sleep(_delay: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(menu_catalog_refresh.asyncio, "sleep", sleep)
    monkeypatch.setattr(
        refresh,
        "run_if_due",
        lambda _now: MenuCatalogRefreshResult(datetime.now(), "failed", "offline"),
    )

    asyncio.run(refresh.run_schedule(failures.append))

    assert failures == ["Scheduled Menu Catalog Refresh failed: offline"]


def test_command_line_adapter_projects_not_configured_outcome(monkeypatch, capsys) -> None:
    outcome = MenuCatalogRefreshResult(datetime(2026, 8, 25, 18), "not_configured", "SCHOOL_ID not set")

    class Refresh:
        def refresh(self):
            return outcome

    monkeypatch.setattr(menu_sync, "default_menu_catalog_refresh", lambda _db_path: Refresh())

    exit_code = menu_sync.main([])

    assert exit_code == 2
    assert capsys.readouterr().err == "SCHOOL_ID not set\n"
