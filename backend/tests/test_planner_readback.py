"""Tests for the display-resolved Planner Readback seam."""

from __future__ import annotations

import db
from planner_readback import PlannerReadback


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
