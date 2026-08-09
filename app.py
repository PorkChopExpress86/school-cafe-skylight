#!/usr/bin/env python3
"""Tiny web app: weekly school lunch menu, with per-kid checkboxes and a
'Send to Skylight' button per day.

Run:
    python app.py            # http://127.0.0.1:5000

Reads secrets (SKYLIGHT_EMAIL, SKYLIGHT_PASSWORD, SKYLIGHT_FRAME_ID,
SCHOOL_ID, ...) from the local `.env` file. SQLite database lives at
`./app.db` next to this script.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, g, redirect, render_template, request, url_for

from school_menu import DayMenu, SchoolCafeConfig, get_week_dates, get_weekly_items
from skylight_menu import (
    SkylightClient,
    load_config as load_skylight_config,
)

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "app.db"

DEFAULT_KIDS = [
    {"name": "Parker", "color": "#3B82F6"},
    {"name": "Kylee", "color": "#EC4899"},
]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS kids (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL DEFAULT '#6366F1'
            );

            CREATE TABLE IF NOT EXISTS choices (
                kid_id      INTEGER NOT NULL,
                menu_date   TEXT    NOT NULL,
                item_text   TEXT    NOT NULL,
                eats        INTEGER NOT NULL DEFAULT 0,
                sent_at     TEXT,
                sent_sitting_id TEXT,
                PRIMARY KEY (kid_id, menu_date, item_text),
                FOREIGN KEY (kid_id) REFERENCES kids(id) ON DELETE CASCADE
            );
            """
        )
        for kid in DEFAULT_KIDS:
            conn.execute(
                "INSERT OR IGNORE INTO kids (name, color) VALUES (?, ?)",
                (kid["name"], kid["color"]),
            )
        conn.commit()
    finally:
        conn.close()


def close_db(_exc: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------------------------------------------------------------------------
# School menu fetching (cached for the request)
# ---------------------------------------------------------------------------


def load_school_config() -> SchoolCafeConfig | None:
    school_id = os.environ.get("SCHOOL_ID", "").strip()
    if not school_id:
        return None
    return SchoolCafeConfig(
        school_id=school_id,
        serving_line=os.environ.get("SCHOOL_SERVING_LINE", "TD Lunch Elementary").strip()
        or "TD Lunch Elementary",
        meal_type=os.environ.get("SCHOOL_MEAL_TYPE", "Lunch").strip() or "Lunch",
        grade=os.environ.get("SCHOOL_GRADE", "02").strip() or "02",
    )


def fetch_week(ref: date) -> list[DayMenu] | None:
    cfg = load_school_config()
    if cfg is None:
        return None
    try:
        return get_weekly_items(cfg, ref)
    except Exception as exc:  # noqa: BLE001 - surface to template
        g.menu_error = f"{type(exc).__name__}: {exc}"
        return None


# ---------------------------------------------------------------------------
# Skylight
# ---------------------------------------------------------------------------


def _skylight_login() -> SkylightClient:
    cfg = load_skylight_config()
    if not cfg["email"] or not cfg["password"]:
        raise RuntimeError(
            "SKYLIGHT_EMAIL and SKYLIGHT_PASSWORD must be set in .env "
            "to send meals to Skylight."
        )
    return SkylightClient.login(cfg["email"], cfg["password"], base_url=cfg["base_url"])


def _resolve_lunch_category_id(client: SkylightClient, frame_id: str) -> str | None:
    cats = client.list_meal_categories(frame_id)
    for c in cats:
        label = (getattr(c, "label", "") or "").lower()
        if label == "lunch":
            return str(c.id)
    return None


# ---------------------------------------------------------------------------
# App + routes
# ---------------------------------------------------------------------------


app = Flask(__name__)
app.teardown_appcontext(close_db)


@app.route("/")
def index():
    ref_str = request.args.get("date")
    if ref_str:
        try:
            ref = datetime.strptime(ref_str, "%Y-%m-%d").date()
        except ValueError:
            ref = date.today()
    else:
        ref = date.today()

    week = fetch_week(ref)
    db = get_db()
    kids = db.execute("SELECT id, name, color FROM kids ORDER BY id").fetchall()

    choices_by_day: dict[str, dict[int, dict[str, bool]]] = {}
    if week and kids:
        dates = [d.isoformat() for d in get_week_dates(ref)]
        placeholders = ",".join("?" * len(dates))
        rows = db.execute(
            f"SELECT kid_id, menu_date, item_text, eats "
            f"FROM choices WHERE menu_date IN ({placeholders})",
            dates,
        ).fetchall()
        for row in rows:
            choices_by_day.setdefault(row["menu_date"], {}).setdefault(
                row["kid_id"], {}
            )[row["item_text"]] = bool(row["eats"])

    return render_template(
        "index.html",
        week=week,
        kids=kids,
        ref=ref,
        prev_week=(ref - timedelta(days=7)).isoformat(),
        next_week=(ref + timedelta(days=7)).isoformat(),
        today=date.today().isoformat(),
        choices=choices_by_day,
        school_cfg=load_school_config(),
        skylight_cfg=load_skylight_config(),
        menu_error=getattr(g, "menu_error", None),
    )


@app.route("/toggle", methods=["POST"])
def toggle():
    """Toggle one kid's check on a (date, item) pair. Idempotent."""
    kid_id = int(request.form["kid_id"])
    menu_date = request.form["menu_date"]
    item_text = request.form["item_text"]
    eats = 1 if request.form.get("eats") == "1" else 0

    db = get_db()
    db.execute(
        """
        INSERT INTO choices (kid_id, menu_date, item_text, eats, sent_at, sent_sitting_id)
        VALUES (?, ?, ?, ?, NULL, NULL)
        ON CONFLICT(kid_id, menu_date, item_text) DO UPDATE
            SET eats = excluded.eats
        """,
        (kid_id, menu_date, item_text, eats),
    )
    db.commit()
    return redirect(request.form.get("next") or url_for("index", date=menu_date))


@app.route("/send-day", methods=["POST"])
def send_day():
    """Send one day's checked items to Skylight as Lunch meal-plan entries.

    For each kid × checked item on `menu_date`:
      - ensure a meal recipe exists whose summary is "Parker — Chicken Nuggets"
        (or just the kid name for plain text meals) under the Lunch category;
      - create a sitting on that date pointing at the recipe.
    Already-sent entries (sent_sitting_id IS NOT NULL) are skipped, so the
    button is idempotent.
    """
    menu_date = request.form["menu_date"]
    next_url = request.form.get("next") or url_for("index", date=menu_date)

    cfg = load_skylight_config()
    if not cfg["frame_id"]:
        return _flash_redirect(
            next_url,
            "SKYLIGHT_FRAME_ID is not set in .env. Run `python skylight_menu.py frames` to find it.",
        )

    db = get_db()
    rows = db.execute(
        """
        SELECT c.id, c.kid_id, c.item_text, k.name AS kid_name, c.sent_sitting_id
        FROM choices c
        JOIN kids k ON k.id = c.kid_id
        WHERE c.menu_date = ? AND c.eats = 1
        ORDER BY k.id, c.item_text
        """,
        (menu_date,),
    ).fetchall()

    if not rows:
        return _flash_redirect(next_url, "Nothing checked for that day — nothing sent.")

    client = _skylight_login()
    try:
        lunch_id = _resolve_lunch_category_id(client, cfg["frame_id"])
        if not lunch_id:
            return _flash_redirect(
                next_url,
                "Could not find a 'Lunch' meal category on this Skylight frame.",
            )

        existing_recipes = {
            ((r.summary or "").strip().lower()): r
            for r in client.list_recipes(cfg["frame_id"])
        }

        sent = 0
        skipped = 0
        errors: list[str] = []
        for row in rows:
            if row["sent_sitting_id"]:
                skipped += 1
                continue

            summary = f"{row['kid_name']} — {row['item_text']}"
            recipe = existing_recipes.get(summary.lower())
            if recipe is None:
                try:
                    recipe = client.create_recipe(
                        cfg["frame_id"],
                        summary=summary,
                        description=f"{row['item_text']} (from school menu)",
                        meal_category_id=lunch_id,
                    )
                    existing_recipes[summary.lower()] = recipe
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"create_recipe({summary!r}): {exc}")
                    continue

            try:
                sitting = client.create_sitting(
                    cfg["frame_id"],
                    date=menu_date,
                    meal_category_id=lunch_id,
                    meal_recipe_id=str(recipe.id),
                )
                db.execute(
                    "UPDATE choices SET sent_at = ?, sent_sitting_id = ? "
                    "WHERE kid_id = ? AND menu_date = ? AND item_text = ?",
                    (
                        datetime.now().isoformat(timespec="seconds"),
                        str(sitting.id),
                        row["kid_id"],
                        menu_date,
                        row["item_text"],
                    ),
                )
                db.commit()
                sent += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"create_sitting({menu_date}, {summary!r}): {exc}")

        msg = f"Sent {sent} to Skylight for {menu_date}."
        if skipped:
            msg += f" Skipped {skipped} already-sent."
        if errors:
            msg += " Errors: " + "; ".join(errors)
        return _flash_redirect(next_url, msg)
    finally:
        client.close()


def _flash_redirect(target: str, message: str):
    """Tiny flash mechanism: put the message in the query string."""
    sep = "&" if "?" in target else "?"
    return redirect(f"{target}{sep}msg={message}")


@app.context_processor
def inject_msg():
    return {"flash": request.args.get("msg")}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    init_db()
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
