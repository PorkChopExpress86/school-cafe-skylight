"""Skylight service module: handles authentication config, recipe matching, and sitting date filtering."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from pyskylight import SkylightClient

APP_DIR = os.path.dirname(os.path.abspath(__file__))
_env_loaded = False


def _load_env() -> None:
    global _env_loaded
    if not _env_loaded:
        load_dotenv(os.path.join(APP_DIR, ".env"))
        _env_loaded = True


def skylight_config() -> dict[str, str]:
    """Load Skylight configuration dict from environment / .env."""
    _load_env()
    from skylight_menu import load_config as load_skylight_config

    return load_skylight_config()


def _skylight_login() -> SkylightClient:
    cfg = skylight_config()
    if not cfg["email"] or not cfg["password"]:
        raise RuntimeError("SKYLIGHT_EMAIL and SKYLIGHT_PASSWORD must be set in .env")
    return SkylightClient.login(cfg["email"], cfg["password"], base_url=cfg["base_url"])


def _resolve_lunch_category_id(client: SkylightClient, frame_id: str) -> str | None:
    for c in client.list_meal_categories(frame_id):
        if (getattr(c, "label", "") or "").lower() == "lunch":
            return str(c.id)
    return None


def _recipe_summary(prefix: str, item_text: str) -> str:
    """Skylight recipe title for one kid's meal, e.g. 'P- Cheese Pizza'."""
    return f"{prefix} {item_text}"


def _sitting_matches_kid_prefixes(
    sitting: Any, recipes_by_id: dict[str, Any], prefixes: set[str], kid_names: set[str]
) -> bool:
    """True if `sitting` belongs to one of our kids and should be wiped before a send."""
    recipe_id = str(getattr(sitting, "meal_recipe_id", ""))
    recipe = recipes_by_id.get(recipe_id)
    if recipe:
        summary = (getattr(recipe, "summary", "") or "").strip().lower()
        if any(summary.startswith(p) for p in prefixes):
            return True
        if any(name.lower() in summary for name in kid_names):
            return True

    attrs = getattr(sitting, "attributes", None) or {}
    sitting_summary = (
        attrs.get("summary") or getattr(sitting, "summary", "") or ""
    ).strip().lower()
    sitting_note = (
        attrs.get("note") or getattr(sitting, "note", "") or ""
    ).strip().lower()
    for name in kid_names:
        nl = name.lower()
        if nl in sitting_summary or nl in sitting_note:
            return True
    return False


def _sitting_falls_on_date(sitting: Any, menu_date: str) -> bool:
    """True if `sitting` is scheduled for `menu_date`."""
    dates_prop = getattr(sitting, "dates", None)
    if dates_prop:
        return menu_date in list(dates_prop)
    instances = getattr(sitting, "instances", None)
    if instances:
        return menu_date in list(instances)
    return True
