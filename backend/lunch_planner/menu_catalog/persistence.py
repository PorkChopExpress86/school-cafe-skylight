"""Menu Catalog-owned SQLite operations."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from lunch_planner.menu_catalog.display import cased_menu_item
from lunch_planner.persistence.connection import DEFAULT_DB_PATH, get_db
from lunch_planner.persistence.schema import init_menu_tables


def fetch_all_overrides(db_path: Path | None = None) -> dict[str, str]:
    """Return {original_description: replacement_description} for all overrides."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    with get_db(target_path) as conn:
        rows = conn.execute(
            "SELECT original_description, replacement_description FROM menu_item_overrides"
        ).fetchall()
    return {r["original_description"]: r["replacement_description"] for r in rows}


def set_menu_override(
    original: str, replacement: str, db_path: Path | None = None
) -> None:
    """Insert or update display override for `original` and its Title Case variant."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    original = original.strip()
    replacement = replacement.strip()
    if not replacement:
        clear_menu_override(original, target_path)
        return
    cased = cased_menu_item(original)
    now = datetime.now().isoformat(timespec="seconds")
    with get_db(target_path) as conn:
        init_menu_tables(conn)
        for key in {original, cased}:
            conn.execute(
                """
                INSERT INTO menu_item_overrides
                    (original_description, replacement_description, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(original_description) DO UPDATE
                    SET replacement_description = excluded.replacement_description,
                        updated_at = excluded.updated_at
                """,
                (key, replacement, now, now),
            )
        conn.commit()


def clear_menu_override(original: str, db_path: Path | None = None) -> None:
    """Remove override for `original` and its Title Case variant."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    original = original.strip()
    cased = cased_menu_item(original)
    with get_db(target_path) as conn:
        init_menu_tables(conn)
        conn.execute(
            "DELETE FROM menu_item_overrides WHERE original_description IN (?, ?)",
            (original, cased),
        )
        conn.commit()


def fetch_recent_sync_attempts(db_path: Path | None = None, limit: int = 50) -> list[dict]:
    """Return most recent sync log entries, newest first."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    with get_db(target_path) as conn:
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


def fetch_unique_menu_items(db_path: Path | None = None) -> list[dict]:
    """Return unique menu items grouped by description."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    with get_db(target_path) as conn:
        rows = conn.execute(
            """
            SELECT description, MAX(category) AS category, MAX(fetched_at) AS fetched_at
            FROM menu_items
            GROUP BY description
            ORDER BY description ASC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_menu_items(db_path: Path | None = None, week_start: str | None = None) -> list[dict]:
    """Return cached menu items, optionally filtered by `week_start`."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    with get_db(target_path) as conn:
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


def fetch_menu_dates(start_date: str, end_date: str, db_path: Path | None = None) -> set[str]:
    """Return locally known Menu Catalog dates in one inclusive range."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    with get_db(target_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT menu_date
            FROM menu_items
            WHERE menu_date >= ? AND menu_date <= ?
            """,
            (start_date, end_date),
        ).fetchall()
    return {row["menu_date"] for row in rows}


def fetch_last_successful_sync(db_path: Path | None = None) -> str | None:
    """Return the most recent successful Menu Catalog Refresh time, if any."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    with get_db(target_path) as conn:
        row = conn.execute(
            """
            SELECT attempted_at
            FROM menu_sync_log
            WHERE succeeded = 1
            ORDER BY attempted_at DESC
            LIMIT 1
            """
        ).fetchone()
    return row["attempted_at"] if row is not None else None


def fetch_distinct_weeks(db_path: Path | None = None) -> list[str]:
    """Return week-start dates for which we have cached menu items."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    with get_db(target_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT week_start FROM menu_items ORDER BY week_start DESC"
        ).fetchall()
    return [r[0] for r in rows]


def store_menu_items(
    weeks: list[tuple[date, list[tuple[date, str, str]]]], db_path: Path | None = None
) -> int:
    """Atomically store fetched menu entries, returning the number of rows written."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    fetched_at = datetime.now().isoformat(timespec="seconds")
    stored = 0
    with get_db(target_path) as conn:
        init_menu_tables(conn)
        for week_start, items in weeks:
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
                    (menu_date.isoformat(), description, category, week_start.isoformat(), fetched_at),
                )
                stored += 1
        conn.commit()
    return stored


def log_sync_attempt(db_path: Path | None, result: Any) -> None:
    """Insert one row into menu_sync_log."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    with get_db(target_path) as conn:
        init_menu_tables(conn)
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
