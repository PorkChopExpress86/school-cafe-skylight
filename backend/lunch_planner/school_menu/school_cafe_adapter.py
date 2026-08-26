"""SchoolCafe HTTP retrieval and response parsing."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

from lunch_planner.school_menu.models import DayMenu, MenuItem, SchoolCafeConfig, get_week_dates

BASE_URL = "https://webapis.schoolcafe.com/api/CalendarView/GetWeeklyMenuitemsByGrade"


def build_url(config: SchoolCafeConfig, target_date: date) -> str:
    """Build the SchoolCafe weekly-menu URL for one Monday-aligned request."""
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
    """Retrieve the raw SchoolCafe weekly payload."""
    url = build_url(config, target_date)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def date_key(value: date) -> str:
    """Return the SchoolCafe date-key format for a school date."""
    return f"{value.month}/{value.day}/{value.year}"


def extract_items(entries: Any) -> list[MenuItem]:
    """Flatten either supported SchoolCafe response shape into source Menu items."""
    items: list[MenuItem] = []
    if isinstance(entries, list):
        for item in entries:
            if isinstance(item, dict):
                description = str(item.get("MenuItemDescription", "")).strip()
                category = str(item.get("Category", "")).strip()
                if description and "not been published" not in description.lower():
                    items.append(MenuItem(description=description, category=category))
    elif isinstance(entries, dict):
        for category, section_items in entries.items():
            if not isinstance(section_items, list):
                continue
            for item in section_items:
                if isinstance(item, dict):
                    description = str(item.get("MenuItemDescription", "")).strip()
                    if description and "not been published" not in description.lower():
                        items.append(MenuItem(description=description, category=category))
    return items


def get_weekly_items(config: SchoolCafeConfig, reference: date) -> list[DayMenu]:
    """Retrieve and parse the Monday-through-Friday SchoolCafe week containing `reference`."""
    week_dates = get_week_dates(reference)
    payload = fetch_weekly_menu(config, week_dates[0])
    return [DayMenu(date=value, items=extract_items(payload.get(date_key(value)))) for value in week_dates]
