"""Active application data store resolver."""

from __future__ import annotations

from typing import Any

from . import storage_settings
from .sqlite_store import SqliteStore

_ACTIVE_STORE = None
_ACTIVE_STORE_KEY: tuple[str, str] | None = None


class LegacyDataStore:
    """Marker adapter for the existing file-backed behavior."""

    mode = storage_settings.DATA_MODE_LEGACY

    def load_config(self) -> dict[str, Any]:
        return {}

    def save_config(self, _payload: dict[str, object]) -> None:
        return None


class SqliteDataStoreAdapter:
    """Adapter exposing SQLite persistence through the active store API."""

    mode = storage_settings.DATA_MODE_SQLITE

    def __init__(self, database_path: str):
        self.database_path = database_path
        self.store = SqliteStore(database_path)
        self.store.initialize()

    def load_config(self) -> dict[str, Any]:
        return self.store.load_config()

    def save_config(self, payload: dict[str, object]) -> None:
        self.store.save_config(payload)

    def load_lists(self) -> dict[str, Any]:
        return self.store.load_lists()

    def save_lists(self, payload: dict[str, object]) -> None:
        self.store.save_lists(payload)

    def add_list_value(self, sheet: str, value: object) -> bool:
        return self.store.add_list_value(sheet, value)

    def remove_list_value(self, sheet: str, value: object) -> None:
        self.store.remove_list_value(sheet, value)

    def save_product_entry(self, payload: dict[str, object]) -> dict[str, Any]:
        return self.store.save_product_entry(payload)

    def load_users(self) -> list[dict[str, Any]]:
        return self.store.load_users()

    def save_users(self, users: list[dict[str, object]]) -> None:
        self.store.save_users(users)

    def load_history(self) -> list[dict[str, Any]]:
        return self.store.load_history()

    def save_history(self, records: list[dict[str, object]]) -> None:
        self.store.save_history(records)

    def append_history(self, record: dict[str, object]) -> None:
        self.store.append_history(record)

    def append_pimcore_submission(self, record: dict[str, object]) -> dict[str, Any]:
        return self.store.append_pimcore_submission(record)

    def query_pimcore_submissions(
        self,
        *,
        operation_type: str = "",
        status: str = "",
        user: str = "",
        query: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return self.store.query_pimcore_submissions(
            operation_type=operation_type,
            status=status,
            user=user,
            query=query,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )

    def load_file_index_cache(self) -> dict[str, Any]:
        return self.store.load_file_index_cache()

    def save_file_index_cache(self, payload: dict[str, object]) -> None:
        self.store.save_file_index_cache(payload)

    def save_file_index_segments(self, snapshot: dict[str, object]) -> int:
        return self.store.save_file_index_segments(snapshot)

    def load_file_index_segment(self, segment_key: str, section: str, lookup_key: str):
        return self.store.load_file_index_segment(segment_key, section, lookup_key)


def reset_active_store_cache() -> None:
    """Clear the cached active store, mainly for tests and runtime switches."""

    global _ACTIVE_STORE, _ACTIVE_STORE_KEY
    _ACTIVE_STORE = None
    _ACTIVE_STORE_KEY = None


def get_active_store():
    """Return the data store selected by bootstrap settings."""

    global _ACTIVE_STORE, _ACTIVE_STORE_KEY
    bootstrap = storage_settings.load_bootstrap_settings()
    mode = storage_settings.normalize_data_mode(
        bootstrap.get(storage_settings.DATA_MODE_KEY)
    )
    database_path = ""
    if mode == storage_settings.DATA_MODE_SQLITE:
        database_path = storage_settings.resolve_sqlite_path(bootstrap)
    key = (mode, database_path)
    if _ACTIVE_STORE is not None and _ACTIVE_STORE_KEY == key:
        return _ACTIVE_STORE
    if mode == storage_settings.DATA_MODE_SQLITE:
        _ACTIVE_STORE = SqliteDataStoreAdapter(database_path)
    else:
        _ACTIVE_STORE = LegacyDataStore()
    _ACTIVE_STORE_KEY = key
    return _ACTIVE_STORE


def is_sqlite_mode() -> bool:
    """Return True when SQLite mode is active."""

    return get_active_store().mode == storage_settings.DATA_MODE_SQLITE
