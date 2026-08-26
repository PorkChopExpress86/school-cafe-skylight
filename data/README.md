# Runtime data

Docker Compose bind-mounts this directory at `/data`. The application creates
the SQLite database as `app.db`, so the host-visible file is `data/app.db`.

Stop the application before copying the database so SQLite's WAL is fully
checkpointed:

```powershell
docker compose stop app
Copy-Item .\data\app.db D:\Backups\school-cafe-app.db
docker compose start app
```

Database files in this directory are intentionally ignored by Git.
