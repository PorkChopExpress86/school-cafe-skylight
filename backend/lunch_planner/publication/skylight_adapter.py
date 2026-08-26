"""Concrete Skylight adapter for Meal-plan Publication."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import timedelta
from typing import Any

from dotenv import load_dotenv
from pyskylight import SkylightClient

from lunch_planner.publication.models import SkylightRecipe, SkylightSitting

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_env_loaded = False


def _load_env() -> None:
    global _env_loaded
    if not _env_loaded:
        load_dotenv(os.path.join(BACKEND_DIR, ".env"))
        _env_loaded = True


@dataclass(frozen=True)
class SkylightCredentials:
    """Everything needed to reach Skylight. Never leaves this module intact."""

    email: str
    password: str
    frame_id: str
    base_url: str

    def published(self) -> dict[str, str]:
        """The only Skylight configuration a route may return.

        The password is deliberately absent: narrowing happens here rather
        than at each call site, so no caller can widen it back.
        """
        return {"email": self.email, "frame_id": self.frame_id}


def skylight_credentials() -> SkylightCredentials:
    """Load Skylight credentials from the environment."""
    _load_env()
    return SkylightCredentials(
        email=os.environ.get("SKYLIGHT_EMAIL", "").strip(),
        password=os.environ.get("SKYLIGHT_PASSWORD", "").strip(),
        frame_id=os.environ.get("SKYLIGHT_FRAME_ID", "").strip(),
        base_url=os.environ.get("SKYLIGHT_BASE_URL", "https://app.ourskylight.com").strip(),
    )


def published_skylight_config() -> dict[str, str]:
    """Skylight configuration safe to put in an API response."""
    return skylight_credentials().published()


def skylight_frame_id() -> str:
    """Return the configured frame identifier without exposing credentials."""
    return skylight_credentials().frame_id


def skylight_login() -> SkylightClient:
    """Open a Skylight client, retrying once after a stale cached token."""
    credentials = skylight_credentials()
    if not credentials.email or not credentials.password:
        raise RuntimeError("SKYLIGHT_EMAIL and SKYLIGHT_PASSWORD must be set in .env")
    try:
        return SkylightClient.login(
            credentials.email, credentials.password, base_url=credentials.base_url
        )
    except Exception:  # noqa: BLE001
        token_path = os.path.expanduser("~/.cache/pyskylight/token.json")
        if os.path.exists(token_path):
            try:
                os.remove(token_path)
            except Exception:  # noqa: BLE001
                pass
        return SkylightClient.login(
            credentials.email, credentials.password, base_url=credentials.base_url
        )


def _sitting_falls_on_date(sitting: Any, menu_date: str) -> bool:
    return menu_date in sitting.dates


class PyskylightAdapter:
    """Translate pyskylight behavior into the publication adapter seam."""

    def __init__(self, client: Any, frame_id: str) -> None:
        self._client = client
        self._frame_id = frame_id

    def resolve_lunch_category_id(self) -> str | None:
        for category in self._client.list_meal_categories(self._frame_id):
            if (category.label or "").lower() == "lunch":
                return str(category.id)
        return None

    def list_recipes(self) -> list[SkylightRecipe]:
        return [
            SkylightRecipe(id=str(recipe.id), summary=(recipe.summary or "").strip())
            for recipe in self._client.list_recipes(self._frame_id)
        ]

    def list_lunch_sittings(self, menu_date: str, lunch_id: str) -> list[SkylightSitting]:
        query_max = (date_cls.fromisoformat(menu_date) + timedelta(days=1)).isoformat()
        try:
            sittings = self._client.list_sittings(
                self._frame_id,
                date_min=menu_date,
                date_max=query_max,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"list_sittings({menu_date}): {exc}") from exc
        return [
            SkylightSitting(id=str(sitting.id), meal_recipe_id=str(sitting.meal_recipe_id or ""))
            for sitting in sittings
            if str(sitting.meal_category_id) == str(lunch_id)
            and _sitting_falls_on_date(sitting, menu_date)
        ]

    def delete_sitting(self, sitting_id: str, menu_date: str) -> None:
        self._client.delete_sitting(self._frame_id, sitting_id, menu_date)

    def create_recipe(self, summary: str, description: str, lunch_id: str) -> SkylightRecipe:
        recipe = self._client.create_recipe(
            self._frame_id,
            summary=summary,
            description=description,
            meal_category_id=lunch_id,
        )
        return SkylightRecipe(id=str(recipe.id), summary=(recipe.summary or "").strip())

    def create_sitting(self, menu_date: str, lunch_id: str, recipe_id: str) -> SkylightSitting:
        sitting = self._client.create_sitting(
            self._frame_id,
            date=menu_date,
            meal_category_id=lunch_id,
            meal_recipe_id=recipe_id,
        )
        return SkylightSitting(id=str(sitting.id), meal_recipe_id=str(sitting.meal_recipe_id))

    def close(self) -> None:
        self._client.close()
