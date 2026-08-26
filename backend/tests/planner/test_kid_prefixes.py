"""Tests for Planner-owned Kid prefix defaults and derivation."""

from __future__ import annotations

import pytest

from lunch_planner.persistence.connection import get_db
from lunch_planner.persistence.schema import init_db
from lunch_planner.planner.models import derive_kid_prefix, unique_kid_prefix


def test_default_kids_get_their_documented_prefixes(tmp_path) -> None:
    db_path = tmp_path / "kid-prefixes.db"
    init_db(db_path)

    with get_db(db_path) as conn:
        rows = conn.execute("SELECT name, prefix FROM kids ORDER BY id").fetchall()

    assert {row["name"]: row["prefix"] for row in rows} == {"Parker": "P-", "Kylee": "K-"}


@pytest.mark.parametrize(
    "name,expected",
    [("Parker", "P-"), ("kylee", "K-"), ("  ada ", "A-"), ("", "?-"), ("   ", "?-"), ("!!", "?-")],
)
def test_derived_prefix_never_raises(name: str, expected: str) -> None:
    assert derive_kid_prefix(name) == expected


def test_prefixes_are_disambiguated() -> None:
    assert unique_kid_prefix("K-", set()) == "K-"
    assert unique_kid_prefix("K-", {"k-"}) == "K2-"
    assert unique_kid_prefix("K-", {"k-", "k2-"}) == "K3-"


def test_schema_initialization_backfills_distinct_prefixes(tmp_path) -> None:
    db_path = tmp_path / "kid-prefixes.db"
    init_db(db_path)
    with get_db(db_path) as conn:
        conn.execute("INSERT INTO kids (name, color, prefix) VALUES ('Kyle', '#000', '')")
        conn.commit()

    init_db(db_path)
    with get_db(db_path) as conn:
        prefixes = [row["prefix"] for row in conn.execute("SELECT prefix FROM kids").fetchall()]

    assert len(prefixes) == len(set(prefixes)), f"prefixes collided: {prefixes}"
