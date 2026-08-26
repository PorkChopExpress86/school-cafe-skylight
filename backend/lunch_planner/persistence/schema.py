"""Central SQLite schema lifecycle and additive migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from lunch_planner.persistence.connection import DEFAULT_DB_PATH, get_db

MAKE_AT_HOME = "__MAKE_AT_HOME__"
HISTORY_RETENTION = 500

DEFAULT_KIDS = [
    {"name": "Parker", "color": "#3B82F6", "prefix": "P-"},
    {"name": "Kylee", "color": "#EC4899", "prefix": "K-"},
]

def init_menu_tables(conn: sqlite3.Connection) -> None:
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
        init_menu_tables(conn)
        conn.commit()


