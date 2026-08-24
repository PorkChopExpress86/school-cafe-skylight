"""Route-facing control for Meal-plan Publication and refreshed planner readback."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import db
from db import fetch_recent_history, load_selections
from meal_plan_publication import MealPlanPublisher, PublicationResult
from skylight_adapter import PyskylightAdapter


@dataclass(frozen=True)
class PublicationControlResult:
    """Publication outcomes plus the planner state callers display afterward."""

    publication: PublicationResult | None
    day_totals: dict[str, int]
    day_sent: dict[str, int]
    history: list[dict]
    error: str | None = None


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
        day_totals, day_sent, history = self._readback(date_values)
        frame_id = self._frame_id()
        if not frame_id:
            return PublicationControlResult(
                publication=None,
                day_totals=day_totals,
                day_sent=day_sent,
                history=history,
                error="SKYLIGHT_FRAME_ID is not set in .env.",
            )

        publisher = MealPlanPublisher(
            self._db_path,
            lambda: PyskylightAdapter(self._login(), frame_id),
        )
        publication = publisher.publish(requested_dates)
        day_totals, day_sent, history = self._readback(date_values)
        return PublicationControlResult(publication, day_totals, day_sent, history)

    def _readback(self, date_values: list[str]) -> tuple[dict[str, int], dict[str, int], list[dict]]:
        with db.get_db(self._db_path) as conn:
            selections = load_selections(conn, date_values)
            history = fetch_recent_history(conn)
        day_totals, day_sent = compute_day_counts(selections, date_values)
        return day_totals, day_sent, history


def compute_day_counts(
    selections: dict[str, dict[int, dict]], dates: list[str]
) -> tuple[dict[str, int], dict[str, int]]:
    totals: dict[str, int] = {}
    sent: dict[str, int] = {}
    for value in dates:
        day = selections.get(value, {})
        totals[value] = len(day)
        sent[value] = sum(1 for selection in day.values() if selection["sent_sitting_id"])
    return totals, sent
