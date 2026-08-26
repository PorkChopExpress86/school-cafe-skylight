"""Tests for route-facing Meal-plan Publication coordination."""

from __future__ import annotations

from datetime import date

import database_support as db
from conftest import FakeSkylightClient

from lunch_planner.publication.control import PublicationControl


def test_control_returns_normalized_publication_and_refreshed_readback(tmp_path):
    db_path = tmp_path / "publication-control.db"
    db.init_db(db_path)
    with db.get_db(db_path) as conn:
        parker_id = conn.execute("SELECT id FROM kids WHERE name = 'Parker'").fetchone()["id"]
        conn.execute(
            "INSERT INTO selections (kid_id, menu_date, selection) VALUES (?, ?, ?)",
            (parker_id, "2026-08-24", "Cheese Pizza"),
        )
        conn.commit()

    client = FakeSkylightClient()
    controlled = PublicationControl(db_path, lambda: "frame-1", lambda: client).publish([date(2026, 8, 24)])

    assert controlled.error is None
    assert controlled.date_results[0].ok is True
    assert [kid.status for kid in controlled.date_results[0].results] == ["sent", "skipped"]
    assert controlled.day_totals == {"2026-08-24": 2}
    assert controlled.day_sent == {"2026-08-24": 1}
    assert controlled.history[0]["action"] == "Sent to Skylight"
    assert controlled.as_day_payload()["results"] == [
        {"kid_name": "Parker", "selection": "Cheese Pizza", "status": "sent"},
        {"kid_name": "Kylee", "selection": "__MAKE_AT_HOME__", "status": "skipped"},
    ]
    assert client.closed is True


def test_control_reports_missing_frame_without_logging_in(tmp_path):
    db_path = tmp_path / "publication-control.db"
    db.init_db(db_path)
    login_called = False

    def login():
        nonlocal login_called
        login_called = True
        raise AssertionError("login should not run without a frame")

    with db.get_db(db_path) as conn:
        parker_id = conn.execute("SELECT id FROM kids WHERE name = 'Parker'").fetchone()["id"]
        conn.execute(
            "INSERT INTO selections (kid_id, menu_date, selection) VALUES (?, ?, ?)",
            (parker_id, "2026-08-24", "Cheese Pizza"),
        )
        conn.commit()

    controlled = PublicationControl(db_path, lambda: "", login).publish([date(2026, 8, 24)])

    assert controlled.error == "SKYLIGHT_FRAME_ID is not set in .env."
    assert controlled.date_results == []
    assert controlled.day_totals == {"2026-08-24": 1}
    assert controlled.day_sent == {"2026-08-24": 0}
    assert controlled.history == []
    assert controlled.as_day_payload()["day_totals"] == {"2026-08-24": 1}
    assert login_called is False


def test_day_route_keeps_readback_when_frame_is_missing(client, app_module, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "skylight_frame_id",
        lambda: "",
    )

    response = client.post("/api/send-day", json={"menu_date": "2026-08-12"})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["day_totals"] == {"2026-08-12": 0}
    assert data["day_sent"] == {"2026-08-12": 0}
    assert data["history"] == []


def test_control_reports_multi_date_make_at_home_and_partial_outcomes(tmp_path):
    db_path = tmp_path / "publication-control.db"
    db.init_db(db_path)
    with db.get_db(db_path) as conn:
        parker_id = conn.execute("SELECT id FROM kids WHERE name = 'Parker'").fetchone()["id"]
        kylee_id = conn.execute("SELECT id FROM kids WHERE name = 'Kylee'").fetchone()["id"]
        conn.executemany(
            "INSERT INTO selections (kid_id, menu_date, selection) VALUES (?, ?, ?)",
            [
                (parker_id, "2026-08-24", "Cheese Pizza"),
                (kylee_id, "2026-08-25", "Hot Dog"),
            ],
        )
        conn.commit()

    client = FakeSkylightClient()
    client.fail_create_recipe_for.add("K- Hot Dog")
    controlled = PublicationControl(db_path, lambda: "frame-1", lambda: client).publish(
        [date(2026, 8, 24), date(2026, 8, 25)]
    )

    assert controlled.error is None
    assert [(result.menu_date, result.ok) for result in controlled.date_results] == [
        ("2026-08-24", True),
        ("2026-08-25", False),
    ]
    assert [kid.status for kid in controlled.date_results[0].results] == [
        "sent",
        "skipped",
    ]
    assert controlled.day_totals == {"2026-08-24": 2, "2026-08-25": 2}
    assert controlled.day_sent == {"2026-08-24": 1, "2026-08-25": 0}
    week_payload = controlled.as_week_payload()
    assert week_payload["ok"] is False
    assert week_payload["sent"] == 1
    assert week_payload["skipped"] == 2
    assert {result["status"] for result in week_payload["results"]} == {"sent", "skipped", "error"}
    assert week_payload["errors"] == [
        "recipe_creation(Kylee): simulated create_recipe failure for 'K- Hot Dog'"
    ]


def test_control_preserves_unowned_sittings(tmp_path):
    db_path = tmp_path / "publication-control.db"
    db.init_db(db_path)
    with db.get_db(db_path) as conn:
        parker_id = conn.execute("SELECT id FROM kids WHERE name = 'Parker'").fetchone()["id"]
        conn.execute(
            "INSERT INTO selections (kid_id, menu_date, selection) VALUES (?, ?, ?)",
            (parker_id, "2026-08-12", "Cheese Pizza"),
        )
        conn.commit()

    client = FakeSkylightClient()
    client.seed("P- Old School Lunch")
    client.seed("Family Taco Night")
    controlled = PublicationControl(db_path, lambda: "frame-1", lambda: client).publish([date(2026, 8, 12)])

    assert controlled.date_results[0].deleted == 1
    assert client.summaries() == ["Family Taco Night", "P- Cheese Pizza"]
