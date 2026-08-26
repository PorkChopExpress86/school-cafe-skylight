"""Typed Meal-plan Publication outcomes and planner response projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

KidPublicationStatus = Literal["published", "make_at_home", "failed"]
DatePublicationStatus = Literal["published", "partial", "blocked", "busy"]
PublicationPhase = Literal[
    "concurrency",
    "connection",
    "discovery",
    "removal",
    "recipe_creation",
    "sitting_creation",
    "persistence",
]
PlannerKidStatus = Literal["sent", "skipped", "error"]


@dataclass(frozen=True)
class SkylightRecipe:
    """Recipe fields Meal-plan Publication owns after adapter translation."""

    id: str
    summary: str


@dataclass(frozen=True)
class SkylightSitting:
    """Sitting fields Meal-plan Publication owns after adapter translation."""

    id: str
    meal_recipe_id: str


@dataclass(frozen=True)
class FrozenSelection:
    """One Selection captured before its Meal-plan Publication begins."""

    kid_id: int
    kid_name: str
    kid_prefix: str
    menu_date: str
    stored_selection: str
    selection: str
    sent_sitting_id: str | None


@dataclass(frozen=True)
class KidPublicationOutcome:
    """One Kid outcome in the Meal-plan Publication vocabulary."""

    kid_id: int
    kid_name: str
    selection: str
    status: KidPublicationStatus
    sitting_id: str | None = None
    phase: PublicationPhase | None = None
    message: str | None = None


@dataclass(frozen=True)
class DatePublicationOutcome:
    """One date outcome in the Meal-plan Publication vocabulary."""

    menu_date: str
    status: DatePublicationStatus
    kid_outcomes: list[KidPublicationOutcome]
    deleted: int = 0
    phase: PublicationPhase | None = None
    message: str | None = None


@dataclass(frozen=True)
class PublicationResult:
    """The outcomes for one Meal-plan Publication request."""

    date_outcomes: list[DatePublicationOutcome]

    @property
    def ok(self) -> bool:
        return all(outcome.status == "published" for outcome in self.date_outcomes)


@dataclass(frozen=True)
class PlannerKidResult:
    """One Kid outcome in the stable planner response vocabulary."""

    kid_name: str
    selection: str
    status: PlannerKidStatus


@dataclass(frozen=True)
class PlannerDateResult:
    """A planner-facing projection of one publication date."""

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
    """Projected outcomes plus refreshed planner state for route adapters."""

    date_results: list[PlannerDateResult]
    day_totals: dict[str, int]
    day_sent: dict[str, int]
    history: list[dict]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and all(result.ok for result in self.date_results)

    def as_day_payload(self) -> dict:
        """Return the established single-day route shape."""
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


def project_publication(publication: PublicationResult) -> list[PlannerDateResult]:
    """Project internal outcomes to the stable planner response vocabulary."""
    return [_project_date_outcome(outcome) for outcome in publication.date_outcomes]


def _project_date_outcome(outcome: DatePublicationOutcome) -> PlannerDateResult:
    results = [
        PlannerKidResult(
            kid_name=kid.kid_name,
            selection=kid.selection,
            status=_PLANNER_KID_STATUS[kid.status],
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


_PLANNER_KID_STATUS: dict[KidPublicationStatus, PlannerKidStatus] = {
    "published": "sent",
    "make_at_home": "skipped",
    "failed": "error",
}
