#!/usr/bin/env python3
"""Skylight Calendar helper - login, list meal-plan data, and add meals.

Reads credentials from a local `.env` file (see `.env.example`). The OAuth
session token is cached by `pyskylight` at
`${XDG_CACHE_HOME:-~/.cache}/pyskylight/token.json` so you only sign in once.

Subcommands
-----------
    frames               List your frames (households). Print IDs + names.
    categories           List meal categories (Breakfast/Lunch/Dinner/Snack).
    recipes              List recipes in your meal library.
    plan                 List already-planned sittings in a date range.
    add-recipe           Create a recipe. Flags: --summary, --category-id, --description.
    add-meal             Plan a recipe onto a date. Flags: --date, --category-id, --recipe-id.
    remove-meal          Remove a sitting from a date. Flags: --sitting-id, --date.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date as date_cls
from datetime import timedelta
from typing import Any

from dotenv import load_dotenv
from pyskylight import SkylightClient


def load_config() -> dict[str, str]:
    """Load secrets from .env in the script directory, then os.environ."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(env_path)

    cfg = {
        "email": os.environ.get("SKYLIGHT_EMAIL", "").strip(),
        "password": os.environ.get("SKYLIGHT_PASSWORD", "").strip(),
        "frame_id": os.environ.get("SKYLIGHT_FRAME_ID", "").strip(),
        "timezone": os.environ.get("SKYLIGHT_TIMEZONE", "").strip(),
        "base_url": os.environ.get(
            "SKYLIGHT_BASE_URL", "https://app.ourskylight.com"
        ).strip(),
    }
    return cfg


def require_credentials(cfg: dict[str, str]) -> tuple[str, str]:
    if not cfg["email"] or not cfg["password"]:
        print(
            "SKYLIGHT_EMAIL and SKYLIGHT_PASSWORD must be set in .env\n"
            "(copy .env.example to .env and fill it in).",
            file=sys.stderr,
        )
        sys.exit(2)
    return cfg["email"], cfg["password"]


def resolve_frame_id(client: SkylightClient, cfg: dict[str, str]) -> str:
    if cfg["frame_id"]:
        return cfg["frame_id"]
    frames = client.list_frames()
    if not frames:
        print("No frames found for this account.", file=sys.stderr)
        sys.exit(1)
    if len(frames) > 1:
        print("Multiple frames found; set SKYLIGHT_FRAME_ID in .env to disambiguate:")
        for f in frames:
            print(f"  {f.id}\t{f.name}")
        sys.exit(1)
    return str(frames[0].id)


def to_jsonable(obj: Any) -> Any:
    """Best-effort serializer for pyskylight model objects."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return {k: to_jsonable(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, list):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    return obj


def print_json(data: Any) -> None:
    print(json.dumps(to_jsonable(data), indent=2, default=str))


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_frames(client: SkylightClient, _cfg: dict[str, str], _args: argparse.Namespace) -> None:
    print_json(client.list_frames())


def cmd_categories(client: SkylightClient, cfg: dict[str, str], _args: argparse.Namespace) -> None:
    fid = resolve_frame_id(client, cfg)
    print_json(client.list_meal_categories(fid))


def cmd_recipes(client: SkylightClient, cfg: dict[str, str], args: argparse.Namespace) -> None:
    fid = resolve_frame_id(client, cfg)
    print_json(client.list_recipes(fid, include=None if args.no_category else "meal_category"))


def cmd_plan(client: SkylightClient, cfg: dict[str, str], args: argparse.Namespace) -> None:
    fid = resolve_frame_id(client, cfg)
    today = date_cls.today()
    date_min = args.date_min or today.isoformat()
    if args.date_max:
        date_max = args.date_max
    else:
        date_max = (today + timedelta(days=int(args.days or 7))).isoformat()
    print_json(client.list_sittings(fid, date_min=date_min, date_max=date_max))


def cmd_add_recipe(client: SkylightClient, cfg: dict[str, str], args: argparse.Namespace) -> None:
    if not args.summary:
        print("--summary is required", file=sys.stderr)
        sys.exit(2)
    fid = resolve_frame_id(client, cfg)
    recipe = client.create_recipe(
        fid,
        summary=args.summary,
        description=args.description,
        meal_category_id=args.category_id,
    )
    print_json(recipe)


def cmd_add_meal(client: SkylightClient, cfg: dict[str, str], args: argparse.Namespace) -> None:
    if not args.date or not args.category_id:
        print("--date and --category-id are required", file=sys.stderr)
        sys.exit(2)
    fid = resolve_frame_id(client, cfg)
    sitting = client.create_sitting(
        fid,
        date=args.date,
        meal_category_id=args.category_id,
        meal_recipe_id=args.recipe_id,
    )
    print_json(sitting)


def cmd_remove_meal(client: SkylightClient, cfg: dict[str, str], args: argparse.Namespace) -> None:
    if not args.sitting_id or not args.date:
        print("--sitting-id and --date are required", file=sys.stderr)
        sys.exit(2)
    fid = resolve_frame_id(client, cfg)
    client.delete_sitting(fid, args.sitting_id, args.date)
    print(f"Removed sitting {args.sitting_id} from {args.date}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Skylight Calendar CLI helper.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("frames", help="List your frames (households).")

    sub.add_parser("categories", help="List meal categories (Breakfast/Lunch/Dinner/Snack).")

    pr = sub.add_parser("recipes", help="List recipes in your meal library.")
    pr.add_argument("--no-category", action="store_true", help="Skip include=meal_category")

    pp = sub.add_parser("plan", help="List planned sittings in a date range.")
    pp.add_argument("--date-min", help="Start date (YYYY-MM-DD); default today")
    pp.add_argument("--date-max", help="End date (YYYY-MM-DD)")
    pp.add_argument("--days", help="If --date-max omitted, window length in days (default 7)")

    pa = sub.add_parser("add-recipe", help="Create a new recipe in your library.")
    pa.add_argument("--summary", required=True, help="Recipe title (e.g. 'Tacos')")
    pa.add_argument("--category-id", help="Meal category ID (Breakfast/Lunch/Dinner/Snack)")
    pa.add_argument("--description", help="Ingredients / instructions text")

    pm = sub.add_parser("add-meal", help="Plan a meal onto a date.")
    pm.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    pm.add_argument("--category-id", required=True, help="Meal category ID")
    pm.add_argument("--recipe-id", help="Recipe ID; omit for a text-only meal")

    prm = sub.add_parser("remove-meal", help="Remove a sitting from a specific date.")
    prm.add_argument("--sitting-id", required=True)
    prm.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")

    return p


COMMANDS = {
    "frames": cmd_frames,
    "categories": cmd_categories,
    "recipes": cmd_recipes,
    "plan": cmd_plan,
    "add-recipe": cmd_add_recipe,
    "add-meal": cmd_add_meal,
    "remove-meal": cmd_remove_meal,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cfg = load_config()
    email, password = require_credentials(cfg)

    client = SkylightClient.login(email, password, base_url=cfg["base_url"])
    try:
        COMMANDS[args.cmd](client, cfg, args)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
