"""Production entry point for the School Lunch Planner application."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

from lunch_planner.application import create_app
from lunch_planner.menu_catalog.refresh import default_menu_catalog_refresh
from lunch_planner.persistence.connection import DEFAULT_DB_PATH
from lunch_planner.persistence.connection import get_db as open_database
from lunch_planner.persistence.schema import init_db as initialize_database
from lunch_planner.publication.skylight_adapter import skylight_frame_id, skylight_login

BACKEND_DIR = Path(__file__).resolve().parent.parent
DB_PATH = DEFAULT_DB_PATH


@contextmanager
def get_db():
    """Open the configured SQLite database for legacy operational callers."""
    with open_database(DB_PATH) as connection:
        yield connection


def init_db() -> None:
    """Initialize the configured SQLite database."""
    initialize_database(DB_PATH)


def _skylight_login():
    """Open a production Skylight client through the narrow adapter seam."""
    return skylight_login()


app = create_app(
    lambda: DB_PATH,
    publication_frame_id=lambda: skylight_frame_id(),
    publication_login=lambda: _skylight_login(),
    report_failure=logging.getLogger(__name__).warning,
    refresh_factory=lambda database_path: default_menu_catalog_refresh(database_path),
    static_dir=BACKEND_DIR / "static",
)
