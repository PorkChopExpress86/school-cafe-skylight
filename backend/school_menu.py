#!/usr/bin/env python3
"""Download the weekly school menu from the SchoolCafé API.

Usage:
    python school_menu.py --school-id 12345
    python school_menu.py --school-id 12345 --meal-type Breakfast
    python school_menu.py --school-id 12345 --date 2026-04-26 --save menu.json

The script uses no third-party packages and writes a formatted weekly menu
(Mon-Fri) to stdout. With --save it also writes the raw JSON payload.

Display casing is not this module's job: descriptions are handed to the Menu
Item Display module on the way out.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from menu_item_display import cased_menu_item

BASE_URL = (
    "https://webapis.schoolcafe.com/api/CalendarView/GetWeeklyMenuitemsByGrade"
)


@dataclass(frozen=True)
class SchoolCafeConfig:
    school_id: str
    serving_line: str = "TD Lunch Elementary"
    meal_type: str = "Lunch"
    grade: str = "02"


def build_url(config: SchoolCafeConfig, target_date: date) -> str:
    # SchoolCafé expects MM/DD/YYYY for date params on this endpoint.
    return (
        f"{BASE_URL}"
        f"?SchoolId={config.school_id}"
        f"&ServingDate={target_date.strftime('%m/%d/%Y')}"
        f"&ServingLine={urllib.parse.quote(config.serving_line)}"
        f"&MealType={config.meal_type}"
        f"&Grade={config.grade}"
        f"&PersonId=null"
    )


def fetch_weekly_menu(config: SchoolCafeConfig, target_date: date) -> dict[str, Any]:
    url = build_url(config, target_date)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = resp.read().decode("utf-8")
    return json.loads(payload)


def date_key(d: date) -> str:
    return f"{d.month}/{d.day}/{d.year}"


def get_week_dates(reference: date) -> list[date]:
    monday = reference - timedelta(days=reference.weekday())
    return [monday + timedelta(days=i) for i in range(5)]


@dataclass(frozen=True)
class MenuItem:
    """One menu item with its category (e.g. 'LUNCH ENTREE', 'FRUIT')."""

    description: str
    category: str = ""


@dataclass(frozen=True)
class DayMenu:
    """One day of menu items, normalized for easy UI consumption."""

    date: date
    items: list[MenuItem]

    @property
    def weekday(self) -> str:
        return self.date.strftime("%A")

    @property
    def entrees(self) -> list[MenuItem]:
        """Only items in the LUNCH ENTREE / BREAKFAST ENTREE category."""
        return [i for i in self.items if "ENTREE" in i.category.upper()]


def extract_items(entries: Any) -> list[MenuItem]:
    """Flatten both API response shapes (list or sectioned dict) into a list of items.

    Preserves the category when the response is a sectioned dict (keyed by
    category name like 'LUNCH ENTREE', 'FRUIT', 'MILK', etc.). Skips the
    API's "menu not published" placeholder strings.

    All-caps descriptions are normalized to Title Case via the Menu Item
    Display module so downstream code sees consistent casing.
    """
    out: list[MenuItem] = []
    if isinstance(entries, list):
        for item in entries:
            if isinstance(item, dict):
                desc = str(item.get("MenuItemDescription", "")).strip()
                cat = str(item.get("Category", "")).strip()
                if desc and "not been published" not in desc.lower():
                    out.append(MenuItem(description=cased_menu_item(desc), category=cat))
    elif isinstance(entries, dict):
        for section, section_items in entries.items():
            if not isinstance(section_items, list):
                continue
            for item in section_items:
                if isinstance(item, dict):
                    desc = str(item.get("MenuItemDescription", "")).strip()
                    if desc and "not been published" not in desc.lower():
                        out.append(MenuItem(description=cased_menu_item(desc), category=section))
    return out


def get_weekly_items(config: SchoolCafeConfig, reference: date) -> list[DayMenu]:
    """Fetch the SchoolCafé week containing `reference` and return a list of DayMenu.

    This always hits the network. The School Menu Source adapter exposes it to
    the Week Menu and Menu Catalog Refresh modules, which own their respective
    caching, Display Text, and persistence behavior.

    Each DayMenu has a `date` and an `items` list. Days with no published menu
    still appear in the result with an empty `items` list, so callers can render
    a consistent Mon-Fri view.

    The API returns keys starting at the ServingDate, so we always pass the
    Monday of the target week as ServingDate to align the response keys with
    the Mon-Fri lookup below.
    """
    week_dates = get_week_dates(reference)
    payload = fetch_weekly_menu(config, week_dates[0])
    return [
        DayMenu(date=d, items=extract_items(payload.get(date_key(d))))
        for d in week_dates
    ]


def format_day(entries: Any) -> str | None:
    items = extract_items(entries)
    if not items:
        return None
    return "\n".join(f"  - {item.description}" for item in items)


def print_menu(
    menu: dict[str, Any],
    reference: date,
    school_id: str,
    serving_line: str,
    meal_type: str,
) -> None:
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    week_dates = get_week_dates(reference)
    monday = week_dates[0]
    friday = week_dates[-1]

    header = f"Week of {monday.strftime('%b %d')} - {friday.strftime('%b %d, %Y')}"
    print(header)
    print(f"School ID: {school_id} | Serving Line: {serving_line} | Meal: {meal_type}")
    print("=" * len(header))

    for day_name, day_date in zip(days, week_dates):
        key = date_key(day_date)
        entries = menu.get(key)
        print(f"\n{day_name} ({day_date.strftime('%a %b %d')}):")
        formatted = format_day(entries)
        if formatted is None:
            print("  (no menu posted)")
        else:
            print(formatted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download the weekly school menu from SchoolCafé.",
    )
    parser.add_argument("--school-id", required=True, help="SchoolCafé school ID")
    parser.add_argument(
        "--serving-line",
        default="TD Lunch Elementary",
        help="Serving line identifier (default: 'TD Lunch Elementary' for CFISD elementary)",
    )
    parser.add_argument(
        "--meal-type",
        default="Lunch",
        help="Meal type, e.g. Lunch or Breakfast (default: Lunch)",
    )
    parser.add_argument(
        "--grade",
        default="02",
        help="Grade code (default: '02'). CFISD uses PK, KG, 01-05.",
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Any date within the target week, YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--save",
        metavar="FILE",
        help="Also save the raw JSON response to this file",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON instead of the formatted weekly view",
    )
    args = parser.parse_args(argv)

    try:
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        print(f"Invalid date: {args.date}. Use YYYY-MM-DD.", file=sys.stderr)
        return 2

    config = SchoolCafeConfig(
        school_id=args.school_id,
        serving_line=args.serving_line,
        meal_type=args.meal_type,
        grade=args.grade,
    )

    try:
        menu = fetch_weekly_menu(config, target)
    except urllib.error.HTTPError as e:
        print(f"HTTP error: {e.code} {e.reason}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Invalid JSON response: {e}", file=sys.stderr)
        return 1

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(menu, f, indent=2)
            f.write("\n")
        print(f"Saved raw JSON to {args.save}", file=sys.stderr)

    if args.json:
        print(json.dumps(menu, indent=2))
    else:
        print_menu(menu, target, args.school_id, args.serving_line, args.meal_type)

    return 0


if __name__ == "__main__":
    sys.exit(main())
