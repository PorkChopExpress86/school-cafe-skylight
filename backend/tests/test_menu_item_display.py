"""Tests for the Menu Item Display interface.

The rule that turns a stored description into display text used to exist in
four places under three variants, so the entree a parent saw and the Skylight
recipe summary written for it could disagree. These tests pin the single rule
and the casing seam behind it.
"""

from __future__ import annotations

from datetime import date

import db
import menu_service
from menu_item_display import MenuItemDisplay, NoCasing
from school_menu import DayMenu, MenuItem


class RecordingCasing:
    """Casing adapter that answers from a script and records what it was asked."""

    def __init__(self, answers: dict[str, str] | None = None) -> None:
        self.answers = answers or {}
        self.asked: list[str] = []

    def suggest(self, text: str) -> str | None:
        self.asked.append(text)
        return self.answers.get(text)


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


class TestPathsAgree:
    """Every path resolves the same raw text to the same display text."""

    OVERRIDES = {"Cheese Pizza": "Cheese Pizza (Veggie)"}

    def _week(self) -> list[DayMenu]:
        return [
            DayMenu(
                date=date(2026, 8, 12),
                items=[MenuItem("CHEESE PIZZA", "LUNCH ENTREE")],
            )
        ]

    def test_week_path_matches_the_selection_path(self, tmp_path):
        from_week = (
            menu_service.apply_overrides_to_week(self._week(), self.OVERRIDES)[0]
            .items[0]
            .description
        )
        from_selection = db.resolve_display_text("CHEESE PIZZA", self.OVERRIDES)
        assert from_week == from_selection == "Cheese Pizza (Veggie)"

    def test_admin_path_matches_the_selection_path(self):
        items = [{"description": "CHEESE PIZZA", "menu_date": "2026-08-12"}]
        from_admin = menu_service.apply_overrides_to_items(items, self.OVERRIDES)[0][
            "display_description"
        ]
        from_selection = db.resolve_display_text("CHEESE PIZZA", self.OVERRIDES)
        assert from_admin == from_selection == "Cheese Pizza (Veggie)"


class TestCasingSeam:
    def test_mixed_case_text_never_reaches_the_casing_adapter(self):
        casing = RecordingCasing()
        assert MenuItemDisplay({}, casing=casing, cache={}).cased("Hot Dog") == "Hot Dog"
        assert casing.asked == []

    def test_items_of_only_short_words_never_reach_the_casing_adapter(self):
        casing = RecordingCasing()
        assert MenuItemDisplay({}, casing=casing, cache={}).cased("PB & J") == "PB & J"
        assert casing.asked == []

    def test_any_all_caps_word_of_three_letters_triggers_a_consultation(self):
        """Pins the heuristic's real reach: it fires for almost every item.

        The source is entirely ALL CAPS, so the "three consecutive uppercase
        letters" rule matches any item containing a three-letter word. Carried
        over unchanged from the previous implementation.
        """
        casing = RecordingCasing()
        MenuItemDisplay({}, casing=casing, cache={}).cased("HOT DOG")
        assert casing.asked == ["HOT DOG"]

    def test_complex_items_are_put_to_the_casing_adapter(self):
        casing = RecordingCasing({"CHIKN, RICE & BEANS": "Chikn, Rice & Beans"})
        display = MenuItemDisplay({}, casing=casing, cache={})
        assert display.cased("CHIKN, RICE & BEANS") == "Chikn, Rice & Beans"
        assert casing.asked == ["CHIKN, RICE & BEANS"]

    def test_a_silent_adapter_falls_back_to_the_simple_rules(self):
        display = MenuItemDisplay({}, casing=NoCasing(), cache={})
        assert display.cased("MAC & CHEESE, ROLL") == "Mac & Cheese, Roll"

    def test_the_adapter_is_consulted_once_per_item(self):
        casing = RecordingCasing({"CHIKN, RICE & BEANS": "Chikn, Rice & Beans"})
        display = MenuItemDisplay({}, casing=casing, cache={})
        display.cased("CHIKN, RICE & BEANS")
        display.cased("CHIKN, RICE & BEANS")
        assert casing.asked == ["CHIKN, RICE & BEANS"]

    def test_bulk_recasing_asks_for_every_item_not_just_complex_ones(self):
        casing = RecordingCasing()
        MenuItemDisplay({}, casing=casing).suggest_casing("HOT DOG")
        assert casing.asked == ["HOT DOG"]
