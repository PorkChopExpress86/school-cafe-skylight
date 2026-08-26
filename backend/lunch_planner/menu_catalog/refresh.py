"""Deep Menu Catalog Refresh workflow and periodic scheduling policy."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from lunch_planner.menu_catalog import persistence as db
from lunch_planner.school_menu.models import SchoolCafeConfig
from lunch_planner.school_menu.source import SchoolCafeMenuSource, SchoolMenuSource

REFRESH_WEEKS = 4
_SUNDAY = 6
_REFRESH_HOUR = 3
_LOCAL_TIME_ZONE = ZoneInfo("America/Chicago")
_POLL_INTERVAL_SECONDS = 600

MenuCatalogRefreshStatus = Literal[
    "not_due",
    "already_attempted",
    "not_configured",
    "refreshed",
    "failed",
]
FailureReporter = Callable[[str], None]


@dataclass(frozen=True)
class MenuCatalogRefreshResult:
    """One Menu Catalog Refresh or scheduling decision."""

    attempted_at: datetime
    status: MenuCatalogRefreshStatus
    message: str
    weeks_fetched: int = 0
    items_stored: int = 0
    error: str | None = None
    weeks_covered: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        """Whether a refresh attempt completed successfully."""
        return self.status == "refreshed"


class MenuCatalogRefresh:
    """Own configuration, acquisition, persistence, logging, scheduling, and outcomes."""

    def __init__(self, db_path: Path, source: SchoolMenuSource) -> None:
        self._db_path = db_path
        self._source = source

    def refresh(
        self,
        reference: date | None = None,
        *,
        attempted_at: datetime | None = None,
    ) -> MenuCatalogRefreshResult:
        """Attempt one four-week refresh and log its typed outcome exactly once."""
        reference = reference or date.today()
        attempted_at = attempted_at or datetime.now()
        try:
            config = self._source.config()
        except Exception as exc:  # noqa: BLE001
            return self._log_attempt(
                MenuCatalogRefreshResult(
                    attempted_at,
                    "failed",
                    f"Could not load SchoolCafe configuration: {type(exc).__name__}: {exc}",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
        if config is None:
            return MenuCatalogRefreshResult(
                attempted_at,
                "not_configured",
                "SCHOOL_ID not set in .env",
            )

        week_starts = _week_starts(reference)
        try:
            fetched_weeks = [
                (week_start, _catalog_items(self._source, config, week_start)) for week_start in week_starts
            ]
            total_stored = db.store_menu_items(fetched_weeks, self._db_path)
            result = MenuCatalogRefreshResult(
                attempted_at,
                "refreshed",
                f"Synced {total_stored} items across {REFRESH_WEEKS} weeks.",
                weeks_fetched=REFRESH_WEEKS,
                items_stored=total_stored,
                weeks_covered=tuple(week_start.isoformat() for week_start in week_starts),
            )
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            result = MenuCatalogRefreshResult(
                attempted_at,
                "failed",
                f"Menu Catalog Refresh failed: {error}",
                error=error,
            )
        return self._log_attempt(result)

    def run_if_due(self, now: datetime) -> MenuCatalogRefreshResult:
        """Apply the Sunday 03:00 America/Chicago scheduling policy."""
        local_now = now.astimezone(_LOCAL_TIME_ZONE) if now.tzinfo else now.replace(tzinfo=_LOCAL_TIME_ZONE)
        local_attempted_at = local_now.replace(tzinfo=None)
        if local_now.weekday() != _SUNDAY or local_now.hour != _REFRESH_HOUR:
            return MenuCatalogRefreshResult(
                local_attempted_at,
                "not_due",
                "The Sunday 03:00 Central Time window is not active.",
            )

        try:
            attempts = db.fetch_recent_sync_attempts(self._db_path, limit=1)
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            return MenuCatalogRefreshResult(
                local_attempted_at,
                "failed",
                f"Could not read refresh history: {error}",
                error=error,
            )

        today = local_now.date().isoformat()
        if attempts and attempts[0]["attempted_at"].startswith(today):
            return MenuCatalogRefreshResult(
                local_attempted_at,
                "already_attempted",
                "A Menu Catalog Refresh was already attempted today.",
            )
        return self.refresh(local_now.date(), attempted_at=local_attempted_at)

    async def run_schedule(self, report_failure: FailureReporter) -> None:
        """Poll the scheduling policy until the application lifecycle cancels it."""
        while True:
            try:
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
                outcome = self.run_if_due(datetime.now(UTC))
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001
                report_failure(f"Menu Catalog Refresh schedule failed: {type(exc).__name__}: {exc}")
                continue

            if outcome.status == "failed":
                report_failure(f"Scheduled Menu Catalog Refresh failed: {outcome.message}")

    def _log_attempt(self, result: MenuCatalogRefreshResult) -> MenuCatalogRefreshResult:
        try:
            db.log_sync_attempt(self._db_path, result)
        except Exception as exc:  # noqa: BLE001
            log_error = f"Could not record Menu Catalog Refresh: {type(exc).__name__}: {exc}"
            message = f"{result.message} {log_error}"
            error = f"{result.error}; {log_error}" if result.error else log_error
            return replace(result, status="failed", message=message, error=error)
        return result


def _week_starts(reference: date) -> list[date]:
    first_week_start = reference - timedelta(days=reference.weekday())
    return [first_week_start + timedelta(days=week_offset * 7) for week_offset in range(REFRESH_WEEKS)]


def _catalog_items(
    source: SchoolMenuSource,
    config: SchoolCafeConfig,
    week_start: date,
) -> list[tuple[date, str, str]]:
    days = source.fetch_week(config, week_start)
    return [(day.date, entree.description, entree.category) for day in days for entree in day.entrees]


def default_menu_catalog_refresh(db_path: Path) -> MenuCatalogRefresh:
    """Create the production Menu Catalog Refresh module."""
    return MenuCatalogRefresh(db_path, SchoolCafeMenuSource())
