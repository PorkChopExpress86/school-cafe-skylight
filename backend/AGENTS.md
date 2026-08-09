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
│   ├── skylight_service.py ← Skylight OAuth login, recipe title formatting, sitting matching
│   ├── school_menu.py   ← SchoolCafé client + case formatting (agy AI integration)
│   ├── menu_sync.py     ← 4-week menu sync CLI + retry loop
│   ├── skylight_menu.py ← Skylight config loader
│   ├── tests/           ← pytest suite (offline, 75+ tests)
│   └── app.db           ← SQLite (gitignored)
├── frontend/         ← React SPA (TypeScript + Tailwind v4 + Post Patriots theme)
│   ├── src/api/         ← typed API client (getWeek, select, sendDay, getAdmin, setOverride, triggerSync, triggerLlmCasing)
│   ├── src/hooks/       ← TanStack Query hooks (useWeek, useSelect, useSendDay, useAdmin, useOverride, useSync, useLlmCasing)
│   ├── src/components/  ← Cell, SendButton, HistoryPanel, DaySection
│   ├── src/pages/       ← WeekPage, AdminPage (deduplicated Unique Items table & search)
│   └── vite.config.ts   ← dev proxy /api → :8000
└── scripts/          ← systemd units
```

## Operating model

- **Container is the runtime.** Local Python is for tests only; the app runs in Podman with bind-mounted source.
- **Container restarts itself** via `systemctl --user start school-cafe.service` (see `~/.config/systemd/user/school-cafe.service`). Auto-restarts on crash/reboot.
- **Automated Sunday 3:00 AM Sync:** Scheduled via crontab (`0 3 * * 0 podman exec school-cafe python menu_sync.py >> /home/specter/dev/school-cafe-skylight/backend/sync.log 2>&1`) and in-container background scheduler (`_sunday_sync_scheduler` in `fastapi_app.py`). Syncs 4 weeks of menus every Sunday at 3:00 AM.
- **AI Case Formatting:** Initial menu items pass through `_query_llm_for_case` via `agy -p ... --model gemini-3.6-flash-low`. On-demand bulk recasing available via Admin button (`POST /api/admin/llm-case-all`).
- **Frontend build automation:** `npm run build` runs a `postbuild` hook copying `frontend/dist` to `backend/static/`.
- **Image:** `localhost/school-cafe-skylight:latest`. Rebuild after `Containerfile` or `requirements*.txt` changes.

## Quick reference

| Action | Command |
|--------|---------|
| Run backend tests | `cd backend && python -m pytest tests/ -q` |
| Lint backend | `cd backend && ruff check .` |
| Type-check backend | `cd backend && mypy fastapi_app.py db.py menu_service.py skylight_service.py school_menu.py menu_sync.py` |
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
| GET | `/api/admin` | Admin data: cached items, overrides, sync history |
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

## Pre-send wipe logic (critical)

`send_day_to_skylight` deletes ALL Lunch sittings on the date that match a kid prefix or name BEFORE creating new ones (`_sitting_matches_kid_prefixes`).

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
- Deep module design (`db.py`, `menu_service.py`, `skylight_service.py`) keeping router thin and domain logic isolated.
- `# noqa: BLE001` is the standard way to justify `except Exception` on a network/DB call.
- Three-phase design for DB and network I/O: read from DB, release connection, do I/O, reopen DB and write.

## Where things live

| Concern | File |
|---------|------|
| API routes & app lifespan | `backend/fastapi_app.py` |
| Database connections, schema & overrides | `backend/db.py` |
| Menu caching & override resolution | `backend/menu_service.py` |
| Skylight login & recipe formatting | `backend/skylight_service.py` |
| SchoolCafé API client & agy AI casing | `backend/school_menu.py` |
| 4-week menu sync CLI + retry loop | `backend/menu_sync.py` |
| Skylight CLI helper | `backend/skylight_menu.py` |
| React SPA | `frontend/src/` |
| Tests | `backend/tests/test_*.py` |
| Container build | `backend/Containerfile` + `backend/.containerignore` |
| systemd unit | `~/.config/systemd/user/school-cafe.service` |
| Domain docs | `backend/SCHOOL_CAFE_API.md`, `backend/SKYLIGHT_API.md`, `backend/CONTAINER.md` |
