"""Assemble the current, display-resolved Planner Readback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from lunch_planner.menu_catalog.display_read import MenuItemDisplayRead
from lunch_planner.planner import persistence as db
from lunch_planner.planner.models import MAKE_AT_HOME
from lunch_planner.school_menu.models import get_week_dates
from lunch_planner.school_menu.week_menu import read_week_menu

SelectionPublicationState = Literal["pending", "published", "make_at_home"]
_SCHOOL_TIME_ZONE = ZoneInfo("America/Chicago")


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
        display = MenuItemDisplayRead.read(db_path, passthrough=(MAKE_AT_HOME,))
        selections, history = db.load_planner_state(db_path, requested_dates)

        _resolve_display_text(selections, history, display)
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
        kids = db.load_kids(db_path)
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


@dataclass(frozen=True)
class MonthPlannerReadback:
    """The current read-only monthly Selection summary."""

    month: str
    kids: list[dict]
    planner: PlannerReadback
    today: str

    @classmethod
    def read(cls, db_path: Path, current_date: date | None = None) -> MonthPlannerReadback:
        """Read the current School Date month without requesting any remote menu data."""
        current_date = current_date or _school_today()
        dates = _month_dates(current_date)
        return cls(
            month=current_date.strftime("%Y-%m"),
            kids=db.load_kids(db_path),
            planner=PlannerReadback.read(db_path, dates),
            today=current_date.isoformat(),
        )

    def as_payload(self) -> dict:
        """Return the Month Planner Readback response shape."""
        return {
            "month": self.month,
            "today": self.today,
            "kids": self.kids,
            "selections": self.planner.selections,
            "day_totals": self.planner.day_totals,
            "day_sent": self.planner.day_sent,
        }


def _school_today() -> date:
    return datetime.now(_SCHOOL_TIME_ZONE).date()


def _month_dates(current_date: date) -> list[str]:
    first_day = current_date.replace(day=1)
    if first_day.month == 12:
        next_month = first_day.replace(year=first_day.year + 1, month=1)
    else:
        next_month = first_day.replace(month=first_day.month + 1)
    days_in_month = (next_month - first_day).days
    return [(first_day + timedelta(days=offset)).isoformat() for offset in range(days_in_month)]


def _resolve_display_text(
    selections: dict[str, dict[int, dict]], history: list[dict], display: MenuItemDisplayRead
) -> None:
    for kid_map in selections.values():
        for state in kid_map.values():
            if state.get("selection"):
                state["selection"] = display.display(state["selection"])
    for entry in history:
        if entry.get("selection"):
            entry["selection"] = display.display(entry["selection"])


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
    if sent_at and selection == MAKE_AT_HOME:
        return "make_at_home"
    return "pending"
