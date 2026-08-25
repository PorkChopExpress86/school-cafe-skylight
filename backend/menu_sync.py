#!/usr/bin/env python3
"""SchoolCafé menu fetch sync: store the next 4 weeks of lunch items in
the local SQLite database so the admin page can show spelling,
capitalization, and sync history.

Used by the in-app Sunday schedule, the immediate admin trigger, and a
one-off command-line invocation.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import db
import menu_service
from school_menu import SchoolCafeConfig, get_weekly_items

SYNC_WEEKS = 4


@dataclass(frozen=True)
class SyncResult:
    """Outcome of one fetch attempt, row in `menu_sync_log`."""

    attempted_at: datetime
    succeeded: bool
    weeks_fetched: int
    items_stored: int
    error: str | None
    weeks_covered: list[str]


def _fetch_one_week(config: SchoolCafeConfig, week_start: date) -> list[tuple[date, str, str]]:
    """Fetch one week without opening the local SQLite database."""
    days = get_weekly_items(config, week_start)
    items: list[tuple[date, str, str]] = []
    for day in days:
        for entree in day.entrees:
            items.append((day.date, entree.description, entree.category))
    return items


def _week_starts(reference: date) -> list[date]:
    first_week_start = reference - timedelta(days=reference.weekday())
    return [first_week_start + timedelta(days=week_offset * 7) for week_offset in range(SYNC_WEEKS)]


def sync_menu(
    config: SchoolCafeConfig,
    reference: date | None = None,
    db_path: Path | None = None,
) -> SyncResult:
    """Fetch and store ``SYNC_WEEKS`` weeks of lunch items."""
    if reference is None:
        reference = date.today()
    if db_path is None:
        db_path = db.DEFAULT_DB_PATH

    attempted_at = datetime.now()
    try:
        week_starts = _week_starts(reference)
        fetched_weeks = [(week_start, _fetch_one_week(config, week_start)) for week_start in week_starts]
        total_stored = db.store_menu_items(fetched_weeks, db_path)
        weeks_covered = [week_start.isoformat() for week_start in week_starts]

        result = SyncResult(
            attempted_at=attempted_at,
            succeeded=True,
            weeks_fetched=SYNC_WEEKS,
            items_stored=total_stored,
            error=None,
            weeks_covered=weeks_covered,
        )
    except Exception as exc:  # noqa: BLE001
        result = SyncResult(
            attempted_at=attempted_at,
            succeeded=False,
            weeks_fetched=0,
            items_stored=0,
            error=f"{type(exc).__name__}: {exc}",
            weeks_covered=[],
        )

    db.log_sync_attempt(db_path, result)
    if not result.succeeded:
        raise RuntimeError(result.error)
    return result


def load_sync_config() -> SchoolCafeConfig | None:
    """Load the optional SchoolCafé configuration for a sync attempt."""
    return menu_service.school_config()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch the next 4 weeks of school lunch menus into the local DB."
    )
    parser.parse_args(argv)

    config = load_sync_config()
    if config is None:
        print("SCHOOL_ID not set in .env", file=sys.stderr)
        return 2

    try:
        result = sync_menu(config)
        print(
            f"Synced {result.items_stored} items across "
            f"{result.weeks_fetched} weeks. "
            f"Weeks: {', '.join(result.weeks_covered)}"
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Menu sync failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
