"""Tests for translating pyskylight models at the publication boundary."""

from __future__ import annotations

from conftest import MENU_DATE, FakeSkylightClient

from lunch_planner.publication.publisher import SkylightRecipe, SkylightSitting
from lunch_planner.publication.skylight_adapter import PyskylightAdapter


def test_adapter_returns_only_publication_owned_recipe_and_sitting_fields():
    client = FakeSkylightClient()
    adapter = PyskylightAdapter(client, "frame-1")
    recipe = adapter.create_recipe("P- Cheese Pizza", "", "cat-lunch")
    sitting = adapter.create_sitting(MENU_DATE, "cat-lunch", recipe.id)

    assert recipe == SkylightRecipe(id=client.recipes[0].id, summary="P- Cheese Pizza")
    assert sitting == SkylightSitting(id=client.sittings[0].id, meal_recipe_id=client.recipes[0].id)
    assert adapter.list_recipes() == [recipe]
    assert adapter.list_lunch_sittings(MENU_DATE, "cat-lunch") == [
        sitting
    ]
