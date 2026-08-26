from __future__ import annotations

from pathlib import Path

import db


def test_database_path_uses_environment_override() -> None:
    assert db.configured_database_path({"DATABASE_PATH": "/data/app.db"}) == Path("/data/app.db")


def test_database_path_defaults_to_backend_directory() -> None:
    assert db.configured_database_path({}) == db.APP_DIR / "app.db"
