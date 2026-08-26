"""School Menu Source seam and SchoolCafe production adapter."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

from lunch_planner.school_menu.models import DayMenu, SchoolCafeConfig
from lunch_planner.school_menu.school_cafe_adapter import get_weekly_items

BACKEND_DIR = Path(__file__).resolve().parents[2]
_env_loaded = False


class SchoolMenuSource(Protocol):
    """External seam shared by Week Menu and Menu Catalog Refresh."""

    def config(self) -> SchoolCafeConfig | None: ...

    def fetch_week(self, config: SchoolCafeConfig, reference: date) -> list[DayMenu]: ...


class SchoolCafeMenuSource:
    """Environment-backed SchoolCafe adapter."""

    def __init__(
        self,
        *,
        config_loader: Callable[[], SchoolCafeConfig | None] | None = None,
        fetch_week: Callable[[SchoolCafeConfig, date], list[DayMenu]] = get_weekly_items,
    ) -> None:
        self._config_loader = config_loader or load_school_menu_config
        self._fetch_week = fetch_week

    def config(self) -> SchoolCafeConfig | None:
        return self._config_loader()

    def fetch_week(self, config: SchoolCafeConfig, reference: date) -> list[DayMenu]:
        return self._fetch_week(config, reference)


def load_school_menu_config() -> SchoolCafeConfig | None:
    """Return SchoolCafe configuration from the local environment, if enabled."""
    global _env_loaded
    if not _env_loaded:
        load_dotenv(BACKEND_DIR / ".env")
        _env_loaded = True

    school_id = os.environ.get("SCHOOL_ID", "").strip()
    if not school_id:
        return None
    return SchoolCafeConfig(
        school_id=school_id,
        serving_line=os.environ.get("SCHOOL_SERVING_LINE", "TD Lunch Elementary").strip() or "TD Lunch Elementary",
        meal_type=os.environ.get("SCHOOL_MEAL_TYPE", "Lunch").strip() or "Lunch",
        grade=os.environ.get("SCHOOL_GRADE", "02").strip() or "02",
    )
