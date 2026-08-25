# Agent Skills — school-cafe-skylight

This file documents conventions, pitfalls, and operating notes for AI agents working in this repo. Keep it short; link out to deeper docs when a topic grows.

## Project overview

A FastAPI JSON API + React SPA that fetches weekly lunch menus from SchoolCafé, lets a parent pick an entree per kid per day, and syncs the picks to a Skylight Calendar as Lunch meal-plan sittings. Single-user, loopback-only, no auth (by design — see `CONTAINER.md` security note). Styled with the Post Elementary Patriots theme (Navy Blue, Patriot Red, Gold accents).

## Architecture

```
school-cafe-skylight/
├── backend/          ← FastAPI JSON API (Python)
│   ├── fastapi_app.py   ← Lean API router & middleware
│   ├── db.py            ← SQLite database schema, connections, selections, overrides, sync logs
│   ├── menu_service.py  ← SchoolCafé config, in-memory TTL caching, override resolution
│   ├── planner_readback.py ← Display-resolved planner state, counts, and history
│   ├── meal_plan_publication.py ← Deep Meal-plan Publication workflow for day/week writes
│   ├── publication_control.py ← Route-facing publication configuration, adapter, and readback control
│   ├── skylight_adapter.py ← Skylight credentials, OAuth, and the pyskylight adapter
│   ├── school_menu.py   ← SchoolCafé client (fetch + parse only)
│   ├── menu_item_display.py ← Display Text: overrides + casing (pure, no I/O)
│   ├── menu_casing.py   ← Bulk Display Override generation via agy (admin only)
│   ├── menu_sync.py     ← One 4-week menu sync attempt
│   ├── menu_sync_schedule.py ← Sunday scheduling policy and explicit outcomes
│   ├── skylight_menu.py ← Skylight config loader
│   ├── tests/           ← pytest suite (offline, 75+ tests)
│   └── app.db           ← SQLite (gitignored)
├── frontend/         ← React SPA (TypeScript + Tailwind v4 + Post Patriots theme)
│   ├── src/api/         ← typed API client (getWeek, select, sendDay, getAdmin, setOverride, triggerSync, triggerLlmCasing)
│   ├── src/hooks/       ← TanStack Query hooks (useWeek, useSelect, useSendDay, useAdmin, useOverride, useSync, useLlmCasing)
│   ├── src/components/  ← Cell, SendButton, HistoryPanel, DaySection
│   ├── src/pages/       ← WeekPage, AdminPage (deduplicated Unique Items table & search)
│   └── vite.config.ts   ← dev proxy /api → :8000
```

## Operating model

- **Container is the runtime.** Local Python is for tests only; the app runs in Podman with bind-mounted source.
- **Container restarts itself** via `systemctl --user start school-cafe.service` (see `~/.config/systemd/user/school-cafe.service`). Auto-restarts on crash/reboot.
- **Automated Sunday 3:00 AM Sync:** `MenuSyncSchedule` is the single scheduler. The FastAPI lifespan calls it every 10 minutes; it makes at most one America/Chicago Sunday 03:00 attempt, records sync failures, and returns explicit not-due, already-attempted, not-configured, synced, or failed outcomes. Do not add cron or systemd timers. `POST /api/admin/sync` remains an immediate manual trigger.
- **AI Case Formatting:** Only the admin bulk re-casing pass talks to a model — `menu_casing.AgyCasingAdapter` (`agy -p ... --model gemini-3.6-flash-low`), triggered by `POST /api/admin/llm-case-all`. It asks for every unique item and pins the answers as Display Overrides. Nothing else shells out: `menu_item_display.MenuItemDisplay` is pure, and ingest/read paths never call a model. Tests pass a fake adapter as a parameter — never add a `PYTEST_CURRENT_TEST` check to production code.
- **Frontend build automation:** `npm run build` runs a `postbuild` hook copying `frontend/dist` to `backend/static/`.
- **Image:** `localhost/school-cafe-skylight:latest`. Rebuild after `Containerfile` or `requirements*.txt` changes.

## Quick reference

| Action | Command |
|--------|---------|
| Run backend tests | `cd backend && python -m pytest tests/ -q` |
| Lint backend | `cd backend && ruff check .` |
| Type-check backend | `cd backend && mypy fastapi_app.py db.py menu_service.py planner_readback.py meal_plan_publication.py publication_control.py skylight_adapter.py school_menu.py menu_sync.py menu_sync_schedule.py menu_item_display.py menu_casing.py` |
| Build frontend & sync static | `cd frontend && npm run build` |
| Frontend dev server | `cd frontend && npm run dev` |
| Start container | `podman start school-cafe` (or `systemctl --user start school-cafe.service`) |
| Container logs | `podman logs -f school-cafe` |
| Rebuild container image | `podman build --build-arg UID=$(id -u) --build-arg GID=$(id -g) -t school-cafe-skylight:latest -f backend/Containerfile .` |

## API surface

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/week?date=YYYY-MM-DD` | Week view: menu, kids, selections, counts, history |
| POST | `/api/select` | Set one kid's selection (JSON body: `{kid_id, menu_date, selection}`) |
| POST | `/api/send-day` | Send a day to Skylight (JSON body: `{menu_date}`) |
| GET | `/api/admin` | Source-unique, Display Text-resolved catalog plus sync attempts and last success |
| POST | `/api/admin/override` | Set/clear permanent display override (`{original, replacement}`) |
| POST | `/api/admin/sync` | Trigger immediate 4-week menu sync |
| POST | `/api/admin/llm-case-all` | Run all unique menu items through `agy` (`gemini-3.6-flash-low`) AI casing |
| GET | `/api/health` | `{"status": "ok"}` |

## Domain model (quick)

- **Kid** — has `id`, `name`, `color`, `prefix` (e.g. `"P-"`, `"K-"`). Prefix is backfilled in `init_db` so every kid has one.
- **Selection** — `(kid_id, menu_date)` → `{selection, sent_at, sent_sitting_id}`. `selection` is resolved via `resolve_display_text` (mapping raw/ALL-CAPS strings through active display overrides).
- **Display Overrides** — stored in `menu_item_overrides`. Deduplicated in Admin view; maps `original_description` (and Title Case variant) to permanent `replacement_description`.
- **Skylight Sitting** — one per (date, kid, entree). Linked to a Skylight Recipe whose `summary` is `"{prefix} {entree}"`.

## Skylight API gotchas (see `SKYLIGHT_API.md` for full detail)

- **API bug:** `list_sittings` with `date_min == date_max` returns empty data. Always query a 2-day window and filter in-process.
- **JSON:API shape:** Sitting fields are under `sitting.attributes["summary"]`, NOT as direct attributes. Use pyskylight's `.dates`, `.summary`, etc. properties when available.
- **Delete pattern:** Use `DELETE /meals/sittings/{id}/instances/{date}` (per-instance).
- **422 "summary must be blank" rule:** When `meal_recipe_id` is set on a sitting POST, omit `summary` entirely.
- **OAuth2 PKCE is the only working auth.**
- **Cache & rate-limit politely:** pyskylight caches the Bearer token at `~/.cache/pyskylight/token.json`.

## Display Text (critical)

One rule, one place: `menu_item_display.MenuItemDisplay.display()`. An active
override on the raw text wins, else the text is cased and an override on the
cased form is applied. Never resolve display text by reaching for
`overrides.get(...)` directly — that variant is what let the entree a Kid picked
and the Skylight recipe summary disagree (ADR-0002).

`MenuItemDisplay` is pure: no adapter, no cache, no subprocess. Casing a
complex item ("PB & J" vs. "Chikn, Rice & Beans") always uses the same
`ACRONYMS` / `TITLE_CASE_EXCEPTIONS` rules — nothing in the read or ingest path
ever shells out. If those rules stop being good enough, the Display Override
table is the intended correction mechanism: a parent pins a replacement, and a
repeated pin is the signal for what to add to the rule tables, not a reason to
consult a model per item again.

## Skylight configuration seam (critical)

`SkylightCredentials` (email, password, frame_id, base_url) is consumed only by
`skylight_login`. Routes may return `published_skylight_config()` — derived from
the credentials via `SkylightCredentials.published()`, which carries `email` and
`frame_id` and nothing else. Never put a raw credentials object, or the dict from
`skylight_menu.load_config()`, in an API response: the password used to ride along
in every `/api/week` payload. Narrowing belongs in `skylight_adapter`, not at the
call site, so tests patch `skylight_credentials` and let the published view derive.

## Pre-send wipe logic (critical)

Meal-plan Publication deletes all Lunch sittings on the date that have a stored sitting identifier or an exact configured Kid prefix before creating new ones. Loose Kid-name matching is deliberately excluded because it can claim unrelated family entries.

## Mistakes I made repeatedly (don't repeat them)

1. **Changed host code and assumed the container picked it up.** Verify the change is live with `podman exec school-cafe grep ... /app/<file>`. Rebuild container image if adding python files to `Containerfile`.
2. **Wrote defensive `getattr(obj, 'attr', '')` on pyskylight models without checking the actual shape.** Fields are under `.attributes[...]`.
3. **Made test changes without first reading the test fixture.** `FakeSkylightClient` uses flat attributes.
4. **Mounted static files BEFORE API routes.** Static mount at `/` must be registered LAST in FastAPI.
5. **Direct string comparison on ALL-CAPS API descriptions.** Always use `resolve_display_text(text, overrides)` to bridge raw SchoolCafé descriptions, Title Case variants, and user permanent overrides across dashboard, API, and Skylight sync.
6. **Mutated live production database in smoke tests.** Smoke test scripts hitting live server endpoints must record initial state and restore user selections upon completion to avoid overwriting active family data.

## Coding conventions

- Use `from __future__ import annotations` at the top of every Python file.
- Pin exact versions in `requirements.txt` and `requirements-dev.txt`.
- Deep module design (`db.py`, `menu_service.py`, `meal_plan_publication.py`) keeping router thin and domain logic isolated.
- `# noqa: BLE001` is the standard way to justify `except Exception` on a network/DB call.
- Three-phase design for DB and network I/O: read from DB, release connection, do I/O, reopen DB and write.

## Where things live

| Concern | File |
|---------|------|
| API routes & app lifespan | `backend/fastapi_app.py` |
| Database connections, schema & overrides | `backend/db.py` |
| Menu caching & override resolution | `backend/menu_service.py` |
| Display-resolved planner state | `backend/planner_readback.py` |
| Day/week Meal-plan Publication | `backend/meal_plan_publication.py` |
| Route-facing publication control | `backend/publication_control.py` |
| Skylight login & external adapter | `backend/skylight_adapter.py` |
| SchoolCafé API client & agy AI casing | `backend/school_menu.py` |
| One 4-week menu sync attempt | `backend/menu_sync.py` |
| Sunday menu-sync scheduling policy | `backend/menu_sync_schedule.py` |
| Skylight CLI helper | `backend/skylight_menu.py` |
| React SPA | `frontend/src/` |
| Tests | `backend/tests/test_*.py` |
| Container build | `backend/Containerfile` + `backend/.containerignore` |
| Optional container service | `~/.config/systemd/user/school-cafe.service` |
| Domain docs | `backend/SCHOOL_CAFE_API.md`, `backend/SKYLIGHT_API.md`, `backend/CONTAINER.md` |
