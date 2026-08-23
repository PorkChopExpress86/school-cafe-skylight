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
from db import (
    fetch_recent_history,
    load_selections,
    log_history,
)
from meal_plan_publication import DatePublicationOutcome, MealPlanPublisher, PublicationResult
from menu_service import school_config
from school_menu import get_week_dates
from skylight_adapter import (
    PyskylightAdapter,
    published_skylight_config,
    skylight_credentials,
    skylight_login,
)

APP_DIR = Path(__file__).resolve().parent
DB_PATH = db.DEFAULT_DB_PATH

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
    return skylight_login()


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
        raise HTTPException(status_code=400, detail=f"Invalid menu_date {menu_date!r}; expected YYYY-MM-DD.")


MAX_SELECTION_LEN = 200


def _sanitize_selection(selection: str) -> str:
    selection = selection.strip()
    if not selection:
        raise HTTPException(status_code=400, detail="selection must not be empty.")
    if len(selection) > MAX_SELECTION_LEN:
        raise HTTPException(status_code=400, detail=f"selection too long (max {MAX_SELECTION_LEN} characters).")
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


def _publication_errors(outcome: DatePublicationOutcome) -> list[str]:
    errors = [outcome.message] if outcome.message else []
    errors.extend(
        f"{kid.phase}({kid.kid_name}): {kid.message}"
        for kid in outcome.kid_outcomes
        if kid.status == "failed" and kid.message
    )
    return errors


def _day_publication_payload(outcome: DatePublicationOutcome) -> dict:
    sent = sum(kid.status == "published" for kid in outcome.kid_outcomes)
    skipped = sum(kid.status == "make_at_home" for kid in outcome.kid_outcomes)
    errors = _publication_errors(outcome)
    message = f"Sent {sent} to Skylight for {outcome.menu_date}."
    if outcome.deleted:
        message += f" Replaced {outcome.deleted} existing."
    if skipped:
        message += f" {skipped} make-at-home (no sitting)."
    if errors:
        message += " Errors: " + "; ".join(errors)
    return {
        "ok": outcome.status == "published",
        "message": message,
        "sent": sent,
        "deleted": outcome.deleted,
        "skipped": skipped,
        "errors": errors,
        "results": [
            {
                "kid_name": kid.kid_name,
                "selection": kid.selection,
                "status": {
                    "published": "sent",
                    "make_at_home": "skipped",
                    "failed": "error",
                }[kid.status],
            }
            for kid in outcome.kid_outcomes
        ],
    }


def send_day_to_skylight(menu_date: str) -> dict:
    """Publish one date through the shared Meal-plan Publication seam."""
    credentials = skylight_credentials()
    if not credentials.frame_id:
        return {"ok": False, "message": "SKYLIGHT_FRAME_ID is not set in .env."}
    publisher = MealPlanPublisher(
        DB_PATH,
        lambda: PyskylightAdapter(_skylight_login(), credentials.frame_id),
    )
    result = publisher.publish([date_cls.fromisoformat(menu_date)])
    return _day_publication_payload(result.date_outcomes[0])


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
        "skylight_cfg": published_skylight_config(),
        "menu_error": err,
    }


# ---------------------------------------------------------------------------
# App & Middleware
# ---------------------------------------------------------------------------

app = FastAPI(title="School Lunch Planner", lifespan=lifespan)

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
        kid = conn.execute("SELECT id, name, color, prefix FROM kids WHERE id = ?", (req.kid_id,)).fetchone()
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
        history = fetch_recent_history(conn)

    result["day_totals"] = {req.menu_date: total}
    result["day_sent"] = {req.menu_date: sent_count}
    result["history"] = history
    return result


class SendWeekRequest(BaseModel):
    date: str


def _week_publication_payload(result: PublicationResult, dates: list[str]) -> dict:
    sent = sum(kid.status == "published" for outcome in result.date_outcomes for kid in outcome.kid_outcomes)
    skipped = sum(kid.status == "make_at_home" for outcome in result.date_outcomes for kid in outcome.kid_outcomes)
    deleted = sum(outcome.deleted for outcome in result.date_outcomes)
    errors = [error for outcome in result.date_outcomes for error in _publication_errors(outcome)]
    results = [
        {
            "kid_name": kid.kid_name,
            "menu_date": outcome.menu_date,
            "selection": kid.selection,
            "status": {
                "published": "sent",
                "make_at_home": "skipped",
                "failed": "error",
            }[kid.status],
        }
        for outcome in result.date_outcomes
        for kid in outcome.kid_outcomes
    ]
    with get_db() as conn:
        selections = load_selections(conn, dates)
        history = fetch_recent_history(conn)
    day_totals, day_sent = _compute_day_counts(selections, dates)
    message = f"Sent {sent} meals across {len(dates)} days to Skylight."
    if deleted:
        message += f" Replaced {deleted} existing."
    if skipped:
        message += f" {skipped} make-at-home."
    if errors:
        message += " Errors: " + "; ".join(errors)
    return {
        "ok": result.ok,
        "message": message,
        "sent": sent,
        "deleted": deleted,
        "skipped": skipped,
        "errors": errors,
        "results": results,
        "day_totals": day_totals,
        "day_sent": day_sent,
        "history": history,
    }


def send_week_to_skylight(ref: date_cls) -> dict:
    """Publish one school week through the shared Meal-plan Publication seam."""
    credentials = skylight_credentials()
    if not credentials.frame_id:
        return {"ok": False, "message": "SKYLIGHT_FRAME_ID is not set in .env."}
    publication_dates = get_week_dates(ref)
    publisher = MealPlanPublisher(
        DB_PATH,
        lambda: PyskylightAdapter(_skylight_login(), credentials.frame_id),
    )
    result = publisher.publish(publication_dates)
    return _week_publication_payload(result, [value.isoformat() for value in publication_dates])


@app.post("/api/send-week")
def api_send_week(req: SendWeekRequest) -> dict:
    try:
        ref = datetime.strptime(req.date, "%Y-%m-%d").date()
    except ValueError:
        ref = date_cls.today()
    return send_week_to_skylight(ref)


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
            "message": (f"Synced {result.items_stored} items across {result.weeks_fetched} weeks."),
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
