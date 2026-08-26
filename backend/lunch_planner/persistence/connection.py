"""SQLite connection configuration."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def configured_database_path(environment: Mapping[str, str] | None = None) -> Path:
    """Return the configured SQLite path, falling back to the backend directory."""
    source = os.environ if environment is None else environment
    configured_path = source.get("DATABASE_PATH", "").strip()
    return Path(configured_path).expanduser() if configured_path else BACKEND_DIR / "app.db"


DEFAULT_DB_PATH = configured_database_path()

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

