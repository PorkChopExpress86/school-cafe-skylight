"""Tests for the activity-history storage: format, pruning, API exposure."""

from __future__ import annotations

from datetime import datetime

from conftest import ENTREES, MENU_DATE

import db
from db import MAKE_AT_HOME


def select(client, kid_id, selection, menu_date=MENU_DATE):
    return client.post(
        "/api/select",
        json={"kid_id": kid_id, "menu_date": menu_date, "selection": selection},
    )


class TestHistoryStorage:
    def test_timestamps_are_stored_as_iso(self, app_module, client, kid_ids):
        select(client, kid_ids["Parker"], ENTREES[0])
        with app_module.get_db() as conn:
            row = conn.execute(
                "SELECT created_at FROM selection_history ORDER BY id DESC LIMIT 1"
            ).fetchone()
        # Parses as ISO, so the column stays sortable and queryable.
        assert datetime.fromisoformat(row["created_at"])

    def test_selection_is_stored_raw_not_prettified(self, app_module, client, kid_ids):
        select(client, kid_ids["Parker"], MAKE_AT_HOME)
        with app_module.get_db() as conn:
            row = conn.execute(
                "SELECT selection FROM selection_history ORDER BY id DESC LIMIT 1"
            ).fetchone()
        assert row["selection"] == MAKE_AT_HOME

    def test_history_is_pruned_to_the_retention_limit(self, app_module):
        with app_module.get_db() as conn:
            for i in range(20):
                db.log_history(
                    conn, "Parker", MENU_DATE, f"Item {i}", "Selected", retention_limit=5
                )
            conn.commit()
            count = conn.execute("SELECT COUNT(*) AS c FROM selection_history").fetchone()["c"]
        assert count <= 6, f"history grew unbounded: {count} rows"


class TestHistoryAPI:
    def test_make_at_home_is_returned_with_sentinel(self, app_module, client, kid_ids):
        """The API returns the raw sentinel; the SPA renders the friendly label."""
        response = select(client, kid_ids["Parker"], MAKE_AT_HOME)
        data = response.json()
        assert data["history"][0]["selection"] == MAKE_AT_HOME

    def test_iso_timestamps_are_returned_raw(self, app_module, client, kid_ids):
        select(client, kid_ids["Parker"], ENTREES[0])
        data = client.get(f"/api/week?date={MENU_DATE}").json()
        created = data["history"][0]["created_at"]
        # Parses as ISO, so the SPA can format it client-side.
        assert datetime.fromisoformat(created)

    def test_history_appears_in_week_payload(self, client, kid_ids):
        select(client, kid_ids["Parker"], ENTREES[0])
        data = client.get(f"/api/week?date={MENU_DATE}").json()
        assert data["history"]
        assert data["history"][0]["action"] == "Selected"
        assert data["history"][0]["kid_name"] == "Parker"
