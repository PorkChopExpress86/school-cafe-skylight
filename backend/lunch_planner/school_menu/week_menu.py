"""Read a cached, Display Text-resolved Week Menu."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from lunch_planner.menu_catalog import persistence as db
from lunch_planner.menu_catalog.display import MenuItemDisplay
from lunch_planner.school_menu.school_cafe_adapter import DayMenu, MenuItem, SchoolCafeConfig, get_week_dates
from lunch_planner.school_menu.source import SchoolCafeMenuSource, SchoolMenuSource

_CACHE_TTL_SECONDS = 15 * 60
_CACHE_MAX_ENTRIES = 16


@dataclass(frozen=True)
class WeekMenuRead:
    """One Week Menu plus its School Menu Source availability."""

    days: list[DayMenu] | None
    source_config: SchoolCafeConfig | None
    error: str | None = None


class WeekMenu:
    """Keep School Menu Source access, caching, and Display Text behind one interface."""

    def __init__(
        self,
        source: SchoolMenuSource,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source = source
        self._clock = clock
        self._cache: dict[tuple[SchoolCafeConfig, str], tuple[float, list[DayMenu]]] = {}

    def read(self, reference: date, db_path: Path | None = None) -> WeekMenuRead:
        """Return one cached Week Menu with current Display Overrides applied."""
        try:
            config = self._source.config()
        except Exception as exc:  # noqa: BLE001
            return WeekMenuRead(None, None, f"{type(exc).__name__}: {exc}")
        if config is None:
            return WeekMenuRead(None, None, "SCHOOL_ID not set in .env")

        monday = get_week_dates(reference)[0]
        source_week = self._cached_week(config, monday)
        if source_week is None:
            try:
                source_week = self._source.fetch_week(config, reference)
            except Exception as exc:  # noqa: BLE001
                return WeekMenuRead(None, config, f"{type(exc).__name__}: {exc}")
            self._store_week(config, monday, source_week)

        overrides = db.fetch_all_overrides(db_path)
        return WeekMenuRead(_display_week(source_week, overrides), config)

    def _cached_week(self, config: SchoolCafeConfig, monday: date) -> list[DayMenu] | None:
        key = (config, monday.isoformat())
        entry = self._cache.get(key)
        if entry is None:
            return None
        deadline, week = entry
        if self._clock() >= deadline:
            self._cache.pop(key, None)
            return None
        return week

    def _store_week(self, config: SchoolCafeConfig, monday: date, week: list[DayMenu]) -> None:
        if len(self._cache) >= _CACHE_MAX_ENTRIES:
            oldest = min(self._cache, key=lambda key: self._cache[key][0])
            self._cache.pop(oldest, None)
        self._cache[(config, monday.isoformat())] = (self._clock() + _CACHE_TTL_SECONDS, week)


def _display_week(week: list[DayMenu], overrides: dict[str, str]) -> list[DayMenu]:
    display = MenuItemDisplay(overrides)
    return [
        DayMenu(
            date=day.date,
            items=[
                MenuItem(description=display.display(item.description), category=item.category) for item in day.items
            ],
        )
        for day in week
    ]


_default_week_menu = WeekMenu(SchoolCafeMenuSource())


def read_week_menu(reference: date, db_path: Path | None = None) -> WeekMenuRead:
    """Read through the process-wide Week Menu cache."""
    return _default_week_menu.read(reference, db_path)
