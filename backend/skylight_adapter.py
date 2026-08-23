"""Concrete Skylight adapter for Meal-plan Publication."""

from __future__ import annotations

import os
from datetime import date as date_cls
from datetime import timedelta
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
    """Load Skylight configuration from the environment."""
    _load_env()
    from skylight_menu import load_config

    return load_config()


def skylight_login() -> SkylightClient:
    """Open a Skylight client, retrying once after a stale cached token."""
    cfg = skylight_config()
    if not cfg["email"] or not cfg["password"]:
        raise RuntimeError("SKYLIGHT_EMAIL and SKYLIGHT_PASSWORD must be set in .env")
    try:
        return SkylightClient.login(cfg["email"], cfg["password"], base_url=cfg["base_url"])
    except Exception:  # noqa: BLE001
        token_path = os.path.expanduser("~/.cache/pyskylight/token.json")
        if os.path.exists(token_path):
            try:
                os.remove(token_path)
            except Exception:  # noqa: BLE001
                pass
        return SkylightClient.login(cfg["email"], cfg["password"], base_url=cfg["base_url"])


def _sitting_falls_on_date(sitting: Any, menu_date: str) -> bool:
    dates = getattr(sitting, "dates", None)
    if dates:
        return menu_date in list(dates)
    instances = getattr(sitting, "instances", None)
    if instances:
        return menu_date in list(instances)
    return True


class PyskylightAdapter:
    """Translate pyskylight behavior into the publication adapter seam."""

    def __init__(self, client: Any, frame_id: str) -> None:
        self._client = client
        self._frame_id = frame_id

    def resolve_lunch_category_id(self) -> str | None:
        for category in self._client.list_meal_categories(self._frame_id):
            if (getattr(category, "label", "") or "").lower() == "lunch":
                return str(category.id)
        return None

    def list_recipes(self) -> list[Any]:
        return self._client.list_recipes(self._frame_id)

    def list_lunch_sittings(self, menu_date: str, lunch_id: str) -> list[Any]:
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
            sitting
            for sitting in sittings
            if str(getattr(sitting, "meal_category_id", "")) == str(lunch_id)
            and _sitting_falls_on_date(sitting, menu_date)
        ]

    def delete_sitting(self, sitting_id: str, menu_date: str) -> None:
        self._client.delete_sitting(self._frame_id, sitting_id, menu_date)

    def create_recipe(self, summary: str, description: str, lunch_id: str) -> Any:
        return self._client.create_recipe(
            self._frame_id,
            summary=summary,
            description=description,
            meal_category_id=lunch_id,
        )

    def create_sitting(self, menu_date: str, lunch_id: str, recipe_id: str) -> Any:
        return self._client.create_sitting(
            self._frame_id,
            date=menu_date,
            meal_category_id=lunch_id,
            meal_recipe_id=recipe_id,
        )

    def close(self) -> None:
        self._client.close()
