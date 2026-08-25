"""Deterministic policy for the automated weekly SchoolCafé menu sync."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import db
from menu_sync import SyncResult, load_sync_config, sync_menu
from school_menu import SchoolCafeConfig

MenuSyncScheduleStatus = Literal["not_due", "already_attempted", "not_configured", "synced", "failed"]
_SUNDAY = 6
_SYNC_HOUR = 3
_LOCAL_TIME_ZONE = ZoneInfo("America/Chicago")


@dataclass(frozen=True)
class MenuSyncScheduleResult:
    """One decision by the Sunday menu-sync policy."""

    status: MenuSyncScheduleStatus
    message: str
    sync_result: SyncResult | None = None


class MenuSyncSchedule:
    """Run at most one configured Sunday sync attempt per local calendar day."""

    def __init__(
        self,
        db_path: Path,
        load_config: Callable[[], SchoolCafeConfig | None] = load_sync_config,
        perform_sync: Callable[[SchoolCafeConfig, Path], SyncResult] | None = None,
    ) -> None:
        self._db_path = db_path
        self._load_config = load_config
        self._perform_sync = perform_sync or self._sync_into_database

    @staticmethod
    def _sync_into_database(config: SchoolCafeConfig, db_path: Path) -> SyncResult:
        return sync_menu(config, db_path=db_path)

    def run_if_due(self, now: datetime) -> MenuSyncScheduleResult:
        """Run the one configured attempt, or return the reason it did not run.

        Aware values are converted to the household's America/Chicago time;
        naive values represent that local time for deterministic tests.
        """
        local_now = now.astimezone(_LOCAL_TIME_ZONE) if now.tzinfo else now.replace(tzinfo=_LOCAL_TIME_ZONE)
        if local_now.weekday() != _SUNDAY or local_now.hour != _SYNC_HOUR:
            return MenuSyncScheduleResult("not_due", "The Sunday 03:00 Central Time window is not active.")

        try:
            attempts = db.fetch_recent_sync_attempts(self._db_path, limit=1)
        except Exception as exc:  # noqa: BLE001
            return MenuSyncScheduleResult("failed", f"Could not read sync history: {type(exc).__name__}: {exc}")

        today = local_now.date().isoformat()
        if attempts and attempts[0]["attempted_at"].startswith(today):
            return MenuSyncScheduleResult("already_attempted", "A menu sync was already attempted today.")

        try:
            config = self._load_config()
        except Exception as exc:  # noqa: BLE001
            return MenuSyncScheduleResult(
                "failed",
                f"Could not load SchoolCafé configuration: {type(exc).__name__}: {exc}",
            )
        if config is None:
            return MenuSyncScheduleResult("not_configured", "SCHOOL_ID is not configured.")

        try:
            result = self._perform_sync(config, self._db_path)
        except Exception as exc:  # noqa: BLE001
            return MenuSyncScheduleResult("failed", f"Menu sync failed: {type(exc).__name__}: {exc}")
        if not result.succeeded:
            return MenuSyncScheduleResult(
                "failed",
                result.error or "Menu sync returned an unsuccessful result.",
                result,
            )
        return MenuSyncScheduleResult(
            "synced",
            f"Synced {result.items_stored} items across {result.weeks_fetched} weeks.",
            result,
        )
