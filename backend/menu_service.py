"""Menu service module: encapsulates fetching, caching, and override logic for school menus."""

from __future__ import annotations

import os
import time
from datetime import date as date_cls
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from db import fetch_all_overrides
from school_menu import DayMenu, MenuItem, SchoolCafeConfig, get_week_dates, get_weekly_items

APP_DIR = Path(__file__).resolve().parent

MENU_CACHE_TTL_SECONDS = 15 * 60
MENU_CACHE_MAX_ENTRIES = 16

# {(config, monday_iso): (monotonic_deadline, week)}
_week_cache: dict[tuple[SchoolCafeConfig, str], tuple[float, list]] = {}
_env_loaded = False


def _load_env() -> None:
    global _env_loaded
    if not _env_loaded:
        load_dotenv(APP_DIR / ".env")
        _env_loaded = True


def school_config() -> SchoolCafeConfig | None:
    """Return SchoolCafeConfig loaded from .env, or None if SCHOOL_ID is empty."""
    _load_env()
    school_id = os.environ.get("SCHOOL_ID", "").strip()
    if not school_id:
        return None
    return SchoolCafeConfig(
        school_id=school_id,
        serving_line=os.environ.get("SCHOOL_SERVING_LINE", "TD Lunch Elementary").strip()
        or "TD Lunch Elementary",
        meal_type=os.environ.get("SCHOOL_MEAL_TYPE", "Lunch").strip() or "Lunch",
        grade=os.environ.get("SCHOOL_GRADE", "02").strip() or "02",
    )


def _cached_week(cfg: SchoolCafeConfig, monday: date_cls) -> list | None:
    entry = _week_cache.get((cfg, monday.isoformat()))
    if entry is None:
        return None
    deadline, week = entry
    if time.monotonic() >= deadline:
        _week_cache.pop((cfg, monday.isoformat()), None)
        return None
    return week


def _store_week(cfg: SchoolCafeConfig, monday: date_cls, week: list) -> None:
    if len(_week_cache) >= MENU_CACHE_MAX_ENTRIES:
        oldest = min(_week_cache, key=lambda k: _week_cache[k][0])
        _week_cache.pop(oldest, None)
    _week_cache[(cfg, monday.isoformat())] = (
        time.monotonic() + MENU_CACHE_TTL_SECONDS,
        week,
    )


def apply_overrides_to_items(
    items: list[dict], overrides: dict[str, str]
) -> list[dict]:
    """Return a copy of `items` with display_description overridden where set."""
    out: list[dict] = []
    for item in items:
        row = dict(item)
        row["display_description"] = overrides.get(
            row["description"], row["description"]
        )
        out.append(row)
    return out


def apply_overrides_to_week(
    week: list[Any], overrides: dict[str, str] | None = None, db_path: Path | None = None
) -> list[Any]:
    """Return a copy of a fetched week (list of DayMenu) with display overrides applied."""
    if overrides is None:
        overrides = fetch_all_overrides(db_path)
    if not overrides:
        return week

    out: list[Any] = []
    for day in week:
        new_items = [
            MenuItem(
                description=overrides.get(i.description, i.description) or i.description,
                category=i.category,
            )
            for i in day.items
        ]
        out.append(DayMenu(date=day.date, items=new_items))
    return out


def fetch_week(
    ref: date_cls, db_path: Path | None = None
) -> tuple[list | None, str | None]:
    """Fetch one week of school menu items (Mon-Fri) with caching and user display overrides."""
    cfg = school_config()
    if cfg is None:
        return None, "SCHOOL_ID not set in .env"
    monday = get_week_dates(ref)[0]
    cached = _cached_week(cfg, monday)
    if cached is not None:
        return apply_overrides_to_week(cached, None, db_path), None
    try:
        week = get_weekly_items(cfg, ref)
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"

    week = apply_overrides_to_week(week, None, db_path)
    _store_week(cfg, monday, week)
    return week, None


def entrees_for_date(
    menu_date: str, parsed_date: date_cls, db_path: Path | None = None
) -> list[str]:
    """Return entree descriptions for one day, or [] if fetching fails."""
    week, _ = fetch_week(parsed_date, db_path)
    if not week:
        return []
    for day in week:
        if day.date.isoformat() == menu_date:
            return [e.description for e in day.entrees]
    return []


def recase_all_items_with_llm(db_path: Path | None = None) -> dict:
    """Run all unique menu items through agy (gemini-3.6-flash-low) and set permanent display overrides."""
    from db import fetch_unique_menu_items, set_menu_override
    from school_menu import _query_llm_for_case

    unique_items = fetch_unique_menu_items(db_path)
    updated = 0
    for item in unique_items:
        orig = item["description"]
        cased = _query_llm_for_case(orig)
        if cased and cased != orig:
            set_menu_override(orig, cased, db_path)
            updated += 1

    return {
        "ok": True,
        "count": len(unique_items),
        "updated": updated,
        "message": f"Processed {len(unique_items)} unique items with Gemini 3.6 Flash. Updated {updated} display overrides.",
    }
