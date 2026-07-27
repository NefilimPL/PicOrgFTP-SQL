from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest

from picorgftp_sql.sqlite_store import SqliteStore


def test_initialize_runs_schema_once_for_parallel_callers(tmp_path, monkeypatch):
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    original = store._initialize_schema
    calls = 0
    calls_lock = Lock()

    def counted():
        nonlocal calls
        with calls_lock:
            calls += 1
        original()

    monkeypatch.setattr(store, "_initialize_schema", counted)
    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(lambda _index: store.initialize(), range(20)))

    assert calls == 1


def test_initialize_retries_after_schema_failure(tmp_path, monkeypatch):
    store = SqliteStore(str(tmp_path / "retry.sqlite"))
    original = store._initialize_schema
    attempts = 0

    def flaky():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("migration failed")
        original()

    monkeypatch.setattr(store, "_initialize_schema", flaky)
    with pytest.raises(RuntimeError, match="migration failed"):
        store.initialize()
    store.initialize()

    assert attempts == 2
