import threading
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest

from picorgftp_sql import storage_settings
from picorgftp_sql import data_store
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


def test_reset_active_store_cache_clears_a_concurrent_active_store_creation(
    tmp_path, monkeypatch
):
    database_path = str(tmp_path / "concurrent.sqlite")
    construction_started = threading.Event()
    allow_construction = threading.Event()

    class InterleavingRegistryLock:
        def __init__(self, lock):
            self._lock = lock
            self.active_thread_id = None
            self.reset_attempted = threading.Event()
            self.reset_holds_lock = threading.Event()
            self.allow_reset = threading.Event()

        def __enter__(self):
            is_reset = (
                self.active_thread_id is not None
                and threading.get_ident() != self.active_thread_id
                and not self.reset_attempted.is_set()
            )
            if is_reset:
                self.reset_attempted.set()
            self._lock.acquire()
            if is_reset:
                self.reset_holds_lock.set()
                assert self.allow_reset.wait(timeout=5)
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self._lock.release()

    class BlockingAdapter:
        mode = storage_settings.DATA_MODE_SQLITE

        def __init__(self, path):
            lock.active_thread_id = threading.get_ident()
            construction_started.set()
            assert allow_construction.wait(timeout=5)
            self.store = get_sqlite_store(path)

    reset_active_store_cache()
    lock = InterleavingRegistryLock(data_store._STORE_REGISTRY_LOCK)
    monkeypatch.setattr(data_store, "_STORE_REGISTRY_LOCK", lock)
    monkeypatch.setattr(data_store, "SqliteDataStoreAdapter", BlockingAdapter)
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

    with ThreadPoolExecutor(max_workers=2) as pool:
        stale_adapter = pool.submit(get_active_store)
        assert construction_started.wait(timeout=5)
        reset = pool.submit(reset_active_store_cache)
        assert lock.reset_attempted.wait(timeout=5)
        allow_construction.set()
        assert lock.reset_holds_lock.wait(timeout=5)
        lock.allow_reset.set()
        stale_adapter = stale_adapter.result(timeout=5)
        reset.result(timeout=5)

    try:
        assert get_active_store() is not stale_adapter
    finally:
        reset_active_store_cache()
