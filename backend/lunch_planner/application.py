"""Compose the FastAPI application from feature routers and shared runtime concerns."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lunch_planner.application_lifespan import create_lifespan
from lunch_planner.menu_catalog.refresh import MenuCatalogRefresh, default_menu_catalog_refresh
from lunch_planner.menu_catalog.router import create_router as create_menu_catalog_router
from lunch_planner.planner.router import create_router as create_planner_router
from lunch_planner.publication.router import create_router as create_publication_router


def create_app(
    database_path: Callable[[], Path],
    *,
    publication_frame_id: Callable[[], str],
    publication_login: Callable[[], Any],
    report_failure: Callable[[str], None],
    static_dir: Path,
    refresh_factory: Callable[[Path], MenuCatalogRefresh] = default_menu_catalog_refresh,
) -> FastAPI:
    """Create the application with feature routers, lifecycle, middleware, and SPA serving."""
    app = FastAPI(
        title="School Lunch Planner",
        lifespan=create_lifespan(
            database_path,
            refresh_factory=refresh_factory,
            report_failure=report_failure,
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(create_planner_router(database_path))
    app.include_router(
        create_publication_router(
            database_path,
            frame_id=publication_frame_id,
            login=publication_login,
        )
    )
    app.include_router(create_menu_catalog_router(database_path, refresh_factory=refresh_factory))

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    if static_dir.is_dir():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str):
            candidate = static_dir / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_dir / "index.html")

    return app
