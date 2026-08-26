"""Planner-owned SQLite operations."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from lunch_planner.menu_catalog.display import MenuItemDisplay
from lunch_planner.menu_catalog.persistence import fetch_all_overrides
from lunch_planner.persistence.connection import get_db

__all__ = [
    "MAKE_AT_HOME",
    "fetch_all_overrides",
    "fetch_recent_history",
    "get_db",
    "load_selections",
    "log_history",
    "resolve_display_text",
]

MAKE_AT_HOME = "__MAKE_AT_HOME__"
HISTORY_RETENTION = 500

def log_history(
    conn: sqlite3.Connection,
    kid_name: str,
    menu_date: str,
    selection: str,
    action: str,
    retention_limit: int = HISTORY_RETENTION,
) -> None:
    """Record one activity row in selection_history and prune beyond history limit."""
    conn.execute(
        """
        INSERT INTO selection_history (kid_name, menu_date, selection, action, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (kid_name, menu_date, selection, action, datetime.now().isoformat(timespec="seconds")),
    )
    conn.execute(
        """
        DELETE FROM selection_history
        WHERE id <= (
            SELECT MAX(id) - ? FROM selection_history
        )
        """,
        (retention_limit,),
    )


def fetch_recent_history(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    """Fetch the `limit` most recent activity history entries."""
    rows = conn.execute(
        """
        SELECT id, kid_name, menu_date, selection, action, created_at
        FROM selection_history
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def load_selections(
    conn: sqlite3.Connection, dates: list[str]
) -> dict[str, dict[int, dict]]:
    """Return {date: {kid_id: {selection, sent_at, sent_sitting_id}}} for given dates."""
    if not dates:
        return {}
    placeholders = ",".join("?" * len(dates))
    rows = conn.execute(
        f"SELECT kid_id, menu_date, selection, sent_at, sent_sitting_id "
        f"FROM selections WHERE menu_date IN ({placeholders})",
        dates,
    ).fetchall()
    out: dict[str, dict[int, dict]] = {}
    for r in rows:
        out.setdefault(r["menu_date"], {})[r["kid_id"]] = {
            "selection": r["selection"],
            "sent_at": r["sent_at"],
            "sent_sitting_id": r["sent_sitting_id"],
        }
    return out


def resolve_display_text(
    text: str, overrides: dict[str, str] | None = None, db_path: Path | None = None
) -> str:
    """Resolve a stored Selection to its display text.

    A thin Selection-flavoured entry point onto the Menu Item Display module:
    it knows the Make at Home sentinel is not a menu item, and where the
    override table lives. The rule itself lives in menu_item_display.
    """
    if overrides is None:
        overrides = fetch_all_overrides(db_path)
    return MenuItemDisplay(overrides, passthrough=(MAKE_AT_HOME,)).display(text)


