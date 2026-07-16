"""Tests for structured operational persistence."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier

from picorgftp_sql.data_store import SqliteDataStoreAdapter
from picorgftp_sql.sqlite_store import SqliteStore


def _event(
    identity: str,
    created_at: str,
    severity: str = "info",
    **overrides: object,
) -> dict[str, object]:
    event: dict[str, object] = {
        "id": identity,
        "created_at": created_at,
        "severity": severity,
        "event_type": "job.started",
        "module": "process",
        "stage": "prepare",
        "username": "alice",
        "ean": "5900000000001",
        "product_id": "product-1",
        "slot": "01",
        "job_id": "job-1",
        "correlation_id": "correlation-1",
        "summary": "Start",
        "recommended_action": "Wait",
        "details": {"step": 1},
    }
    event.update(overrides)
    return event


def test_operational_schema_and_cursor_queries(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.initialize()
    first = store.append_operational_event(
        _event("evt-1", "2026-07-16T10:00:00.000Z")
    )
    store.append_operational_event(
        {
            **first,
            "id": "evt-2",
            "created_at": "2026-07-16T10:01:00.000Z",
            "severity": "error",
            "summary": "FTP failed",
        }
    )
    store.append_operational_event(
        _event(
            "evt-3",
            "2026-07-16T10:02:00.000Z",
            "warning",
            username="bob",
            ean="5900000000002",
            job_id="job-2",
            correlation_id="correlation-2",
            module="pimcore",
            summary="Pimcore warning",
        )
    )

    error_page = store.query_operational_events(severities=("error",), limit=20)
    assert [item["id"] for item in error_page["items"]] == ["evt-2"]
    assert error_page["items"][0]["details"] == {"step": 1}
    assert "details_json" not in error_page["items"][0]
    assert error_page["next_cursor"] == ""

    first_page = store.query_operational_events(limit=2)
    assert [item["id"] for item in first_page["items"]] == ["evt-3", "evt-2"]
    assert first_page["next_cursor"]
    second_page = store.query_operational_events(cursor=first_page["next_cursor"], limit=2)
    assert [item["id"] for item in second_page["items"]] == ["evt-1"]
    assert second_page["next_cursor"] == ""

    assert [
        item["id"]
        for item in store.query_operational_events(
            username="bob",
            ean="5900000000002",
            job_id="job-2",
            module="pimcore",
            query="warning",
            since="2026-07-16T10:01:30.000Z",
        )["items"]
    ] == ["evt-3"]
    assert [
        item["id"]
        for item in store.query_operational_events(after_id="evt-1")["items"]
    ] == ["evt-3", "evt-2"]
    assert [
        item["id"]
        for item in store.query_operational_events(correlation_id="correlation-1")[
            "items"
        ]
    ] == ["evt-2", "evt-1"]


def test_event_timestamps_are_canonical_and_sort_chronologically(
    tmp_path: Path,
) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.initialize()
    store.append_operational_event(
        _event("evt-whole", "2026-07-16T10:00:00Z")
    )
    store.append_operational_event(
        _event("evt-fraction", "2026-07-16T10:00:00.999Z")
    )
    offset = store.append_operational_event(
        _event("evt-offset", "2026-07-16T12:00:00+02:00")
    )
    malformed = store.append_operational_event(
        _event("evt-malformed", "not-aTtimestampZ")
    )

    page = store.query_operational_events(
        since="2026-07-16T10:00:00.000Z", limit=20
    )
    ordered_ids = [item["id"] for item in page["items"]]
    assert ordered_ids.index("evt-fraction") < ordered_ids.index("evt-whole")
    by_id = {item["id"]: item for item in page["items"]}
    assert by_id["evt-whole"]["created_at"] == "2026-07-16T10:00:00.000Z"
    assert by_id["evt-fraction"]["created_at"] == "2026-07-16T10:00:00.999Z"
    assert offset["created_at"] == "2026-07-16T10:00:00.000Z"
    assert malformed["created_at"] != "not-aTtimestampZ"
    datetime.fromisoformat(malformed["created_at"].replace("Z", "+00:00"))


def test_equal_timestamp_cursor_uses_id_tie_breaker_and_handles_bad_cursor(
    tmp_path: Path,
) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.initialize()
    for identity in ("evt-a", "evt-b", "evt-c"):
        store.append_operational_event(
            _event(identity, "2026-07-16T10:00:00.000Z")
        )

    first = store.query_operational_events(limit=2)
    second = store.query_operational_events(cursor=first["next_cursor"], limit=2)
    malformed = store.query_operational_events(cursor="not-base64!", limit=200)

    assert [item["id"] for item in first["items"]] == ["evt-c", "evt-b"]
    assert [item["id"] for item in second["items"]] == ["evt-a"]
    assert [item["id"] for item in malformed["items"]] == [
        "evt-c",
        "evt-b",
        "evt-a",
    ]


def test_job_and_incident_roundtrips_use_descending_cursors(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.initialize()
    first_job = store.upsert_job_run(
        {
            "id": "job-1",
            "username": "alice",
            "ean": "5900000000001",
            "status": "running",
            "summary": "Preparing",
            "started_at": "2026-07-16T10:00:00.000Z",
            "stages": [{"name": "prepare", "status": "running"}],
            "details": {"files": 2},
        }
    )
    store.upsert_job_run(
        {
            **first_job,
            "status": "completed",
            "finished_at": "2026-07-16T10:03:00.000Z",
        }
    )
    store.upsert_job_run(
        {
            "id": "job-2",
            "status": "failed",
            "started_at": "2026-07-16T10:02:00.000Z",
        }
    )
    jobs = store.query_job_runs(limit=1)
    assert [item["id"] for item in jobs["items"]] == ["job-2"]
    assert jobs["next_cursor"]
    older_jobs = store.query_job_runs(cursor=jobs["next_cursor"], limit=1)
    assert older_jobs["items"][0]["id"] == "job-1"
    assert older_jobs["items"][0]["stages"][0]["name"] == "prepare"
    assert older_jobs["items"][0]["details"] == {"files": 2}

    first_incident = store.upsert_incident(
        {
            "id": "inc-1",
            "fingerprint": "ftp-failed",
            "severity": "error",
            "event_type": "ftp.failed",
            "first_seen_at": "2026-07-16T10:00:00.000Z",
            "last_seen_at": "2026-07-16T10:00:00.000Z",
            "first_event_id": "evt-1",
            "latest_event_id": "evt-1",
            "job_id": "job-1",
            "context": {"host": "ftp.example.com"},
        }
    )
    store.upsert_incident(
        {
            **first_incident,
            "last_seen_at": "2026-07-16T10:01:00.000Z",
            "latest_event_id": "evt-2",
            "occurrence_count": 2,
        }
    )
    store.upsert_incident(
        {
            "id": "inc-2",
            "fingerprint": "disk-full",
            "severity": "critical",
            "event_type": "disk.full",
            "first_seen_at": "2026-07-16T10:02:00.000Z",
            "last_seen_at": "2026-07-16T10:02:00.000Z",
            "first_event_id": "evt-3",
            "latest_event_id": "evt-3",
        }
    )

    found = store.find_open_incident("ftp-failed")
    assert found is not None
    assert found["occurrence_count"] == 2
    assert found["context"] == {"host": "ftp.example.com"}
    incidents = store.query_incidents(severity="error", limit=1)
    assert [item["id"] for item in incidents["items"]] == ["inc-1"]
    assert incidents["next_cursor"] == ""


def test_atomic_incident_coalescing_across_store_connections(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite"
    stores = [SqliteStore(str(db_path)), SqliteStore(str(db_path))]
    for store in stores:
        store.initialize()
    barrier = Barrier(2)

    def coalesce(index: int) -> dict[str, object]:
        barrier.wait()
        return stores[index].coalesce_incident(
            {
                "id": f"inc-{index}",
                "fingerprint": "same-failure",
                "severity": "error",
                "event_type": "ftp.failed",
                "status": "open",
                "first_seen_at": "2026-07-16T10:00:00.000Z",
                "last_seen_at": "2026-07-16T10:00:00.000Z",
                "first_event_id": f"evt-{index}",
                "latest_event_id": f"evt-{index}",
                "correlation_id": f"corr-{index}",
                "notification_window_at": "2026-07-16T10:00:00.000Z",
                "context": {"attempt": index},
            }
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(coalesce, range(2)))

    stored = stores[0].find_open_incident("same-failure")
    assert stored is not None
    assert stored["occurrence_count"] == 2
    assert len({item["id"] for item in results}) == 1
    assert sorted(item["notification_due"] for item in results) == [False, True]
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM incidents WHERE fingerprint = ? AND status = 'open'",
            ("same-failure",),
        ).fetchone()[0] == 1


def test_unread_alert_markers_are_per_user_and_severity(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.initialize()
    store.append_operational_event(
        _event("evt-warning", "2026-07-16T10:00:00.000Z", "warning")
    )
    store.append_operational_event(
        _event("evt-error", "2026-07-16T10:01:00.000Z", "error")
    )
    store.append_operational_event(
        _event("evt-critical", "2026-07-16T10:02:00.000Z", "critical")
    )

    assert store.unread_alert_summary("alice") == {
        "warning": 1,
        "error": 1,
        "critical": 1,
        "total": 3,
        "highest": "critical",
    }
    store.mark_alerts_read(
        "alice", "error", "evt-error", "2026-07-16T10:01:00.000Z"
    )
    assert store.unread_alert_summary("alice")["error"] == 0
    assert store.unread_alert_summary("bob")["error"] == 1


def test_alert_read_marker_does_not_regress_to_an_older_event(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite"
    store = SqliteStore(str(db_path))
    store.initialize()
    store.append_operational_event(
        _event("evt-old", "2026-07-16T10:00:00.000Z", "error")
    )
    store.append_operational_event(
        _event("evt-new", "2026-07-16T10:01:00.000Z", "error")
    )

    store.mark_alerts_read(
        "alice", "error", "evt-new", "2026-07-16T10:01:00.000Z"
    )
    store.mark_alerts_read(
        "alice", "error", "evt-old", "2026-07-16T10:00:00.000Z"
    )
    store.mark_alerts_read(
        "alice", "error", "evt-aaa", "2026-07-16T10:01:00.000Z"
    )

    assert store.unread_alert_summary("alice")["error"] == 0
    with sqlite3.connect(db_path) as conn:
        marker = conn.execute(
            """
            SELECT event_id, created_at FROM alert_reads
            WHERE username = 'alice' AND severity = 'error'
            """
        ).fetchone()
    assert marker == ("evt-new", "2026-07-16T10:01:00.000Z")


def test_prune_and_clear_operational_data_preserve_web_history(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.initialize()
    store.append_history(
        {"id": "history-1", "created_at": "2026-07-15T09:00:00.000Z"}
    )
    store.append_operational_event(
        _event("evt-old", "2026-07-15T09:59:59.999Z")
    )
    store.append_operational_event(
        _event("evt-boundary", "2026-07-15T10:00:00.000Z")
    )
    store.append_operational_event(
        _event("evt-warning", "2026-07-15T09:00:00.000Z", "warning")
    )
    store.upsert_job_run(
        {"id": "job-1", "status": "running", "started_at": "2026-07-16T10:00:00.000Z"}
    )
    store.upsert_incident(
        {
            "id": "inc-1",
            "fingerprint": "failure",
            "severity": "warning",
            "event_type": "job.warning",
            "first_seen_at": "2026-07-16T10:00:00.000Z",
            "last_seen_at": "2026-07-16T10:00:00.000Z",
            "first_event_id": "evt-warning",
            "latest_event_id": "evt-warning",
        }
    )
    store.mark_alerts_read(
        "alice", "warning", "evt-warning", "2026-07-15T09:00:00.000Z"
    )

    assert store.prune_info_events("2026-07-15T10:00:00.000Z") == 1
    assert [
        item["id"] for item in store.query_operational_events(limit=20)["items"]
    ] == ["evt-boundary", "evt-warning"]

    assert store.clear_operational_data() == {
        "operational_events": 2,
        "job_runs": 1,
        "incidents": 1,
        "alert_reads": 1,
    }
    assert store.load_history()[0]["id"] == "history-1"


def test_sqlite_adapter_delegates_observability_repository(tmp_path: Path) -> None:
    adapter = SqliteDataStoreAdapter(str(tmp_path / "app.sqlite"))
    adapter.append_operational_event(
        _event("evt-1", "2026-07-16T10:00:00.000Z", "error")
    )
    assert adapter.query_operational_events(severities=("error",))["items"][0][
        "id"
    ] == "evt-1"
    assert adapter.query_operational_events(correlation_id="correlation-1")[
        "items"
    ][0]["id"] == "evt-1"


def test_sqlite_adapter_delegates_atomic_incident_coalescing(tmp_path: Path) -> None:
    adapter = SqliteDataStoreAdapter(str(tmp_path / "app.sqlite"))

    incident = adapter.coalesce_incident(
        {
            "id": "inc-1",
            "fingerprint": "failure",
            "severity": "error",
            "event_type": "ftp.failed",
            "first_seen_at": "2026-07-16T10:00:00.000Z",
            "last_seen_at": "2026-07-16T10:00:00.000Z",
            "first_event_id": "evt-1",
            "latest_event_id": "evt-1",
            "notification_window_at": "2026-07-16T10:00:00.000Z",
        }
    )

    assert incident["id"] == "inc-1"
    assert incident["notification_due"] is True
