#!/usr/bin/env python3
"""SchoolCafé menu fetch sync: store the next 4 weeks of lunch items in
the local SQLite database so the admin page can show spelling,
capitalization, and sync history.

Used by:
  - The Sunday cron task (via `python menu_sync.py`)
  - The internal retry loop (every 2 hours for 48 hours on failure)
  - The admin page (read-only access to the cache)

The fetch itself delegates to `school_menu.get_weekly_items` — the same
function the live page uses — so what the admin page shows is exactly
what the live page will render.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from school_menu import (
    SchoolCafeConfig,
    get_weekly_items,
)

# Layout: weeks start Monday and span Mon-Fri. ``_sync_weeks`` weeks ahead
# of the reference date are fetched; the first week containing the reference
# is week 0, so today + 4 weeks of coverage includes the current week.
SYNC_WEEKS = 4

# Retry policy: every 2 hours for 48 hours.
RETRY_INTERVAL_SECONDS = 2 * 60 * 60
RETRY_WINDOW_SECONDS = 48 * 60 * 60


@dataclass(frozen=True)
class SyncResult:
    """Outcome of one fetch attempt, row in `menu_sync_log`."""

    attempted_at: datetime
    succeeded: bool
    weeks_fetched: int
    items_stored: int
    error: str | None
    weeks_covered: list[str]  # ISO date strings of week starts


def _init_menu_tables(conn: Any) -> None:
    """Create the menu cache + sync-log tables (idempotent).

    Two tables back the admin page:

    menu_items - the cached items the live page uses.
      (menu_date, description) is the natural key — only entrees are stored,
      one row per (date, description). We've already filtered to entrees
      by the time we get here, so the admin page just lists what's
      available to pick.

    menu_sync_log - one row per fetch attempt.
      Both successful and failed attempts are logged so the admin page can
      show "last 7 days of retries" and we can see if a Sunday fetch
      failed silently. The ``attempted_at`` column is the primary key
      for the retry loop (``>= since`` queries).
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS menu_items (
            menu_date    TEXT NOT NULL,
            description  TEXT NOT NULL,
            category     TEXT NOT NULL DEFAULT '',
            week_start   TEXT NOT NULL,
            fetched_at   TEXT NOT NULL,
            PRIMARY KEY (menu_date, description)
        );

        CREATE INDEX IF NOT EXISTS idx_menu_items_week_start
            ON menu_items(week_start);

        CREATE TABLE IF NOT EXISTS menu_sync_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            attempted_at    TEXT NOT NULL,
            succeeded       INTEGER NOT NULL,
            weeks_fetched   INTEGER NOT NULL DEFAULT 0,
            items_stored    INTEGER NOT NULL DEFAULT 0,
            weeks_covered   TEXT NOT NULL DEFAULT '[]',
            error           TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_menu_sync_log_attempted_at
            ON menu_sync_log(attempted_at);

        -- Per-item display overrides. A lookup table that maps the original
        -- case-formatted description to whatever the user wants to show
        -- instead. No date column: an override applies to every occurrence
        -- of that description, past and future, until the user clears it.
        CREATE TABLE IF NOT EXISTS menu_item_overrides (
            original_description     TEXT PRIMARY KEY,
            replacement_description TEXT NOT NULL,
            created_at              TEXT NOT NULL,
            updated_at              TEXT NOT NULL
        );
        """
    )


def fetch_all_overrides(db_path: Path) -> dict[str, str]:
    """Return {original_description: replacement_description} for all overrides.

    Used by the admin page to render items with the user's chosen display
    text. Called fresh on every page load so edits show up immediately.
    """
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT original_description, replacement_description "
            "FROM menu_item_overrides"
        ).fetchall()
    return {orig: repl for orig, repl in rows}


def set_menu_override(
    original: str, replacement: str, db_path: Path | None = None
) -> None:
    """Insert or update the override for ``original``.

    Empty ``replacement`` clears the override (see ``clear_menu_override``).
    Whitespace is stripped. The original must already appear in
    ``menu_items`` (we don't override items that don't exist).
    """
    import sqlite3
    if db_path is None:
        db_path = Path(__file__).resolve().parent / "app.db"
    original = original.strip()
    replacement = replacement.strip()
    if not replacement:
        clear_menu_override(original, db_path)
        return
    now = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as conn:
        _init_menu_tables(conn)
        conn.execute(
            """
            INSERT INTO menu_item_overrides
                (original_description, replacement_description, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(original_description) DO UPDATE
                SET replacement_description = excluded.replacement_description,
                    updated_at = excluded.updated_at
            """,
            (original, replacement, now, now),
        )
        conn.commit()


def clear_menu_override(original: str, db_path: Path | None = None) -> None:
    """Remove the override for ``original`` so it displays normally again."""
    import sqlite3
    if db_path is None:
        db_path = Path(__file__).resolve().parent / "app.db"
    with sqlite3.connect(db_path) as conn:
        _init_menu_tables(conn)
        conn.execute(
            "DELETE FROM menu_item_overrides WHERE original_description = ?",
            (original.strip(),),
        )
        conn.commit()


def apply_overrides_to_items(
    items: list[dict], overrides: dict[str, str]
) -> list[dict]:
    """Return a copy of ``items`` with overrides applied.

    Returns a shallow dict copy per row so the input list and dicts
    aren't mutated. Items without an override pass through with
    ``display_description == description``.
    """
    out: list[dict] = []
    for item in items:
        row = dict(item)
        row["display_description"] = overrides.get(
            row["description"], row["description"]
        )
        out.append(row)
    return out


def apply_overrides_to_week(
    week: list[Any], overrides: dict[str, str] | None = None, db_path: Path | None = None
) -> list[Any]:
    """Return a copy of a fetched week (list of DayMenu) with display
    overrides applied to every entree description.

    ``week`` is what ``school_menu.get_weekly_items`` returns: a list of
    DayMenu objects, each with ``date`` and ``items`` (list of MenuItem).
    The returned list has the same structure; only the entree
    descriptions are rewritten to the user's chosen display text.

    If ``overrides`` is None, the overrides are loaded from the DB.
    """
    if overrides is None:
        if db_path is None:
            db_path = Path(__file__).resolve().parent / "app.db"
        overrides = fetch_all_overrides(db_path)
    if not overrides:
        return week

    from school_menu import DayMenu, MenuItem

    out: list[Any] = []
    for day in week:
        new_items = [
            MenuItem(
                description=overrides.get(i.description, i.description) or i.description,
                category=i.category,
            )
            for i in day.items
        ]
        out.append(DayMenu(date=day.date, items=new_items))
    return out


def _store_menu_items(
    conn: Any, week_start: date, items: list[tuple[date, str, str]]
) -> int:
    """Upsert menu items for one week. Returns the number of rows written.

    items = list of (menu_date, description, category) tuples.
    """
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
    """Fetch and store one week's entrees. Returns (items_stored, week_starts).

    Raises on network failure so the caller can log the error.
    """
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
    """Fetch and store ``SYNC_WEEKS`` weeks of lunch items.

    Logs every attempt (success or failure) to ``menu_sync_log``. On
    failure, raises the underlying exception so the caller (cron or
    retry shell loop) can decide what to do next.
    """
    if reference is None:
        reference = date.today()
    if db_path is None:
        db_path = Path(__file__).resolve().parent / "app.db"

    attempted_at = datetime.now()
    weeks_covered: list[str] = []
    total_stored = 0
    try:
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            _init_menu_tables(conn)
            for week_offset in range(SYNC_WEEKS):
                week_start = reference + timedelta(days=week_offset * 7)
                # Align to Monday so every fetch is keyed by week-start.
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

    # Log the attempt regardless of outcome.
    _log_sync_attempt(db_path, result)
    if not result.succeeded:
        raise RuntimeError(result.error)
    return result


def _log_sync_attempt(db_path: Path, result: SyncResult) -> None:
    """Insert one row into menu_sync_log."""
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        _init_menu_tables(conn)
        conn.execute(
            """
            INSERT INTO menu_sync_log
                (attempted_at, succeeded, weeks_fetched, items_stored,
                 weeks_covered, error)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                result.attempted_at.isoformat(timespec="seconds"),
                int(result.succeeded),
                result.weeks_fetched,
                result.items_stored,
                json.dumps(result.weeks_covered),
                result.error,
            ),
        )
        conn.commit()


def fetch_recent_sync_attempts(db_path: Path, limit: int = 50) -> list[dict]:
    """Return the most recent sync attempts, newest first. For the admin page."""
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT attempted_at, succeeded, weeks_fetched, items_stored,
                   weeks_covered, error
            FROM menu_sync_log
            ORDER BY attempted_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_menu_items(db_path: Path, week_start: str | None = None) -> list[dict]:
    """Return cached menu items, optionally filtered by week_start.

    For the admin page. Returns plain dicts so Jinja2 can iterate them.
    """
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if week_start:
            rows = conn.execute(
                """
                SELECT menu_date, description, category, week_start, fetched_at
                FROM menu_items
                WHERE week_start = ?
                ORDER BY menu_date, description
                """,
                (week_start,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT menu_date, description, category, week_start, fetched_at
                FROM menu_items
                ORDER BY week_start, menu_date, description
                """
            ).fetchall()
    return [dict(r) for r in rows]


def fetch_distinct_weeks(db_path: Path) -> list[str]:
    """Return week-start dates (ISO strings) for which we have cached items."""
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT week_start FROM menu_items ORDER BY week_start DESC"
        ).fetchall()
    return [r[0] for r in rows]


def _load_env_config() -> SchoolCafeConfig | None:
    """Read SchoolCafé config from .env. Returns None if SCHOOL_ID is missing."""
    import os

    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_path)
    school_id = os.environ.get("SCHOOL_ID")
    if not school_id:
        return None
    return SchoolCafeConfig(
        school_id=school_id,
        serving_line=os.environ.get("SCHOOL_SERVING_LINE", "TD Lunch Elementary"),
        meal_type=os.environ.get("SCHOOL_MEAL_TYPE", "Lunch"),
        grade=os.environ.get("SCHOOL_GRADE", "02"),
    )


def _retry_loop() -> int:
    """Retry every RETRY_INTERVAL_SECONDS for up to RETRY_WINDOW_SECONDS.

    Called from the CLI when the initial sync fails. Each attempt is
    logged to menu_sync_log; the loop exits as soon as one succeeds.

    Returns 0 on eventual success, 1 on giving up.
    """
    deadline = time.monotonic() + RETRY_WINDOW_SECONDS
    while time.monotonic() < deadline:
        wait = RETRY_INTERVAL_SECONDS
        time.sleep(wait)
        try:
            config = _load_env_config()
            if config is None:
                print("SCHOOL_ID not set in .env", file=sys.stderr)
                continue
            sync_menu(config)
            print(f"Retry succeeded at {datetime.now().isoformat(timespec='seconds')}")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(
                f"Retry failed at {datetime.now().isoformat(timespec='seconds')}: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
    print(f"Gave up after {RETRY_WINDOW_SECONDS // 3600} hours", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch the next 4 weeks of school lunch menus into the local DB."
    )
    parser.add_argument(
        "--no-retry",
        action="store_true",
        help="Don't retry on failure; just exit non-zero. Used by the cron task.",
    )
    parser.add_argument(
        "--retry-only",
        action="store_true",
        help="Skip the initial sync and only run the retry loop. "
             "Used by the follow-up systemd timer.",
    )
    args = parser.parse_args(argv)

    if args.retry_only:
        return _retry_loop()

    config = _load_env_config()
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
        print(f"Initial sync failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        if args.no_retry:
            return 1
        return _retry_loop()


if __name__ == "__main__":
    sys.exit(main())
