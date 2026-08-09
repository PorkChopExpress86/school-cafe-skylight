# Container Guide

Build and run the FastAPI app as a rootless Podman container on Fedora.

---

## 1. Development Mode (with Live Hot-Reloading)

To edit Python code (`fastapi_app.py`, `school_menu.py`, `skylight_menu.py`) or HTML templates (`templates/`) and have changes reflect **instantly without rebuilding the container**, bind-mount the source files and pass `--reload` to uvicorn:

```bash
podman run -d \
  --name school-cafe \
  --userns=keep-id \
  -p 127.0.0.1:8000:8000 \
  -v "$HOME/.cache/pyskylight:/home/app/.cache/pyskylight:z" \
  -v "$PWD/.env:/app/.env:z" \
  -v "$PWD/app.db:/app/app.db:z" \
  -v "$PWD/fastapi_app.py:/app/fastapi_app.py:z" \
  -v "$PWD/school_menu.py:/app/school_menu.py:z" \
  -v "$PWD/skylight_menu.py:/app/skylight_menu.py:z" \
  -v "$PWD/templates:/app/templates:z" \
  -v "$PWD/static:/app/static:z" \
  school-cafe-skylight:latest \
  uvicorn fastapi_app:app --host 0.0.0.0 --port 8000 --reload
```

---

## 2. Production Mode (Standalone / Self-Contained)

For a self-contained image where code files are baked into the container:

```bash
# Build image
podman build \
  --build-arg UID=$(id -u) --build-arg GID=$(id -g) \
  -t school-cafe-skylight:latest .

# Run container
podman run -d \
  --name school-cafe \
  --userns=keep-id \
  -p 127.0.0.1:8000:8000 \
  -v "$HOME/.cache/pyskylight:/home/app/.cache/pyskylight:z" \
  -v "$PWD/.env:/app/.env:z" \
  school-cafe-skylight:latest
```

---

## 3. Operations & Management

```bash
# Check status / logs
podman logs -f school-cafe
curl -sI http://127.0.0.1:8000/health

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
