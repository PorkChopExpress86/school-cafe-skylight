"""Tests for the week view and the /select radio-button endpoint."""

from __future__ import annotations

import re

from conftest import ENTREES, MENU_DATE


def cell_fragments(html: str) -> list[tuple[str, str]]:
    """(cell_id, attributes) for every cell div in an HTMX response."""
    return re.findall(r'<div id="(cell-[^"]+)"([^>]*)>', html)


def primary_cells(html: str) -> list[tuple[str, str]]:
    """Cells htmx would swap into the clicked element (i.e. not out-of-band)."""
    return [c for c in cell_fragments(html) if "hx-swap-oob" not in c[1]]


class TestSendButtonAnchor:
    """The send fragment must keep its id on every path.

    It is both the hx-target of /send-day and the OOB target of /select; a
    response that drops the id leaves the button with no resolvable target,
    which silently breaks every later send for that day.
    """

    def test_page_renders_one_anchor_per_weekday(self, client):
        body = client.get(f"/?date={MENU_DATE}").text
        assert body.count('id="send-') == 5
        assert body.count(f'id="send-{MENU_DATE}"') == 1

    def test_select_returns_the_anchor_out_of_band(self, client, kid_ids):
        response = client.post(
            "/select",
            data={"kid_id": kid_ids["Parker"], "menu_date": MENU_DATE, "selection": ENTREES[0]},
        )
        assert response.status_code == 200
        assert f'id="send-{MENU_DATE}" hx-swap-oob="true"' in response.text

    def test_send_day_returns_the_anchor_as_the_swap_target(self, client, skylight, kid_ids):
        client.post(
            "/select",
            data={"kid_id": kid_ids["Parker"], "menu_date": MENU_DATE, "selection": ENTREES[0]},
        )
        response = client.post("/send-day", data={"menu_date": MENU_DATE})
        assert response.status_code == 200
        assert f'id="send-{MENU_DATE}"' in response.text
        # It is the target of the swap, so it must NOT also be marked OOB.
        assert "hx-swap-oob" not in response.text.split("\n")[0]


class TestSelectPrimarySwap:
    """/select must always return exactly one non-OOB cell.

    If every fragment were OOB, htmx would swap an empty body into the
    clicked cell and the cell would vanish from the page.
    """

    def test_known_selection_has_one_primary_cell(self, client, kid_ids):
        kid = kid_ids["Parker"]
        response = client.post(
            "/select",
            data={"kid_id": kid, "menu_date": MENU_DATE, "selection": ENTREES[1]},
        )
        primary = primary_cells(response.text)
        assert len(primary) == 1
        assert primary[0][0] == f"cell-{MENU_DATE}-{kid}-2"

    def test_make_at_home_has_one_primary_cell(self, client, app_module, kid_ids):
        kid = kid_ids["Parker"]
        response = client.post(
            "/select",
            data={"kid_id": kid, "menu_date": MENU_DATE, "selection": app_module.MAKE_AT_HOME},
        )
        primary = primary_cells(response.text)
        assert len(primary) == 1
        assert primary[0][0] == f"cell-{MENU_DATE}-{kid}-home"
        assert "emerald" in response.text

    def test_unknown_selection_falls_back_to_the_htmx_target(self, client, kid_ids):
        """A stale page can post an entree this process no longer knows about."""
        kid = kid_ids["Parker"]
        stale_target = f"cell-{MENU_DATE}-{kid}-3"
        response = client.post(
            "/select",
            data={"kid_id": kid, "menu_date": MENU_DATE, "selection": "Sloppy Joe"},
            headers={"HX-Target": stale_target},
        )
        primary = primary_cells(response.text)
        assert len(primary) == 1
        assert primary[0][0] == stale_target
        assert "Sloppy Joe" in response.text

    def test_unknown_selection_without_htmx_target_still_has_a_primary(self, client, kid_ids):
        response = client.post(
            "/select",
            data={"kid_id": kid_ids["Parker"], "menu_date": MENU_DATE, "selection": "Sloppy Joe"},
        )
        assert len(primary_cells(response.text)) == 1

    def test_fallback_never_duplicates_a_cell_id(self, client, kid_ids):
        """A stale target id can collide with one this process would emit."""
        kid = kid_ids["Parker"]
        response = client.post(
            "/select",
            data={"kid_id": kid, "menu_date": MENU_DATE, "selection": "Sloppy Joe"},
            headers={"HX-Target": f"cell-{MENU_DATE}-{kid}-1"},
        )
        ids = [c[0] for c in cell_fragments(response.text)]
        assert len(ids) == len(set(ids))
        assert len(primary_cells(response.text)) == 1


class TestSelectValidation:
    """Bad input should produce a 4xx, never an unhandled 500."""

    def test_malformed_menu_date_is_rejected(self, client, kid_ids):
        response = client.post(
            "/select",
            data={"kid_id": kid_ids["Parker"], "menu_date": "not-a-date", "selection": ENTREES[0]},
        )
        assert response.status_code == 400

    def test_unknown_kid_is_rejected_and_writes_nothing(self, client, app_module):
        response = client.post(
            "/select",
            data={"kid_id": 999999, "menu_date": MENU_DATE, "selection": ENTREES[0]},
        )
        assert response.status_code == 404
        with app_module.get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM selections WHERE kid_id = 999999"
            ).fetchone()["c"]
        assert count == 0

    def test_non_integer_kid_id_is_rejected(self, client):
        response = client.post(
            "/select",
            data={"kid_id": "abc", "menu_date": MENU_DATE, "selection": ENTREES[0]},
        )
        assert response.status_code == 422

    def test_whitespace_only_selection_is_rejected(self, client, kid_ids):
        response = client.post(
            "/select",
            data={"kid_id": kid_ids["Parker"], "menu_date": MENU_DATE, "selection": "   "},
        )
        assert response.status_code == 400

    def test_oversized_selection_is_rejected(self, client, kid_ids):
        response = client.post(
            "/select",
            data={"kid_id": kid_ids["Parker"], "menu_date": MENU_DATE, "selection": "x" * 500},
        )
        assert response.status_code == 400

    def test_control_characters_are_rejected(self, client, kid_ids):
        response = client.post(
            "/select",
            data={"kid_id": kid_ids["Parker"], "menu_date": MENU_DATE, "selection": "Tacos\x00"},
        )
        assert response.status_code == 400

    def test_unrecognised_but_wellformed_selection_is_accepted(self, client, kid_ids):
        """Validation must not defeat the stale-page fallback above."""
        response = client.post(
            "/select",
            data={"kid_id": kid_ids["Parker"], "menu_date": MENU_DATE, "selection": "Sloppy Joe"},
        )
        assert response.status_code == 200

    def test_send_day_rejects_a_malformed_date(self, client):
        assert client.post("/send-day", data={"menu_date": "13/45/9999"}).status_code == 400


class TestSelectionSemantics:
    def test_one_selection_per_kid_per_day(self, client, app_module, kid_ids):
        kid = kid_ids["Parker"]
        for choice in (ENTREES[0], ENTREES[1], app_module.MAKE_AT_HOME):
            client.post(
                "/select",
                data={"kid_id": kid, "menu_date": MENU_DATE, "selection": choice},
            )
        with app_module.get_db() as conn:
            rows = conn.execute(
                "SELECT selection FROM selections WHERE kid_id = ? AND menu_date = ?",
                (kid, MENU_DATE),
            ).fetchall()
        assert [r["selection"] for r in rows] == [app_module.MAKE_AT_HOME]

    def test_changing_a_selection_clears_the_sent_marker(self, client, app_module, skylight, kid_ids):
        kid = kid_ids["Parker"]
        client.post(
            "/select", data={"kid_id": kid, "menu_date": MENU_DATE, "selection": ENTREES[0]}
        )
        client.post("/send-day", data={"menu_date": MENU_DATE})
        client.post(
            "/select", data={"kid_id": kid, "menu_date": MENU_DATE, "selection": ENTREES[1]}
        )
        with app_module.get_db() as conn:
            row = conn.execute(
                "SELECT sent_at, sent_sitting_id FROM selections WHERE kid_id = ? AND menu_date = ?",
                (kid, MENU_DATE),
            ).fetchone()
        assert row["sent_at"] is None
        assert row["sent_sitting_id"] is None
