"""Authenticated API coverage for structured observability data."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from picorgftp_sql import data_store, web_data
from picorgftp_sql.sqlite_store import SqliteStore
from picorgftp_sql.web import app as web_app


def _event(
    identity: str,
    created_at: str,
    severity: str = "info",
    *,
    event_type: str = "test.event",
    job_id: str = "",
    correlation_id: str = "",
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": identity,
        "created_at": created_at,
        "severity": severity,
        "event_type": event_type,
        "module": "tests",
        "job_id": job_id,
        "correlation_id": correlation_id,
        "summary": identity,
        "details": details or {},
    }


@pytest.fixture
def api_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    previous_auth = os.environ.get("PICORG_WEB_AUTH")
    os.environ["PICORG_WEB_AUTH"] = "1"
    database_path = tmp_path / "app.sqlite"
    monkeypatch.setattr(web_app.settings, "AC", str(tmp_path))
    monkeypatch.setattr(
        web_app.storage_settings, "resolve_sqlite_path", lambda: str(database_path)
    )
    data_store.reset_active_store_cache()
    store = SqliteStore(str(database_path))
    store.initialize()
    client = TestClient(web_app.app)
    yield client, store
    client.close()
    data_store.reset_active_store_cache()
    if previous_auth is None:
        os.environ.pop("PICORG_WEB_AUTH", None)
    else:
        os.environ["PICORG_WEB_AUTH"] = previous_auth


def _login(client: TestClient, username: str = "admin", password: str = "admin") -> str:
    response = client.post(
        "/api/login",
        data={"username": username, "password": password},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


def test_events_are_admin_only_paginated_filtered_and_validate_cursor(
    api_environment,
) -> None:
    client, store = api_environment
    for index in range(25):
        store.append_operational_event(
            _event(
                f"evt-{index:02d}",
                f"2026-07-16T10:{index:02d}:00.000Z",
                "warning" if index % 2 else "info",
            )
        )
    web_data.add_user("operator", "secret", "user")

    _login(client, "operator", "secret")
    assert client.get("/api/observability/events").status_code == 403

    client = TestClient(web_app.app)
    _login(client)
    first_page = client.get("/api/observability/events")
    assert first_page.status_code == 200
    assert len(first_page.json()["items"]) == 20
    assert first_page.json()["next_cursor"]
    assert first_page.json()["server_time"].endswith("Z")
    assert first_page.json()["unread"]["warning"] == 12

    warning_page = client.get(
        "/api/observability/events", params={"severity": "warning", "limit": 1000}
    )
    assert warning_page.status_code == 200
    assert len(warning_page.json()["items"]) == 12
    assert {item["severity"] for item in warning_page.json()["items"]} == {"warning"}
    assert client.get(
        "/api/observability/events", params={"severity": "verbose"}
    ).status_code == 400
    assert client.get(
        "/api/observability/events", params={"cursor": "not-a-cursor"}
    ).status_code == 400
    assert client.get(
        "/api/observability/events",
        params={"cursor": first_page.json()["next_cursor"] + "!"},
    ).status_code == 400
    assert client.get(
        "/api/observability/events",
        params={"cursor": " " + first_page.json()["next_cursor"]},
    ).status_code == 400
    assert client.get(
        "/api/observability/events",
        params={"cursor": first_page.json()["next_cursor"]},
    ).status_code == 200
    not_a_date = base64.urlsafe_b64encode(
        json.dumps(["not-a-date", "evt-1"]).encode("utf-8")
    ).decode("ascii").rstrip("=")
    assert client.get(
        "/api/observability/events", params={"cursor": not_a_date}
    ).status_code == 400
    for noncanonical_timestamp in (
        "2026-07-16 10:05:00.000+00:00",
        "2026-07-16T12:05:00.000+02:00",
    ):
        noncanonical = base64.urlsafe_b64encode(
            json.dumps([noncanonical_timestamp, "evt-1"]).encode("utf-8")
        ).decode("ascii").rstrip("=")
        assert client.get(
            "/api/observability/events", params={"cursor": noncanonical}
        ).status_code == 400


def test_incidents_include_only_their_correlated_context(api_environment) -> None:
    client, store = api_environment
    _login(client)
    correlated = [
        _event("evt-before", "2026-07-16T10:00:00.000Z", job_id="job-1"),
        _event(
            "evt-problem",
            "2026-07-16T10:01:00.000Z",
            "error",
            job_id="job-1",
        ),
        _event("evt-after", "2026-07-16T10:02:00.000Z", job_id="job-1"),
        _event(
            "evt-unrelated",
            "2026-07-16T10:01:30.000Z",
            "critical",
            job_id="job-2",
        ),
    ]
    for event in correlated:
        store.append_operational_event(event)
    store.upsert_incident(
        {
            "id": "inc-1",
            "fingerprint": "same-failure",
            "severity": "error",
            "event_type": "test.failure",
            "first_seen_at": "2026-07-16T10:01:00.000Z",
            "last_seen_at": "2026-07-16T10:01:00.000Z",
            "first_event_id": "evt-problem",
            "latest_event_id": "evt-problem",
            "job_id": "job-1",
        }
    )

    response = client.get("/api/observability/incidents", params={"severity": "error"})

    assert response.status_code == 200
    incident = response.json()["items"][0]
    assert [item["id"] for item in incident["before"]] == ["evt-before"]
    assert [item["id"] for item in incident["problem"]] == ["evt-problem"]
    assert [item["id"] for item in incident["after"]] == ["evt-after"]
    assert "evt-unrelated" not in response.text


def test_jobs_endpoint_returns_durable_runs_for_admin(api_environment) -> None:
    client, store = api_environment
    _login(client)
    store.upsert_job_run(
        {
            "id": "job-1",
            "username": "admin",
            "status": "completed",
            "summary": "Done",
            "started_at": "2026-07-16T10:00:00.000Z",
        }
    )

    response = client.get("/api/observability/jobs")

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "job-1"
    assert set(response.json()) == {"items", "next_cursor", "unread", "server_time"}


def test_sse_stream_is_admin_only_and_frames_events(api_environment) -> None:
    client, store = api_environment
    web_data.add_user("operator", "secret", "user")
    _login(client, "operator", "secret")
    assert client.get("/api/observability/stream").status_code == 403
    store.append_operational_event(
        _event("evt-sse", "2026-07-16T10:00:00.000Z", "warning")
    )
    endpoint = next(
        route.endpoint
        for route in web_app.app.routes
        if getattr(route, "path", "") == "/api/observability/stream"
    )

    class RequestStub:
        headers: dict[str, str] = {}

        async def is_disconnected(self) -> bool:
            return False

    async def first_frame() -> str:
        with patch.object(
            web_app,
            "_require_admin",
            return_value={"username": "admin", "role": "admin"},
        ):
            response = await endpoint(RequestStub(), after_id="")
            iterator = response.body_iterator
            frame = await anext(iterator)
            await iterator.aclose()
            return frame

    frame = asyncio.run(first_frame())
    assert frame.startswith("id: evt-sse\n")
    assert "data: {" in frame
    assert '"severity": "warning"' in frame
    assert frame.endswith("\n\n")


def test_sse_stream_yields_nothing_when_already_disconnected(api_environment) -> None:
    _client, store = api_environment
    store.append_operational_event(
        _event("evt-snapshot", "2026-07-16T10:00:00.000Z")
    )
    endpoint = next(
        route.endpoint
        for route in web_app.app.routes
        if getattr(route, "path", "") == "/api/observability/stream"
    )

    class RequestStub:
        headers: dict[str, str] = {}

        async def is_disconnected(self) -> bool:
            return True

    async def collect() -> list[str]:
        with patch.object(
            web_app,
            "_require_admin",
            return_value={"username": "admin", "role": "admin"},
        ):
            response = await endpoint(RequestStub(), after_id="")
            return [frame async for frame in response.body_iterator]

    assert asyncio.run(collect()) == []


def test_sse_stream_stops_during_initial_snapshot(api_environment) -> None:
    _client, store = api_environment
    for index in range(3):
        store.append_operational_event(
            _event(f"evt-{index}", f"2026-07-16T10:0{index}:00.000Z")
        )
    endpoint = next(
        route.endpoint
        for route in web_app.app.routes
        if getattr(route, "path", "") == "/api/observability/stream"
    )

    class RequestStub:
        headers: dict[str, str] = {}

        def __init__(self) -> None:
            self.states = iter((False, True))

        async def is_disconnected(self) -> bool:
            return next(self.states, True)

    async def collect() -> list[str]:
        with patch.object(
            web_app,
            "_require_admin",
            return_value={"username": "admin", "role": "admin"},
        ):
            response = await endpoint(RequestStub(), after_id="")
            return [frame async for frame in response.body_iterator]

    frames = asyncio.run(collect())
    assert len(frames) == 1
    assert frames[0].startswith("id: evt-0\n")


def test_sse_stream_reconnect_drains_more_than_one_page_without_duplicates(
    api_environment,
) -> None:
    client, store = api_environment
    _login(client)
    store.append_operational_event(
        _event("evt-marker", "2026-07-16T10:00:00.000Z")
    )
    expected = []
    for index in range(205):
        identity = f"evt-{index:03d}"
        expected.append(identity)
        store.append_operational_event(
            _event(identity, "2026-07-16T10:00:00.000Z")
        )
    endpoint = next(
        route.endpoint
        for route in web_app.app.routes
        if getattr(route, "path", "") == "/api/observability/stream"
    )

    class RequestStub:
        headers: dict[str, str] = {}
        calls = 0

        async def is_disconnected(self) -> bool:
            self.calls += 1
            return self.calls > 1000

    async def event_ids() -> list[str]:
        with (
            patch.object(
                web_app,
                "_require_admin",
                return_value={"username": "admin", "role": "admin"},
            ),
            patch.object(web_app.asyncio, "sleep", return_value=None),
        ):
            response = await endpoint(RequestStub(), after_id="evt-marker")
            iterator = response.body_iterator
            identities = []
            try:
                while len(identities) < len(expected):
                    frame = await anext(iterator)
                    if frame.startswith("id: "):
                        identities.append(frame.splitlines()[0][4:])
            except StopAsyncIteration:
                pass
            await iterator.aclose()
            return identities

    streamed = asyncio.run(event_ids())
    assert streamed == expected
    assert len(streamed) == len(set(streamed))


def test_sse_stream_prefers_standard_last_event_id_header(api_environment) -> None:
    client, store = api_environment
    _login(client)
    for identity in ("evt-query-marker", "evt-replayed", "evt-header-marker", "evt-next"):
        store.append_operational_event(
            _event(identity, "2026-07-16T10:00:00.000Z")
        )
    endpoint = next(
        route.endpoint
        for route in web_app.app.routes
        if getattr(route, "path", "") == "/api/observability/stream"
    )

    class RequestStub:
        headers = {"last-event-id": "evt-header-marker"}

        async def is_disconnected(self) -> bool:
            return False

    async def first_frame() -> str:
        with patch.object(
            web_app,
            "_require_admin",
            return_value={"username": "admin", "role": "admin"},
        ):
            response = await endpoint(RequestStub(), after_id="evt-query-marker")
            iterator = response.body_iterator
            frame = await anext(iterator)
            await iterator.aclose()
            return frame

    frame = asyncio.run(first_frame())
    assert frame.startswith("id: evt-next\n")
    assert "evt-replayed" not in frame


def test_mark_read_state_is_scoped_to_current_authenticated_user(api_environment) -> None:
    client, store = api_environment
    web_data.add_user("operator", "secret", "user")
    web_data.add_user("second-operator", "secret", "user")
    store.append_operational_event(
        _event("evt-warning", "2026-07-16T10:00:00.000Z", "warning")
    )
    anonymous = TestClient(web_app.app)
    assert anonymous.post(
        "/api/observability/read",
        json={
            "severity": "warning",
            "event_id": "evt-warning",
            "created_at": "2026-07-16T10:00:00.000Z",
        },
    ).status_code == 401
    csrf = _login(client, "operator", "secret")

    marked = client.post(
        "/api/observability/read",
        headers={"X-PicOrg-CSRF": csrf},
        json={
            "severity": "warning",
            "event_id": "evt-warning",
            "created_at": "2026-07-16T10:00:00.000Z",
            "username": "second-operator",
        },
    )

    assert marked.status_code == 200
    assert marked.json()["unread"]["warning"] == 0
    assert store.unread_alert_summary("operator")["warning"] == 0
    assert store.unread_alert_summary("second-operator")["warning"] == 1


def test_clear_logs_clears_operational_tables_but_preserves_audits(
    api_environment,
) -> None:
    client, store = api_environment
    csrf = _login(client)
    store.append_history(
        {"id": "history-1", "created_at": "2026-07-16T09:00:00.000Z"}
    )
    store.append_pimcore_submission(
        {
            "id": "pim-1",
            "operation_type": "create",
            "status": "success",
            "created_at": "2026-07-16T09:30:00.000Z",
        }
    )
    store.append_operational_event(
        _event("evt-1", "2026-07-16T10:00:00.000Z", "error")
    )
    store.upsert_job_run(
        {"id": "job-1", "status": "failed", "started_at": "2026-07-16T10:00:00.000Z"}
    )
    store.upsert_incident(
        {
            "id": "inc-1",
            "fingerprint": "failure",
            "severity": "error",
            "event_type": "test.failure",
            "first_seen_at": "2026-07-16T10:00:00.000Z",
            "last_seen_at": "2026-07-16T10:00:00.000Z",
            "first_event_id": "evt-1",
            "latest_event_id": "evt-1",
        }
    )
    store.mark_alerts_read("admin", "error", "evt-1", "2026-07-16T10:00:00.000Z")

    with patch.object(
        web_app, "_clear_log_files", return_value={"cleared": [], "errors": []}
    ):
        response = client.post(
            "/api/logs/clear",
            headers={"X-PicOrg-CSRF": csrf},
            json={"password": "admin"},
        )

    assert response.status_code == 200
    assert response.json()["structured_cleared"] == {
        "operational_events": 1,
        "job_runs": 1,
        "incidents": 1,
        "alert_reads": 1,
    }
    assert store.query_operational_events()["items"] == []
    assert store.query_job_runs()["items"] == []
    assert store.query_incidents()["items"] == []
    assert store.load_history()[0]["id"] == "history-1"
    assert store.query_pimcore_submissions()[0]["id"] == "pim-1"


def test_health_reports_local_components_and_last_known_integrations(
    api_environment,
) -> None:
    client, store = api_environment
    store.append_operational_event(
        _event(
            "evt-ftp",
            "2026-07-16T10:00:00.000Z",
            event_type="integration.ftp.completed",
            details={
                "status": "error",
                "error": "password=secret at C:/private/path",
            },
        )
    )
    store.append_operational_event(
        _event(
            "evt-profile",
            "2026-07-16T10:01:00.000Z",
            event_type="integration.sql_profile.completed",
            details={"status": "success", "profile_id": "catalogue"},
        )
    )

    with (
        patch.object(web_app, "test_ftp_connection", side_effect=AssertionError),
        patch.object(web_app, "test_sql_connection", side_effect=AssertionError),
        patch.object(web_app, "test_pimcore_settings", side_effect=AssertionError),
    ):
        response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload["components"]) >= {"backend", "sqlite", "job_processor"}
    assert payload["components"]["backend"]["status"] == "online"
    assert payload["components"]["sqlite"]["status"] == "online"
    assert payload["integrations"]["ftp"]["status"] == "error"
    assert payload["integrations"]["sql_profiles"] == [
        {
            "profile_id": "catalogue",
            "status": "success",
            "observed_at": "2026-07-16T10:01:00.000Z",
        }
    ]
    assert "password" not in response.text.lower()
    assert "private" not in response.text.lower()


def test_last_known_integration_stops_at_newest_unknown_status(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.append_operational_event(
        _event(
            "evt-known",
            "2026-07-16T10:00:00.000Z",
            event_type="integration.ftp.completed",
            details={"status": "success"},
        )
    )
    store.append_operational_event(
        _event(
            "evt-unknown",
            "2026-07-16T10:01:00.000Z",
            event_type="integration.ftp.completed",
            details={"status": "unexpected-status"},
        )
    )

    result = web_app._last_known_integrations(store)

    assert result["ftp"] == {
        "status": "unknown",
        "observed_at": "2026-07-16T10:01:00.000Z",
    }


def test_operational_clear_invalidates_cached_health_integrations(
    api_environment,
) -> None:
    client, store = api_environment
    csrf = _login(client)
    store.append_operational_event(
        _event(
            "evt-ftp",
            "2026-07-16T10:00:00.000Z",
            event_type="integration.ftp.completed",
            details={"status": "error"},
        )
    )
    with patch.object(web_app, "_HEALTH_INTEGRATION_CACHE_SECONDS", 3600):
        assert client.get("/api/health").json()["integrations"]["ftp"]["status"] == "error"

        with patch.object(
            web_app, "_clear_log_files", return_value={"cleared": [], "errors": []}
        ):
            response = client.post(
                "/api/logs/clear",
                headers={"X-PicOrg-CSRF": csrf},
                json={"password": "admin"},
            )

        assert response.status_code == 200
        assert client.get("/api/health").json()["integrations"]["ftp"]["status"] == "unknown"
