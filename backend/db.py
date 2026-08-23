"""Centralized SQLite database seam for SchoolCafé + Skylight.

Encapsulates connections, schema migrations, and data access for:
- Kids & prefixes
- Meal selections & sent states
- Selection activity history
- Cached menu items
- Per-item display overrides
- Menu sync logs
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = APP_DIR / "app.db"

MAKE_AT_HOME = "__MAKE_AT_HOME__"
HISTORY_RETENTION = 500

DEFAULT_KIDS = [
    {"name": "Parker", "color": "#3B82F6", "prefix": "P-"},
    {"name": "Kylee", "color": "#EC4899", "prefix": "K-"},
]


@contextmanager
def get_db(db_path: Path | None = None):
    """Yield a configured SQLite connection with foreign keys, WAL mode, and busy_timeout enabled."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    conn = sqlite3.connect(target_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        yield conn
    finally:
        conn.close()


def _init_menu_tables(conn: sqlite3.Connection) -> None:
    """Create menu cache, override, and sync log tables (idempotent)."""
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

        CREATE TABLE IF NOT EXISTS menu_item_overrides (
            original_description     TEXT PRIMARY KEY,
            replacement_description TEXT NOT NULL,
            created_at              TEXT NOT NULL,
            updated_at              TEXT NOT NULL
        );
        """
    )


def _derive_kid_prefix(kid_name: str) -> str:
    """Best-effort prefix for a kid with none stored, e.g. "Parker" -> "P-".

    Returns "?-" rather than raising for a name with no usable character.
    """
    initial = next((c for c in kid_name.strip().upper() if c.isalnum()), "")
    return f"{initial}-" if initial else "?-"


def _unique_prefix(base: str, taken: set[str]) -> str:
    """Disambiguate `base` against already-assigned prefixes."""
    if base.lower() not in taken:
        return base
    stem = base.rstrip("-")
    for n in range(2, 100):
        candidate = f"{stem}{n}-"
        if candidate.lower() not in taken:
            return candidate
    return base


def _backfill_kid_prefixes(conn: sqlite3.Connection) -> None:
    """Give every kid a non-empty, unique prefix."""
    rows = conn.execute("SELECT id, name, prefix FROM kids ORDER BY id").fetchall()
    taken = {r["prefix"].strip().lower() for r in rows if (r["prefix"] or "").strip()}
    defaults = {k["name"]: k["prefix"] for k in DEFAULT_KIDS}
    for r in rows:
        if (r["prefix"] or "").strip():
            continue
        candidate = _unique_prefix(
            defaults.get(r["name"]) or _derive_kid_prefix(r["name"]), taken
        )
        taken.add(candidate.lower())
        conn.execute("UPDATE kids SET prefix = ? WHERE id = ?", (candidate, r["id"]))


def init_db(db_path: Path | None = None) -> None:
    """Initialize database schema, migrations, default kids, and menu tables."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    with get_db(target_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS kids (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL DEFAULT '#6366F1',
                prefix TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS selections (
                kid_id           INTEGER NOT NULL,
                menu_date        TEXT    NOT NULL,
                selection        TEXT    NOT NULL,
                sent_at          TEXT,
                sent_sitting_id  TEXT,
                PRIMARY KEY (kid_id, menu_date),
                FOREIGN KEY (kid_id) REFERENCES kids(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_selections_menu_date
                ON selections(menu_date);

            CREATE TABLE IF NOT EXISTS selection_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                kid_name   TEXT NOT NULL,
                menu_date  TEXT NOT NULL,
                selection  TEXT NOT NULL,
                action     TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(kids)")}
        if "prefix" not in existing_cols:
            conn.execute("ALTER TABLE kids ADD COLUMN prefix TEXT NOT NULL DEFAULT ''")

        for kid in DEFAULT_KIDS:
            conn.execute(
                "INSERT OR IGNORE INTO kids (name, color, prefix) VALUES (?, ?, ?)",
                (kid["name"], kid["color"], kid["prefix"]),
            )
        _backfill_kid_prefixes(conn)
        _init_menu_tables(conn)
        conn.commit()


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


from school_menu import format_menu_item


def resolve_display_text(
    text: str, overrides: dict[str, str] | None = None, db_path: Path | None = None
) -> str:
    """Resolve raw or ALL-CAPS menu text to its active display override or Title Case version."""
    if not text or text == MAKE_AT_HOME:
        return text
    if overrides is None:
        overrides = fetch_all_overrides(db_path)
    if text in overrides and overrides[text]:
        return overrides[text]
    cased = format_menu_item(text)
    if cased in overrides and overrides[cased]:
        return overrides[cased]
    return cased


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
    cased = format_menu_item(original)
    now = datetime.now().isoformat(timespec="seconds")
    with get_db(target_path) as conn:
        _init_menu_tables(conn)
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
    cased = format_menu_item(original)
    with get_db(target_path) as conn:
        _init_menu_tables(conn)
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


def fetch_distinct_weeks(db_path: Path | None = None) -> list[str]:
    """Return week-start dates for which we have cached menu items."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    with get_db(target_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT week_start FROM menu_items ORDER BY week_start DESC"
        ).fetchall()
    return [r[0] for r in rows]


def log_sync_attempt(db_path: Path | None, result: Any) -> None:
    """Insert one row into menu_sync_log."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    with get_db(target_path) as conn:
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
