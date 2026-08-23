# Container Guide

Build and run the FastAPI + React app as a rootless Podman container on Fedora.

---

## 1. Development Mode (with Live Hot-Reloading)

To edit Python code (`backend/*.py`) and have changes reflect instantly without rebuilding the container, bind-mount the source files and pass `--reload` to uvicorn:

```bash
podman run -d \
  --name school-cafe \
  --userns=keep-id \
  -p 127.0.0.1:8000:8000 \
  -v "$HOME/.cache/pyskylight:/home/app/.cache/pyskylight:z" \
  -v "$PWD/backend/.env:/app/.env:z" \
  -v "$PWD/backend/app.db:/app/app.db:z" \
  -v "$PWD/backend/fastapi_app.py:/app/fastapi_app.py:z" \
  -v "$PWD/backend/db.py:/app/db.py:z" \
  -v "$PWD/backend/menu_service.py:/app/menu_service.py:z" \
  -v "$PWD/backend/meal_plan_publication.py:/app/meal_plan_publication.py:z" \
  -v "$PWD/backend/skylight_adapter.py:/app/skylight_adapter.py:z" \
  -v "$PWD/backend/school_menu.py:/app/school_menu.py:z" \
  -v "$PWD/backend/skylight_menu.py:/app/skylight_menu.py:z" \
  -v "$PWD/backend/menu_sync.py:/app/menu_sync.py:z" \
  school-cafe-skylight:latest \
  uvicorn fastapi_app:app --host 0.0.0.0 --port 8000 --reload
```

For frontend development, run the Vite dev server separately:

```bash
cd frontend && npm run dev
# Vite serves the SPA on :5173 and proxies /api to :8000
```

---

## 2. Production Mode (Standalone / Self-Contained)

The multi-stage Containerfile builds the React SPA (Node stage) and the Python API (Python stage) into one image:

```bash
# Build image
podman build \
  --build-arg UID=$(id -u) --build-arg GID=$(id -g) \
  -t school-cafe-skylight:latest \
  -f backend/Containerfile .

# Run container
podman run -d \
  --name school-cafe \
  --userns=keep-id \
  -p 127.0.0.1:8000:8000 \
  -v "$HOME/.cache/pyskylight:/home/app/.cache/pyskylight:z" \
  -v "$PWD/backend/.env:/app/.env:z" \
  school-cafe-skylight:latest
```

The image serves both the API (`/api/*`) and the built SPA (`/` and `/admin`) on port 8000.

---

## 3. Operations & Management

```bash
# Check status / logs
podman logs -f school-cafe
curl -s http://127.0.0.1:8000/api/health

# Restart / stop / remove
podman restart school-cafe
podman stop    school-cafe
podman rm      school-cafe
```

---

## Key Container Flags Explained

| Flag | Why |
| :--- | :--- |
| `--userns=keep-id` | Maps in-container UID 1000 to host UID so bind-mounted files remain writable on host. |
| `-p 127.0.0.1:8000:8000` | Publishes the port to **loopback only**. See the security note below. |
| `:z` volume suffix | Required SELinux relabeling on Fedora/RHEL to grant container read/write access. |
| `--reload` | Instructs Uvicorn (using `watchfiles`) to auto-reload on file edits. |

---

## Security note: keep it on loopback

The app has **no authentication and no CSRF protection**, and it can write to
your real Skylight calendar. It is only safe because nothing off this machine
can reach it.

`uvicorn --host 0.0.0.0` inside the container is correct and necessary - that
binds all interfaces *within the container's own network namespace*. What
controls real exposure is how the port is published:

- `-p 127.0.0.1:8000:8000` - reachable only from this machine. **Use this.**
- `-p 8000:8000` - reachable from anywhere on your LAN.
- `--network host` - the container shares the host's namespace, so
  `--host 0.0.0.0` binds every real interface. Also reachable from your LAN.

The last two hand anyone on your network the ability to change what your kids
are eating. If you genuinely need remote access, put the app behind a reverse
proxy that authenticates first, and add CSRF tokens before doing so.
