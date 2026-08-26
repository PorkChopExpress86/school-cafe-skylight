"""Planner-owned SQLite operations."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from lunch_planner.persistence.connection import get_db
from lunch_planner.planner.models import HISTORY_RETENTION, MAKE_AT_HOME

__all__ = [
    "MAKE_AT_HOME",
    "fetch_recent_history",
    "load_kids",
    "load_planner_state",
    "load_selections",
    "log_history",
    "persist_selection_change",
]

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


def load_kids(db_path: Path) -> list[dict]:
    """Return the family's Kids in stable planner order."""
    with get_db(db_path) as conn:
        rows = conn.execute("SELECT id, name, color, prefix FROM kids ORDER BY id").fetchall()
    return [dict(row) for row in rows]


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


def load_planner_state(
    db_path: Path, dates: list[str]
) -> tuple[dict[str, dict[int, dict]], list[dict]]:
    """Return stored Selections and recent history for one Planner Readback."""
    with get_db(db_path) as conn:
        return load_selections(conn, dates), fetch_recent_history(conn)


def persist_selection_change(db_path: Path, kid_id: int, menu_date: str, selection: str) -> bool:
    """Persist one Selection Change and its history, returning whether the Kid exists."""
    with get_db(db_path) as conn:
        kid = conn.execute("SELECT name FROM kids WHERE id = ?", (kid_id,)).fetchone()
        if kid is None:
            return False
        conn.execute(
            """
            INSERT INTO selections (kid_id, menu_date, selection, sent_at, sent_sitting_id)
            VALUES (?, ?, ?, NULL, NULL)
            ON CONFLICT(kid_id, menu_date) DO UPDATE
                SET selection = excluded.selection,
                    sent_at = NULL,
                    sent_sitting_id = NULL
            """,
            (kid_id, menu_date, selection),
        )
        log_history(conn, kid["name"], menu_date, selection, "Selected")
        conn.commit()
    return True


