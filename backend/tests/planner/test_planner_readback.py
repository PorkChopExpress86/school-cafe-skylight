"""Tests for the display-resolved Planner Readback seam."""

from __future__ import annotations

from datetime import date

import database_support as db

from lunch_planner.planner import readback as planner_readback
from lunch_planner.planner.readback import PlannerReadback, WeekPlannerReadback
from lunch_planner.school_menu.models import DayMenu, MenuItem
from lunch_planner.school_menu.week_menu import WeekMenuRead


def test_readback_resolves_display_text_and_keeps_global_history(tmp_path):
    db_path = tmp_path / "planner-readback.db"
    db.init_db(db_path)
    with db.get_db(db_path) as conn:
        parker_id = conn.execute("SELECT id FROM kids WHERE name = 'Parker'").fetchone()["id"]
        conn.execute(
            "INSERT INTO selections (kid_id, menu_date, selection) VALUES (?, ?, ?)",
            (parker_id, "2026-08-24", "CHEESE PIZZA"),
        )
        db.log_history(conn, "Parker", "2026-08-24", "CHEESE PIZZA", "Selected")
        db.log_history(conn, "Kylee", "2026-08-25", "HOT DOG", "Selected")
        conn.commit()
    db.set_menu_override("CHEESE PIZZA", "Pizza Friday", db_path)

    readback = PlannerReadback.read(db_path, ["2026-08-24"])

    assert readback.selections["2026-08-24"][parker_id]["selection"] == "Pizza Friday"
    assert readback.day_totals == {"2026-08-24": 1}
    assert readback.day_sent == {"2026-08-24": 0}
    assert [(entry["menu_date"], entry["selection"]) for entry in readback.history] == [
        ("2026-08-25", "Hot Dog"),
        ("2026-08-24", "Pizza Friday"),
    ]


def test_week_planner_readback_owns_the_complete_week_response(monkeypatch, tmp_path):
    db_path = tmp_path / "week-planner.db"
    db.init_db(db_path)
    ref = date(2026, 8, 12)
    week = [DayMenu(date(2026, 8, 10), [MenuItem("Cheese Pizza", "LUNCH ENTREE")])]
    monkeypatch.setattr(
        planner_readback,
        "read_week_menu",
        lambda _ref, _path: WeekMenuRead(week, None),
    )
    monkeypatch.setattr(planner_readback, "_published_skylight_config", lambda: {"frame_id": "frame-1"})

    readback = WeekPlannerReadback.read(db_path, ref)

    assert readback.as_payload() == {
        "week": [{"date": "2026-08-10", "weekday": "Monday", "entrees": ["Cheese Pizza"]}],
        "kids": [
            {"id": 1, "name": "Parker", "color": "#3B82F6", "prefix": "P-"},
            {"id": 2, "name": "Kylee", "color": "#EC4899", "prefix": "K-"},
        ],
        "selections": {},
        "day_totals": {
            "2026-08-10": 0,
            "2026-08-11": 0,
            "2026-08-12": 0,
            "2026-08-13": 0,
            "2026-08-14": 0,
        },
        "day_sent": {
            "2026-08-10": 0,
            "2026-08-11": 0,
            "2026-08-12": 0,
            "2026-08-13": 0,
            "2026-08-14": 0,
        },
        "history": [],
        "ref": "2026-08-12",
        "prev_week": "2026-08-05",
        "next_week": "2026-08-19",
        "today": date.today().isoformat(),
        "school_cfg": None,
        "skylight_cfg": {"frame_id": "frame-1"},
        "menu_error": None,
    }


def test_readback_presents_pending_published_and_make_at_home_states(tmp_path):
    db_path = tmp_path / "publication-state.db"
    db.init_db(db_path)
    with db.get_db(db_path) as conn:
        kid_ids = {
            row["name"]: row["id"] for row in conn.execute("SELECT id, name FROM kids").fetchall()
        }
        conn.executemany(
            """
            INSERT INTO selections (kid_id, menu_date, selection, sent_at, sent_sitting_id)
            VALUES (?, '2026-08-24', ?, ?, ?)
            """,
            [
                (kid_ids["Parker"], "CHEESE PIZZA", "2026-08-24T12:00:00", "sitting-1"),
                (kid_ids["Kylee"], db.MAKE_AT_HOME, "2026-08-24T12:00:00", None),
            ],
        )
        conn.commit()

    readback = PlannerReadback.read(db_path, ["2026-08-24", "2026-08-25"])

    assert readback.selections["2026-08-24"][kid_ids["Parker"]]["publication_state"] == "published"
    assert readback.selections["2026-08-24"][kid_ids["Kylee"]]["publication_state"] == "make_at_home"
    assert readback.day_sent == {"2026-08-24": 1, "2026-08-25": 0}
