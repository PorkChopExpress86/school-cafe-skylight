# ⭐️ Post Elementary SchoolCafé ➡️ Skylight Calendar Lunch Planner

A modern, containerized FastAPI + React web application designed for families at **Post Elementary School (CFISD)** to view weekly school lunch menus, select entrees per child per day, and sync selections to a **Skylight Calendar** as Lunch meal-plan sittings.

![Post Patriots Theme](https://img.shields.io/badge/Theme-Post_Elementary_Patriots-0F172A?style=for-the-badge&logoColor=F59E0B)
![Stack](https://img.shields.io/badge/Stack-FastAPI_%7C_React_%7C_Vite_%7C_SQLite-DC2626?style=for-the-badge)
![Container](https://img.shields.io/badge/Container-Podman-0052CC?style=for-the-badge)

---

## ✨ Features

- 🍔 **SchoolCafé Menu Integration**: Automatically syncs weekly elementary lunch entrees directly from the SchoolCafé API.
- 📅 **Skylight Calendar Sync**: Publishes selected meals directly to your family's Skylight Frame with customized kid prefixes (`P- Brisket BBQ Sandwich`, `K- Cheese Pizza`).
- 🤖 **AI Case Normalization (`agy`)**: Uses `agy` powered by `gemini-3.6-flash-low` to normalize ALL-CAPS API descriptions into clean, food-service display names.
- ⚙️ **Deduplicated Admin Panel**: View unique menu items in a single consolidated list, search items in real time, run bulk AI recasing, and save permanent display overrides across all past and future weeks.
- ⏰ **Automated Sunday Cron Sync**: Automatically syncs **4 weeks ahead** every Sunday at 3:00 AM via cron and an internal lifespan background scheduler.
- 🎨 **Post Patriots Aesthetics**: Dark-mode UI styled in Post Elementary Patriots school colors (Navy `#0F172A`, Patriot Red `#DC2626`, and Gold accents).

---

## 🏗️ Architecture

```
school-cafe-skylight/
├── backend/                  ← FastAPI JSON API (Python 3.14)
│   ├── fastapi_app.py        ← Router, endpoints & background lifespan scheduler
│   ├── db.py                 ← SQLite schema, connections, overrides & sync logs
│   ├── menu_service.py       ← SchoolCafé config, in-memory caching & override resolution
│   ├── skylight_service.py    ← Skylight OAuth, recipe summary formatting & sitting matching
│   ├── school_menu.py        ← SchoolCafé API client & agy AI title casing
│   ├── menu_sync.py          ← 4-week menu sync CLI & retry loop
│   ├── Containerfile         ← Production multi-stage Podman container definition
│   └── tests/                ← Pytest suite (75+ offline tests)
├── frontend/                 ← React SPA (TypeScript + Vite + Tailwind v4)
│   ├── src/pages/            ← WeekPage dashboard & AdminPage
│   ├── src/components/       ← Cell, SendButton, DaySection, HistoryPanel
│   └── src/api/              ← Typed API client & TanStack Query hooks
└── scripts/                  ← systemd user units
```

---

## 🚀 Quick Start (Podman Container)

### 1. Prerequisites
- [Podman](https://podman.io/) or Docker installed.
- Python 3.11+ (optional, for running local unit tests).

### 2. Configure Environment Variables
Copy `.env.example` to `backend/.env` and enter your credentials:

```bash
cp .env.example backend/.env
```

Edit `backend/.env`:
```env
SKYLIGHT_EMAIL=your_email@example.com
SKYLIGHT_PASSWORD=your_skylight_password
SKYLIGHT_FRAME_ID=   # Optional: auto-detected if left blank

SCHOOL_ID=12345      # Your CFISD SchoolCafé school ID
SCHOOL_SERVING_LINE=TD Lunch Elementary
SCHOOL_MEAL_TYPE=Lunch
SCHOOL_GRADE=02
```

### 3. Build & Run Container
Build the container image:
```bash
podman build --build-arg UID=$(id -u) --build-arg GID=$(id -g) -t school-cafe-skylight:latest -f backend/Containerfile .
```

Start the container daemon:
```bash
podman run -d \
  --name school-cafe \
  --userns=keep-id \
  -p 127.0.0.1:8000:8000 \
  -v "$HOME/.cache/pyskylight:/home/app/.cache/pyskylight:z" \
  -v "$PWD/backend/.env:/app/.env:z" \
  -v "$PWD/backend/app.db:/app/app.db:z" \
  school-cafe-skylight:latest
```

Open your browser and navigate to:
👉 **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

---

## ⏰ Automated Sunday 3:00 AM Cronjob

To automatically sync the next 4 weeks of menus every Sunday at 3:00 AM, add this entry to your user crontab (`crontab -e`):

```cron
0 3 * * 0 podman exec school-cafe python menu_sync.py >> $HOME/dev/school-cafe-skylight/backend/sync.log 2>&1
```

---

## 🧪 Testing & Verification

Run the Python unit test suite:
```bash
cd backend
python -m pytest tests/ -v
```

Run the container smoke tests against a running container:
```bash
python backend/tests/smoke_test.py
```

---

## 📄 License

MIT License. Designed for Post Elementary Patriots families in Cypress-Fairbanks ISD (CFISD).
