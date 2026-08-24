"""Tests for the Skylight configuration seam.

Credentials and the published view are two interfaces behind one seam: the
password is needed to log in and must never reach a route response.
"""

from __future__ import annotations

import json

from skylight_adapter import SkylightCredentials


class TestPublishedView:
    def test_published_view_carries_only_email_and_frame_id(self):
        credentials = SkylightCredentials(
            email="parent@example.com",
            password="hunter2",
            frame_id="frame-1",
            base_url="https://app.ourskylight.com",
        )
        assert credentials.published() == {
            "email": "parent@example.com",
            "frame_id": "frame-1",
        }

    def test_published_view_omits_the_password_even_when_set(self):
        credentials = SkylightCredentials(
            email="parent@example.com",
            password="hunter2",
            frame_id="frame-1",
            base_url="",
        )
        assert "hunter2" not in json.dumps(credentials.published())


class TestWeekPayload:
    def test_week_response_never_carries_the_skylight_password(self, client):
        """The fixture's credentials carry a password; the wire must not."""
        response = client.get("/api/week")
        assert response.status_code == 200
        assert "secret" not in response.text

    def test_week_response_still_reports_email_and_frame_id(self, client):
        payload = client.get("/api/week").json()
        assert payload["skylight_cfg"] == {
            "email": "test@example.com",
            "frame_id": "frame-1",
        }
