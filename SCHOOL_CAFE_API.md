# SchoolCafé API Integration Guide

This document outlines how to interact with the SchoolCafé Weekly Menu API to fetch school lunch and breakfast menus. It details the endpoint parameters, request headers, JSON response schemas, key formatting quirks, error handling, and reusable code examples.

---

## 1. Overview & Base Endpoint

SchoolCafé exposes a RESTful web API for retrieving weekly menu items for a specific school, serving line, and meal type.

- **Base Endpoint:** `https://webapis.schoolcafe.com/api/CalendarView/GetWeeklyMenuitems`
- **HTTP Method:** `GET`
- **Response Format:** JSON

---

## 2. HTTP Request Specification

### Query Parameters

| Parameter | Type | Required | Description | Example |
| :--- | :--- | :--- | :--- | :--- |
| `SchoolId` | `string` / `int` | **Yes** | Unique identifier for the school within SchoolCafé. | `12345` |
| `ServingDate` | `string` | **Yes** | Any date in `YYYY-MM-DD` format within the desired target week. The API returns the full week containing this date. | `2026-04-26` |
| `ServingLine` | `string` / `int` | **Yes** | Identifier for the serving line (e.g., Main Line, Express, Line 1). | `1` |
| `MealType` | `string` / `int` | **Yes** | Meal type identifier (e.g., Lunch, Breakfast). | `Lunch` or `1` |

### Headers

| Header | Value | Description |
| :--- | :--- | :--- |
| `Accept` | `application/json` | Requests JSON response payload. |

---

## 3. Response Schema & Structure

### Date Key Formatting (CRITICAL QUIRK)

The root level of the JSON response is a dictionary keyed by date string.

> [!IMPORTANT]
> While the request parameter `ServingDate` uses ISO format (`YYYY-MM-DD`), the **keys in the returned JSON object use unpadded month and day strings** formatted as `M/D/YYYY` (e.g., `"4/26/2026"` for April 26, 2026, or `"10/5/2026"` for October 5, 2026).

When looking up a target date in Python, construct the key using integer attributes:
```python
key = f"{target_date.month}/{target_date.day}/{target_date.year}"
```

### Response Formats

Depending on the school district's menu configuration, the date key entry will take one of two structural shapes:

#### Shape 1: Flat Array of Items
Used when all menu items for the day are listed under a single flat list.

```json
{
  "4/26/2026": [
    {
      "MenuItemDescription": "CHICKEN NUGGETS"
    },
    {
      "MenuItemDescription": "MASHED POTATOES"
    }
  ]
}
```

#### Shape 2: Sectioned Categories Object
Used when items are categorized into sections (e.g., Entrees, Sides).

```json
{
  "4/27/2026": {
    "Featured Entrees": [
      { "MenuItemDescription": "CHICKEN SANDWICH" },
      { "MenuItemDescription": "TOMATO SOUP" }
    ],
    "Sides": [
      { "MenuItemDescription": "BABY CARROTS" }
    ]
  }
}
```

---

## 4. Key Fields

- **`MenuItemDescription`** (`string`): The description or name of the menu item, typically provided by the API in all uppercase (e.g., `"CHICKEN NUGGETS"`).

---

## 5. Quick Start (cURL)

To test the endpoint directly from the command line:

```bash
curl -s "https://webapis.schoolcafe.com/api/CalendarView/GetWeeklyMenuitems?SchoolId=YOUR_SCHOOL_ID&ServingDate=$(date +%Y-%m-%d)&ServingLine=1&MealType=Lunch" \
  -H "Accept: application/json"
```

---

## 6. Reusable Python Implementation

Below is a self-contained, fully typed Python module implementing menu retrieval and formatting using `httpx`.

```python
"""SchoolCafé API Client and Menu Formatter.

Provides functionality for querying the SchoolCafé web API and formatting
daily menu responses into clean human-readable text.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
import httpx


@dataclass(frozen=True)
class SchoolCafeConfig:
    """Configuration parameters for querying SchoolCafé API."""

    school_id: str
    serving_line: str = "1"
    meal_type: str = "Lunch"


def build_schoolcafe_url(config: SchoolCafeConfig, target_date: date) -> str:
    """Build the request URL for the SchoolCafé weekly menu endpoint.

    Args:
        config: SchoolCafé configuration instance containing identifiers.
        target_date: Target date to fetch weekly menu for.

    Returns:
        Formatted endpoint URL with query parameters.
    """
    formatted_date = target_date.strftime("%Y-%m-%d")
    return (
        "https://webapis.schoolcafe.com/api/CalendarView/GetWeeklyMenuitems"
        f"?SchoolId={config.school_id}"
        f"&ServingDate={formatted_date}"
        f"&ServingLine={config.serving_line}"
        f"&MealType={config.meal_type}"
    )


def parse_menu_items(items: list[dict[str, Any]]) -> list[str]:
    """Extract and title-case item descriptions from a raw list of item dicts.

    Args:
        items: List of raw item dictionaries from API response.

    Returns:
        List of formatted bullet-point strings.
    """
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_description = str(item.get("MenuItemDescription", "")).strip()
        if raw_description:
            title_description = raw_description.lower().title()
            lines.append(f"- {title_description}")
    return lines


def format_schoolcafe_menu(menu_json: dict[str, Any], target_date: date) -> str | None:
    """Extract and format the menu for a target date from API JSON payload.

    Handles both flat item lists and sectioned category dictionaries.

    Args:
        menu_json: JSON response dictionary from SchoolCafé API.
        target_date: Date to extract from the weekly menu payload.

    Returns:
        Formatted menu string or None if menu is absent/unpublished.
    """
    # Key format in response is M/D/YYYY (unpadded month/day)
    date_key = f"{target_date.month}/{target_date.day}/{target_date.year}"

    if date_key not in menu_json:
        return None

    entries = menu_json[date_key]
    if not entries:
        return None

    lines: list[str] = []

    if isinstance(entries, list):
        lines.extend(parse_menu_items(entries))
    elif isinstance(entries, dict):
        for section_name, section_items in entries.items():
            if not isinstance(section_items, list):
                continue
            item_lines = parse_menu_items(section_items)
            if not item_lines:
                continue
            section_title = section_name.strip().lower().title()
            lines.append(f"**{section_title}**:")
            lines.extend(item_lines)
            lines.append("")
    else:
        return None

    content = "\n".join(lines).strip()
    if not content or "not published" in content.lower():
        return None

    return content


def fetch_schoolcafe_menu(config: SchoolCafeConfig, target_date: date) -> str | None:
    """Fetch and format the SchoolCafé menu for a specific target date.

    Args:
        config: SchoolCafé configuration instance.
        target_date: Date for which to retrieve the menu.

    Returns:
        Formatted menu text string, or None if unavailable.

    Raises:
        httpx.HTTPError: If network or HTTP request fails.
    """
    url = build_schoolcafe_url(config, target_date)
    headers = {"Accept": "application/json"}

    with httpx.Client(timeout=10.0) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        menu_json: dict[str, Any] = response.json()

    return format_schoolcafe_menu(menu_json, target_date)


if __name__ == "__main__":
    # Example usage:
    demo_config = SchoolCafeConfig(school_id="12345", serving_line="1", meal_type="Lunch")
    today = date.today()
    menu = fetch_schoolcafe_menu(demo_config, today)
    if menu:
        print(f"Menu for {today}:\n{menu}")
    else:
        print(f"No menu available for {today}.")
```

---

## 7. Common Edge Cases & Troubleshooting

1. **Unpublished Menus:**
   When a school has not posted the menu for a holiday or future period, the response might return `"Menu not published"` or omit the date key entirely. Always check `if date_key not in menu_json` and check for `"not published"` in text content.
2. **Invalid `SchoolId` or `ServingLine`:**
   Passing incorrect identifiers typically returns an empty dictionary `{}` HTTP 200 rather than a 404 error.
3. **Date Key Padding:**
   Never format the date key as `YYYY-MM-DD` or `MM/DD/YYYY` with leading zeros when parsing the response JSON; use `f"{date.month}/{date.day}/{date.year}"`.
