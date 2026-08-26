"""Behavior tests for the Meal-plan Publication interface."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from threading import Event

from lunch_planner.persistence.connection import get_db
from lunch_planner.persistence.schema import init_db
from lunch_planner.planner.models import MAKE_AT_HOME
from lunch_planner.publication.models import SkylightRecipe, SkylightSitting
from lunch_planner.publication.publisher import MealPlanPublisher


@dataclass(frozen=True)
class _StoredSitting:
    id: str
    menu_date: str
    meal_category_id: str
    meal_recipe_id: str


class InMemorySkylightAdapter:
    """Skylight adapter used only at the external publication seam."""

    def __init__(self) -> None:
        self.recipes: list[SkylightRecipe] = []
        self.sittings: list[_StoredSitting] = []
        self.fail_delete_ids: set[str] = set()
        self.fail_list_dates: set[str] = set()
        self.fail_create_recipe_summaries: set[str] = set()
        self.fail_create_sitting_summaries: set[str] = set()
        self.fail_recipe_discovery = False
        self.fail_category_discovery = False
        self.on_list_sittings: Callable[[str], None] | None = None
        self.closed = False

    def resolve_lunch_category_id(self) -> str:
        if self.fail_category_discovery:
            raise RuntimeError("simulated category discovery failure")
        return "cat-lunch"

    def list_recipes(self) -> list[SkylightRecipe]:
        if self.fail_recipe_discovery:
            raise RuntimeError("simulated recipe discovery failure")
        return list(self.recipes)

    def list_lunch_sittings(self, menu_date: str, _lunch_id: str) -> list[SkylightSitting]:
        if self.on_list_sittings is not None:
            self.on_list_sittings(menu_date)
        if menu_date in self.fail_list_dates:
            raise RuntimeError("simulated discovery failure")
        return [
            SkylightSitting(id=sitting.id, meal_recipe_id=sitting.meal_recipe_id)
            for sitting in self.sittings
            if sitting.menu_date == menu_date
        ]

    def delete_sitting(self, sitting_id: str, menu_date: str) -> None:
        if sitting_id in self.fail_delete_ids:
            raise RuntimeError("simulated removal failure")
        self.sittings = [
            sitting
            for sitting in self.sittings
            if not (sitting.id == sitting_id and sitting.menu_date == menu_date)
        ]

    def create_recipe(self, summary: str, description: str, lunch_id: str) -> SkylightRecipe:
        if summary in self.fail_create_recipe_summaries:
            raise RuntimeError("simulated recipe failure")
        recipe = SkylightRecipe(
            id=f"recipe-{len(self.recipes) + 1}",
            summary=summary,
        )
        self.recipes.append(recipe)
        return recipe

    def create_sitting(self, menu_date: str, lunch_id: str, recipe_id: str) -> SkylightSitting:
        recipe = next(recipe for recipe in self.recipes if recipe.id == recipe_id)
        if recipe.summary in self.fail_create_sitting_summaries:
            raise RuntimeError("simulated sitting failure")
        sitting = _StoredSitting(
            id=f"sitting-{len(self.sittings) + 1}",
            menu_date=menu_date,
            meal_category_id=lunch_id,
            meal_recipe_id=recipe_id,
        )
        self.sittings.append(sitting)
        return SkylightSitting(id=sitting.id, meal_recipe_id=sitting.meal_recipe_id)

    def close(self) -> None:
        self.closed = True

    def summaries(self) -> list[str]:
        recipes = {recipe.id: recipe for recipe in self.recipes}
        return sorted(recipes[sitting.meal_recipe_id].summary for sitting in self.sittings)

    def seed(self, summary: str, menu_date: str) -> None:
        recipe = self.create_recipe(summary, "seeded", "cat-lunch")
        self.create_sitting(menu_date, "cat-lunch", recipe.id)


class BlockingSkylightAdapter(InMemorySkylightAdapter):
    def __init__(self, started: Event, release: Event) -> None:
        super().__init__()
        self.started = started
        self.release = release

    def list_lunch_sittings(self, menu_date: str, lunch_id: str) -> list[SkylightSitting]:
        self.started.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("test timed out waiting to release publication")
        return super().list_lunch_sittings(menu_date, lunch_id)


def test_publication_publishes_one_date_through_one_interface(tmp_path):
    db_path = tmp_path / "publication.db"
    init_db(db_path)
    with get_db(db_path) as conn:
        parker_id = conn.execute("SELECT id FROM kids WHERE name = 'Parker'").fetchone()["id"]
        conn.execute(
            "INSERT INTO selections (kid_id, menu_date, selection) VALUES (?, ?, ?)",
            (parker_id, "2026-08-24", "Cheese Pizza"),
        )
        conn.commit()

    skylight = InMemorySkylightAdapter()
    publisher = MealPlanPublisher(db_path, lambda: skylight)

    result = publisher.publish([date(2026, 8, 24)])

    assert result.date_outcomes[0].status == "published"
    assert [(o.kid_name, o.status) for o in result.date_outcomes[0].kid_outcomes] == [
        ("Parker", "published"),
        ("Kylee", "make_at_home"),
    ]
    assert skylight.summaries() == ["P- Cheese Pizza"]


def test_sitting_creation_failure_is_reported_for_one_kid(tmp_path):
    db_path = tmp_path / "publication.db"
    init_db(db_path)
    with get_db(db_path) as conn:
        parker_id = conn.execute("SELECT id FROM kids WHERE name = 'Parker'").fetchone()["id"]
        conn.execute(
            "INSERT INTO selections (kid_id, menu_date, selection) VALUES (?, ?, ?)",
            (parker_id, "2026-08-24", "Cheese Pizza"),
        )
        conn.commit()
    skylight = InMemorySkylightAdapter()
    skylight.fail_create_sitting_summaries.add("P- Cheese Pizza")

    result = MealPlanPublisher(db_path, lambda: skylight).publish([date(2026, 8, 24)])

    parker = result.date_outcomes[0].kid_outcomes[0]
    assert (result.date_outcomes[0].status, parker.status, parker.phase) == (
        "partial",
        "failed",
        "sitting_creation",
    )
    assert skylight.summaries() == []
    assert skylight.closed is True


def test_overlapping_publication_is_rejected_as_busy(tmp_path):
    db_path = tmp_path / "publication.db"
    init_db(db_path)
    started = Event()
    release = Event()
    first_skylight = BlockingSkylightAdapter(started, release)
    second_skylight = InMemorySkylightAdapter()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            MealPlanPublisher(db_path, lambda: first_skylight).publish,
            [date(2026, 8, 24)],
        )
        assert started.wait(timeout=2)
        overlapping = MealPlanPublisher(db_path, lambda: second_skylight).publish([date(2026, 8, 24)])
        release.set()
        assert first.result(timeout=5).date_outcomes[0].status == "published"

    assert overlapping.date_outcomes[0].status == "busy"
    assert second_skylight.closed is False


def test_publication_replaces_exact_prefix_sittings_without_touching_family_entries(tmp_path):
    db_path = tmp_path / "publication.db"
    init_db(db_path)
    skylight = InMemorySkylightAdapter()
    skylight.seed("P- Old School Lunch", "2026-08-24")
    skylight.seed("Family Taco Night", "2026-08-24")

    result = MealPlanPublisher(db_path, lambda: skylight).publish([date(2026, 8, 24)])

    assert result.date_outcomes[0].deleted == 1
    assert skylight.summaries() == ["Family Taco Night"]


def test_stored_sitting_identifier_proves_ownership_without_a_prefix(tmp_path):
    db_path = tmp_path / "publication.db"
    init_db(db_path)
    skylight = InMemorySkylightAdapter()
    skylight.seed("Legacy School Lunch", "2026-08-24")
    stored_sitting_id = str(skylight.sittings[0].id)
    with get_db(db_path) as conn:
        parker_id = conn.execute("SELECT id FROM kids WHERE name = 'Parker'").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO selections (kid_id, menu_date, selection, sent_sitting_id)
            VALUES (?, ?, ?, ?)
            """,
            (parker_id, "2026-08-24", MAKE_AT_HOME, stored_sitting_id),
        )
        conn.commit()

    result = MealPlanPublisher(db_path, lambda: skylight).publish([date(2026, 8, 24)])

    assert result.date_outcomes[0].deleted == 1
    assert skylight.summaries() == []


def test_removal_failure_blocks_new_sittings_for_that_date(tmp_path):
    db_path = tmp_path / "publication.db"
    init_db(db_path)
    with get_db(db_path) as conn:
        parker_id = conn.execute("SELECT id FROM kids WHERE name = 'Parker'").fetchone()["id"]
        conn.execute(
            "INSERT INTO selections (kid_id, menu_date, selection) VALUES (?, ?, ?)",
            (parker_id, "2026-08-24", "Cheese Pizza"),
        )
        conn.commit()

    skylight = InMemorySkylightAdapter()
    skylight.seed("P- Old School Lunch", "2026-08-24")
    skylight.fail_delete_ids.add(str(skylight.sittings[0].id))

    result = MealPlanPublisher(db_path, lambda: skylight).publish([date(2026, 8, 24)])

    assert result.date_outcomes[0].status == "blocked"
    assert result.date_outcomes[0].phase == "removal"
    assert skylight.summaries() == ["P- Old School Lunch"]


def test_removal_failure_clears_only_successfully_removed_sitting_state(tmp_path):
    db_path = tmp_path / "publication.db"
    init_db(db_path)
    skylight = InMemorySkylightAdapter()
    skylight.seed("P- Old School Lunch", "2026-08-24")
    parker_sitting_id = str(skylight.sittings[0].id)
    skylight.seed("K- Old School Lunch", "2026-08-24")
    kylee_sitting_id = str(skylight.sittings[1].id)
    skylight.fail_delete_ids.add(kylee_sitting_id)

    with get_db(db_path) as conn:
        kids = {row["name"]: row["id"] for row in conn.execute("SELECT id, name FROM kids")}
        conn.executemany(
            """
            INSERT INTO selections (kid_id, menu_date, selection, sent_at, sent_sitting_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (kids["Parker"], "2026-08-24", "Cheese Pizza", "2026-08-23T12:00:00", parker_sitting_id),
                (kids["Kylee"], "2026-08-24", "Hot Dog", "2026-08-23T12:00:00", kylee_sitting_id),
            ],
        )
        conn.commit()

    result = MealPlanPublisher(db_path, lambda: skylight).publish([date(2026, 8, 24)])

    assert (result.date_outcomes[0].status, result.date_outcomes[0].deleted) == ("blocked", 1)
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT kid_id, sent_at, sent_sitting_id FROM selections WHERE menu_date = ? ORDER BY kid_id",
            ("2026-08-24",),
        ).fetchall()
    assert [(row["sent_at"], row["sent_sitting_id"]) for row in rows] == [
        (None, None),
        ("2026-08-23T12:00:00", kylee_sitting_id),
    ]
    assert skylight.summaries() == ["K- Old School Lunch"]


def test_concurrent_selection_change_is_not_marked_published_by_a_stale_snapshot(tmp_path):
    db_path = tmp_path / "publication.db"
    init_db(db_path)
    skylight = InMemorySkylightAdapter()
    skylight.seed("P- Cheese Pizza", "2026-08-24")
    old_sitting_id = str(skylight.sittings[0].id)

    with get_db(db_path) as conn:
        parker_id = conn.execute("SELECT id FROM kids WHERE name = 'Parker'").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO selections (kid_id, menu_date, selection, sent_at, sent_sitting_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (parker_id, "2026-08-24", "Cheese Pizza", "2026-08-23T12:00:00", old_sitting_id),
        )
        conn.commit()

    def change_selection_after_snapshot(menu_date: str) -> None:
        with get_db(db_path) as conn:
            conn.execute(
                """
                UPDATE selections
                SET selection = ?, sent_at = NULL, sent_sitting_id = NULL
                WHERE menu_date = ?
                """,
                ("Hot Dog", menu_date),
            )
            conn.commit()

    skylight.on_list_sittings = change_selection_after_snapshot
    result = MealPlanPublisher(db_path, lambda: skylight).publish([date(2026, 8, 24)])

    outcome = result.date_outcomes[0]
    assert (outcome.status, outcome.kid_outcomes[0].status, outcome.kid_outcomes[0].phase) == (
        "partial",
        "failed",
        "concurrency",
    )
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT selection, sent_at, sent_sitting_id FROM selections WHERE kid_id = ? AND menu_date = ?",
            (parker_id, "2026-08-24"),
        ).fetchone()
    assert dict(row) == {"selection": "Hot Dog", "sent_at": None, "sent_sitting_id": None}
    assert skylight.summaries() == ["P- Cheese Pizza"]


def test_discovery_failure_is_isolated_to_one_date(tmp_path):
    db_path = tmp_path / "publication.db"
    init_db(db_path)
    with get_db(db_path) as conn:
        parker_id = conn.execute("SELECT id FROM kids WHERE name = 'Parker'").fetchone()["id"]
        conn.executemany(
            "INSERT INTO selections (kid_id, menu_date, selection) VALUES (?, ?, ?)",
            [
                (parker_id, "2026-08-24", "Cheese Pizza"),
                (parker_id, "2026-08-25", "Hot Dog"),
            ],
        )
        conn.commit()

    skylight = InMemorySkylightAdapter()
    skylight.fail_list_dates.add("2026-08-24")

    result = MealPlanPublisher(db_path, lambda: skylight).publish([date(2026, 8, 24), date(2026, 8, 25)])

    assert [(outcome.menu_date, outcome.status) for outcome in result.date_outcomes] == [
        ("2026-08-24", "blocked"),
        ("2026-08-25", "published"),
    ]
    assert skylight.summaries() == ["P- Hot Dog"]


def test_recipe_discovery_failure_blocks_every_requested_date(tmp_path):
    db_path = tmp_path / "publication.db"
    init_db(db_path)
    skylight = InMemorySkylightAdapter()
    skylight.fail_recipe_discovery = True

    result = MealPlanPublisher(db_path, lambda: skylight).publish([date(2026, 8, 24), date(2026, 8, 25)])

    assert [(outcome.status, outcome.phase) for outcome in result.date_outcomes] == [
        ("blocked", "discovery"),
        ("blocked", "discovery"),
    ]
    assert skylight.closed is True


def test_category_discovery_failure_returns_blocked_outcome(tmp_path):
    db_path = tmp_path / "publication.db"
    init_db(db_path)
    skylight = InMemorySkylightAdapter()
    skylight.fail_category_discovery = True

    result = MealPlanPublisher(db_path, lambda: skylight).publish([date(2026, 8, 24)])

    assert (result.date_outcomes[0].status, result.date_outcomes[0].phase) == (
        "blocked",
        "discovery",
    )
    assert skylight.closed is True


def test_connection_failure_blocks_every_requested_date(tmp_path):
    db_path = tmp_path / "publication.db"
    init_db(db_path)

    def fail_to_connect():
        raise RuntimeError("simulated login failure")

    result = MealPlanPublisher(db_path, fail_to_connect).publish([date(2026, 8, 24), date(2026, 8, 25)])

    assert [(outcome.status, outcome.phase) for outcome in result.date_outcomes] == [
        ("blocked", "connection"),
        ("blocked", "connection"),
    ]


def test_publication_uses_one_frozen_snapshot_for_all_requested_dates(tmp_path):
    db_path = tmp_path / "publication.db"
    init_db(db_path)
    with get_db(db_path) as conn:
        parker_id = conn.execute("SELECT id FROM kids WHERE name = 'Parker'").fetchone()["id"]
        conn.executemany(
            "INSERT INTO selections (kid_id, menu_date, selection) VALUES (?, ?, ?)",
            [
                (parker_id, "2026-08-24", "Cheese Pizza"),
                (parker_id, "2026-08-25", "Hot Dog"),
            ],
        )
        conn.commit()

    skylight = InMemorySkylightAdapter()
    changed = False

    def change_second_date_after_publication_starts(menu_date: str) -> None:
        nonlocal changed
        if menu_date != "2026-08-24" or changed:
            return
        changed = True
        with get_db(db_path) as conn:
            conn.execute(
                "UPDATE selections SET selection = 'Chicken Nuggets' WHERE kid_id = ? AND menu_date = '2026-08-25'",
                (parker_id,),
            )
            conn.commit()

    skylight.on_list_sittings = change_second_date_after_publication_starts

    result = MealPlanPublisher(db_path, lambda: skylight).publish([date(2026, 8, 24), date(2026, 8, 25)])

    second_date = result.date_outcomes[1]
    parker = next(kid for kid in second_date.kid_outcomes if kid.kid_name == "Parker")
    assert parker.selection == "Hot Dog"
    assert skylight.summaries() == ["P- Cheese Pizza", "P- Hot Dog"]


def test_kid_creation_failure_produces_a_partial_date_outcome(tmp_path):
    db_path = tmp_path / "publication.db"
    init_db(db_path)
    with get_db(db_path) as conn:
        kids = {row["name"]: row["id"] for row in conn.execute("SELECT id, name FROM kids ORDER BY id").fetchall()}
        conn.executemany(
            "INSERT INTO selections (kid_id, menu_date, selection) VALUES (?, ?, ?)",
            [
                (kids["Parker"], "2026-08-24", "Cheese Pizza"),
                (kids["Kylee"], "2026-08-24", "Hot Dog"),
            ],
        )
        conn.commit()

    skylight = InMemorySkylightAdapter()
    skylight.fail_create_recipe_summaries.add("K- Hot Dog")

    result = MealPlanPublisher(db_path, lambda: skylight).publish([date(2026, 8, 24)])

    outcome = result.date_outcomes[0]
    assert outcome.status == "partial"
    assert [(kid.kid_name, kid.status, kid.phase) for kid in outcome.kid_outcomes] == [
        ("Parker", "published", None),
        ("Kylee", "failed", "recipe_creation"),
    ]
    assert skylight.summaries() == ["P- Cheese Pizza"]
