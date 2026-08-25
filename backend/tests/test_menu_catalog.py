"""Tests for the deep Menu Catalog Readback module."""

from __future__ import annotations

from datetime import datetime

import db
from menu_catalog import MenuCatalogReadback
from menu_sync import SyncResult


def test_menu_catalog_readback_resolves_orders_and_summarizes(tmp_path):
    db_path = tmp_path / "menu-catalog.db"
    db.init_db(db_path)
    with db.get_db(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO menu_items (menu_date, description, category, week_start, fetched_at)
            VALUES (?, ?, 'LUNCH ENTREE', '2026-08-10', '2026-08-01T00:00:00')
            """,
            [("2026-08-11", "CHEESE PIZZA"), ("2026-08-12", "HOT DOG")],
        )
        conn.commit()
    db.set_menu_override("CHEESE PIZZA", "Pizza Friday", db_path)
    db.log_sync_attempt(
        db_path,
        SyncResult(
            attempted_at=datetime(2026, 8, 12, 3),
            succeeded=True,
            weeks_fetched=4,
            items_stored=2,
            error=None,
            weeks_covered=["2026-08-10"],
        ),
    )

    readback = MenuCatalogReadback.read(db_path)

    assert readback.items == [
        {"description": "HOT DOG", "category": "LUNCH ENTREE", "display_description": "Hot Dog"},
        {"description": "CHEESE PIZZA", "category": "LUNCH ENTREE", "display_description": "Pizza Friday"},
    ]
    assert readback.last_success == readback.attempts[0]
    assert readback.as_payload()["items"] == readback.items
