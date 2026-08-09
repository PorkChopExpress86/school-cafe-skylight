# Container

Build and run the FastAPI app as a rootless Podman container on Fedora.

```bash
```bash
# One-time build (pass your host UID/GID so the in-container user
# matches yours exactly -- no orphan files, no permission surprises)
podman build \
  --build-arg UID=$(id -u) --build-arg GID=$(id -g) \
  -t school-cafe-skylight:latest .

# Run (port 8000, host network, bind-mounted .env + token cache)
podman run -d \
  --name school-cafe \
  --userns=keep-id \
  --network host \
  -v "$HOME/.cache/pyskylight:/home/app/.cache/pyskylight:z" \
  -v "$PWD/.env:/app/.env:z" \
  school-cafe-skylight:latest

# Verify
curl -sI http://127.0.0.1:8000/health   # -> 200 ok
curl -s  "http://127.0.0.1:8000/?date=2026-08-12" | grep -c 'Cheese Pizza'
```

Open http://127.0.0.1:8000/ in a browser.

## Restart / stop

```bash
podman restart school-cafe
podman stop    school-cafe
podman rm      school-cafe
```

## Why these flags

## Why these flags

| Flag | Why |
|------|-----|
| `--userns=keep-id` | Map the in-container UID 1000 (the `app` user) to your host UID so bind-mounted files are writable |
| `--network host` | Container listens on the host's port 8000 directly (no `-p` needed with host netns) |
| `:z` on each volume | SELinux relabel — required on Fedora for bind mounts; without it you get `Permission denied` even as root |
| `--name school-cafe` | Stable name so `restart`/`logs`/`rm` are easy |
| `-d` | Detached; logs go to `podman logs school-cafe` |

## OAuth token

`pyskylight` writes its session token to `~/.cache/pyskylight/token.json` after the first login. We bind-mount that path into the container so subsequent restarts reuse the cached token. If you ever delete the container, your token survives — just don't `rm -rf ~/.cache/pyskylight`.

## What's in the image

- Python 3.12-slim base
- `git` (only needed at build time to install `pyskylight` from GitHub)
- `fastapi`, `uvicorn[standard]`, `jinja2`, `python-dotenv`, `python-multipart`, `pyskylight`
- The four source files (`fastapi_app.py`, `school_menu.py`, `skylight_menu.py`, plus `templates/` and `static/`)

`.env` and `app.db` are *not* baked in — they're bind-mounted at run time so your secrets and data stay on the host.
