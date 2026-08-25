"""Route-facing control for Meal-plan Publication and refreshed planner readback."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from meal_plan_publication import DatePublicationOutcome, MealPlanPublisher, PublicationResult
from planner_readback import PlannerReadback
from skylight_adapter import PyskylightAdapter


@dataclass(frozen=True)
class PlannerKidResult:
    """One Kid outcome in the planner's stable response vocabulary."""

    kid_name: str
    selection: str
    status: str


@dataclass(frozen=True)
class PlannerDateResult:
    """A normalized Meal-plan Publication outcome for one planner date."""

    menu_date: str
    ok: bool
    message: str
    sent: int
    deleted: int
    skipped: int
    errors: list[str]
    results: list[PlannerKidResult]


@dataclass(frozen=True)
class PublicationControlResult:
    """Normalized planner outcomes plus refreshed planner state for route adapters."""

    date_results: list[PlannerDateResult]
    day_totals: dict[str, int]
    day_sent: dict[str, int]
    history: list[dict]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and all(result.ok for result in self.date_results)

    def as_day_payload(self) -> dict:
        """Return the established single-day route shape with refreshed planner state."""
        if self.error:
            payload = {"ok": False, "message": self.error}
        else:
            if len(self.date_results) != 1:
                raise ValueError("A day response requires exactly one date result.")
            result = self.date_results[0]
            payload = {
                "ok": result.ok,
                "message": result.message,
                "sent": result.sent,
                "deleted": result.deleted,
                "skipped": result.skipped,
                "errors": result.errors,
                "results": [
                    {
                        "kid_name": kid.kid_name,
                        "selection": kid.selection,
                        "status": kid.status,
                    }
                    for kid in result.results
                ],
            }
        payload["day_totals"] = self.day_totals
        payload["day_sent"] = self.day_sent
        payload["history"] = self.history
        return payload

    def as_week_payload(self) -> dict:
        """Return the established multi-date route shape."""
        if self.error:
            return {"ok": False, "message": self.error}

        sent = sum(result.sent for result in self.date_results)
        deleted = sum(result.deleted for result in self.date_results)
        skipped = sum(result.skipped for result in self.date_results)
        errors = [error for result in self.date_results for error in result.errors]
        message = f"Sent {sent} meals across {len(self.date_results)} days to Skylight."
        if deleted:
            message += f" Replaced {deleted} existing."
        if skipped:
            message += f" {skipped} make-at-home."
        if errors:
            message += " Errors: " + "; ".join(errors)
        return {
            "ok": self.ok,
            "message": message,
            "sent": sent,
            "deleted": deleted,
            "skipped": skipped,
            "errors": errors,
            "results": [
                {
                    "kid_name": kid.kid_name,
                    "menu_date": result.menu_date,
                    "selection": kid.selection,
                    "status": kid.status,
                }
                for result in self.date_results
                for kid in result.results
            ],
            "day_totals": self.day_totals,
            "day_sent": self.day_sent,
            "history": self.history,
        }


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
            _normalize_publication(publication),
            readback.day_totals,
            readback.day_sent,
            readback.history,
        )


def _normalize_publication(publication: PublicationResult) -> list[PlannerDateResult]:
    return [_normalize_date_outcome(outcome) for outcome in publication.date_outcomes]


def _normalize_date_outcome(outcome: DatePublicationOutcome) -> PlannerDateResult:
    results = [
        PlannerKidResult(
            kid_name=kid.kid_name,
            selection=kid.selection,
            status=_planner_kid_status(kid.status),
        )
        for kid in outcome.kid_outcomes
    ]
    sent = sum(kid.status == "published" for kid in outcome.kid_outcomes)
    skipped = sum(kid.status == "make_at_home" for kid in outcome.kid_outcomes)
    errors = _publication_errors(outcome)
    message = f"Sent {sent} to Skylight for {outcome.menu_date}."
    if outcome.deleted:
        message += f" Replaced {outcome.deleted} existing."
    if skipped:
        message += f" {skipped} make-at-home (no sitting)."
    if errors:
        message += " Errors: " + "; ".join(errors)
    return PlannerDateResult(
        menu_date=outcome.menu_date,
        ok=outcome.status == "published",
        message=message,
        sent=sent,
        deleted=outcome.deleted,
        skipped=skipped,
        errors=errors,
        results=results,
    )


def _publication_errors(outcome: DatePublicationOutcome) -> list[str]:
    errors = [outcome.message] if outcome.message else []
    errors.extend(
        f"{kid.phase}({kid.kid_name}): {kid.message}"
        for kid in outcome.kid_outcomes
        if kid.status == "failed" and kid.message
    )
    return errors


def _planner_kid_status(status: str) -> str:
    return {
        "published": "sent",
        "make_at_home": "skipped",
        "failed": "error",
    }[status]
