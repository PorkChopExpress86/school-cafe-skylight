"""Tests for the activity-history panel: storage format, pruning, rendering."""

from __future__ import annotations

from datetime import datetime

from conftest import ENTREES, MENU_DATE


class TestHistoryStorage:
    def test_timestamps_are_stored_as_iso(self, app_module, client, kid_ids):
        client.post(
            "/select",
            data={"kid_id": kid_ids["Parker"], "menu_date": MENU_DATE, "selection": ENTREES[0]},
        )
        with app_module.get_db() as conn:
            row = conn.execute(
                "SELECT created_at FROM selection_history ORDER BY id DESC LIMIT 1"
            ).fetchone()
        # Parses as ISO, so the column stays sortable and queryable.
        assert datetime.fromisoformat(row["created_at"])

    def test_selection_is_stored_raw_not_prettified(self, app_module, client, kid_ids):
        client.post(
            "/select",
            data={
                "kid_id": kid_ids["Parker"],
                "menu_date": MENU_DATE,
                "selection": app_module.MAKE_AT_HOME,
            },
        )
        with app_module.get_db() as conn:
            row = conn.execute(
                "SELECT selection FROM selection_history ORDER BY id DESC LIMIT 1"
            ).fetchone()
        assert row["selection"] == app_module.MAKE_AT_HOME

    def test_history_is_pruned_to_the_retention_limit(self, app_module, monkeypatch):
        monkeypatch.setattr(app_module, "HISTORY_RETENTION", 5)
        with app_module.get_db() as conn:
            for i in range(20):
                app_module.log_history(conn, "Parker", MENU_DATE, f"Item {i}", "Selected")
            conn.commit()
            count = conn.execute("SELECT COUNT(*) AS c FROM selection_history").fetchone()["c"]
        assert count <= 6, f"history grew unbounded: {count} rows"


class TestHistoryRendering:
    def test_make_at_home_renders_with_a_friendly_label(self, app_module, client, kid_ids):
        response = client.post(
            "/select",
            data={
                "kid_id": kid_ids["Parker"],
                "menu_date": MENU_DATE,
                "selection": app_module.MAKE_AT_HOME,
            },
        )
        assert "Make at home" in response.text
        # The raw sentinel must never leak into the history panel markup.
        history_panel = response.text.split('id="history-panel"')[1]
        assert app_module.MAKE_AT_HOME not in history_panel

    def test_iso_timestamps_render_human_readably(self, app_module):
        rendered = app_module._format_history_time("2026-08-12T07:35:00")
        assert rendered == "Aug 12, 07:35 AM"

    def test_legacy_display_timestamps_pass_through(self, app_module):
        """Rows written before ISO storage already hold a display string."""
        assert app_module._format_history_time("Aug 12, 07:35 AM") == "Aug 12, 07:35 AM"

    def test_panel_appears_on_the_week_page(self, client):
        body = client.get(f"/?date={MENU_DATE}").text
        assert 'id="history-panel"' in body
