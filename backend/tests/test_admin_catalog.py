"""Tests for the source-unique Display Override catalog returned to administration."""

from __future__ import annotations

import db


def _store_menu_item(app_module, menu_date: str, description: str) -> None:
    with app_module.get_db() as conn:
        conn.execute(
            """
            INSERT INTO menu_items (menu_date, description, category, week_start, fetched_at)
            VALUES (?, ?, 'LUNCH ENTREE', '2026-08-10', '2026-08-01T00:00:00')
            """,
            (menu_date, description),
        )
        conn.commit()


def test_admin_returns_unique_display_resolved_catalog(client, app_module):
    _store_menu_item(app_module, "2026-08-11", "CHEESE PIZZA")
    _store_menu_item(app_module, "2026-08-12", "CHEESE PIZZA")
    _store_menu_item(app_module, "2026-08-12", "HOT DOG")

    client.post(
        "/api/admin/override",
        json={"original": "CHEESE PIZZA", "replacement": "Pizza Friday"},
    )
    catalog = client.get("/api/admin")

    assert catalog.status_code == 200
    data = catalog.json()
    assert set(data) == {"items", "attempts", "last_success"}
    assert data["items"] == [
        {
            "description": "HOT DOG",
            "category": "LUNCH ENTREE",
            "display_description": "Hot Dog",
        },
        {
            "description": "CHEESE PIZZA",
            "category": "LUNCH ENTREE",
            "display_description": "Pizza Friday",
        },
    ]

    client.post(
        "/api/admin/override",
        json={"original": "CHEESE PIZZA", "replacement": ""},
    )
    cleared_catalog = client.get("/api/admin").json()
    assert cleared_catalog["items"][0]["display_description"] == "Cheese Pizza"
