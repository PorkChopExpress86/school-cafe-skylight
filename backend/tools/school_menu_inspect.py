#!/usr/bin/env python3
"""Command-line inspection and formatting for one SchoolCafe week."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
from datetime import date, datetime
from typing import Any

from lunch_planner.menu_catalog.display import cased_menu_item
from lunch_planner.school_menu.models import SchoolCafeConfig, get_week_dates
from lunch_planner.school_menu.school_cafe_adapter import date_key, extract_items, fetch_weekly_menu


def format_day(entries: Any) -> str | None:
    """Format one raw SchoolCafe day for command-line inspection."""
    items = extract_items(entries)
    if not items:
        return None
    return "\n".join(f"  - {cased_menu_item(item.description)}" for item in items)


def print_menu(menu: dict[str, Any], reference: date, config: SchoolCafeConfig) -> None:
    """Print one formatted Monday-through-Friday SchoolCafe week."""
    week_dates = get_week_dates(reference)
    monday = week_dates[0]
    friday = week_dates[-1]
    header = f"Week of {monday.strftime('%b %d')} - {friday.strftime('%b %d, %Y')}"
    print(header)
    print(f"School ID: {config.school_id} | Serving Line: {config.serving_line} | Meal: {config.meal_type}")
    print("=" * len(header))

    for day_name, day_date in zip(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], week_dates):
        print(f"\n{day_name} ({day_date.strftime('%a %b %d')}):")
        formatted = format_day(menu.get(date_key(day_date)))
        print(formatted if formatted is not None else "  (no menu posted)")


def main(argv: list[str] | None = None) -> int:
    """Fetch, optionally save, and render one SchoolCafe week for an operator."""
    parser = argparse.ArgumentParser(description="Download the weekly school menu from SchoolCafe.")
    parser.add_argument("--school-id", required=True, help="SchoolCafe school ID")
    parser.add_argument(
        "--serving-line",
        default="TD Lunch Elementary",
        help="Serving line identifier (default: 'TD Lunch Elementary' for CFISD elementary)",
    )
    parser.add_argument("--meal-type", default="Lunch", help="Meal type, e.g. Lunch or Breakfast (default: Lunch)")
    parser.add_argument("--grade", default="02", help="Grade code (default: '02'). CFISD uses PK, KG, 01-05.")
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Any date within the target week, YYYY-MM-DD (default: today)",
    )
    parser.add_argument("--save", metavar="FILE", help="Also save the raw JSON response to this file")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of the formatted weekly view")
    args = parser.parse_args(argv)

    try:
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        print(f"Invalid date: {args.date}. Use YYYY-MM-DD.", file=sys.stderr)
        return 2

    config = SchoolCafeConfig(args.school_id, args.serving_line, args.meal_type, args.grade)
    try:
        menu = fetch_weekly_menu(config, target)
    except urllib.error.HTTPError as exc:
        print(f"HTTP error: {exc.code} {exc.reason}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON response: {exc}", file=sys.stderr)
        return 1

    if args.save:
        with open(args.save, "w", encoding="utf-8") as file:
            json.dump(menu, file, indent=2)
            file.write("\n")
        print(f"Saved raw JSON to {args.save}", file=sys.stderr)

    if args.json:
        print(json.dumps(menu, indent=2))
    else:
        print_menu(menu, target, config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
