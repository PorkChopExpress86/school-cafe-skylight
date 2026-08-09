#!/usr/bin/env python3
"""Download the weekly school menu from the SchoolCafé API.

Usage:
    python school_menu.py --school-id 12345
    python school_menu.py --school-id 12345 --meal-type Breakfast
    python school_menu.py --school-id 12345 --date 2026-04-26 --save menu.json

The script is dependency-free (stdlib only) and writes a formatted weekly
menu (Mon-Fri) to stdout. With --save it also writes the raw JSON payload.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

BASE_URL = (
    "https://webapis.schoolcafe.com/api/CalendarView/GetWeeklyMenuitemsByGrade"
)

# Acronyms and abbreviations to preserve in title case.
# SchoolCafé returns everything in ALL CAPS, so these are the tokens that
# should stay uppercase when the rest of the item is normalized to Title Case.
ACRONYMS: frozenset[str] = frozenset({
    "BBQ",   # Barbeque
    "PB",    # Peanut Butter
    "PBJ",   # Peanut Butter & Jelly
    "OG",    # Orange
    "USDA",  # U.S. Department of Agriculture
})

# Words that have unusual capitalization in food-service nomenclature and
# should NOT be lower-cased by Title Case (e.g. "Mac" in "Mac & Cheese").
# Applied as a sanity pass after the simple title-case conversion.
_TITLE_CASE_EXCEPTIONS: dict[str, str] = {
    "mac": "Mac",   # Mac & Cheese
    "nugget": "Nugget",
    "chikn": "Chikn",
    "rotini": "Rotini",
    "pita": "Pita",
}

# Cache of all-caps source -> properly-cased display string.
# Avoids re-querying the LLM for the same item every time the menu loads.
_case_cache: dict[str, str] = {}


def _title_case_simple(text: str) -> str:
    """Convert ALL CAPS to Title Case, preserving acronyms and punctuation.

    Splits on whitespace, capitalizes each word unless it's a known acronym,
    then re-joins. Punctuation (commas, &, parentheses) is preserved as-is.
    """
    words = text.split()
    out: list[str] = []
    for word in words:
        # Strip punctuation for the acronym lookup, keep it for output.
        stripped = word.strip(".,;:!?'\"()[]/")
        if stripped.upper() in ACRONYMS:
            out.append(word.replace(stripped, stripped.upper()))
        else:
            # Lower-case then capitalize to handle things like "McDONALD'S"
            lower = word.lower()
            out.append(lower.capitalize())
    return " ".join(out)


def _apply_title_case_exceptions(text: str) -> str:
    """Apply per-word capitalization overrides for known food terms.

    Only touches words that appear as standalone tokens (not inside other
    words), so "Mac" overrides apply to "Mac & Cheese" but not to "Macaroni".
    """
    for word, replacement in _TITLE_CASE_EXCEPTIONS.items():
        text = re.sub(rf"(?<![A-Za-z]){word}(?![A-Za-z])", replacement, text, flags=re.IGNORECASE)
    return text


def _needs_llm_lookup(text: str) -> bool:
    """True if the item is complex enough to warrant an LLM consultation.

    Heuristic: items with commas (multi-part descriptions), semicolons,
    or unusual compound words (two or more consecutive multi-letter caps
    clusters) are sent to the LLM.
    """
    if "," in text or ";" in text:
        return True
    # Three or more consecutive uppercase letters inside the string
    # (not just leading caps) suggests a brand name or acronym mid-word.
    if re.search(r"[A-Z]{3,}", text[1:]):
        return True
    return False


def _query_llm_for_case(text: str) -> str | None:
    """Look up proper case formatting for a complex menu item via the LLM.

    Returns the LLM-suggested case, or None if the query fails / times out
    (caller should fall back to simple title case).

    This is a stub: wire to ollama-cloud/minimax-m3 when the model is
    available, or to a web-search-backed LLM call. The prompt asks for
    the canonical display capitalization of a food-service menu item.
    """
    # TODO: wire to minimax-m3 LLM endpoint. For now, return None and
    # let the caller fall back to simple title case.
    return None


def format_menu_item(text: str) -> str:
    """Convert an ALL CAPS menu item description to proper Title Case.

    The SchoolCafé API returns every menu item in ALL CAPS (e.g.
    "BRISKET BBQ SANDWICH"). Display, storage, and Skylight sync all
    expect Title Case ("Brisket BBQ Sandwich").

    Rules:
      - Already mixed-case text is returned as-is (idempotent).
      - ALL CAPS text is converted to Title Case.
      - Known acronyms (BBQ, PB, PBJ, OG, USDA) are preserved uppercase.
      - Known food terms (Mac, Rotini, etc.) get their canonical casing.
      - Complex items (commas, semicolons, unusual caps clusters) are
        sent to the LLM on first appearance; the result is cached.

    The cache is per-process and not persisted — the LLM is only consulted
    once per unique all-caps item per server lifetime.
    """
    if not text:
        return text
    if not text.isupper():
        return text

    if text in _case_cache:
        return _case_cache[text]

    result = _title_case_simple(text)
    result = _apply_title_case_exceptions(result)

    if _needs_llm_lookup(text):
        llm_result = _query_llm_for_case(text)
        if llm_result:
            result = llm_result

    _case_cache[text] = result
    return result


def _reset_case_cache() -> None:
    """Test helper: clear the case-formatting cache."""
    _case_cache.clear()


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

    All-caps descriptions are normalized to Title Case via format_menu_item
    so downstream code (UI, DB, Skylight sync) sees consistent casing.
    """
    out: list[MenuItem] = []
    if isinstance(entries, list):
        for item in entries:
            if isinstance(item, dict):
                desc = str(item.get("MenuItemDescription", "")).strip()
                cat = str(item.get("Category", "")).strip()
                if desc and "not been published" not in desc.lower():
                    out.append(MenuItem(description=format_menu_item(desc), category=cat))
    elif isinstance(entries, dict):
        for section, section_items in entries.items():
            if not isinstance(section_items, list):
                continue
            for item in section_items:
                if isinstance(item, dict):
                    desc = str(item.get("MenuItemDescription", "")).strip()
                    if desc and "not been published" not in desc.lower():
                        out.append(MenuItem(description=format_menu_item(desc), category=section))
    return out


def get_weekly_items(config: SchoolCafeConfig, reference: date) -> list[DayMenu]:
    """Fetch the SchoolCafé week containing `reference` and return a list of DayMenu.

    This always hits the network. Callers that need caching should do it
    themselves with a policy that suits them - `fastapi_app.fetch_week`
    keeps a short-lived, week-keyed cache so a menu correction shows up
    without restarting the server.

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
    return "\n".join(f"  - {item.description.lower().title()}" for item in items)


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
