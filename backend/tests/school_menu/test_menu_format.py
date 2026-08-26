"""Tests for the casing pass of the Menu Item Display module."""

from __future__ import annotations

import pytest

from lunch_planner.menu_catalog.display import cased_menu_item
from lunch_planner.school_menu.school_cafe_adapter import format_day


class TestTitleCaseFormatting:
    """SchoolCafe returns everything in ALL CAPS. The casing pass normalizes
    this to Title Case while preserving acronyms."""

    def test_empty_string_passes_through(self):
        assert cased_menu_item("") == ""

    def test_already_proper_case_passes_through(self):
        # Idempotent: don't reformat mixed-case text.
        assert cased_menu_item("Cheese Pizza") == "Cheese Pizza"

    def test_simple_all_caps_to_title_case(self):
        assert cased_menu_item("CHEESE PIZZA") == "Cheese Pizza"

    def test_preserves_bbq_acronym(self):
        """The user-specified exception: BBQ stays uppercase."""
        assert cased_menu_item("BRISKET BBQ SANDWICH") == "Brisket BBQ Sandwich"

    def test_preserves_pb_acronym(self):
        assert cased_menu_item("PB AND J SANDWICH") == "PB And J Sandwich"

    def test_preserves_ampersand(self):
        assert cased_menu_item("ROTINI & MEATBALLS") == "Rotini & Meatballs"

    def test_preserves_commas_and_punctuation(self):
        assert cased_menu_item(
            "SUNBUTTER & JELLY CRUSTLESS SANDWICH, CRACKERS, & STRING CHEESE"
        ) == "Sunbutter & Jelly Crustless Sandwich, Crackers, & String Cheese"

    def test_caches_repeated_calls(self):
        # First call populates the cache; subsequent calls return the same value.
        first = cased_menu_item("CHEESE PIZZA")
        second = cased_menu_item("CHEESE PIZZA")
        assert first == second == "Cheese Pizza"

    def test_mixed_case_passes_through_unchanged(self):
        # Not all-caps -> not reformatted, even if Title Case would change it.
        assert cased_menu_item("Cheese pizza") == "Cheese pizza"

    @pytest.mark.parametrize(
        "source,expected",
        [
            ("HOT DOG", "Hot Dog"),
            ("STEAK FINGERS", "Steak Fingers"),
            ("PEPPERONI PIZZA", "Pepperoni Pizza"),
            ("HOMESTYLE BONELESS WINGS", "Homestyle Boneless Wings"),
            ("YOGURT BOX ENTREE", "Yogurt Box Entree"),
        ],
    )
    def test_common_items(self, source, expected):
        assert cased_menu_item(source) == expected


class TestCommandLineFormatting:
    def test_preserves_display_text_acronyms(self):
        entries = [{"MenuItemDescription": "PB & J", "Category": "LUNCH ENTREE"}]

        assert format_day(entries) == "  - PB & J"
