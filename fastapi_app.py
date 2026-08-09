#!/usr/bin/env python3
"""FastAPI + HTMX web app for picking school meals per kid and sending to Skylight.

Run:
    uvicorn fastapi_app:app --reload --port 8000

Each kid has exactly one lunch selection per day - either an entree from the
school menu, or "make at home". Sending a day to Skylight creates one sitting
per kid per day, overwriting any previously-sent sitting for that kid/day.

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
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from school_menu import SchoolCafeConfig, get_week_dates, get_weekly_items
from skylight_menu import SkylightClient, load_config as load_skylight_config

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "app.db"

MAKE_AT_HOME = "__MAKE_AT_HOME__"

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
        # Drop the old choices table (many-items-per-kid-per-day) so the new
        # schema (one-selection-per-kid-per-day) is clean. Migrations aren't
        # worth it for a personal app with a few days of test data.
        conn.executescript(
            """
            DROP TABLE IF EXISTS choices;

            CREATE TABLE IF NOT EXISTS kids (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL DEFAULT '#6366F1'
            );

            CREATE TABLE IF NOT EXISTS selections (
                kid_id           INTEGER NOT NULL,
                menu_date        TEXT    NOT NULL,
                selection       TEXT    NOT NULL,
                sent_at          TEXT,
                sent_sitting_id  TEXT,
                PRIMARY KEY (kid_id, menu_date),
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
    return load_skylight_config()


# ---------------------------------------------------------------------------
# App + templates
# ---------------------------------------------------------------------------


app = FastAPI(title="School Lunch - Parker & Kylee", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
templates.env.globals["MAKE_AT_HOME"] = MAKE_AT_HOME


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fetch_week(ref: date_cls) -> tuple[list | None, str | None]:
    cfg = school_config()
    if cfg is None:
        return None, "SCHOOL_ID not set in .env"
    try:
        return get_weekly_items(cfg, ref), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def load_selections(
    conn: sqlite3.Connection, dates: list[str]
) -> dict[str, dict[int, dict]]:
    """Return {date: {kid_id: {selection, sent_sitting_id}}} for the given dates."""
    if not dates:
        return {}
    placeholders = ",".join("?" * len(dates))
    rows = conn.execute(
        f"SELECT kid_id, menu_date, selection, sent_sitting_id "
        f"FROM selections WHERE menu_date IN ({placeholders})",
        dates,
    ).fetchall()
    out: dict[str, dict[int, dict]] = {}
    for r in rows:
        out.setdefault(r["menu_date"], {})[r["kid_id"]] = {
            "selection": r["selection"],
            "sent_sitting_id": r["sent_sitting_id"],
        }
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


def _recipe_summary(kid_name: str, item_text: str) -> str:
    return f"{kid_name} - {item_text}"


def send_day_to_skylight(menu_date: str) -> dict:
    """For each kid with a selection on this date:
       - if selection == MAKE_AT_HOME: delete any existing sitting, skip creation
       - else: delete any existing sitting, then create a new one for the new item
       One sitting per kid per day; overwriting.
    """
    cfg = skylight_config()
    if not cfg["frame_id"]:
        return {"ok": False, "message": "SKYLIGHT_FRAME_ID is not set in .env."}

    conn = get_conn()
    rows = conn.execute(
        """
        SELECT s.kid_id, s.selection, s.sent_sitting_id, k.name AS kid_name
        FROM selections s
        JOIN kids k ON k.id = s.kid_id
        WHERE s.menu_date = ?
        ORDER BY k.id
        """,
        (menu_date,),
    ).fetchall()

    if not rows:
        return {"ok": False, "message": "No selections for that day - nothing sent."}

    client = _skylight_login()
    try:
        lunch_id = _resolve_lunch_category_id(client, cfg["frame_id"])
        if not lunch_id:
            return {"ok": False, "message": "Could not find a 'Lunch' meal category on this Skylight frame."}

        existing_recipes = {
            ((r.summary or "").strip().lower()): r
            for r in client.list_recipes(cfg["frame_id"])
        }

        sent = 0
        skipped = 0
        deleted = 0
        errors: list[str] = []
        for row in rows:
            # Always overwrite: if there's a previously-sent sitting, delete it first.
            if row["sent_sitting_id"]:
                try:
                    client.delete_sitting(cfg["frame_id"], row["sent_sitting_id"], menu_date)
                    deleted += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"delete_sitting({row['kid_name']}): {exc}")
                    # Continue anyway - try to create the new one.

            # "Make at home" means no sitting should exist on Skylight.
            if row["selection"] == MAKE_AT_HOME:
                conn.execute(
                    "UPDATE selections SET sent_at = NULL, sent_sitting_id = NULL "
                    "WHERE kid_id = ? AND menu_date = ?",
                    (row["kid_id"], menu_date),
                )
                conn.commit()
                skipped += 1
                continue

            # Create a new sitting for the selected entree.
            summary = _recipe_summary(row["kid_name"], row["selection"])
            recipe = existing_recipes.get(summary.lower())
            if recipe is None:
                try:
                    recipe = client.create_recipe(
                        cfg["frame_id"],
                        summary=summary,
                        description=f"{row['selection']} (from school menu)",
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
                conn.execute(
                    "UPDATE selections SET sent_at = ?, sent_sitting_id = ? "
                    "WHERE kid_id = ? AND menu_date = ?",
                    (datetime.now().isoformat(timespec="seconds"), str(sitting.id),
                     row["kid_id"], menu_date),
                )
                conn.commit()
                sent += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"create_sitting({menu_date}, {summary!r}): {exc}")

        msg = f"Sent {sent} to Skylight for {menu_date}."
        if deleted:
            msg += f" Replaced {deleted} existing."
        if skipped:
            msg += f" {skipped} make-at-home (no sitting)."
        if errors:
            msg += " Errors: " + "; ".join(errors)
        return {"ok": True, "message": msg, "sent": sent, "deleted": deleted,
                "skipped": skipped, "errors": errors}
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
    selections = load_selections(conn, dates)

    return templates.TemplateResponse(request, "week.html", {
        "request": request,
        "week": week,
        "kids": kids,
        "ref": ref,
        "prev_week": (ref - timedelta(days=7)).isoformat(),
        "next_week": (ref + timedelta(days=7)).isoformat(),
        "today": date_cls.today().isoformat(),
        "selections": selections,
        "school_cfg": school_config(),
        "skylight_cfg": skylight_config(),
        "menu_error": err,
        "flash": flash,
    })


@app.post("/select", response_class=HTMLResponse)
def select(
    request: Request,
    kid_id: Annotated[int, Form()],
    menu_date: Annotated[str, Form()],
    selection: Annotated[str, Form()],
):
    """Set one kid's selection for one day. Radio-button semantics:
       one row per (kid, date). Returns the clicked cell (primary swap)
       plus out-of-band updates for all the kid's other cells on that
       day so they clear their selected state.
    """
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO selections (kid_id, menu_date, selection, sent_at, sent_sitting_id)
        VALUES (?, ?, ?, NULL, NULL)
        ON CONFLICT(kid_id, menu_date) DO UPDATE
            SET selection = excluded.selection,
                sent_at = NULL,
                sent_sitting_id = NULL
        """,
        (kid_id, menu_date, selection),
    )
    conn.commit()

    kid = conn.execute("SELECT id, name, color FROM kids WHERE id = ?", (kid_id,)).fetchone()
    current = conn.execute(
        "SELECT selection, sent_sitting_id FROM selections WHERE kid_id=? AND menu_date=?",
        (kid_id, menu_date),
    ).fetchone()
    is_sent = bool(current and current["sent_sitting_id"])

    # Fetch this day's entrees so we can update every cell for this kid.
    week, _ = fetch_week(datetime.strptime(menu_date, "%Y-%m-%d").date())
    entrees = []
    if week:
        for d in week:
            if d.date.isoformat() == menu_date:
                entrees = d.entrees
                break

    # Build the primary response (the clicked cell) + OOB updates for all
    # other cells so they reflect the new selection state.
    parts: list[str] = []

    # Primary: the clicked cell's new state (swaps in place of the clicked button)
    clicked_selected = current and current["selection"] == selection
    parts.append(templates.get_template("_cell.html").render(
        kid=kid, menu_date=menu_date, item=selection,
        selected=bool(clicked_selected), is_sent=is_sent,
    ))

    # OOB: every other cell for this kid on this day. Each is wrapped in a div
    # with the matching container id and hx-swap-oob="true" so htmx replaces
    # the whole container (div + button) with the fresh state.
    all_items = [e.description for e in entrees] + [MAKE_AT_HOME]
    for idx, item in enumerate(all_items, 1):
        if item == selection:
            continue  # Already handled as primary
        cell_id = f"cell-{menu_date}-{kid_id}-{idx}" if idx <= len(entrees) else f"cell-{menu_date}-{kid_id}-home"
        is_selected = current and current["selection"] == item
        cell_html = templates.get_template("_cell.html").render(
            kid=kid, menu_date=menu_date, item=item,
            selected=bool(is_selected), is_sent=is_sent,
        )
        parts.append(f'<div id="{cell_id}" hx-swap-oob="true" class="text-center w-8">{cell_html}</div>')

    return HTMLResponse("\n".join(parts))


@app.post("/send-day", response_class=HTMLResponse)
async def send_day(request: Request, menu_date: Annotated[str, Form()]):
    """Send one day's selections to Skylight. One sitting per kid, overwriting."""
    try:
        result = send_day_to_skylight(menu_date)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}

    conn = get_conn()
    sels = load_selections(conn, [menu_date])
    sent_count = sum(1 for k in sels.get(menu_date, {}).values() if k["sent_sitting_id"])
    total = len(sels.get(menu_date, {}))

    return templates.TemplateResponse(request, "_send.html", {
        "request": request,
        "menu_date": menu_date,
        "total": total,
        "sent_count": sent_count,
        "result": result,
    })


@app.get("/health", response_class=HTMLResponse)
def health():
    return HTMLResponse("ok")