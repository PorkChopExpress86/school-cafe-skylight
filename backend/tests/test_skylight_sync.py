"""Tests for the Skylight write path (send_day_to_skylight and /api/send-day)."""

from __future__ import annotations

import pytest
from conftest import ENTREES, MENU_DATE, FakeObj, failing_db


def pick(client, kid_id, selection, menu_date=MENU_DATE):
    response = client.post(
        "/api/select",
        json={"kid_id": kid_id, "menu_date": menu_date, "selection": selection},
    )
    assert response.status_code == 200
    return response


def send_day(client, menu_date=MENU_DATE):
    return client.post("/api/send-day", json={"menu_date": menu_date})


class TestRecipeNaming:
    def test_summary_uses_the_stored_prefix(self, app_module):
        assert app_module._recipe_summary("P-", "Cheese Pizza") == "P- Cheese Pizza"
        assert app_module._recipe_summary("K-", "Hot Dog") == "K- Hot Dog"

    def test_default_kids_get_their_documented_prefixes(self, app_module):
        with app_module.get_db() as conn:
            rows = conn.execute("SELECT name, prefix FROM kids ORDER BY id").fetchall()
        assert {r["name"]: r["prefix"] for r in rows} == {"Parker": "P-", "Kylee": "K-"}

    @pytest.mark.parametrize(
        "name,expected",
        [("Parker", "P-"), ("kylee", "K-"), ("  ada ", "A-"), ("", "?-"), ("   ", "?-"), ("!!", "?-")],
    )
    def test_derived_prefix_never_raises(self, app_module, name, expected):
        """An empty or punctuation-only name used to raise IndexError."""
        assert app_module._derive_kid_prefix(name) == expected

    def test_prefixes_are_disambiguated(self, app_module):
        assert app_module._unique_prefix("K-", set()) == "K-"
        assert app_module._unique_prefix("K-", {"k-"}) == "K2-"
        assert app_module._unique_prefix("K-", {"k-", "k2-"}) == "K3-"

    def test_backfill_gives_same_initial_kids_distinct_prefixes(self, app_module):
        with app_module.get_db() as conn:
            conn.execute("INSERT INTO kids (name, color, prefix) VALUES ('Kyle', '#000', '')")
            conn.commit()
            app_module._backfill_kid_prefixes(conn)
            conn.commit()
            rows = conn.execute("SELECT name, prefix FROM kids").fetchall()
        prefixes = [r["prefix"] for r in rows]
        assert len(prefixes) == len(set(prefixes)), f"prefixes collided: {prefixes}"


class TestPrefixScopedWipe:
    """A send replaces both kids' entries and nothing else on the calendar."""

    def test_creates_a_sitting_per_kid(self, client, skylight, kid_ids):
        pick(client, kid_ids["Parker"], ENTREES[0])
        pick(client, kid_ids["Kylee"], ENTREES[1])

        result = send_day(client)
        assert result.status_code == 200
        assert result.json()["ok"] is True
        assert skylight.summaries() == ["K- Hot Dog", "P- Cheese Pizza"]

    def test_leaves_a_non_prefixed_lunch_alone(self, app_module, client, skylight, kid_ids):
        family = skylight.seed("Family Taco Night", "cat-lunch")
        pick(client, kid_ids["Parker"], ENTREES[0])
        pick(client, kid_ids["Kylee"], ENTREES[0])

        app_module.send_day_to_skylight(MENU_DATE)

        assert str(family.id) not in skylight.deleted_ids
        assert "Family Taco Night" in skylight.summaries()

    def test_leaves_a_prefixed_sitting_in_another_category_alone(
        self, app_module, client, skylight, kid_ids
    ):
        dinner = skylight.seed("P- Family Dinner Idea", "cat-dinner")
        pick(client, kid_ids["Parker"], ENTREES[0])

        app_module.send_day_to_skylight(MENU_DATE)

        assert str(dinner.id) not in skylight.deleted_ids

    def test_cleans_up_an_untracked_prefixed_sitting(self, app_module, client, skylight, kid_ids):
        """A sitting the local DB has no record of is still ours to remove."""
        stray = skylight.seed("K- Leftover From Before", "cat-lunch")
        pick(client, kid_ids["Parker"], app_module.MAKE_AT_HOME)
        pick(client, kid_ids["Kylee"], app_module.MAKE_AT_HOME)

        result = app_module.send_day_to_skylight(MENU_DATE)

        assert str(stray.id) in skylight.deleted_ids
        assert skylight.sittings == []
        assert result["deleted"] == 1

    def test_both_kids_are_replaced_when_only_one_changed(
        self, app_module, client, skylight, kid_ids
    ):
        pick(client, kid_ids["Parker"], ENTREES[0])
        pick(client, kid_ids["Kylee"], ENTREES[1])
        app_module.send_day_to_skylight(MENU_DATE)
        kylee_original = next(
            s for s in skylight.sittings
            if skylight.recipe_by_id(s.meal_recipe_id).summary.startswith("K-")
        )

        pick(client, kid_ids["Parker"], ENTREES[1])  # only Parker changes
        result = app_module.send_day_to_skylight(MENU_DATE)

        assert str(kylee_original.id) in skylight.deleted_ids
        assert result["deleted"] == 2
        assert len(skylight.sittings) == 2

    def test_make_at_home_removes_only_that_kid(self, app_module, client, skylight, kid_ids):
        pick(client, kid_ids["Parker"], ENTREES[0])
        pick(client, kid_ids["Kylee"], ENTREES[1])
        app_module.send_day_to_skylight(MENU_DATE)

        pick(client, kid_ids["Parker"], app_module.MAKE_AT_HOME)
        app_module.send_day_to_skylight(MENU_DATE)

        assert skylight.summaries() == ["K- Hot Dog"]

    def test_wipes_a_sitting_identified_by_kid_name_in_recipe(
        self, app_module, client, skylight, kid_ids
    ):
        """A sitting whose recipe summary contains the kid's full name
        (no prefix) should still be wiped on send."""
        stray = skylight.seed("Parker Homemade Pasta", "cat-lunch")
        pick(client, kid_ids["Parker"], app_module.MAKE_AT_HOME)
        pick(client, kid_ids["Kylee"], app_module.MAKE_AT_HOME)

        result = app_module.send_day_to_skylight(MENU_DATE)

        assert str(stray.id) in skylight.deleted_ids
        assert result["deleted"] == 1

    def test_wipes_a_free_form_sitting_with_kid_name(
        self, app_module, client, skylight, kid_ids
    ):
        """A sitting with no linked recipe but a kid name in its summary
        should still be wiped on send."""
        skylight.seed("Some Generic Recipe", "cat-lunch")
        stray = FakeObj(
            id="stray-1",
            meal_category_id="cat-lunch",
            meal_recipe_id=None,
            summary="Kylee Lunch",
            note="",
            instances=[MENU_DATE],
        )
        skylight.sittings.append(stray)
        pick(client, kid_ids["Parker"], app_module.MAKE_AT_HOME)
        pick(client, kid_ids["Kylee"], app_module.MAKE_AT_HOME)

        result = app_module.send_day_to_skylight(MENU_DATE)

        assert "stray-1" in skylight.deleted_ids
        assert result["deleted"] == 1

    def test_wipes_all_duplicates_not_just_one(
        self, app_module, client, skylight, kid_ids
    ):
        """If the calendar already has multiple sittings for the same kid
        on the same date (duplicates from prior sends), every one of them
        must be removed before the new sitting is created."""
        dup1 = skylight.seed("P- Cheese Pizza", "cat-lunch")
        dup2 = skylight.seed("P- Cheese Pizza", "cat-lunch")
        dup3 = skylight.seed("K- Hot Dog", "cat-lunch")
        pick(client, kid_ids["Parker"], ENTREES[0])
        pick(client, kid_ids["Kylee"], ENTREES[1])

        result = app_module.send_day_to_skylight(MENU_DATE)

        assert str(dup1.id) in skylight.deleted_ids
        assert str(dup2.id) in skylight.deleted_ids
        assert str(dup3.id) in skylight.deleted_ids
        assert result["deleted"] == 3
        assert len(skylight.sittings) == 2


class TestUnpickedKidsDefaultToMakeAtHome:
    """An unattended send must never invent a meal nobody chose."""

    def test_a_kid_with_no_selection_gets_no_sitting(self, app_module, client, skylight, kid_ids):
        pick(client, kid_ids["Parker"], ENTREES[0])  # Kylee never picked

        result = app_module.send_day_to_skylight(MENU_DATE)

        assert skylight.summaries() == ["P- Cheese Pizza"]
        statuses = {r["kid_name"]: r["status"] for r in result["results"]}
        assert statuses == {"Parker": "sent", "Kylee": "skipped"}

    def test_the_default_is_recorded_as_make_at_home(self, app_module, client, skylight, kid_ids):
        pick(client, kid_ids["Parker"], ENTREES[0])
        app_module.send_day_to_skylight(MENU_DATE)

        with app_module.get_db() as conn:
            row = conn.execute(
                "SELECT selection FROM selections WHERE kid_id = ? AND menu_date = ?",
                (kid_ids["Kylee"], MENU_DATE),
            ).fetchone()
        assert row["selection"] == app_module.MAKE_AT_HOME


class TestFailureReporting:
    def test_a_partial_failure_is_not_reported_as_success(
        self, app_module, client, skylight, kid_ids
    ):
        skylight.fail_create_recipe_for.add("K- Hot Dog")
        pick(client, kid_ids["Parker"], ENTREES[0])
        pick(client, kid_ids["Kylee"], ENTREES[1])

        result = app_module.send_day_to_skylight(MENU_DATE)

        assert result["ok"] is False
        assert len(result["errors"]) == 1
        statuses = {r["kid_name"]: r["status"] for r in result["results"]}
        assert statuses == {"Parker": "sent", "Kylee": "error"}

    def test_history_records_only_confirmed_sends(self, app_module, client, skylight, kid_ids):
        skylight.fail_create_recipe_for.add("K- Hot Dog")
        pick(client, kid_ids["Parker"], app_module.MAKE_AT_HOME)
        pick(client, kid_ids["Kylee"], ENTREES[1])

        send_day(client)

        with app_module.get_db() as conn:
            sent_rows = conn.execute(
                "SELECT kid_name FROM selection_history WHERE action = 'Sent to Skylight'"
            ).fetchall()
        # Parker was skipped (make-at-home), Kylee errored - neither was sent.
        assert sent_rows == []

    def test_history_records_a_successful_send(self, app_module, client, skylight, kid_ids):
        pick(client, kid_ids["Kylee"], ENTREES[1])

        send_day(client)

        with app_module.get_db() as conn:
            rows = conn.execute(
                "SELECT kid_name FROM selection_history WHERE action = 'Sent to Skylight'"
            ).fetchall()
        assert [r["kid_name"] for r in rows] == ["Kylee"]

    def test_partial_failure_returns_ok_false(self, app_module, client, skylight, kid_ids):
        skylight.fail_create_recipe_for.add("P- Cheese Pizza")
        pick(client, kid_ids["Parker"], ENTREES[0])

        response = send_day(client)

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert data["errors"]

    def test_success_returns_ok_true(self, client, skylight, kid_ids):
        pick(client, kid_ids["Parker"], ENTREES[0])
        response = send_day(client)
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_send_returns_updated_counts_and_history(self, client, skylight, kid_ids):
        """After sending, the response includes day counts and history so
        the SPA can refresh without a second round-trip."""
        kid = kid_ids["Parker"]
        pick(client, kid, ENTREES[0])
        response = send_day(client)
        data = response.json()
        # Parker picked an entree; Kylee defaults to make-at-home on send.
        assert data["day_totals"][MENU_DATE] == 2
        assert data["day_sent"][MENU_DATE] == 1
        assert any(h["action"] == "Sent to Skylight" for h in data["history"])

    def test_the_client_is_always_closed(self, app_module, client, skylight, kid_ids):
        skylight.fail_create_recipe_for.add("P- Cheese Pizza")
        pick(client, kid_ids["Parker"], ENTREES[0])
        app_module.send_day_to_skylight(MENU_DATE)
        assert skylight.closed is True

    def test_list_sittings_failure_aborts_send(self, app_module, client, skylight, kid_ids):
        """A list_sittings failure must abort, not silently create duplicates."""
        pick(client, kid_ids["Parker"], ENTREES[0])

        def _fail(*a, **kw):
            raise RuntimeError("simulated list_sittings failure")

        skylight.list_sittings = _fail
        result = app_module.send_day_to_skylight(MENU_DATE)

        assert result["ok"] is False
        assert "list_sittings" in result["message"]
        assert result["sent"] == 0
        assert skylight.sittings == []


class TestDatabaseFailureIsolation:
    """A DB failure must not undo work Skylight already confirmed."""

    def test_a_failed_write_still_leaves_the_calendar_correct(
        self, app_module, client, skylight, kid_ids, monkeypatch
    ):
        pick(client, kid_ids["Parker"], ENTREES[0])
        app_module.send_day_to_skylight(MENU_DATE)
        original = skylight.sittings[0]

        pick(client, kid_ids["Parker"], ENTREES[1])
        with failing_db(app_module, monkeypatch, "sent_sitting_id = ?") as state:
            result = app_module.send_day_to_skylight(MENU_DATE)

        assert state["tripped"], "the simulated DB failure never fired"
        assert any("db update after create_sitting" in e for e in result["errors"])
        # The old sitting was still removed and the new one still created.
        assert str(original.id) in skylight.deleted_ids
        assert skylight.summaries() == ["P- Hot Dog"]


class TestConfigGuards:
    def test_missing_frame_id_is_reported_not_raised(self, app_module, monkeypatch):
        monkeypatch.setattr(
            app_module,
            "skylight_config",
            lambda: {"email": "e", "password": "p", "frame_id": "", "timezone": "", "base_url": ""},
        )
        result = app_module.send_day_to_skylight(MENU_DATE)
        assert result["ok"] is False
        assert "SKYLIGHT_FRAME_ID" in result["message"]

    def test_missing_lunch_category_is_reported(self, app_module, client, skylight, kid_ids):
        skylight.categories = [c for c in skylight.categories if c.label != "Lunch"]
        pick(client, kid_ids["Parker"], ENTREES[0])
        result = app_module.send_day_to_skylight(MENU_DATE)
        assert result["ok"] is False
        assert "Lunch" in result["message"]
