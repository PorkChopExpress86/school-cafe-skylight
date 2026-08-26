"""Assemble the current, display-resolved Planner Readback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

from lunch_planner.planner import persistence as db
from lunch_planner.school_menu.school_cafe_adapter import get_week_dates
from lunch_planner.school_menu.week_menu import read_week_menu

SelectionPublicationState = Literal["pending", "published", "make_at_home"]


@dataclass(frozen=True)
class PlannerReadback:
    """Current planner state for requested dates and recent activity."""

    selections: dict[str, dict[int, dict]]
    day_totals: dict[str, int]
    day_sent: dict[str, int]
    history: list[dict]

    @classmethod
    def read(cls, db_path: Path, dates: list[str]) -> PlannerReadback:
        """Read one display-resolved planner state after a completed write or publication."""
        requested_dates = list(dict.fromkeys(dates))
        overrides = db.fetch_all_overrides(db_path)
        with db.get_db(db_path) as conn:
            selections = db.load_selections(conn, requested_dates)
            history = db.fetch_recent_history(conn)

        _resolve_display_text(selections, history, overrides)
        _present_selection_publication_state(selections)
        day_totals, day_sent = _compute_day_counts(selections, requested_dates)
        return cls(selections, day_totals, day_sent, history)


def _published_skylight_config() -> dict | None:
    """Load the published Skylight configuration only for the week readback."""
    from lunch_planner.publication.skylight_adapter import published_skylight_config

    return published_skylight_config()


@dataclass(frozen=True)
class WeekPlannerReadback:
    """The complete current weekly planning view for the route caller."""

    week: list[dict[str, Any]]
    kids: list[dict]
    planner: PlannerReadback
    ref: str
    prev_week: str
    next_week: str
    today: str
    school_cfg: Any
    skylight_cfg: dict | None
    menu_error: str | None

    @classmethod
    def read(cls, db_path: Path, ref: date) -> WeekPlannerReadback:
        """Read the displayed Menu and all planner state for one school week."""
        menu = read_week_menu(ref, db_path)
        dates = [menu_date.isoformat() for menu_date in get_week_dates(ref)]
        planner = PlannerReadback.read(db_path, dates)
        with db.get_db(db_path) as conn:
            kids = [
                dict(row)
                for row in conn.execute("SELECT id, name, color, prefix FROM kids ORDER BY id").fetchall()
            ]
        return cls(
            week=[
                {
                    "date": day.date.isoformat(),
                    "weekday": day.date.strftime("%A"),
                    "entrees": [entree.description for entree in day.entrees],
                }
                for day in (menu.days or [])
            ],
            kids=kids,
            planner=planner,
            ref=ref.isoformat(),
            prev_week=(ref - timedelta(days=7)).isoformat(),
            next_week=(ref + timedelta(days=7)).isoformat(),
            today=date.today().isoformat(),
            school_cfg=menu.source_config,
            skylight_cfg=_published_skylight_config(),
            menu_error=menu.error,
        )

    def as_payload(self) -> dict:
        """Return the established Week Planner response shape."""
        return {
            "week": self.week,
            "kids": self.kids,
            "selections": self.planner.selections,
            "day_totals": self.planner.day_totals,
            "day_sent": self.planner.day_sent,
            "history": self.planner.history,
            "ref": self.ref,
            "prev_week": self.prev_week,
            "next_week": self.next_week,
            "today": self.today,
            "school_cfg": self.school_cfg,
            "skylight_cfg": self.skylight_cfg,
            "menu_error": self.menu_error,
        }


def _resolve_display_text(
    selections: dict[str, dict[int, dict]], history: list[dict], overrides: dict[str, str]
) -> None:
    for kid_map in selections.values():
        for state in kid_map.values():
            if state.get("selection"):
                state["selection"] = db.resolve_display_text(state["selection"], overrides)
    for entry in history:
        if entry.get("selection"):
            entry["selection"] = db.resolve_display_text(entry["selection"], overrides)


def _compute_day_counts(
    selections: dict[str, dict[int, dict]], dates: list[str]
) -> tuple[dict[str, int], dict[str, int]]:
    totals: dict[str, int] = {}
    sent: dict[str, int] = {}
    for menu_date in dates:
        day = selections.get(menu_date, {})
        totals[menu_date] = len(day)
        sent[menu_date] = sum(1 for selection in day.values() if selection["publication_state"] == "published")
    return totals, sent


def _present_selection_publication_state(selections: dict[str, dict[int, dict]]) -> None:
    for kid_map in selections.values():
        for state in kid_map.values():
            state["publication_state"] = _selection_publication_state(
                state["selection"],
                state["sent_at"],
                state["sent_sitting_id"],
            )


def _selection_publication_state(
    selection: str,
    sent_at: str | None,
    sent_sitting_id: str | None,
) -> SelectionPublicationState:
    if sent_sitting_id:
        return "published"
    if sent_at and selection == db.MAKE_AT_HOME:
        return "make_at_home"
    return "pending"
