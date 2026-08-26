"""Tests for Display Override storage behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from lunch_planner.persistence.database import clear_menu_override, fetch_all_overrides, set_menu_override


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


def test_set_and_fetch_override(db_path):
    set_menu_override("Cheese Pizza", "Cheese Pizza (Veggie)", db_path)
    assert fetch_all_overrides(db_path) == {"Cheese Pizza": "Cheese Pizza (Veggie)"}


def test_update_existing_override(db_path):
    set_menu_override("Hot Dog", "Hot Dog (Beef)", db_path)
    set_menu_override("Hot Dog", "Hot Dog (Turkey)", db_path)
    assert fetch_all_overrides(db_path) == {"Hot Dog": "Hot Dog (Turkey)"}


def test_clear_override(db_path):
    set_menu_override("Hot Dog", "Hot Dog (Beef)", db_path)
    clear_menu_override("Hot Dog", db_path)
    assert fetch_all_overrides(db_path) == {}


def test_empty_replacement_clears(db_path):
    set_menu_override("Hot Dog", "Hot Dog (Beef)", db_path)
    set_menu_override("Hot Dog", "   ", db_path)
    assert fetch_all_overrides(db_path) == {}


def test_overrides_persist_across_connections(db_path):
    set_menu_override("Cheese Pizza", "Cheese Pizza (Veggie)", db_path)
    assert fetch_all_overrides(db_path)["Cheese Pizza"] == "Cheese Pizza (Veggie)"
