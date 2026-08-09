#!/usr/bin/env python3
"""FastAPI + HTMX web app for picking school meals per kid and sending to Skylight.

Run:
    uvicorn fastapi_app:app --reload --port 8000

Each kid has exactly one lunch selection per day - either an entree from the
school menu, or "make at home". Sending a day to Skylight wipes every sitting
on that date belonging to one of our kids (matched by recipe-title prefix)
and recreates them from the current selections, leaving the rest of the
calendar untouched.

Reads secrets from the local .env file. SQLite database lives at ./app.db.
The OAuth token cache (pyskylight) lives at ~/.cache/pyskylight/token.json.

Security note: this app has no authentication and no CSRF protection, and it
can write to a real Skylight calendar. It is only safe while nothing off this
machine can reach it, so it must be published to loopback only - see the
"Security note" section in CONTAINER.md for how to run it that way. Binding it
to a LAN-reachable address without putting authentication in front of it hands
anyone on the network control of the calendar.
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import date as date_cls
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from school_menu import SchoolCafeConfig, get_week_dates, get_weekly_items
from skylight_menu import SkylightClient
from skylight_menu import load_config as load_skylight_config

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "app.db"

MAKE_AT_HOME = "__MAKE_AT_HOME__"

DEFAULT_KIDS = [
    {"name": "Parker", "color": "#3B82F6", "prefix": "P-"},
    {"name": "Kylee", "color": "#EC4899", "prefix": "K-"},
]

# Rows kept in selection_history before the oldest are pruned. The panel only
# ever shows the most recent handful; this just stops the table growing without
# bound over years of daily use.
HISTORY_RETENTION = 500


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


@contextmanager
def get_db():
    # `timeout` + busy_timeout let a second concurrent request wait for a write
    # lock instead of failing outright with "database is locked".
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        # WAL is a persistent property of the database file, so setting it
        # once here covers every later connection.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS kids (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL DEFAULT '#6366F1',
                prefix TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS selections (
                kid_id           INTEGER NOT NULL,
                menu_date        TEXT    NOT NULL,
                selection        TEXT    NOT NULL,
                sent_at          TEXT,
                sent_sitting_id  TEXT,
                PRIMARY KEY (kid_id, menu_date),
                FOREIGN KEY (kid_id) REFERENCES kids(id) ON DELETE CASCADE
            );

            -- The (kid_id, menu_date) primary key can't serve lookups that
            -- filter on menu_date alone, which is what the week view does.
            CREATE INDEX IF NOT EXISTS idx_selections_menu_date
                ON selections(menu_date);

            CREATE TABLE IF NOT EXISTS selection_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                kid_name   TEXT NOT NULL,
                menu_date  TEXT NOT NULL,
                selection  TEXT NOT NULL,
                action     TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        # Migrate databases created before `kids.prefix` existed.
        existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(kids)")}
        if "prefix" not in existing_cols:
            conn.execute("ALTER TABLE kids ADD COLUMN prefix TEXT NOT NULL DEFAULT ''")

        for kid in DEFAULT_KIDS:
            conn.execute(
                "INSERT OR IGNORE INTO kids (name, color, prefix) VALUES (?, ?, ?)",
                (kid["name"], kid["color"], kid["prefix"]),
            )
        _backfill_kid_prefixes(conn)
        conn.commit()


def _derive_kid_prefix(kid_name: str) -> str:
    """Best-effort prefix for a kid with none stored, e.g. "Parker" -> "P-".

    Returns "?-" rather than raising for a name with no usable character, so
    a bad row in the kids table can't take the whole send path down.
    """
    initial = next((c for c in kid_name.strip().upper() if c.isalnum()), "")
    return f"{initial}-" if initial else "?-"


def _unique_prefix(base: str, taken: set[str]) -> str:
    """Disambiguate `base` against already-assigned prefixes.

    Prefixes drive which Skylight sittings get wiped on a send, so two kids
    sharing one would make their calendar entries indistinguishable.
    """
    if base.lower() not in taken:
        return base
    stem = base.rstrip("-")
    for n in range(2, 100):
        candidate = f"{stem}{n}-"
        if candidate.lower() not in taken:
            return candidate
    return base


def _backfill_kid_prefixes(conn: sqlite3.Connection) -> None:
    """Give every kid a non-empty, unique prefix."""
    rows = conn.execute("SELECT id, name, prefix FROM kids ORDER BY id").fetchall()
    taken = {r["prefix"].strip().lower() for r in rows if (r["prefix"] or "").strip()}
    defaults = {k["name"]: k["prefix"] for k in DEFAULT_KIDS}
    for r in rows:
        if (r["prefix"] or "").strip():
            continue
        candidate = _unique_prefix(
            defaults.get(r["name"]) or _derive_kid_prefix(r["name"]), taken
        )
        taken.add(candidate.lower())
        conn.execute("UPDATE kids SET prefix = ? WHERE id = ?", (candidate, r["id"]))


def log_history(conn: sqlite3.Connection, kid_name: str, menu_date: str, selection: str, action: str) -> None:
    """Record one activity row.

    `created_at` is stored as an ISO timestamp and `selection` as the raw
    value (including the MAKE_AT_HOME sentinel); both are formatted for
    display at render time, so the stored data stays sortable and queryable.
    """
    conn.execute(
        """
        INSERT INTO selection_history (kid_name, menu_date, selection, action, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (kid_name, menu_date, selection, action, datetime.now().isoformat(timespec="seconds")),
    )
    conn.execute(
        """
        DELETE FROM selection_history
        WHERE id <= (
            SELECT MAX(id) - ? FROM selection_history
        )
        """,
        (HISTORY_RETENTION,),
    )


def fetch_recent_history(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, kid_name, menu_date, selection, action, created_at
        FROM selection_history
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


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


def _format_history_time(value: str) -> str:
    """Render a stored ISO timestamp for the history panel.

    Rows written before timestamps were stored as ISO already hold a
    display string, so fall back to showing those verbatim.
    """
    try:
        return datetime.fromisoformat(value).strftime("%b %d, %I:%M %p")
    except (TypeError, ValueError):
        return value


def _format_selection(value: str) -> str:
    return "Make at home" if value == MAKE_AT_HOME else value


templates.env.filters["history_time"] = _format_history_time
templates.env.filters["selection_label"] = _format_selection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# How long a fetched week stays usable before it's re-fetched. Bounded by
# week so the cache holds one entry per visited week rather than one per
# visited day, and time-limited so a menu correction shows up without a
# restart.
MENU_CACHE_TTL_SECONDS = 15 * 60
MENU_CACHE_MAX_ENTRIES = 16

# {(config, monday_iso): (monotonic_deadline, week)}
_week_cache: dict[tuple[SchoolCafeConfig, str], tuple[float, list]] = {}


def _cached_week(cfg: SchoolCafeConfig, monday: date_cls) -> list | None:
    entry = _week_cache.get((cfg, monday.isoformat()))
    if entry is None:
        return None
    deadline, week = entry
    if time.monotonic() >= deadline:
        _week_cache.pop((cfg, monday.isoformat()), None)
        return None
    return week


def _store_week(cfg: SchoolCafeConfig, monday: date_cls, week: list) -> None:
    if len(_week_cache) >= MENU_CACHE_MAX_ENTRIES:
        # Cheap bound: drop whatever expires soonest.
        oldest = min(_week_cache, key=lambda k: _week_cache[k][0])
        _week_cache.pop(oldest, None)
    _week_cache[(cfg, monday.isoformat())] = (
        time.monotonic() + MENU_CACHE_TTL_SECONDS,
        week,
    )


def fetch_week(ref: date_cls) -> tuple[list | None, str | None]:
    cfg = school_config()
    if cfg is None:
        return None, "SCHOOL_ID not set in .env"
    monday = get_week_dates(ref)[0]
    cached = _cached_week(cfg, monday)
    if cached is not None:
        return cached, None
    try:
        week = get_weekly_items(cfg, ref)
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    _store_week(cfg, monday, week)
    return week, None


def entrees_for_date(menu_date: str, parsed_date: date_cls) -> list[str]:
    """Entree descriptions for one day, or [] if the menu can't be fetched."""
    week, _ = fetch_week(parsed_date)
    if not week:
        return []
    for day in week:
        if day.date.isoformat() == menu_date:
            return [e.description for e in day.entrees]
    return []


def _parse_menu_date(menu_date: str) -> date_cls:
    """Parse a form-supplied menu_date, or fail the request with 400.

    There's no legitimate way for a browser following this app's own links
    and forms to post anything but YYYY-MM-DD here, so unlike `selection`
    (see `_sanitize_selection`) this rejects anything that doesn't parse.
    """
    try:
        return datetime.strptime(menu_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid menu_date {menu_date!r}; expected YYYY-MM-DD."
        )


MAX_SELECTION_LEN = 200


def _sanitize_selection(selection: str) -> str:
    """Reject garbage `selection` values before they're stored and, on send,
    become a Skylight recipe title.

    This intentionally does NOT require an exact match against the day's
    current entree list - a selection can legitimately be a real school
    entree this process just doesn't have cached (e.g. right after a
    restart, or a page left open across a menu update); `select()` already
    handles that case by rendering whatever was posted. This only guards
    against empty, oversized, or control-character input.
    """
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


def _recipe_summary(prefix: str, item_text: str) -> str:
    """Skylight recipe title for one kid's meal, e.g. "P- Cheese Pizza".

    The prefix comes from `kids.prefix` (see `_backfill_kid_prefixes`) rather
    than being derived from the name at call time, so it stays stable and
    unique per kid.
    """
    return f"{prefix} {item_text}"


def _sitting_matches_kid_prefixes(
    sitting: Any, recipes_by_id: dict[str, Any], prefixes: set[str]
) -> bool:
    """True if `sitting`'s linked recipe title starts with one of our kids'
    prefixes (e.g. "P-", "K-") - i.e. this is a sitting the app itself could
    have created for one of our kids, as opposed to anything else a family
    member put on the calendar for that meal."""
    recipe_id = str(getattr(sitting, "meal_recipe_id", ""))
    recipe = recipes_by_id.get(recipe_id)
    if not recipe:
        return False
    summary = (getattr(recipe, "summary", "") or "").strip().lower()
    return any(summary.startswith(p) for p in prefixes)


def send_day_to_skylight(menu_date: str) -> dict:
    """Sync one day's lunch selections to Skylight.

    A kid with no selection recorded for `menu_date` defaults to
    MAKE_AT_HOME - never to a menu entree - so an unattended send can't put
    a meal nobody chose onto the calendar.

    Deletes EVERY Lunch sitting on that date whose recipe title starts with
    one of our kids' prefixes ("P-", "K-", ...) - i.e. every sitting this app
    could have created for either kid that day - before creating anything
    new. Both kids' entries are wiped together on every send, regardless of
    which kid's selection actually changed; nothing else on the Skylight
    calendar for that date is touched. Kids set to "make at home" get no new
    sitting.

    The database connection is deliberately released before any Skylight
    call and reopened afterwards, so a slow API can't hold a SQLite write
    lock for the duration.
    """
    cfg = skylight_config()
    if not cfg["frame_id"]:
        return {"ok": False, "message": "SKYLIGHT_FRAME_ID is not set in .env."}

    # --- Phase 1: read what we need from the DB, then let the connection go.
    with get_db() as conn:
        kids = conn.execute("SELECT id, name, prefix FROM kids ORDER BY id").fetchall()
        if not kids:
            return {"ok": False, "message": "No kids configured in database."}

        # A kid who was never picked for defaults to make-at-home, which
        # creates no sitting at all.
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
            (k["prefix"] or _derive_kid_prefix(k["name"])).strip().lower() for k in kids
        }
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

    # --- Phase 2: all Skylight I/O, with no DB connection held open.
    sent = 0
    skipped = 0
    deleted = 0
    errors: list[str] = []
    # Per-kid outcomes for this send, so the caller can log history that
    # matches what actually happened rather than assuming every kid succeeded.
    results: list[dict] = []
    # (kid_id, sitting_id) pairs to record once the network work is done.
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
            skylight_sittings = client.list_sittings(
                cfg["frame_id"], date_min=menu_date, date_max=menu_date
            )
            lunch_sittings = [
                s for s in skylight_sittings
                if str(getattr(s, "meal_category_id", "")) == str(lunch_id)
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

        # Wipe every Lunch sitting on this date that belongs to one of our
        # kids, up front, before creating anything new. Deleting by prefix
        # match (rather than per-kid, via a stored sitting id) means a stray
        # sitting Skylight-side that our DB lost track of still gets cleaned
        # up, and it means both kids' entries are always wiped together on a
        # send - not just the one whose selection changed.
        stale_sittings = [
            s for s in lunch_sittings
            if _sitting_matches_kid_prefixes(s, recipes_by_id, kid_prefixes)
        ]
        for s in stale_sittings:
            try:
                client.delete_sitting(cfg["frame_id"], str(s.id), menu_date)
                deleted += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"delete_sitting({menu_date}): {exc}")

        for row in rows:
            kid_name = row["kid_name"]

            if row["selection"] == MAKE_AT_HOME:
                db_updates.append((row["kid_id"], None))
                skipped += 1
                results.append({"kid_name": kid_name, "selection": row["selection"], "status": "skipped"})
                continue

            prefix = (row["kid_prefix"] or _derive_kid_prefix(kid_name)).strip()
            summary = _recipe_summary(prefix, row["selection"])
            recipe = recipes_by_summary.get(summary.lower())
            if recipe is None:
                try:
                    recipe = client.create_recipe(
                        cfg["frame_id"],
                        summary=summary,
                        description=f"{row['selection']} (from school menu)",
                        meal_category_id=lunch_id,
                    )
                    recipes_by_summary[summary.lower()] = recipe
                    recipes_by_id[str(recipe.id)] = recipe
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"create_recipe({summary!r}): {exc}")
                    results.append({"kid_name": kid_name, "selection": row["selection"], "status": "error"})
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
                results.append({"kid_name": kid_name, "selection": row["selection"], "status": "error"})
                continue

            sent += 1
            results.append({"kid_name": kid_name, "selection": row["selection"], "status": "sent"})
            db_updates.append((row["kid_id"], str(new_sitting.id)))
    finally:
        client.close()

    # --- Phase 3: record what Skylight confirmed. A failure here is reported
    # but never undoes phase 2 - the prefix wipe on the next send reconciles
    # any sitting we failed to write down.
    now_iso = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        for kid_id, sitting_id in db_updates:
            try:
                conn.execute(
                    "UPDATE selections SET sent_at = ?, sent_sitting_id = ? "
                    "WHERE kid_id = ? AND menu_date = ?",
                    (now_iso if sitting_id else None, sitting_id, kid_id, menu_date),
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

    with get_db() as conn:
        kids = conn.execute("SELECT id, name, color, prefix FROM kids ORDER BY id").fetchall()
        selections = load_selections(conn, dates)
        history = fetch_recent_history(conn)

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
        "history": history,
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
       update for the send button and selection history.
    """
    parsed_date = _parse_menu_date(menu_date)
    selection = _sanitize_selection(selection)

    with get_db() as conn:
        kid = conn.execute(
            "SELECT id, name, color, prefix FROM kids WHERE id = ?", (kid_id,)
        ).fetchone()
        if kid is None:
            raise HTTPException(status_code=404, detail=f"Unknown kid_id {kid_id}.")

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

        current = conn.execute(
            "SELECT selection, sent_sitting_id FROM selections WHERE kid_id=? AND menu_date=?",
            (kid_id, menu_date),
        ).fetchone()

        log_history(conn, kid["name"], menu_date, selection, "Selected")
        conn.commit()

        # Compute updated send-button counts for this day.
        day_sels = load_selections(conn, [menu_date])
        day_data = day_sels.get(menu_date, {})
        total = len(day_data)
        sent_count = sum(1 for v in day_data.values() if v["sent_sitting_id"])
        history = fetch_recent_history(conn)

    is_sent = bool(current and current["sent_sitting_id"])

    # Normally a cache hit from the page load that rendered these cells;
    # falls back to a live fetch (and [] if that fails) after a restart.
    entree_descriptions = entrees_for_date(menu_date, parsed_date)

    cell_template = templates.get_template("_cell.html")

    def render_cell(item: str, cell_id: str, is_oob: bool) -> str:
        return cell_template.render(
            kid=kid, menu_date=menu_date, item=item,
            selected=bool(current and current["selection"] == item),
            is_sent=is_sent, cell_id=cell_id, is_oob=is_oob,
        )

    all_items = entree_descriptions + [MAKE_AT_HOME]

    # htmx swaps the single non-OOB fragment into the clicked cell. If the
    # posted selection isn't in the entree list this process knows about - a
    # stale page, or a menu fetch that failed after a restart - every fragment
    # below would be OOB, htmx would swap an empty body into the clicked cell,
    # and the cell would disappear. Render that cell explicitly instead, using
    # the id htmx tells us it is targeting.
    fallback_id: str | None = None
    if selection not in all_items:
        fallback_id = request.headers.get("HX-Target") or f"cell-{menu_date}-{kid_id}-home"

    parts: list[str] = []
    for idx, item in enumerate(all_items, 1):
        cell_id = (
            f"cell-{menu_date}-{kid_id}-{idx}"
            if idx <= len(entree_descriptions)
            else f"cell-{menu_date}-{kid_id}-home"
        )
        if cell_id == fallback_id:
            continue  # emitted below as the primary swap instead
        parts.append(render_cell(item, cell_id, is_oob=(item != selection)))

    if fallback_id is not None:
        parts.append(render_cell(selection, fallback_id, is_oob=False))

    # OOB update for the send button so it enables immediately after a selection.
    parts.append(templates.get_template("_send.html").render(
        menu_date=menu_date, total=total, sent_count=sent_count,
        result=None, is_oob=True,
    ))

    # OOB update for the history panel.
    parts.append(templates.get_template("_history.html").render(history=history, is_oob=True))

    return HTMLResponse("\n".join(parts))


@app.post("/send-day", response_class=HTMLResponse)
def send_day(request: Request, menu_date: Annotated[str, Form()]):
    """Send one day's selections to Skylight. One sitting per kid, overwriting."""
    _parse_menu_date(menu_date)  # raises 400 on malformed dates

    try:
        result = send_day_to_skylight(menu_date)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}

    with get_db() as conn:
        sels = load_selections(conn, [menu_date])
        day_data = sels.get(menu_date, {})
        sent_count = sum(1 for v in day_data.values() if v["sent_sitting_id"])
        total = len(day_data)
        # Log per kid from what actually happened, not from the overall "ok"
        # flag - one kid's error shouldn't suppress another kid's real send,
        # and a skipped (make-at-home) kid never had a sitting created.
        for r in result.get("results", []):
            if r["status"] == "sent":
                log_history(conn, r["kid_name"], menu_date, r["selection"], "Sent to Skylight")
        conn.commit()
        history = fetch_recent_history(conn)

    send_html = templates.get_template("_send.html").render({
        "menu_date": menu_date,
        "total": total,
        "sent_count": sent_count,
        "result": result,
        "is_oob": False,
    })
    history_html = templates.get_template("_history.html").render(history=history, is_oob=True)
    return HTMLResponse(send_html + "\n" + history_html)


@app.get("/health", response_class=HTMLResponse)
def health():
    return HTMLResponse("ok")
