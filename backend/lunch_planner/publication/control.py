"""Route-facing control for Meal-plan Publication and refreshed planner readback."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date
from pathlib import Path
from typing import Any

from lunch_planner.planner.readback import PlannerReadback
from lunch_planner.publication.models import PublicationControlResult, project_publication
from lunch_planner.publication.publisher import MealPlanPublisher
from lunch_planner.publication.skylight_adapter import PyskylightAdapter


class PublicationControl:
    """Coordinate one or more dates through the existing Meal-plan Publication seam."""

    def __init__(
        self,
        db_path: Path,
        frame_id: Callable[[], str],
        login: Callable[[], Any],
    ) -> None:
        self._db_path = db_path
        self._frame_id = frame_id
        self._login = login

    def publish(self, dates: Iterable[date]) -> PublicationControlResult:
        requested_dates = list(dates)
        date_values = [value.isoformat() for value in requested_dates]
        readback = PlannerReadback.read(self._db_path, date_values)
        try:
            frame_id = self._frame_id()
            if not frame_id:
                return PublicationControlResult(
                    date_results=[],
                    day_totals=readback.day_totals,
                    day_sent=readback.day_sent,
                    history=readback.history,
                    error="SKYLIGHT_FRAME_ID is not set in .env.",
                )
            publisher = MealPlanPublisher(
                self._db_path,
                lambda: PyskylightAdapter(self._login(), frame_id),
            )
            publication = publisher.publish(requested_dates)
            readback = PlannerReadback.read(self._db_path, date_values)
        except Exception as exc:  # noqa: BLE001
            return PublicationControlResult(
                date_results=[],
                day_totals=readback.day_totals,
                day_sent=readback.day_sent,
                history=readback.history,
                error=f"{type(exc).__name__}: {exc}",
            )
        return PublicationControlResult(
            project_publication(publication),
            readback.day_totals,
            readback.day_sent,
            readback.history,
        )
