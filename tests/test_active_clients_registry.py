from __future__ import annotations

import json
import threading

from picorgftp_sql.web import active_clients
from picorgftp_sql.web.active_clients import ActiveClientRegistry


def client_record(username: str, generation: int) -> dict[str, object]:
    return {
        "username": username,
        "client_id": f"browser-{generation}",
        "last_seen_epoch": float(generation),
        "last_seen": "2026-07-27 10:00:00",
        "method": "GET",
        "path": "/",
        "status_code": 200,
        "remote_address": "127.0.0.1",
        "remote_port": 12345,
        "user_agent": "test",
    }


def test_writer_serializes_without_holding_registry_lock(tmp_path):
    lock_was_free = []

    def serializer(payload):
        acquired = registry.acquire_lock_for_test(blocking=False)
        lock_was_free.append(acquired)
        if acquired:
            registry.release_lock_for_test()
        return json.dumps(payload)

    registry = ActiveClientRegistry(tmp_path / "active.json", serializer=serializer)
    try:
        registry.record(client_record("alice", generation=1))
        registry.flush(force=True)
    finally:
        registry.close(timeout=5.0)

    assert lock_was_free == [True]


def test_writer_replaces_file_without_holding_registry_lock(tmp_path, monkeypatch):
    lock_was_free = []
    real_replace = active_clients.os.replace

    def replace(source, destination):
        acquired = registry.acquire_lock_for_test(blocking=False)
        lock_was_free.append(acquired)
        if acquired:
            registry.release_lock_for_test()
        real_replace(source, destination)

    monkeypatch.setattr(active_clients.os, "replace", replace)
    registry = ActiveClientRegistry(tmp_path / "active.json")
    try:
        registry.record(client_record("alice", generation=1))
        registry.flush(force=True)
    finally:
        registry.close(timeout=5.0)

    assert lock_was_free == [True]


def test_generation_change_during_io_schedules_one_follow_up_flush(tmp_path):
    write_started = threading.Event()
    release_write = threading.Event()
    serialized_payloads: list[list[dict[str, object]]] = []

    def serializer(payload):
        serialized_payloads.append(payload)
        if len(serialized_payloads) == 1:
            write_started.set()
            assert release_write.wait(timeout=5.0)
        return json.dumps(payload)

    path = tmp_path / "active.json"
    registry = ActiveClientRegistry(path, serializer=serializer)
    try:
        registry.record(client_record("alice", generation=1))
        registry.schedule_flush(force=True)
        assert write_started.wait(timeout=5.0)

        registry.record(client_record("bob", generation=2))
        release_write.set()
        registry.flush(force=True)
    finally:
        release_write.set()
        registry.close(timeout=5.0)

    assert len(serialized_payloads) == 2
    assert {item["username"] for item in serialized_payloads[-1]} == {"alice", "bob"}
    assert {item["username"] for item in json.loads(path.read_text(encoding="utf-8"))} == {
        "alice",
        "bob",
    }


def test_force_flush_bypasses_minimum_ordinary_interval(tmp_path):
    now = [100.0]
    serialized_payloads = []

    def serializer(payload):
        serialized_payloads.append(payload)
        return json.dumps(payload)

    registry = ActiveClientRegistry(
        tmp_path / "active.json",
        serializer=serializer,
        flush_interval_seconds=1.0,
        clock=lambda: now[0],
    )
    try:
        registry.record(client_record("alice", generation=1))
        assert registry.flush(force=True)

        now[0] = 114.0
        registry.record(client_record("bob", generation=2))
        assert not registry.schedule_flush()
        assert len(serialized_payloads) == 1

        assert registry.flush(force=True)
    finally:
        registry.close(timeout=5.0)

    assert len(serialized_payloads) == 2


def test_first_ordinary_flush_is_not_delayed_by_interval(tmp_path):
    path = tmp_path / "active.json"
    registry = ActiveClientRegistry(path, clock=lambda: 0.0)
    try:
        registry.record(client_record("alice", generation=1))
        assert registry.schedule_flush()
        assert registry.flush(force=True)
    finally:
        registry.close(timeout=5.0)

    assert path.exists()


def test_record_with_request_time_prunes_expired_clients_before_scheduling(tmp_path):
    path = tmp_path / "active.json"
    registry = ActiveClientRegistry(path, max_age_seconds=180.0)
    try:
        registry.record(client_record("stale", generation=1))
        registry.record(client_record("fresh", generation=1000), now=1000.0)
        registry.flush(force=True)
    finally:
        registry.close(timeout=5.0)

    assert [item["username"] for item in json.loads(path.read_text(encoding="utf-8"))] == [
        "fresh"
    ]
