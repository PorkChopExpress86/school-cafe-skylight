"""Behavior tests for the SchoolCafe inspection command-line adapter."""

from __future__ import annotations

from tools import school_menu_inspect


def test_main_prints_the_formatted_week_from_the_school_menu_source(monkeypatch, capsys) -> None:
    menu = {
        "8/24/2026": [
            {"MenuItemDescription": "CHEESE PIZZA", "Category": "LUNCH ENTREE"},
        ]
    }
    monkeypatch.setattr(school_menu_inspect, "fetch_weekly_menu", lambda _config, _date: menu)

    result = school_menu_inspect.main(["--school-id", "school-1", "--date", "2026-08-24"])

    captured = capsys.readouterr()
    assert result == 0
    assert "Week of Aug 24 - Aug 28, 2026" in captured.out
    assert "  - Cheese Pizza" in captured.out
