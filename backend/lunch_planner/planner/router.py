"""Planner HTTP routes and request validation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from lunch_planner.planner.readback import WeekPlannerReadback
from lunch_planner.planner.selection_change import SelectionChange, UnknownKidError

MAX_SELECTION_LEN = 200


class SelectRequest(BaseModel):
    """One Planner Selection Change request."""

    kid_id: int
    menu_date: str
    selection: str


def create_router(database_path: Callable[[], Path]) -> APIRouter:
    """Create the Planner router with its application-provided SQLite path."""
    router = APIRouter(prefix="/api")

    @router.get("/week")
    def read_week(date: Annotated[str | None, Query()] = None) -> dict:
        ref = _parse_week_reference(date)
        return WeekPlannerReadback.read(database_path(), ref).as_payload()

    @router.post("/select")
    def apply_selection(request: SelectRequest) -> dict:
        _parse_menu_date(request.menu_date)
        selection = _sanitize_selection(request.selection)
        try:
            result = SelectionChange(database_path()).apply(request.kid_id, request.menu_date, selection)
        except UnknownKidError:
            raise HTTPException(status_code=404, detail=f"Unknown kid_id {request.kid_id}.")
        return {
            "kid_id": result.kid_id,
            "menu_date": result.menu_date,
            "selection": result.selection,
            "sent_at": result.sent_at,
            "day_totals": result.readback.day_totals,
            "day_sent": result.readback.day_sent,
            "history": result.readback.history,
        }

    return router


def _parse_week_reference(value: str | None) -> date_cls:
    if value:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            pass
    return date_cls.today()


def _parse_menu_date(value: str) -> date_cls:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid menu_date {value!r}; expected YYYY-MM-DD.")


def _sanitize_selection(selection: str) -> str:
    selection = selection.strip()
    if not selection:
        raise HTTPException(status_code=400, detail="selection must not be empty.")
    if len(selection) > MAX_SELECTION_LEN:
        raise HTTPException(status_code=400, detail=f"selection too long (max {MAX_SELECTION_LEN} characters).")
    if any(ord(character) < 0x20 for character in selection):
        raise HTTPException(status_code=400, detail="selection contains control characters.")
    return selection
