# ⭐️ Post Elementary SchoolCafé ➡️ Skylight Calendar Lunch Planner

A modern, containerized FastAPI + React web application designed for families at **Post Elementary School (CFISD)** to view weekly school lunch menus, select entrees per child per day, and sync selections to a **Skylight Calendar** as Lunch meal-plan sittings.

![Post Patriots Theme](https://img.shields.io/badge/Theme-Post_Elementary_Patriots-0F172A?style=for-the-badge&logoColor=F59E0B)
![Stack](https://img.shields.io/badge/Stack-FastAPI_%7C_React_%7C_Vite_%7C_SQLite-DC2626?style=for-the-badge)
![Container](https://img.shields.io/badge/Container-Docker_Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)

---

## ✨ Features

- 🍔 **SchoolCafé Menu Integration**: Automatically syncs weekly elementary lunch entrees directly from the SchoolCafé API.
- 📅 **Skylight Calendar Sync**: Publishes selected meals directly to your family's Skylight Frame with customized kid prefixes (`P- Brisket BBQ Sandwich`, `K- Cheese Pizza`).
- 🤖 **AI Case Normalization (`agy`)**: Uses `agy` powered by `gemini-3.6-flash-low` to normalize ALL-CAPS API descriptions into clean, food-service display names.
- ⚙️ **Deduplicated Admin Panel**: View unique menu items in a single consolidated list, search items in real time, run bulk AI recasing, and save permanent display overrides across all past and future weeks.
- ⏰ **Automated Sunday Sync**: The running application syncs **4 weeks ahead** once every Sunday at 3:00 AM Central Time.
- 🎨 **Post Patriots Aesthetics**: Dark-mode UI styled in Post Elementary Patriots school colors (Navy `#0F172A`, Patriot Red `#DC2626`, and Gold accents).

---

## 🏗️ Architecture

```
school-cafe-skylight/
├── backend/                  ← FastAPI JSON API (Python 3.14)
│   ├── fastapi_app.py        ← Router, endpoints & lifespan wiring
│   ├── db.py                 ← SQLite schema, connections, overrides & sync logs
│   ├── week_menu.py          ← Deep Week Menu read, cache & Display Text
│   ├── school_menu_source.py ← Shared School Menu Source adapter seam
│   ├── menu_catalog.py       ← Display-resolved Menu Catalog Readback
│   ├── menu_catalog_refresh.py ← Refresh, persistence, outcomes & schedule
│   ├── meal_plan_publication.py ← Shared day/week publication workflow
│   ├── publication_outcome.py ← Typed outcomes & response projection
│   ├── skylight_adapter.py     ← Skylight OAuth & pyskylight adapter
│   ├── school_menu.py        ← SchoolCafé API client & agy AI title casing
│   ├── menu_sync.py          ← Thin Menu Catalog Refresh command-line adapter
│   ├── Containerfile         ← Production multi-stage container definition
│   └── tests/                ← Pytest suite (75+ offline tests)
├── frontend/                 ← React SPA (TypeScript + Vite + Tailwind v4)
│   ├── src/pages/            ← WeekPage dashboard & AdminPage
│   ├── src/components/       ← Cell, SendButton, DaySection, HistoryPanel
│   ├── src/api/              ← Typed API client
│   └── src/hooks/            ← TanStack Query and deep Planner Interaction State
├── compose.yaml              ← Production runtime and persistence wiring
└── data/app.db               ← Host-visible SQLite database (gitignored)
```

---

## 🚀 Quick Start (Docker Compose)

### 1. Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with Docker Compose.
- Python 3.11+ (optional, for running local unit tests).

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and enter your credentials:

```powershell
Copy-Item .env.example .env
```

Edit `.env`:
```env
SKYLIGHT_EMAIL=your_email@example.com
SKYLIGHT_PASSWORD=your_skylight_password
SKYLIGHT_FRAME_ID=   # Optional: auto-detected if left blank

SCHOOL_ID=12345      # Your CFISD SchoolCafé school ID
SCHOOL_SERVING_LINE=TD Lunch Elementary
SCHOOL_MEAL_TYPE=Lunch
SCHOOL_GRADE=02
```

### 3. Build and start

```powershell
docker compose up --detach --build
docker compose ps
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/). Compose keeps the
unauthenticated service loopback-only and creates the SQLite file at
`data/app.db`. Stop the service before copying that file so SQLite can
checkpoint its write-ahead log:

```powershell
docker compose stop app
Copy-Item .\data\app.db D:\Backups\school-cafe-app.db
docker compose start app
```

See [`backend/CONTAINER.md`](backend/CONTAINER.md) for logs, updates, restore,
and Linux UID/GID guidance.

---

## ⏰ Automated Sunday 3:00 AM Sync

The FastAPI application is the sole automated scheduler. While it is running, it checks every 10 minutes and makes at most one sync attempt in the Sunday 3:00 AM America/Chicago window. No cron entry or systemd timer is needed. Failures are written to the Admin sync history; `POST /api/admin/sync` remains available for an immediate manual refresh.

---

## 🧪 Testing & Verification

Run the Python unit test suite:
```bash
cd backend
python -m pytest tests/ -v
```

Run the frontend behavior suite:
```bash
cd frontend
npm test
```

Run the container smoke tests against a running container:
```bash
python backend/tests/smoke_test.py
```

---

## 📄 License

MIT License. Designed for Post Elementary Patriots families in Cypress-Fairbanks ISD (CFISD).
