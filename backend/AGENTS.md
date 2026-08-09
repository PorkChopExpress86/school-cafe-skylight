# Agent Skills — school-cafe-skylight

This file documents conventions, pitfalls, and operating notes for AI agents working in this repo. Keep it short; link out to deeper docs when a topic grows.

## Project overview

A FastAPI JSON API + React SPA that fetches weekly lunch menus from SchoolCafé, lets a parent pick an entree per kid per day, and syncs the picks to a Skylight Calendar as Lunch meal-plan sittings. Single-user, loopback-only, no auth (by design — see `CONTAINER.md` security note).

## Architecture

```
school-cafe-skylight/
├── backend/          ← FastAPI JSON API (Python)
│   ├── fastapi_app.py   ← API routes + business logic
│   ├── school_menu.py   ← SchoolCafé client + case formatting
│   ├── skylight_menu.py ← Skylight config loader
│   ├── menu_sync.py     ← weekly menu sync + DB helpers
│   ├── tests/           ← pytest suite (offline)
│   └── app.db           ← SQLite (gitignored)
├── frontend/         ← React SPA (TypeScript)
│   ├── src/api/         ← typed API client
│   ├── src/hooks/       ← TanStack Query hooks
│   ├── src/components/  ← Cell, SendButton, HistoryPanel, DaySection
│   ├── src/pages/       ← WeekPage, AdminPage
│   └── vite.config.ts   ← dev proxy /api → :8000
└── scripts/          ← systemd units
```

## Operating model

- **Container is the runtime.** Local Python is for tests only; the app runs in Podman with bind-mounted source.
- **Container restarts itself** via `systemctl --user start school-cafe.service` (see `~/.config/systemd/user/school-cafe.service`). Auto-restarts on crash/reboot; explicit `podman stop` or `systemctl --user stop` sticks.
- **Image:** `localhost/school-cafe-skylight:latest`. Rebuild after `Containerfile` or `requirements*.txt` changes.
- **Frontend dev:** `cd frontend && npm run dev` (Vite on :5173, proxies /api to :8000). Production build: `npm run build` → `frontend/dist/`, served by FastAPI.

## Quick reference

| Action | Command |
|--------|---------|
| Run backend tests | `cd backend && python -m pytest tests/ -q` |
| Lint backend | `cd backend && ruff check .` |
| Type-check backend | `cd backend && mypy fastapi_app.py school_menu.py skylight_menu.py menu_sync.py` |
| Build frontend | `cd frontend && npm run build` |
| Frontend dev server | `cd frontend && npm run dev` |
| Start container | `podman start school-cafe` (or `systemctl --user start school-cafe.service`) |
| Container logs | `podman logs -f school-cafe` |
| Rebuild image | `podman build --build-arg UID=$(id -u) --build-arg GID=$(id -g) -t school-cafe-skylight:latest -f backend/Containerfile .` |

## API surface

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/week?date=YYYY-MM-DD` | Week view: menu, kids, selections, counts, history |
| POST | `/api/select` | Set one kid's selection (JSON body: `{kid_id, menu_date, selection}`) |
| POST | `/api/send-day` | Send a day to Skylight (JSON body: `{menu_date}`) |
| GET | `/api/admin` | Admin data: cached items, overrides, sync history |
| POST | `/api/admin/override` | Set/clear display override (`{original, replacement}`) |
| POST | `/api/admin/sync` | Trigger immediate menu sync |
| GET | `/api/health` | `{"status": "ok"}` |

## Domain model (quick)

- **Kid** — has `id`, `name`, `color`, `prefix` (e.g. `"P-"`, `"K-"`). Prefix is backfilled in `init_db` so every kid has one.
- **Selection** — `(kid_id, menu_date)` → `{selection, sent_at, sent_sitting_id}`. `selection` is either an entree description or the `MAKE_AT_HOME` sentinel.
- **Skylight Sitting** — one per (date, kid, entree). Linked to a Skylight Recipe whose `summary` is `"{prefix} {entree}"`.
- `sent_at` set = "this kid was included in a send" (even make-at-home). `sent_sitting_id` set = "a real Skylight sitting was created" (NULL for make-at-home).

## Skylight API gotchas (see `SKYLIGHT_API.md` for full detail)

- **API bug:** `list_sittings` with `date_min == date_max` returns empty data. Always query a 2-day window and filter in-process.
- **JSON:API shape:** Sitting fields are under `sitting.attributes["summary"]`, NOT as direct attributes. Same for `note`, `instances`, `rrule`. Use pyskylight's `.dates`, `.summary`, etc. properties when available.
- **Delete pattern:** Use `DELETE /meals/sittings/{id}/instances/{date}` (per-instance). Deleting the sitting resource itself leaves a dangling entry.
- **422 "summary must be blank" rule:** When `meal_recipe_id` is set on a sitting POST, omit `summary` entirely or the API rejects.
- **OAuth2 PKCE is the only working auth.** Basic auth (`POST /api/sessions`) is dead.
- **Cache & rate-limit politely:** pyskylight caches the Bearer token at `~/.cache/pyskylight/token.json`. On repeated 429s the cache is cleared and you must wait before retrying.

## Pre-send wipe logic (critical)

`send_day_to_skylight` deletes ALL Lunch sittings on the date that match a kid prefix or name BEFORE creating new ones. The matching (`_sitting_matches_kid_prefixes`) checks three things:
1. Recipe summary starts with one of the kid prefixes (`P-`, `K-`)
2. Recipe summary contains a kid's full name
3. Sitting's own `attributes["summary"]` or `attributes["note"]` contains a kid's full name

This catches strays from old code paths, manually-added entries, and free-form sittings with no linked recipe.

## Mistakes I made repeatedly (don't repeat them)

1. **Changed host code and assumed the container picked it up.** The container runs uvicorn with `--reload`, but it watches `/app` (the bind mount). Verify the change is live with `podman exec school-cafe grep ... /app/<file>`. If not, restart.
2. **Wrote defensive `getattr(obj, 'attr', '')` on pyskylight models without checking the actual shape.** pyskylight uses JSON:API dataclasses — fields are under `.attributes[...]`, not direct attributes. Use the model properties (`sitting.dates`, `recipe.summary`) when they exist; otherwise read `obj.attributes.get('key')`.
3. **Made test changes without first reading the test fixture.** The `FakeSkylightClient` uses flat attributes (no `.attributes` dict, no `.dates` property). Code that works with the real pyskylight shape will fail every test, and vice versa. Write helpers (`_sitting_falls_on_date`, `getattr_fallback`) that handle both shapes, OR change the fake to match reality.
4. **Assumed the `.env` was loading without checking.** The `_env_loaded` global flag and `load_dotenv` interplay is fragile. Verify with `podman exec school-cafe python3 -c "from fastapi_app import school_config; print(school_config())"`.
5. **Replaced text in the wrong occurrence (replaceAll hit).** Once I did `replaceAll` on a variable name and it mangled indentation in a different function. Always re-read the file after a multi-occurrence replace.
6. **Declared a fix "done" without running it against the live system.** After fixing the pre-send wipe, I needed to actually send to Skylight and inspect the result with `client.list_sittings` to confirm duplicates were wiped. Always close the loop with a live verification for anything that hits an external API.
7. **Mounted static files BEFORE API routes.** The SPA static mount at `/` must be registered LAST in FastAPI, or it shadows every `/api/*` route with 404s. The mount is at the bottom of `fastapi_app.py` for this reason.

## Coding conventions

- Use `from __future__ import annotations` at the top of every Python file.
- Pin exact versions in `requirements.txt` and `requirements-dev.txt`.
- Type annotations on all public functions. `mypy` is configured but not strict (`ignore_missing_imports = true`).
- `# noqa: BLE001` is the standard way to justify `except Exception` on a network/DB call.
- Three-phase design for any function that mixes DB and network: read from DB, release connection, do I/O, reopen DB and write. Never hold a SQLite write lock across a network call.
- Frontend: TypeScript strict, TanStack Query for server state, Tailwind v4 utility classes, components in `src/components/`, pages in `src/pages/`.

## Where things live

| Concern | File |
|---------|------|
| API routes, DB, Skylight sync | `backend/fastapi_app.py` |
| SchoolCafé API client | `backend/school_menu.py` |
| Skylight CLI helper | `backend/skylight_menu.py` |
| Menu sync + DB helpers | `backend/menu_sync.py` |
| React SPA | `frontend/src/` |
| Tests | `backend/tests/test_*.py` |
| Container build | `backend/Containerfile` + `backend/.containerignore` |
| systemd unit | `~/.config/systemd/user/school-cafe.service` |
| Domain docs | `backend/SCHOOL_CAFE_API.md`, `backend/SKYLIGHT_API.md`, `backend/CONTAINER.md` |
