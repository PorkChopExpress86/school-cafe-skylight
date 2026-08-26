"""Application lifecycle composition for persistence and scheduled refreshes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI

from lunch_planner.menu_catalog.refresh import MenuCatalogRefresh, default_menu_catalog_refresh
from lunch_planner.persistence.schema import init_db


def create_lifespan(
    database_path: Callable[[], Path],
    *,
    refresh_factory: Callable[[Path], MenuCatalogRefresh] = default_menu_catalog_refresh,
    report_failure: Callable[[str], None],
):
    """Build the application lifespan that initializes SQLite and polls refreshes."""

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db(database_path())
        refresh = refresh_factory(database_path())
        task = asyncio.create_task(refresh.run_schedule(report_failure))
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    return lifespan
