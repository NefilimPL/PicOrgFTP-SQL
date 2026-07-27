from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest

from picorgftp_sql import storage_settings
from picorgftp_sql.data_store import (
    get_active_store,
    get_sqlite_store,
    reset_active_store_cache,
)
from picorgftp_sql.observability import observability_store
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


def test_get_sqlite_store_reuses_instance_for_canonical_path(tmp_path):
    first = get_sqlite_store(str(tmp_path / "." / "app.sqlite"))
    second = get_sqlite_store(str(tmp_path / "app.sqlite"))

    assert first is second


def test_get_sqlite_store_is_thread_safe(tmp_path):
    path = str(tmp_path / "parallel.sqlite")

    with ThreadPoolExecutor(max_workers=12) as pool:
        stores = list(pool.map(lambda _index: get_sqlite_store(path), range(40)))

    assert len({id(store) for store in stores}) == 1


def test_observability_store_and_active_adapter_share_instance(tmp_path, monkeypatch):
    database_path = str(tmp_path / "shared.sqlite")
    monkeypatch.setattr(
        storage_settings,
        "load_bootstrap_settings",
        lambda: {storage_settings.DATA_MODE_KEY: storage_settings.DATA_MODE_SQLITE},
    )
    monkeypatch.setattr(
        storage_settings,
        "resolve_sqlite_path",
        lambda _bootstrap=None: database_path,
    )
    reset_active_store_cache()

    try:
        active_store = get_active_store()

        assert observability_store() is active_store.store
    finally:
        reset_active_store_cache()
