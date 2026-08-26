"""Behavior tests for publication vocabulary and planner projection."""

from __future__ import annotations

from lunch_planner.publication.models import (
    DatePublicationOutcome,
    KidPublicationOutcome,
    PublicationControlResult,
    PublicationResult,
    project_publication,
)


def test_projection_owns_the_complete_planner_status_mapping() -> None:
    publication = PublicationResult(
        [
            DatePublicationOutcome(
                menu_date="2026-08-24",
                status="partial",
                deleted=1,
                kid_outcomes=[
                    KidPublicationOutcome(1, "Parker", "Pizza", "published", sitting_id="sitting-1"),
                    KidPublicationOutcome(2, "Kylee", "__MAKE_AT_HOME__", "make_at_home"),
                    KidPublicationOutcome(
                        3,
                        "Jamie",
                        "Hot Dog",
                        "failed",
                        phase="sitting_creation",
                        message="offline",
                    ),
                ],
            )
        ]
    )

    projected = project_publication(publication)[0]

    assert projected.ok is False
    assert (projected.sent, projected.skipped, projected.deleted) == (1, 1, 1)
    assert [result.status for result in projected.results] == ["sent", "skipped", "error"]
    assert projected.errors == ["sitting_creation(Jamie): offline"]


def test_projected_outcome_builds_the_established_day_payload() -> None:
    publication = PublicationResult(
        [
            DatePublicationOutcome(
                menu_date="2026-08-24",
                status="published",
                kid_outcomes=[KidPublicationOutcome(1, "Parker", "Pizza", "published", sitting_id="sitting-1")],
            )
        ]
    )
    controlled = PublicationControlResult(
        date_results=project_publication(publication),
        day_totals={"2026-08-24": 1},
        day_sent={"2026-08-24": 1},
        history=[],
    )

    payload = controlled.as_day_payload()

    assert payload["ok"] is True
    assert payload["results"] == [{"kid_name": "Parker", "selection": "Pizza", "status": "sent"}]
    assert payload["day_sent"] == {"2026-08-24": 1}
