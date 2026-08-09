#!/usr/bin/env python3
"""FastAPI JSON API for picking school meals per kid and sending to Skylight.

Run:
    uvicorn fastapi_app:app --reload --port 8000

The frontend is a React SPA (in ../frontend) that consumes the /api/*
endpoints below. This module returns JSON only - no templates, no HTML.
"""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from datetime import date as date_cls
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db
import menu_service
import skylight_service
from db import (
    DEFAULT_DB_PATH,
    HISTORY_RETENTION,
    MAKE_AT_HOME,
    _backfill_kid_prefixes,
    _derive_kid_prefix,
    _unique_prefix,
    fetch_recent_history,
    load_selections,
    log_history,
)
from menu_service import _week_cache, school_config
from school_menu import get_week_dates
from skylight_service import (
    _recipe_summary,
    _resolve_lunch_category_id,
    _sitting_falls_on_date,
    _sitting_matches_kid_prefixes,
    skylight_config,
)

APP_DIR = Path(__file__).resolve().parent
DB_PATH = DEFAULT_DB_PATH

# ---------------------------------------------------------------------------
# Database & Lifespan
# ---------------------------------------------------------------------------


@contextmanager
def get_db():
    with db.get_db(DB_PATH) as conn:
        yield conn


def init_db() -> None:
    db.init_db(DB_PATH)


async def _sunday_sync_scheduler():
    """Background task inside container: syncs 4 weeks of menus every Sunday at 3:00 AM."""
    import asyncio
    while True:
        try:
            await asyncio.sleep(600)  # Check every 10 minutes
            now = datetime.now()
            # Sunday is weekday 6, check 03:00 AM window
            if now.weekday() == 6 and now.hour == 3:
                attempts = db.fetch_recent_sync_attempts(DB_PATH, limit=1)
                last_attempt = attempts[0]["attempted_at"] if attempts else ""
                today_iso = now.date().isoformat()
                if not last_attempt.startswith(today_iso):
                    from menu_sync import _load_env_config, sync_menu
                    cfg = _load_env_config()
                    if cfg:
                        sync_menu(cfg, db_path=DB_PATH)
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001
            pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    import asyncio
    init_db()
    task = asyncio.create_task(_sunday_sync_scheduler())
    try:
        yield
    finally:
        task.cancel()


def _skylight_login():
    return skylight_service._skylight_login()


def fetch_week(ref: date_cls):
    return menu_service.fetch_week(ref, DB_PATH)


def entrees_for_date(menu_date: str, parsed_date: date_cls) -> list[str]:
    return menu_service.entrees_for_date(menu_date, parsed_date, DB_PATH)


# ---------------------------------------------------------------------------
# Helpers & Validation
# ---------------------------------------------------------------------------


def _parse_menu_date(menu_date: str) -> date_cls:
    try:
        return datetime.strptime(menu_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid menu_date {menu_date!r}; expected YYYY-MM-DD."
        )


MAX_SELECTION_LEN = 200


def _sanitize_selection(selection: str) -> str:
    selection = selection.strip()
    if not selection:
        raise HTTPException(status_code=400, detail="selection must not be empty.")
    if len(selection) > MAX_SELECTION_LEN:
        raise HTTPException(
            status_code=400, detail=f"selection too long (max {MAX_SELECTION_LEN} characters)."
        )
    if any(ord(c) < 0x20 for c in selection):
        raise HTTPException(status_code=400, detail="selection contains control characters.")
    return selection


def _compute_day_counts(
    selections: dict[str, dict[int, dict]], dates: list[str]
) -> tuple[dict[str, int], dict[str, int]]:
    totals: dict[str, int] = {}
    sent: dict[str, int] = {}
    for d in dates:
        day = selections.get(d, {})
        totals[d] = len(day)
        sent[d] = sum(1 for v in day.values() if v["sent_sitting_id"])
    return totals, sent


def send_day_to_skylight(menu_date: str) -> dict:
    """Sync one day's lunch selections to Skylight calendar."""
    cfg = skylight_config()
    if not cfg["frame_id"]:
        return {"ok": False, "message": "SKYLIGHT_FRAME_ID is not set in .env."}

    # Phase 1: DB query
    with get_db() as conn:
        kids = conn.execute("SELECT id, name, prefix FROM kids ORDER BY id").fetchall()
        if not kids:
            return {"ok": False, "message": "No kids configured in database."}

        for kid in kids:
            conn.execute(
                """
                INSERT INTO selections (kid_id, menu_date, selection, sent_at, sent_sitting_id)
                VALUES (?, ?, ?, NULL, NULL)
                ON CONFLICT(kid_id, menu_date) DO NOTHING
                """,
                (kid["id"], menu_date, MAKE_AT_HOME),
            )
        conn.commit()

        kid_prefixes = {
            (k["prefix"] or db._derive_kid_prefix(k["name"])).strip().lower() for k in kids
        }
        kid_names = {k["name"] for k in kids}
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT s.kid_id, s.selection, s.sent_sitting_id,
                       k.name AS kid_name, k.prefix AS kid_prefix
                FROM selections s
                JOIN kids k ON k.id = s.kid_id
                WHERE s.menu_date = ?
                ORDER BY k.id
                """,
                (menu_date,),
            ).fetchall()
        ]

    # Phase 2: Skylight network I/O
    sent = 0
    skipped = 0
    deleted = 0
    errors: list[str] = []
    results: list[dict] = []
    db_updates: list[tuple[int, str | None]] = []

    client = _skylight_login()
    try:
        lunch_id = _resolve_lunch_category_id(client, cfg["frame_id"])
        if not lunch_id:
            return {"ok": False, "message": "Could not find a 'Lunch' meal category on this Skylight frame."}

        all_recipes = client.list_recipes(cfg["frame_id"])
        recipes_by_summary = {((r.summary or "").strip().lower()): r for r in all_recipes}
        recipes_by_id = {str(r.id): r for r in all_recipes}

        try:
            query_max = (date_cls.fromisoformat(menu_date) + timedelta(days=1)).isoformat()
            skylight_sittings = client.list_sittings(
                cfg["frame_id"], date_min=menu_date, date_max=query_max
            )
            lunch_sittings = [
                s for s in skylight_sittings
                if str(getattr(s, "meal_category_id", "")) == str(lunch_id)
                and _sitting_falls_on_date(s, menu_date)
            ]
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "message": (
                    f"Could not list existing sittings from Skylight for "
                    f"{menu_date}: {exc}. Aborting to avoid creating "
                    f"duplicate entries."
                ),
                "sent": 0,
                "deleted": 0,
                "skipped": 0,
                "errors": [f"list_sittings({menu_date}): {exc}"],
                "results": [],
            }

        stale_sittings = [
            s for s in lunch_sittings
            if _sitting_matches_kid_prefixes(s, recipes_by_id, kid_prefixes, kid_names)
        ]
        for s in stale_sittings:
            try:
                client.delete_sitting(cfg["frame_id"], str(s.id), menu_date)
                deleted += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"delete_sitting({menu_date}): {exc}")

        overrides = db.fetch_all_overrides(DB_PATH)
        for row in rows:
            kid_name = row["kid_name"]
            raw_selection = row["selection"]

            if raw_selection == MAKE_AT_HOME:
                db_updates.append((row["kid_id"], None))
                skipped += 1
                results.append({"kid_name": kid_name, "selection": raw_selection, "status": "skipped"})
                continue

            selection = db.resolve_display_text(raw_selection, overrides)
            prefix = (row["kid_prefix"] or db._derive_kid_prefix(kid_name)).strip()
            summary = _recipe_summary(prefix, selection)
            recipe = recipes_by_summary.get(summary.lower())
            if recipe is None:
                try:
                    recipe = client.create_recipe(
                        cfg["frame_id"],
                        summary=summary,
                        description=f"{selection} (from school menu)",
                        meal_category_id=lunch_id,
                    )
                    recipes_by_summary[summary.lower()] = recipe
                    recipes_by_id[str(recipe.id)] = recipe
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"create_recipe({summary!r}): {exc}")
                    results.append({"kid_name": kid_name, "selection": selection, "status": "error"})
                    continue

            try:
                new_sitting = client.create_sitting(
                    cfg["frame_id"],
                    date=menu_date,
                    meal_category_id=lunch_id,
                    meal_recipe_id=str(recipe.id),
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"create_sitting({menu_date}, {summary!r}): {exc}")
                results.append({"kid_name": kid_name, "selection": selection, "status": "error"})
                continue

            sent += 1
            results.append({"kid_name": kid_name, "selection": selection, "status": "sent"})
            db_updates.append((row["kid_id"], str(new_sitting.id)))
    finally:
        client.close()

    # Phase 3: DB updates
    now_iso = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        for kid_id, sitting_id in db_updates:
            try:
                conn.execute(
                    "UPDATE selections SET sent_at = ?, sent_sitting_id = ? "
                    "WHERE kid_id = ? AND menu_date = ?",
                    (now_iso, sitting_id, kid_id, menu_date),
                )
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"db update after create_sitting(kid {kid_id}): {exc}")

    msg = f"Sent {sent} to Skylight for {menu_date}."
    if deleted:
        msg += f" Replaced {deleted} existing."
    if skipped:
        msg += f" {skipped} make-at-home (no sitting)."
    if errors:
        msg += " Errors: " + "; ".join(errors)
    return {
        "ok": not errors,
        "message": msg,
        "sent": sent,
        "deleted": deleted,
        "skipped": skipped,
        "errors": errors,
        "results": results,
    }


def _week_payload(ref: date_cls) -> dict:
    week, err = fetch_week(ref)
    dates = [d.isoformat() for d in get_week_dates(ref)]

    with get_db() as conn:
        kids = conn.execute("SELECT id, name, color, prefix FROM kids ORDER BY id").fetchall()
        selections = load_selections(conn, dates)
        history = fetch_recent_history(conn)

    overrides = db.fetch_all_overrides(DB_PATH)
    for day_date, kid_map in selections.items():
        for kid_id, state in kid_map.items():
            if state.get("selection"):
                state["selection"] = db.resolve_display_text(state["selection"], overrides)

    for h in history:
        if h.get("selection"):
            h["selection"] = db.resolve_display_text(h["selection"], overrides)

    day_totals, day_sent = _compute_day_counts(selections, dates)

    return {
        "week": [
            {
                "date": d.date.isoformat(),
                "weekday": d.date.strftime("%A"),
                "entrees": [e.description for e in d.entrees],
            }
            for d in (week or [])
        ],
        "kids": [dict(k) for k in kids],
        "selections": selections,
        "day_totals": day_totals,
        "day_sent": day_sent,
        "history": history,
        "ref": ref.isoformat(),
        "prev_week": (ref - timedelta(days=7)).isoformat(),
        "next_week": (ref + timedelta(days=7)).isoformat(),
        "today": date_cls.today().isoformat(),
        "school_cfg": school_config(),
        "skylight_cfg": skylight_config(),
        "menu_error": err,
    }


# ---------------------------------------------------------------------------
# App & Middleware
# ---------------------------------------------------------------------------

app = FastAPI(title="School Lunch - Parker & Kylee", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request Models & Routes
# ---------------------------------------------------------------------------


class SelectRequest(BaseModel):
    kid_id: int
    menu_date: str
    selection: str


class SendDayRequest(BaseModel):
    menu_date: str


class OverrideRequest(BaseModel):
    original: str
    replacement: str


@app.get("/api/week")
def api_week(date: Annotated[str | None, Query()] = None) -> dict:
    if date:
        try:
            ref = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            ref = date_cls.today()
    else:
        ref = date_cls.today()
    return _week_payload(ref)


@app.post("/api/select")
def api_select(req: SelectRequest) -> dict:
    _parse_menu_date(req.menu_date)
    selection = _sanitize_selection(req.selection)
    overrides = db.fetch_all_overrides(DB_PATH)
    selection = db.resolve_display_text(selection, overrides)

    with get_db() as conn:
        kid = conn.execute(
            "SELECT id, name, color, prefix FROM kids WHERE id = ?", (req.kid_id,)
        ).fetchone()
        if kid is None:
            raise HTTPException(status_code=404, detail=f"Unknown kid_id {req.kid_id}.")

        conn.execute(
            """
            INSERT INTO selections (kid_id, menu_date, selection, sent_at, sent_sitting_id)
            VALUES (?, ?, ?, NULL, NULL)
            ON CONFLICT(kid_id, menu_date) DO UPDATE
                SET selection = excluded.selection,
                    sent_at = NULL,
                    sent_sitting_id = NULL
            """,
            (req.kid_id, req.menu_date, selection),
        )
        conn.commit()

        current = conn.execute(
            "SELECT selection, sent_at FROM selections WHERE kid_id=? AND menu_date=?",
            (req.kid_id, req.menu_date),
        ).fetchone()

        log_history(conn, kid["name"], req.menu_date, selection, "Selected")
        conn.commit()

        day_sels = load_selections(conn, [req.menu_date])
        day_data = day_sels.get(req.menu_date, {})
        total = len(day_data)
        sent_count = sum(1 for v in day_data.values() if v["sent_sitting_id"])
        history = fetch_recent_history(conn)

    return {
        "kid_id": req.kid_id,
        "menu_date": req.menu_date,
        "selection": selection,
        "sent_at": current["sent_at"] if current else None,
        "day_totals": {req.menu_date: total},
        "day_sent": {req.menu_date: sent_count},
        "history": history,
    }


@app.post("/api/send-day")
def api_send_day(req: SendDayRequest) -> dict:
    _parse_menu_date(req.menu_date)

    try:
        result = send_day_to_skylight(req.menu_date)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}

    with get_db() as conn:
        sels = load_selections(conn, [req.menu_date])
        day_data = sels.get(req.menu_date, {})
        sent_count = sum(1 for v in day_data.values() if v["sent_sitting_id"])
        total = len(day_data)
        for r in result.get("results", []):
            if r["status"] == "sent":
                log_history(conn, r["kid_name"], req.menu_date, r["selection"], "Sent to Skylight")
        conn.commit()
        history = fetch_recent_history(conn)

    result["day_totals"] = {req.menu_date: total}
    result["day_sent"] = {req.menu_date: sent_count}
    result["history"] = history
    return result


@app.get("/api/admin")
def api_admin() -> dict:
    weeks = db.fetch_distinct_weeks(DB_PATH)
    items = db.fetch_menu_items(DB_PATH)
    overrides = db.fetch_all_overrides(DB_PATH)
    items = menu_service.apply_overrides_to_items(items, overrides)
    attempts = db.fetch_recent_sync_attempts(DB_PATH, limit=50)
    return {
        "weeks": weeks,
        "items": items,
        "overrides": overrides,
        "attempts": attempts,
        "last_success": next((a for a in attempts if a["succeeded"]), None),
    }


@app.post("/api/admin/override")
def api_admin_override(req: OverrideRequest) -> dict:
    db.set_menu_override(req.original, req.replacement, DB_PATH)
    return {"ok": True, "overrides": db.fetch_all_overrides(DB_PATH)}


@app.post("/api/admin/sync")
def api_admin_sync() -> dict:
    from menu_sync import _load_env_config
    from menu_sync import sync_menu as _sync_menu

    config = _load_env_config()
    if config is None:
        return {"ok": False, "message": "SCHOOL_ID not set in .env"}
    try:
        result = _sync_menu(config, db_path=DB_PATH)
        return {
            "ok": True,
            "message": (
                f"Synced {result.items_stored} items across "
                f"{result.weeks_fetched} weeks."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}


@app.post("/api/admin/llm-case-all")
def api_admin_llm_case_all() -> dict:
    """Run all unique menu items through agy (gemini-3.6-flash-low) to generate permanent display overrides."""
    return menu_service.recase_all_items_with_llm(DB_PATH)


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok"}


# SPA static file serving fallback
_STATIC_DIR = APP_DIR / "static"
if _STATIC_DIR.is_dir():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount(
        "/assets",
        StaticFiles(directory=str(_STATIC_DIR / "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        candidate = _STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_STATIC_DIR / "index.html")
