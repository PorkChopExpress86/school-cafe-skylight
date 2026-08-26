"""Tests for the admin bulk re-casing pass.

The only caller of a real language model in this codebase. The adapter is a
parameter, not a global, so these tests never shell out.
"""

from __future__ import annotations

from pathlib import Path

import database_support as db
import pytest

from lunch_planner.menu_catalog.casing import pin_display_overrides_for_all_items


class FakeCasing:
    """Casing adapter that answers from a script and records what it was asked."""

    def __init__(self, answers: dict[str, str] | None = None) -> None:
        self.answers = answers or {}
        self.asked: list[str] = []

    def suggest(self, text: str) -> str | None:
        self.asked.append(text)
        return self.answers.get(text)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    db.init_db(path)
    return path


def _store_item(db_path: Path, description: str) -> None:
    with db.get_db(db_path) as conn:
        db._init_menu_tables(conn)
        conn.execute(
            "INSERT INTO menu_items (menu_date, description, category, week_start, fetched_at) "
            "VALUES ('2026-08-12', ?, 'LUNCH ENTREE', '2026-08-10', '2026-08-01T00:00:00')",
            (description,),
        )
        conn.commit()


class TestBulkRecasing:
    def test_asks_the_adapter_for_every_unique_item(self, db_path):
        _store_item(db_path, "Hot Dog")
        _store_item(db_path, "Cheese Pizza")
        casing = FakeCasing()

        pin_display_overrides_for_all_items(db_path, casing=casing)

        assert sorted(casing.asked) == ["Cheese Pizza", "Hot Dog"]

    def test_pins_a_changed_answer_as_a_display_override(self, db_path):
        _store_item(db_path, "Chikn, Rice & Beans")
        casing = FakeCasing({"Chikn, Rice & Beans": "Chik'n Rice & Beans"})

        result = pin_display_overrides_for_all_items(db_path, casing=casing)

        assert result["updated"] == 1
        assert db.fetch_all_overrides(db_path)["Chikn, Rice & Beans"] == "Chik'n Rice & Beans"

    def test_an_unchanged_or_silent_answer_pins_nothing(self, db_path):
        _store_item(db_path, "Hot Dog")
        casing = FakeCasing({"Hot Dog": "Hot Dog"})

        result = pin_display_overrides_for_all_items(db_path, casing=casing)

        assert result["updated"] == 0
        assert db.fetch_all_overrides(db_path) == {}

    def test_reports_the_total_item_count(self, db_path):
        _store_item(db_path, "Hot Dog")
        _store_item(db_path, "Cheese Pizza")

        result = pin_display_overrides_for_all_items(db_path, casing=FakeCasing())

        assert result["count"] == 2
        assert result["ok"] is True
