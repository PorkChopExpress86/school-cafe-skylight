"""Value types shared across the School Menu feature."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class SchoolCafeConfig:
    school_id: str
    serving_line: str = "TD Lunch Elementary"
    meal_type: str = "Lunch"
    grade: str = "02"


@dataclass(frozen=True)
class MenuItem:
    """One School Menu item and its source category."""

    description: str
    category: str = ""


@dataclass(frozen=True)
class DayMenu:
    """One day of School Menu items."""

    date: date
    items: list[MenuItem]

    @property
    def weekday(self) -> str:
        return self.date.strftime("%A")

    @property
    def entrees(self) -> list[MenuItem]:
        return [item for item in self.items if "ENTREE" in item.category.upper()]


def get_week_dates(reference: date) -> list[date]:
    monday = reference - timedelta(days=reference.weekday())
    return [monday + timedelta(days=offset) for offset in range(5)]
