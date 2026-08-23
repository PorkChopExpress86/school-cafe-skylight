"""Shared fixtures for the offline test suite.

Every test here runs without network access and without touching the real
./app.db: the SchoolCafe menu fetch is stubbed and the Skylight client is
replaced with an in-memory fake, so the suite is safe to run at any time
and can't write to anyone's real calendar.
"""

from __future__ import annotations

import sys
from datetime import date as date_cls
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fastapi_app  # noqa: E402
import menu_item_display  # noqa: E402
from school_menu import DayMenu, MenuItem, get_week_dates  # noqa: E402
from skylight_adapter import SkylightCredentials  # noqa: E402


@pytest.fixture(autouse=True)
def offline_casing():
    """No test shells out to the casing adapter, and none shares a cache.

    Substituting NoCasing at the seam is what keeps the suite offline — the
    production code has no idea it is running under pytest.
    """
    previous = menu_item_display.default_casing()
    menu_item_display.set_default_casing(menu_item_display.NoCasing())
    menu_item_display.reset_cache()
    yield
    menu_item_display.set_default_casing(previous)
    menu_item_display.reset_cache()


# A Wednesday, so get_week_dates() yields a full Mon-Fri around it.
MENU_DATE = "2026-08-12"
ENTREES = ["Cheese Pizza", "Hot Dog"]


class FakeObj:
    """Stand-in for a pyskylight model object."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __repr__(self) -> str:
        return f"FakeObj({self.__dict__})"


class FakeSkylightClient:
    """In-memory replacement for pyskylight's SkylightClient.

    Records every delete so tests can assert on exactly what was removed,
    and can be told to fail specific recipe/sitting creations to exercise
    the partial-failure paths.
    """

    def __init__(self):
        self.categories = [
            FakeObj(id="cat-lunch", label="Lunch"),
            FakeObj(id="cat-dinner", label="Dinner"),
        ]
        self.recipes: list[FakeObj] = []
        self.sittings: list[FakeObj] = []
        self.deleted_ids: list[str] = []
        self.fail_create_recipe_for: set[str] = set()
        self.fail_create_sitting_for: set[str] = set()
        self.closed = False
        self._next_id = 100

    def _new_id(self) -> str:
        self._next_id += 1
        return str(self._next_id)

    # --- pyskylight surface used by the app -------------------------------

    def list_meal_categories(self, frame_id):
        return self.categories

    def list_recipes(self, frame_id):
        return self.recipes

    def list_sittings(self, frame_id, date_min, date_max):
        return self.sittings

    def create_recipe(self, frame_id, summary, description, meal_category_id):
        if summary in self.fail_create_recipe_for:
            raise RuntimeError(f"simulated create_recipe failure for {summary!r}")
        recipe = FakeObj(id=self._new_id(), summary=summary)
        self.recipes.append(recipe)
        return recipe

    def create_sitting(self, frame_id, date, meal_category_id, meal_recipe_id):
        recipe = self.recipe_by_id(meal_recipe_id)
        if recipe is not None and recipe.summary in self.fail_create_sitting_for:
            raise RuntimeError(f"simulated create_sitting failure for {recipe.summary!r}")
        sitting = FakeObj(
            id=self._new_id(),
            meal_category_id=meal_category_id,
            meal_recipe_id=meal_recipe_id,
            instances=[date],
        )
        self.sittings.append(sitting)
        return sitting

    def delete_sitting(self, frame_id, sitting_id, date):
        self.deleted_ids.append(str(sitting_id))
        self.sittings = [s for s in self.sittings if str(s.id) != str(sitting_id)]

    def close(self):
        self.closed = True

    # --- test helpers -----------------------------------------------------

    def recipe_by_id(self, recipe_id):
        return next((r for r in self.recipes if str(r.id) == str(recipe_id)), None)

    def seed(self, summary: str, category_id: str = "cat-lunch") -> FakeObj:
        """Pre-existing recipe + sitting, as if already on the calendar."""
        recipe = FakeObj(id=self._new_id(), summary=summary)
        self.recipes.append(recipe)
        sitting = FakeObj(
            id=self._new_id(),
            meal_category_id=category_id,
            meal_recipe_id=recipe.id,
            instances=[MENU_DATE],
        )
        self.sittings.append(sitting)
        return sitting

    def summaries(self) -> list[str]:
        """Recipe titles of the sittings currently planned, sorted."""
        out = []
        for s in self.sittings:
            recipe = self.recipe_by_id(s.meal_recipe_id)
            out.append(recipe.summary if recipe else "<no recipe>")
        return sorted(out)


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    """fastapi_app wired to a throwaway DB, a stubbed menu, and no real env."""
    monkeypatch.setattr(fastapi_app, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(fastapi_app.menu_service, "_week_cache", {})

    week = [
        DayMenu(date=d, items=[MenuItem(e, "LUNCH ENTREE") for e in ENTREES])
        for d in get_week_dates(date_cls.fromisoformat(MENU_DATE))
    ]
    monkeypatch.setattr(fastapi_app, "fetch_week", lambda ref: (week, None))
    monkeypatch.setattr(fastapi_app, "school_config", lambda: None)
    # Patch the credentials, not the published view: the published view is
    # derived from them inside skylight_adapter, so a leak would show up here.
    credentials = SkylightCredentials(
        email="test@example.com",
        password="secret",
        frame_id="frame-1",
        base_url="",
    )
    monkeypatch.setattr(fastapi_app, "skylight_credentials", lambda: credentials)
    monkeypatch.setattr(fastapi_app, "published_skylight_config", credentials.published)
    fastapi_app.init_db()
    return fastapi_app


@pytest.fixture
def client(app_module):
    from fastapi.testclient import TestClient

    return TestClient(app_module.app)


@pytest.fixture
def skylight(app_module, monkeypatch):
    fake = FakeSkylightClient()
    monkeypatch.setattr(app_module, "_skylight_login", lambda: fake)
    return fake


@pytest.fixture
def kid_ids(app_module):
    with app_module.get_db() as conn:
        rows = conn.execute("SELECT id, name FROM kids ORDER BY id").fetchall()
    return {r["name"]: r["id"] for r in rows}
