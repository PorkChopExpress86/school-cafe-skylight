"""Planner domain values shared by Planner workflows and schema initialization."""

from __future__ import annotations

from dataclasses import dataclass

MAKE_AT_HOME = "__MAKE_AT_HOME__"
HISTORY_RETENTION = 500


@dataclass(frozen=True)
class DefaultKid:
    """One Kid seeded when the family database is initialized."""

    name: str
    color: str
    prefix: str


DEFAULT_KIDS = (
    DefaultKid("Parker", "#3B82F6", "P-"),
    DefaultKid("Kylee", "#EC4899", "K-"),
)


def derive_kid_prefix(kid_name: str) -> str:
    """Return the fallback publication prefix for one Kid name."""
    initial = next((character for character in kid_name.strip().upper() if character.isalnum()), "")
    return f"{initial}-" if initial else "?-"


def unique_kid_prefix(base: str, taken: set[str]) -> str:
    """Return a case-insensitively unique Kid prefix derived from ``base``."""
    if base.lower() not in taken:
        return base
    stem = base.rstrip("-")
    for number in range(2, 100):
        candidate = f"{stem}{number}-"
        if candidate.lower() not in taken:
            return candidate
    return base
