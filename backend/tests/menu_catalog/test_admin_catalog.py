"""Tests for the source-unique Display Override catalog returned to administration."""

from __future__ import annotations

from datetime import datetime

from lunch_planner.menu_catalog.refresh import MenuCatalogRefreshResult


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


def test_manual_refresh_route_projects_the_shared_typed_outcome(client, app_module, monkeypatch):
    expected = MenuCatalogRefreshResult(datetime(2026, 8, 25, 18), "refreshed", "Refreshed catalog.")

    class Refresh:
        def refresh(self):
            return expected

    monkeypatch.setattr(
        app_module,
        "default_menu_catalog_refresh",
        lambda db_path: Refresh() if db_path == app_module.DB_PATH else None,
    )

    response = client.post("/api/admin/sync")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "Refreshed catalog."}
