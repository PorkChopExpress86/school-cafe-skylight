# Docker Compose Guide

Docker Compose is the production runtime for the FastAPI API and bundled React
SPA. The service is intentionally published only on `127.0.0.1:8000` because
the application has no authentication or CSRF protection and can write to a
real Skylight calendar.

## Start

Create the environment file once, then build and start the service:

```powershell
Copy-Item .env.example .env
docker compose up --detach --build
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Compose injects `.env` into the service, persists the pyskylight token cache in
a named volume, and sets `DATABASE_PATH=/data/app.db`. The repository's `data`
directory is bind-mounted at `/data`, making the database directly available
on the host as `data/app.db`.

On Linux hosts whose user is not UID/GID 1000, set the build identity in `.env`
before building:

```env
CONTAINER_UID=1001
CONTAINER_GID=1001
```

## Operate

```powershell
docker compose logs --follow app
docker compose restart app
docker compose stop app
docker compose start app
docker compose down
```

`docker compose down` removes the container and network, but it does not remove
`data/app.db` or the pyskylight cache volume. Do not add `--volumes` unless you
intend to discard the cached Skylight login.

## Back up and restore SQLite

Stop the service before copying the database so SQLite checkpoints its WAL and
the copied file is self-contained:

```powershell
docker compose stop app
Copy-Item .\data\app.db D:\Backups\school-cafe-app.db
docker compose start app
```

To restore, stop the service, keep a safety copy of the current file, copy the
backup into `data/app.db`, then start and verify health:

```powershell
docker compose stop app
Copy-Item .\data\app.db .\data\app.db.before-restore
Copy-Item D:\Backups\school-cafe-app.db .\data\app.db
docker compose start app
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

## Development

Run the API and frontend directly for hot reload; Compose represents the
production-shaped runtime:

```powershell
Set-Location backend
uvicorn lunch_planner.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
Set-Location frontend
npm.cmd run dev
```

Vite serves the SPA on port 5173 and proxies `/api` to port 8000.

## Security boundary

Keep the host mapping as `127.0.0.1:8000:8000`. Publishing `8000:8000` exposes
the unauthenticated write API to the local network. Remote access requires an
authenticating reverse proxy and CSRF protection first.
