"""Tests for the Menu Item Display interface.

The rule that turns a stored description into display text used to exist in
four places under three variants, so the entree a parent saw and the Skylight
recipe summary written for it could disagree. These tests pin the single rule.

The module is pure: no adapter, no cache, no subprocess. Casing via a
language model is a separate concern tested in test_menu_casing.py.
"""

from __future__ import annotations

from datetime import date

import database_support as db

from lunch_planner.menu_catalog.display import MenuItemDisplay, cased_menu_item
from lunch_planner.menu_catalog.display_read import MenuItemDisplayRead
from lunch_planner.menu_catalog.readback import MenuCatalogReadback
from lunch_planner.planner.models import MAKE_AT_HOME
from lunch_planner.school_menu.school_cafe_adapter import DayMenu, MenuItem, SchoolCafeConfig
from lunch_planner.school_menu.week_menu import WeekMenu


class TestDisplayRule:
    def test_an_override_on_the_raw_text_wins(self):
        display = MenuItemDisplay({"CHEESE PIZZA": "Pizza Friday"})
        assert display.display("CHEESE PIZZA") == "Pizza Friday"

    def test_an_override_on_the_cased_text_is_found_from_raw_text(self):
        """The divergence that used to split the two paths apart."""
        display = MenuItemDisplay({"Cheese Pizza": "Cheese Pizza (Veggie)"})
        assert display.display("CHEESE PIZZA") == "Cheese Pizza (Veggie)"

    def test_text_with_no_override_is_cased(self):
        assert MenuItemDisplay({}).display("CHEESE PIZZA") == "Cheese Pizza"

    def test_an_empty_override_does_not_blank_the_item(self):
        display = MenuItemDisplay({"Cheese Pizza": ""})
        assert display.display("CHEESE PIZZA") == "Cheese Pizza"

    def test_passthrough_values_are_returned_untouched(self):
        display = MenuItemDisplay({}, passthrough=(db.MAKE_AT_HOME,))
        assert display.display(db.MAKE_AT_HOME) == db.MAKE_AT_HOME

    def test_empty_text_is_returned_untouched(self):
        assert MenuItemDisplay({"": "x"}).display("") == ""


def test_display_text_read_loads_current_overrides_and_planner_passthrough(tmp_path):
    db_path = tmp_path / "display-read.db"
    db.init_db(db_path)
    db.set_menu_override("Cheese Pizza", "Cheese Pizza (Veggie)", db_path)

    display = MenuItemDisplayRead.read(db_path, passthrough=(MAKE_AT_HOME,))

    assert display.display("CHEESE PIZZA") == "Cheese Pizza (Veggie)"
    assert display.display(MAKE_AT_HOME) == MAKE_AT_HOME


class TestCasingRule:
    """The casing pass alone: pure, deterministic, no adapter."""

    def test_already_mixed_case_passes_through(self):
        assert cased_menu_item("Hot Dog") == "Hot Dog"

    def test_all_caps_is_title_cased(self):
        assert cased_menu_item("HOT DOG") == "Hot Dog"

    def test_acronyms_are_preserved(self):
        assert cased_menu_item("BRISKET BBQ SANDWICH") == "Brisket BBQ Sandwich"
        assert cased_menu_item("PB & J") == "PB & J"

    def test_exception_words_get_their_canonical_casing(self):
        assert cased_menu_item("MAC & CHEESE") == "Mac & Cheese"

    def test_complex_items_get_the_same_simple_rules_as_any_other(self):
        """No adapter is consulted; commas and clusters don't change the rule."""
        assert (
            cased_menu_item("CHIKN, RICE & BEANS, ROLL")
            == "Chikn, Rice & Beans, Roll"
        )

    def test_empty_text_passes_through(self):
        assert cased_menu_item("") == ""

    def test_is_deterministic_with_no_shared_state(self):
        first = cased_menu_item("HOT DOG")
        second = MenuItemDisplay().cased("HOT DOG")
        assert first == second == "Hot Dog"


class TestDisplayConsumersAgree:
    """Every path resolves the same raw text to the same display text."""

    def _week(self) -> list[DayMenu]:
        return [
            DayMenu(
                date=date(2026, 8, 12),
                items=[MenuItem("CHEESE PIZZA", "LUNCH ENTREE")],
            )
        ]

    def test_week_menu_matches_persisted_display_text(self, tmp_path):
        db_path = tmp_path / "display.db"
        db.init_db(db_path)
        db.set_menu_override("Cheese Pizza", "Cheese Pizza (Veggie)", db_path)

        class Source:
            def config(self):
                return SchoolCafeConfig("school-1")

            def fetch_week(self, _config, _reference):
                return self_week

        self_week = self._week()
        read = WeekMenu(Source()).read(date(2026, 8, 12), db_path)
        assert read.days is not None
        from_week = read.days[0].items[0].description
        from_display_read = MenuItemDisplayRead.read(db_path).display("CHEESE PIZZA")
        assert from_week == from_display_read == "Cheese Pizza (Veggie)"

    def test_admin_catalog_matches_persisted_display_text(self, tmp_path):
        db_path = tmp_path / "display.db"
        db.init_db(db_path)
        with db.get_db(db_path) as conn:
            conn.execute(
                """
                INSERT INTO menu_items (menu_date, description, category, week_start, fetched_at)
                VALUES ('2026-08-12', 'CHEESE PIZZA', 'LUNCH ENTREE', '2026-08-10', '2026-08-01')
                """
            )
            conn.commit()
        db.set_menu_override("Cheese Pizza", "Cheese Pizza (Veggie)", db_path)

        from_admin = MenuCatalogReadback.read(db_path).items[0]["display_description"]
        from_display_read = MenuItemDisplayRead.read(db_path).display("CHEESE PIZZA")
        assert from_admin == from_display_read == "Cheese Pizza (Veggie)"
