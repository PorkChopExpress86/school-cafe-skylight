#!/usr/bin/env python3
"""FastAPI + HTMX web app for picking school meals per kid and sending to Skylight.

Run:
    uvicorn fastapi_app:app --reload --port 8000

Reads secrets from the local .env file. SQLite database lives at ./app.db.
The OAuth token cache (pyskylight) lives at ~/.cache/pyskylight/token.json.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import date as date_cls, datetime, timedelta
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from school_menu import DayMenu, SchoolCafeConfig, get_week_dates, get_weekly_items
from skylight_menu import SkylightClient, load_config as load_skylight_config

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "app.db"

DEFAULT_KIDS = [
    {"name": "Parker", "color": "#3B82F6"},
    {"name": "Kylee", "color": "#EC4899"},
]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_conn()
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _load_env() -> None:
    load_dotenv(APP_DIR / ".env")


def school_config() -> SchoolCafeConfig | None:
    _load_env()
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


def skylight_config() -> dict[str, str]:
    _load_env()
    cfg = load_skylight_config()
    return cfg


# ---------------------------------------------------------------------------
# App + templates
# ---------------------------------------------------------------------------


app = FastAPI(title="School Lunch - Parker & Kylee", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


def render(request: Request, template: str, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, template, ctx)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fetch_week(ref: date_cls) -> tuple[list[DayMenu] | None, str | None]:
    cfg = school_config()
    if cfg is None:
        return None, "SCHOOL_ID not set in .env"
    try:
        return get_weekly_items(cfg, ref), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def load_choices(conn: sqlite3.Connection, dates: list[str]) -> dict[str, dict[int, dict[str, bool]]]:
    if not dates:
        return {}
    placeholders = ",".join("?" * len(dates))
    rows = conn.execute(
        f"SELECT kid_id, menu_date, item_text, eats "
        f"FROM choices WHERE menu_date IN ({placeholders})",
        dates,
    ).fetchall()
    out: dict[str, dict[int, dict[str, bool]]] = {}
    for r in rows:
        out.setdefault(r["menu_date"], {}).setdefault(r["kid_id"], {})[r["item_text"]] = bool(r["eats"])
    return out


def load_send_state(conn: sqlite3.Connection, dates: list[str]) -> dict[str, dict[int, dict[str, bool]]]:
    """Return {date: {kid_id: {item: sent_bool}}} for already-sent items."""
    if not dates:
        return {}
    placeholders = ",".join("?" * len(dates))
    rows = conn.execute(
        f"SELECT kid_id, menu_date, item_text, sent_sitting_id "
        f"FROM choices WHERE menu_date IN ({placeholders}) AND sent_sitting_id IS NOT NULL",
        dates,
    ).fetchall()
    out: dict[str, dict[int, dict[str, bool]]] = {}
    for r in rows:
        out.setdefault(r["menu_date"], {}).setdefault(r["kid_id"], {})[r["item_text"]] = True
    return out


# ---------------------------------------------------------------------------
# Skylight write path
# ---------------------------------------------------------------------------


def _skylight_login() -> SkylightClient:
    cfg = skylight_config()
    if not cfg["email"] or not cfg["password"]:
        raise RuntimeError("SKYLIGHT_EMAIL and SKYLIGHT_PASSWORD must be set in .env")
    return SkylightClient.login(cfg["email"], cfg["password"], base_url=cfg["base_url"])


def _resolve_lunch_category_id(client: SkylightClient, frame_id: str) -> str | None:
    for c in client.list_meal_categories(frame_id):
        if (getattr(c, "label", "") or "").lower() == "lunch":
            return str(c.id)
    return None


def send_day_to_skylight(menu_date: str) -> dict:
    cfg = skylight_config()
    if not cfg["frame_id"]:
        return {"ok": False, "message": "SKYLIGHT_FRAME_ID is not set in .env."}

    conn = get_conn()
    rows = conn.execute(
        """
        SELECT c.kid_id, c.item_text, k.name AS kid_name, c.sent_sitting_id
        FROM choices c
        JOIN kids k ON k.id = c.kid_id
        WHERE c.menu_date = ? AND c.eats = 1
        ORDER BY k.id, c.item_text
        """,
        (menu_date,),
    ).fetchall()

    if not rows:
        return {"ok": False, "message": "Nothing checked for that day - nothing sent."}

    client = _skylight_login()
    try:
        lunch_id = _resolve_lunch_category_id(client, cfg["frame_id"])
        if not lunch_id:
            return {"ok": False, "message": "Could not find a 'Lunch' meal category on this Skylight frame."}

        existing = {
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
            summary = f"{row['kid_name']} - {row['item_text']}"
            recipe = existing.get(summary.lower())
            if recipe is None:
                try:
                    recipe = client.create_recipe(
                        cfg["frame_id"],
                        summary=summary,
                        description=f"{row['item_text']} (from school menu)",
                        meal_category_id=lunch_id,
                    )
                    existing[summary.lower()] = recipe
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
                conn.execute(
                    "UPDATE choices SET sent_at = ?, sent_sitting_id = ? "
                    "WHERE kid_id = ? AND menu_date = ? AND item_text = ?",
                    (datetime.now().isoformat(timespec="seconds"), str(sitting.id),
                     row["kid_id"], menu_date, row["item_text"]),
                )
                conn.commit()
                sent += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"create_sitting({menu_date}, {summary!r}): {exc}")

        msg = f"Sent {sent} to Skylight for {menu_date}."
        if skipped:
            msg += f" Skipped {skipped} already-sent."
        if errors:
            msg += " Errors: " + "; ".join(errors)
        return {"ok": True, "message": msg, "sent": sent, "skipped": skipped, "errors": errors}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    date: Annotated[str | None, Query()] = None,
    flash: Annotated[str | None, Query()] = None,
):
    if date:
        try:
            ref = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            ref = date_cls.today()
    else:
        ref = date_cls.today()

    week, err = fetch_week(ref)
    conn = get_conn()
    kids = conn.execute("SELECT id, name, color FROM kids ORDER BY id").fetchall()
    dates = [d.isoformat() for d in get_week_dates(ref)]
    choices = load_choices(conn, dates)
    sent = load_send_state(conn, dates)

    return render(
        request,
        "week.html",
        week=week,
        kids=kids,
        ref=ref,
        prev_week=(ref - timedelta(days=7)).isoformat(),
        next_week=(ref + timedelta(days=7)).isoformat(),
        today=date_cls.today().isoformat(),
        choices=choices,
        sent=sent,
        school_cfg=school_config(),
        skylight_cfg=skylight_config(),
        menu_error=err,
        flash=flash,
    )


@app.post("/toggle", response_class=HTMLResponse)
def toggle(
    request: Request,
    kid_id: Annotated[int, Form()],
    menu_date: Annotated[str, Form()],
    item_text: Annotated[str, Form()],
    eats: Annotated[int, Form()] = 0,
):
    """Toggle one (kid, date, item) choice. Returns the cell fragment for HTMX swap."""
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO choices (kid_id, menu_date, item_text, eats, sent_at, sent_sitting_id)
        VALUES (?, ?, ?, ?, NULL, NULL)
        ON CONFLICT(kid_id, menu_date, item_text) DO UPDATE
            SET eats = excluded.eats,
                sent_sitting_id = NULL,
                sent_at = NULL
        """,
        (kid_id, menu_date, item_text, 1 if eats else 0),
    )
    conn.commit()
    kid = conn.execute("SELECT id, name, color FROM kids WHERE id = ?", (kid_id,)).fetchone()
    item_state = conn.execute(
        "SELECT eats, sent_sitting_id FROM choices WHERE kid_id=? AND menu_date=? AND item_text=?",
        (kid_id, menu_date, item_text),
    ).fetchone()
    return templates.TemplateResponse(
        request,
        "_cell.html",
        {"kid": kid, "menu_date": menu_date, "item": item_text,
         "checked": bool(item_state and item_state["eats"]),
         "is_sent": bool(item_state and item_state["sent_sitting_id"])},
    )


@app.post("/send-day", response_class=HTMLResponse)
async def send_day(request: Request, menu_date: Annotated[str, Form()]):
    """Send one day's checked items to Skylight. Returns an updated send-button fragment."""
    try:
        result = send_day_to_skylight(menu_date)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}

    conn = get_conn()
    sent = load_send_state(conn, [menu_date])
    sent_count = sum(len(items) for kids_map in sent.values() for items in kids_map.values())
    eats_count = conn.execute(
        "SELECT COUNT(*) FROM choices WHERE menu_date=? AND eats=1", (menu_date,)
    ).fetchone()[0]

    return templates.TemplateResponse(
        request,
        "_send.html",
        {"menu_date": menu_date,
         "eats_count": eats_count,
         "sent_count": sent_count,
         "result": result},
    )


@app.get("/health", response_class=HTMLResponse)
def health():
    return HTMLResponse("ok")
