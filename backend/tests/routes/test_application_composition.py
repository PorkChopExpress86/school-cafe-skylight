"""Behavior tests for application composition around feature routers."""

from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Event

from fastapi.testclient import TestClient

from lunch_planner.application import create_app
from lunch_planner.persistence.connection import get_db


class _Refresh:
    def __init__(self) -> None:
        self.started = Event()

    async def run_schedule(self, _report_failure) -> None:
        self.started.set()
        await asyncio.Event().wait()


def test_application_starts_refresh_and_serves_health_before_spa_fallback(tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    static_dir = tmp_path / "static"
    (static_dir / "assets").mkdir(parents=True)
    (static_dir / "index.html").write_text("Lunch Planner", encoding="utf-8")
    refresh = _Refresh()
    app = create_app(
        lambda: database_path,
        publication_frame_id=lambda: "frame-1",
        publication_login=object,
        report_failure=lambda _message: None,
        refresh_factory=lambda _database_path: refresh,
        static_dir=static_dir,
    )

    with TestClient(app) as client:
        assert refresh.started.wait(timeout=1)
        with get_db(database_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM kids").fetchone()[0] == 2
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/planner").text == "Lunch Planner"
