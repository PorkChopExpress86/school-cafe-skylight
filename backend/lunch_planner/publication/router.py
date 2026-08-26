"""Meal-plan Publication HTTP routes and request validation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from lunch_planner.publication.control import PublicationControl
from lunch_planner.school_menu.models import get_week_dates


class SendDayRequest(BaseModel):
    """One requested date for Meal-plan Publication."""

    menu_date: str


class SendWeekRequest(BaseModel):
    """Any reference date within the requested school week."""

    date: str


def create_router(
    database_path: Callable[[], Path],
    *,
    frame_id: Callable[[], str],
    login: Callable[[], Any],
) -> APIRouter:
    """Create the Meal-plan Publication router with external provider seams."""
    router = APIRouter(prefix="/api")

    @router.post("/send-day")
    def publish_day(request: SendDayRequest) -> dict:
        _parse_menu_date(request.menu_date)
        control = PublicationControl(database_path(), frame_id, login)
        return control.publish([date_cls.fromisoformat(request.menu_date)]).as_day_payload()

    @router.post("/send-week")
    def publish_week(request: SendWeekRequest) -> dict:
        reference = _parse_week_reference(request.date)
        control = PublicationControl(database_path(), frame_id, login)
        return control.publish(get_week_dates(reference)).as_week_payload()

    return router


def _parse_menu_date(value: str) -> date_cls:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid menu_date {value!r}; expected YYYY-MM-DD.")


def _parse_week_reference(value: str) -> date_cls:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return date_cls.today()
