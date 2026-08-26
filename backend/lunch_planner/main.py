#!/usr/bin/env python3
"""FastAPI JSON API for picking school meals per kid and sending to Skylight.

Run:
    uvicorn lunch_planner.main:app --reload --port 8000

The frontend is a React SPA (in ../frontend) that consumes the /api/*
endpoints below. This module returns JSON only - no templates, no HTML.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager, contextmanager, suppress
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from lunch_planner.menu_catalog.casing import pin_display_overrides_for_all_items
from lunch_planner.menu_catalog.readback import MenuCatalogReadback
from lunch_planner.menu_catalog.refresh import default_menu_catalog_refresh
from lunch_planner.persistence import database as db
from lunch_planner.planner.readback import WeekPlannerReadback
from lunch_planner.planner.selection_change import SelectionChange, UnknownKidError
from lunch_planner.publication.control import PublicationControl
from lunch_planner.publication.skylight_adapter import (
    skylight_frame_id,
    skylight_login,
)
from lunch_planner.school_menu.school_cafe_adapter import get_week_dates

BACKEND_DIR = Path(__file__).resolve().parent.parent
DB_PATH = db.DEFAULT_DB_PATH
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database & Lifespan
# ---------------------------------------------------------------------------


@contextmanager
def get_db():
    with db.get_db(DB_PATH) as conn:
        yield conn


def init_db() -> None:
    db.init_db(DB_PATH)


@asynccontextmanager
async def lifespan(_: FastAPI):
    import asyncio

    init_db()
    refresh = default_menu_catalog_refresh(DB_PATH)
    task = asyncio.create_task(refresh.run_schedule(logger.warning))
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def _skylight_login():
    return skylight_login()


# ---------------------------------------------------------------------------
# Helpers & Validation
# ---------------------------------------------------------------------------


def _parse_menu_date(menu_date: str) -> date_cls:
    try:
        return datetime.strptime(menu_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid menu_date {menu_date!r}; expected YYYY-MM-DD.")


MAX_SELECTION_LEN = 200


def _sanitize_selection(selection: str) -> str:
    selection = selection.strip()
    if not selection:
        raise HTTPException(status_code=400, detail="selection must not be empty.")
    if len(selection) > MAX_SELECTION_LEN:
        raise HTTPException(status_code=400, detail=f"selection too long (max {MAX_SELECTION_LEN} characters).")
    if any(ord(c) < 0x20 for c in selection):
        raise HTTPException(status_code=400, detail="selection contains control characters.")
    return selection


def send_day_to_skylight(menu_date: str) -> dict:
    """Publish one date through the shared Meal-plan Publication seam."""
    control = PublicationControl(DB_PATH, skylight_frame_id, _skylight_login)
    return control.publish([date_cls.fromisoformat(menu_date)]).as_day_payload()


def _week_payload(ref: date_cls) -> dict:
    return WeekPlannerReadback.read(DB_PATH, ref).as_payload()


# ---------------------------------------------------------------------------
# App & Middleware
# ---------------------------------------------------------------------------

app = FastAPI(title="School Lunch Planner", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request Models & Routes
# ---------------------------------------------------------------------------


class SelectRequest(BaseModel):
    kid_id: int
    menu_date: str
    selection: str


class SendDayRequest(BaseModel):
    menu_date: str


class OverrideRequest(BaseModel):
    original: str
    replacement: str


@app.get("/api/week")
def api_week(date: Annotated[str | None, Query()] = None) -> dict:
    if date:
        try:
            ref = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            ref = date_cls.today()
    else:
        ref = date_cls.today()
    return _week_payload(ref)


@app.post("/api/select")
def api_select(req: SelectRequest) -> dict:
    _parse_menu_date(req.menu_date)
    selection = _sanitize_selection(req.selection)
    try:
        result = SelectionChange(DB_PATH).apply(req.kid_id, req.menu_date, selection)
    except UnknownKidError:
        raise HTTPException(status_code=404, detail=f"Unknown kid_id {req.kid_id}.")

    return {
        "kid_id": result.kid_id,
        "menu_date": result.menu_date,
        "selection": result.selection,
        "sent_at": result.sent_at,
        "day_totals": result.readback.day_totals,
        "day_sent": result.readback.day_sent,
        "history": result.readback.history,
    }


@app.post("/api/send-day")
def api_send_day(req: SendDayRequest) -> dict:
    _parse_menu_date(req.menu_date)
    return send_day_to_skylight(req.menu_date)


class SendWeekRequest(BaseModel):
    date: str


def send_week_to_skylight(ref: date_cls) -> dict:
    """Publish one school week through the shared Meal-plan Publication seam."""
    publication_dates = get_week_dates(ref)
    control = PublicationControl(DB_PATH, skylight_frame_id, _skylight_login)
    return control.publish(publication_dates).as_week_payload()


@app.post("/api/send-week")
def api_send_week(req: SendWeekRequest) -> dict:
    try:
        ref = datetime.strptime(req.date, "%Y-%m-%d").date()
    except ValueError:
        ref = date_cls.today()
    return send_week_to_skylight(ref)


@app.get("/api/admin")
def api_admin() -> dict:
    return MenuCatalogReadback.read(DB_PATH).as_payload()


@app.post("/api/admin/override")
def api_admin_override(req: OverrideRequest) -> dict:
    db.set_menu_override(req.original, req.replacement, DB_PATH)
    return {"ok": True, "overrides": db.fetch_all_overrides(DB_PATH)}


@app.post("/api/admin/sync")
def api_admin_sync() -> dict:
    outcome = default_menu_catalog_refresh(DB_PATH).refresh()
    return {"ok": outcome.succeeded, "message": outcome.message}


@app.post("/api/admin/llm-case-all")
def api_admin_llm_case_all() -> dict:
    """Run all unique menu items through agy (gemini-3.6-flash-low) to generate permanent display overrides."""
    return pin_display_overrides_for_all_items(DB_PATH)


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok"}


# SPA static file serving fallback
_STATIC_DIR = BACKEND_DIR / "static"
if _STATIC_DIR.is_dir():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount(
        "/assets",
        StaticFiles(directory=str(_STATIC_DIR / "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        candidate = _STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_STATIC_DIR / "index.html")
