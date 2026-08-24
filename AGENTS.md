# Repository Guidelines

## Project Structure & Module Organization

This is a FastAPI JSON API with a React/Vite single-page application. Backend code lives in `backend/`: keep route wiring in `fastapi_app.py`, persistence in `db.py`, and domain or external-service workflows in focused modules such as `meal_plan_publication.py` and `skylight_adapter.py`. Put backend tests in `backend/tests/test_*.py`. The React app is in `frontend/src/`, organized into `api/`, `hooks/`, `components/`, and `pages/`. `scripts/` contains systemd units; generated SQLite data and built assets are ignored.

Read `backend/AGENTS.md` before changing API, persistence, Skylight publication, or container behavior: it records the domain vocabulary and ownership/security invariants.

## Build, Test, and Development Commands

- `cd backend; python -m pytest tests/ -q` runs the offline Python suite.
- `cd backend; ruff check .` checks Python lint and import ordering.
- `cd backend; mypy fastapi_app.py db.py menu_service.py meal_plan_publication.py publication_control.py skylight_adapter.py school_menu.py menu_sync.py menu_item_display.py menu_casing.py` type-checks maintained backend modules.
- `cd frontend; npm run dev` starts the Vite development server; it proxies `/api` to the backend.
- `cd frontend; npm run lint` runs Oxlint. `npm run build` type-checks, builds the SPA, and copies it to `backend/static/`.
- `docker build -t school-cafe-skylight:latest -f backend/Containerfile .` builds the production image. The running service must be reachable at `/api/health`.

Use `python backend/tests/smoke_test.py` only against a running local service; it is a manual live-data check, not a pytest test.

## Coding Style & Testing

Use four-space Python indentation, `from __future__ import annotations`, and Ruff's 120-character limit. Keep FastAPI routes thin and place I/O behind explicit adapters or workflows. Use `PascalCase` for Python classes and React components, `snake_case` for Python functions/modules, and `camelCase` for TypeScript values and hooks (for example, `useApi.ts`).

Add focused `test_*.py` coverage for behavior changes. The suite uses fixtures and fakes so it remains offline; do not introduce live SchoolCafé or Skylight calls into unit tests.

## Commits, Pull Requests, and Configuration

Recent history uses Conventional Commit-style subjects, e.g. `fix: preserve selections after smoke tests`; keep subjects imperative and scoped. Pull requests should state the behavioral change, tests run, related issue (if any), and include screenshots for UI changes.

Copy `.env.example` to `backend/.env` for local configuration. Keep credentials, token caches, `app.db`, and generated frontend assets untracked. Never return raw Skylight credentials from an API response.

## Agent skills

### Issue tracker

GitHub Issues are the issue tracker. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical labels are used. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: `CONTEXT.md` and `docs/adr/`. See `docs/agents/domain.md`.
