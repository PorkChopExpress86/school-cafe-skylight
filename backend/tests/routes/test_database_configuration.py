from __future__ import annotations

from pathlib import Path

from lunch_planner.persistence import database as db


def test_database_path_uses_environment_override() -> None:
    assert db.configured_database_path({"DATABASE_PATH": "/data/app.db"}) == Path("/data/app.db")


def test_database_path_defaults_to_backend_directory() -> None:
    backend_directory = Path(__file__).resolve().parents[2]
    assert db.configured_database_path({}) == backend_directory / "app.db"
