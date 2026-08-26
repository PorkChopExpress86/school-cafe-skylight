"""Tests for the week view and the /api/select endpoint."""

from __future__ import annotations

import database_support as db
import pytest
from conftest import ENTREES, MENU_DATE

from lunch_planner.planner.persistence import MAKE_AT_HOME
from lunch_planner.planner.selection_change import SelectionChange, UnknownKidError


def select(client, kid_id, selection, menu_date=MENU_DATE):
    return client.post(
        "/api/select",
        json={"kid_id": kid_id, "menu_date": menu_date, "selection": selection},
    )


class TestWeekView:
    """GET /api/week returns the full week payload as JSON."""

    def test_returns_week_kids_and_selections(self, client, kid_ids):
        response = client.get(f"/api/week?date={MENU_DATE}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["week"]) == 5  # Mon-Fri
        assert {k["name"] for k in data["kids"]} == {"Parker", "Kylee"}
        assert data["selections"] == {}
        assert data["day_totals"] == {d: 0 for d in data["week"] and [w["date"] for w in data["week"]]}
        assert data["day_sent"] == {d: 0 for d in [w["date"] for w in data["week"]]}
        assert data["history"] == []
        assert data["ref"] == MENU_DATE

    def test_week_entrees_are_listed(self, client):
        data = client.get(f"/api/week?date={MENU_DATE}").json()
        for day in data["week"]:
            assert day["entrees"] == ENTREES
            assert day["weekday"] in (
                "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            )

    def test_bad_date_falls_back_to_today(self, client):
        data = client.get("/api/week?date=not-a-date").json()
        assert data["ref"]  # today's ISO date, non-empty


class TestSelectSemantics:
    """POST /api/select sets one selection per (kid, day)."""

    def test_select_returns_updated_state(self, client, kid_ids):
        kid = kid_ids["Parker"]
        response = select(client, kid, ENTREES[0])
        assert response.status_code == 200
        data = response.json()
        assert data["selection"] == ENTREES[0]
        assert data["kid_id"] == kid
        assert data["menu_date"] == MENU_DATE
        assert data["day_totals"][MENU_DATE] == 1
        assert data["day_sent"][MENU_DATE] == 0
        assert data["history"][0]["action"] == "Selected"

    def test_one_selection_per_kid_per_day(self, client, app_module, kid_ids):
        kid = kid_ids["Parker"]
        for choice in (ENTREES[0], ENTREES[1], MAKE_AT_HOME):
            select(client, kid, choice)
        with app_module.get_db() as conn:
            rows = conn.execute(
                "SELECT selection FROM selections WHERE kid_id = ? AND menu_date = ?",
                (kid, MENU_DATE),
            ).fetchall()
        assert [r["selection"] for r in rows] == [MAKE_AT_HOME]

    def test_changing_a_selection_clears_the_sent_marker(self, client, app_module, skylight, kid_ids):
        kid = kid_ids["Parker"]
        select(client, kid, ENTREES[0])
        client.post("/api/send-day", json={"menu_date": MENU_DATE})
        select(client, kid, ENTREES[1])
        with app_module.get_db() as conn:
            row = conn.execute(
                "SELECT sent_at, sent_sitting_id FROM selections WHERE kid_id = ? AND menu_date = ?",
                (kid, MENU_DATE),
            ).fetchone()
        assert row["sent_at"] is None
        assert row["sent_sitting_id"] is None

    def test_make_at_home_is_accepted(self, client, app_module, kid_ids):
        response = select(client, kid_ids["Parker"], MAKE_AT_HOME)
        assert response.status_code == 200
        assert response.json()["selection"] == MAKE_AT_HOME


class TestSelectValidation:
    """Bad input should produce a 4xx, never an unhandled 500."""

    def test_malformed_menu_date_is_rejected(self, client, kid_ids):
        response = select(client, kid_ids["Parker"], ENTREES[0], menu_date="not-a-date")
        assert response.status_code == 400

    def test_unknown_kid_is_rejected_and_writes_nothing(self, client, app_module):
        response = select(client, 999999, ENTREES[0])
        assert response.status_code == 404
        with app_module.get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM selections WHERE kid_id = 999999"
            ).fetchone()["c"]
        assert count == 0

    def test_non_integer_kid_id_is_rejected(self, client):
        response = client.post(
            "/api/select",
            json={"kid_id": "abc", "menu_date": MENU_DATE, "selection": ENTREES[0]},
        )
        assert response.status_code == 422

    def test_whitespace_only_selection_is_rejected(self, client, kid_ids):
        response = select(client, kid_ids["Parker"], "   ")
        assert response.status_code == 400

    def test_oversized_selection_is_rejected(self, client, kid_ids):
        response = select(client, kid_ids["Parker"], "x" * 500)
        assert response.status_code == 400

    def test_control_characters_are_rejected(self, client, kid_ids):
        response = select(client, kid_ids["Parker"], "Tacos\x00")
        assert response.status_code == 400

    def test_unrecognised_but_wellformed_selection_is_accepted(self, client, kid_ids):
        """Validation must not reject a stale-page selection."""
        response = select(client, kid_ids["Parker"], "Sloppy Joe")
        assert response.status_code == 200

    def test_send_day_rejects_a_malformed_date(self, client):
        response = client.post("/api/send-day", json={"menu_date": "13/45/9999"})
        assert response.status_code == 400


def test_selection_change_owns_persistence_history_and_refreshed_readback(tmp_path):
    db_path = tmp_path / "selection-change.db"
    db.init_db(db_path)
    db.set_menu_override("CHEESE PIZZA", "Pizza Friday", db_path)
    with db.get_db(db_path) as conn:
        kid_id = conn.execute("SELECT id FROM kids WHERE name = 'Parker'").fetchone()["id"]

    result = SelectionChange(db_path).apply(kid_id, MENU_DATE, "CHEESE PIZZA")

    assert result.selection == "Pizza Friday"
    assert result.readback.selections[MENU_DATE][kid_id]["selection"] == "Pizza Friday"
    assert result.readback.day_totals == {MENU_DATE: 1}
    assert result.readback.history[0]["action"] == "Selected"


def test_selection_change_rejects_an_unknown_kid(tmp_path):
    db_path = tmp_path / "selection-change.db"
    db.init_db(db_path)

    with pytest.raises(UnknownKidError):
        SelectionChange(db_path).apply(999999, MENU_DATE, "Cheese Pizza")
