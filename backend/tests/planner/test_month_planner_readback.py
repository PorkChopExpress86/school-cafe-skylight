"""Behavior tests for the current Month Planner Readback contract."""

from __future__ import annotations

from datetime import date

from conftest import ENTREES

from lunch_planner.persistence.connection import get_db
from lunch_planner.planner import readback as planner_readback
from lunch_planner.planner.models import MAKE_AT_HOME


def test_current_month_readback_summarizes_selection_publication_states(
    client, app_module, kid_ids, monkeypatch, skylight
):
    current_date = date(2026, 8, 12)
    monkeypatch.setattr(planner_readback, "_school_today", lambda: current_date)
    today = current_date.isoformat()
    client.post("/api/select", json={"kid_id": kid_ids["Parker"], "menu_date": today, "selection": ENTREES[0]})
    client.post("/api/select", json={"kid_id": kid_ids["Kylee"], "menu_date": today, "selection": MAKE_AT_HOME})
    client.post("/api/send-day", json={"menu_date": today})
    with get_db(app_module.DB_PATH) as conn:
        conn.execute(
            "UPDATE selections SET sent_at = ? WHERE kid_id = ? AND menu_date = ?",
            (f"{today}T12:00:00", kid_ids["Kylee"], today),
        )
        conn.commit()

    response = client.get("/api/month")

    assert response.status_code == 200
    data = response.json()
    assert data["month"] == today[:7]
    assert data["today"] == today
    assert data["day_totals"][today] == 2
    assert data["selections"][today][str(kid_ids["Parker"])]["publication_state"] == "published"
    assert data["selections"][today][str(kid_ids["Kylee"])]["publication_state"] == "make_at_home"


def test_month_readback_uses_an_addressable_month_and_safely_falls_back(client, monkeypatch):
    monkeypatch.setattr(planner_readback, "_school_today", lambda: date(2026, 8, 12))

    september = client.get("/api/month?month=2026-09").json()
    invalid = client.get("/api/month?month=September").json()

    assert september["month"] == "2026-09"
    assert september["today"] == "2026-08-12"
    assert september["prev_month"] == "2026-08"
    assert september["next_month"] == "2026-10"
    assert september["current_month"] == "2026-08"
    assert invalid["month"] == "2026-08"
