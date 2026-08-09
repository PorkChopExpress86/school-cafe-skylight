#!/usr/bin/env python3
"""FastAPI + HTMX web app for picking school meals per kid and sending to Skylight.

Run:
    uvicorn fastapi_app:app --reload --port 8000

Each kid has exactly one lunch selection per day - either an entree from the
school menu, or "make at home". Sending a day to Skylight creates one sitting
per kid per day, overwriting any previously-sent sitting for that kid/day.

Reads secrets from the local .env file. SQLite database lives at ./app.db.
The OAuth token cache (pyskylight) lives at ~/.cache/pyskylight/token.json.

Security note: this app runs on localhost only. No CSRF protection is
implemented because the attack surface is limited to the local machine.
If you expose it on a network, add CSRF tokens or put it behind a
reverse proxy with authentication.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
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

# Cache of entree descriptions per date, populated on page load so /select
# doesn't re-fetch the SchoolCafé API on every radio-button click.
_day_entrees_cache: dict[str, list[str]] = {}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_env_loaded = False


def _load_env() -> None:
    global _env_loaded
    if not _env_loaded:
        load_dotenv(APP_DIR / ".env")
        _env_loaded = True


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


def _compute_day_counts(
    selections: dict[str, dict[int, dict]], dates: list[str]
) -> tuple[dict[str, int], dict[str, int]]:
    """Return (totals, sent) dicts keyed by date_iso."""
    totals: dict[str, int] = {}
    sent: dict[str, int] = {}
    for d in dates:
        day = selections.get(d, {})
        totals[d] = len(day)
        sent[d] = sum(1 for v in day.values() if v["sent_sitting_id"])
    return totals, sent


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
       - else: create a new sitting first, then delete the old one (atomic:
         the kid always has at least one sitting on Skylight).
       One sitting per kid per day; overwriting.
    """
    cfg = skylight_config()
    if not cfg["frame_id"]:
        return {"ok": False, "message": "SKYLIGHT_FRAME_ID is not set in .env."}

    with get_db() as conn:
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
                # "Make at home" — delete the old sitting if it exists, but
                # only clear the DB after a successful delete.
                if row["selection"] == MAKE_AT_HOME:
                    if row["sent_sitting_id"]:
                        try:
                            client.delete_sitting(cfg["frame_id"], row["sent_sitting_id"], menu_date)
                            deleted += 1
                            conn.execute(
                                "UPDATE selections SET sent_at = NULL, sent_sitting_id = NULL "
                                "WHERE kid_id = ? AND menu_date = ?",
                                (row["kid_id"], menu_date),
                            )
                            conn.commit()
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"delete_sitting({row['kid_name']}): {exc}")
                            # Don't clear DB — Skylight still has the old sitting.
                            continue
                    skipped += 1
                    continue

                # Create the new sitting first (so the kid always has one).
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
                    continue

                # Now that the new sitting is in place, delete the old one.
                if row["sent_sitting_id"]:
                    try:
                        client.delete_sitting(cfg["frame_id"], row["sent_sitting_id"], menu_date)
                        deleted += 1
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"delete_sitting({row['kid_name']}): {exc}")
                        # Old sitting is orphaned but the new one is in place.

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
    dates = [d.isoformat() for d in get_week_dates(ref)]

    # Populate the entree cache so /select doesn't re-fetch the API.
    if week:
        for d in week:
            _day_entrees_cache[d.date.isoformat()] = [e.description for e in d.entrees]

    with get_db() as conn:
        kids = conn.execute("SELECT id, name, color FROM kids ORDER BY id").fetchall()
        selections = load_selections(conn, dates)

    day_totals, day_sent = _compute_day_counts(selections, dates)

    return templates.TemplateResponse(request, "week.html", {
        "request": request,
        "week": week,
        "kids": kids,
        "ref": ref,
        "prev_week": (ref - timedelta(days=7)).isoformat(),
        "next_week": (ref + timedelta(days=7)).isoformat(),
        "today": date_cls.today().isoformat(),
        "selections": selections,
        "day_totals": day_totals,
        "day_sent": day_sent,
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
       one row per (kid, date). Returns all cells for this kid on this day
       (the clicked one as primary swap, the rest as OOB) plus an OOB
       update for the send button so it enables immediately.
    """
    with get_db() as conn:
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

        # Compute updated send-button counts for this day.
        day_sels = load_selections(conn, [menu_date])
        day_data = day_sels.get(menu_date, {})
        total = len(day_data)
        sent_count = sum(1 for v in day_data.values() if v["sent_sitting_id"])

    is_sent = bool(current and current["sent_sitting_id"])

    # Use the cache populated by index(); fall back to API fetch on cache miss.
    entree_descriptions = _day_entrees_cache.get(menu_date)
    if entree_descriptions is None:
        week, _ = fetch_week(datetime.strptime(menu_date, "%Y-%m-%d").date())
        entree_descriptions = []
        if week:
            for d in week:
                if d.date.isoformat() == menu_date:
                    entree_descriptions = [e.description for e in d.entrees]
                    _day_entrees_cache[menu_date] = entree_descriptions
                    break

    parts: list[str] = []
    all_items = entree_descriptions + [MAKE_AT_HOME]

    for idx, item in enumerate(all_items, 1):
        cell_id = f"cell-{menu_date}-{kid_id}-{idx}" if idx <= len(entree_descriptions) else f"cell-{menu_date}-{kid_id}-home"
        is_selected = current and current["selection"] == item
        is_oob = (item != selection)
        parts.append(templates.get_template("_cell.html").render(
            kid=kid, menu_date=menu_date, item=item,
            selected=bool(is_selected), is_sent=is_sent,
            cell_id=cell_id, is_oob=is_oob,
        ))

    # OOB update for the send button so it enables immediately after a selection.
    send_html = templates.get_template("_send.html").render(
        menu_date=menu_date, total=total, sent_count=sent_count, result=None,
    )
    parts.append(f'<div id="send-{menu_date}" hx-swap-oob="true">{send_html}</div>')

    return HTMLResponse("\n".join(parts))


@app.post("/send-day", response_class=HTMLResponse)
def send_day(request: Request, menu_date: Annotated[str, Form()]):
    """Send one day's selections to Skylight. One sitting per kid, overwriting."""
    try:
        result = send_day_to_skylight(menu_date)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}

    with get_db() as conn:
        sels = load_selections(conn, [menu_date])
    day_data = sels.get(menu_date, {})
    sent_count = sum(1 for v in day_data.values() if v["sent_sitting_id"])
    total = len(day_data)

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