"""Menu Catalog administration HTTP routes and request schemas."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from lunch_planner.menu_catalog import persistence
from lunch_planner.menu_catalog.casing import pin_display_overrides_for_all_items
from lunch_planner.menu_catalog.readback import MenuCatalogReadback
from lunch_planner.menu_catalog.refresh import MenuCatalogRefresh, default_menu_catalog_refresh


class OverrideRequest(BaseModel):
    """One Display Override administration request."""

    original: str
    replacement: str


def create_router(
    database_path: Callable[[], Path],
    *,
    refresh_factory: Callable[[Path], MenuCatalogRefresh] = default_menu_catalog_refresh,
) -> APIRouter:
    """Create the Menu Catalog administration router."""
    router = APIRouter(prefix="/api/admin")

    @router.get("")
    def read_catalog() -> dict:
        return MenuCatalogReadback.read(database_path()).as_payload()

    @router.post("/override")
    def set_override(request: OverrideRequest) -> dict:
        persistence.set_menu_override(request.original, request.replacement, database_path())
        return {"ok": True, "overrides": persistence.fetch_all_overrides(database_path())}

    @router.post("/sync")
    def refresh_catalog() -> dict:
        outcome = refresh_factory(database_path()).refresh()
        return {"ok": outcome.succeeded, "message": outcome.message}

    @router.post("/llm-case-all")
    def pin_all_display_overrides() -> dict:
        return pin_display_overrides_for_all_items(database_path())

    return router
