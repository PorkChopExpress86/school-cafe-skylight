"""Assemble the current, display-resolved Planner Readback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import db


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
        day_totals, day_sent = _compute_day_counts(selections, requested_dates)
        return cls(selections, day_totals, day_sent, history)


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
        sent[menu_date] = sum(1 for selection in day.values() if selection["sent_sitting_id"])
    return totals, sent
