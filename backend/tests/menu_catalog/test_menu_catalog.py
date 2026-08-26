"""Tests for the deep Menu Catalog Readback module."""

from __future__ import annotations

from datetime import datetime

from lunch_planner.menu_catalog.persistence import log_sync_attempt, set_menu_override
from lunch_planner.menu_catalog.readback import MenuCatalogReadback
from lunch_planner.menu_catalog.refresh import MenuCatalogRefreshResult
from lunch_planner.persistence.connection import get_db
from lunch_planner.persistence.schema import init_db


def test_menu_catalog_readback_resolves_orders_and_summarizes(tmp_path):
    db_path = tmp_path / "menu-catalog.db"
    init_db(db_path)
    with get_db(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO menu_items (menu_date, description, category, week_start, fetched_at)
            VALUES (?, ?, 'LUNCH ENTREE', '2026-08-10', '2026-08-01T00:00:00')
            """,
            [("2026-08-11", "CHEESE PIZZA"), ("2026-08-12", "HOT DOG")],
        )
        conn.commit()
    set_menu_override("CHEESE PIZZA", "Pizza Friday", db_path)
    log_sync_attempt(
        db_path,
        MenuCatalogRefreshResult(
            attempted_at=datetime(2026, 8, 12, 3),
            status="refreshed",
            message="done",
            weeks_fetched=4,
            items_stored=2,
            weeks_covered=("2026-08-10",),
        ),
    )

    readback = MenuCatalogReadback.read(db_path)

    assert readback.items == [
        {"description": "HOT DOG", "category": "LUNCH ENTREE", "display_description": "Hot Dog"},
        {"description": "CHEESE PIZZA", "category": "LUNCH ENTREE", "display_description": "Pizza Friday"},
    ]
    assert readback.last_success == readback.attempts[0]
    assert readback.as_payload()["items"] == readback.items
