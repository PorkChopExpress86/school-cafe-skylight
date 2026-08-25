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
from typing import Any

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


def _store_menu_items(
    conn: Any, week_start: date, items: list[tuple[date, str, str]]
) -> int:
    """Upsert menu items for one week. Returns the number of rows written."""
    fetched_at = datetime.now().isoformat(timespec="seconds")
    week_start_iso = week_start.isoformat()
    stored = 0
    for menu_date, description, category in items:
        conn.execute(
            """
            INSERT INTO menu_items
                (menu_date, description, category, week_start, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(menu_date, description) DO UPDATE
                SET category = excluded.category,
                    week_start = excluded.week_start,
                    fetched_at = excluded.fetched_at
            """,
            (menu_date.isoformat(), description, category, week_start_iso, fetched_at),
        )
        stored += 1
    return stored


def _sync_one_week(
    conn: Any, config: SchoolCafeConfig, week_start: date
) -> tuple[int, list[str]]:
    """Fetch and store one week's entrees. Returns (items_stored, week_starts)."""
    days = get_weekly_items(config, week_start)
    items: list[tuple[date, str, str]] = []
    for day in days:
        for entree in day.entrees:
            items.append((day.date, entree.description, entree.category))
    stored = _store_menu_items(conn, week_start, items)
    return stored, [week_start.isoformat()]


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
    weeks_covered: list[str] = []
    total_stored = 0
    try:
        with db.get_db(db_path) as conn:
            db._init_menu_tables(conn)
            for week_offset in range(SYNC_WEEKS):
                week_start = reference + timedelta(days=week_offset * 7)
                week_start = week_start - timedelta(days=week_start.weekday())
                stored, _ = _sync_one_week(conn, config, week_start)
                total_stored += stored
                weeks_covered.append(week_start.isoformat())
            conn.commit()

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
