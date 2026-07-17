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
    supports_atomic_incident_event = True

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

    def append_operational_event(
        self, event: dict[str, object]
    ) -> dict[str, Any]:
        return self.store.append_operational_event(event)

    def query_operational_events(
        self,
        *,
        severities=(),
        username: str = "",
        ean: str = "",
        job_id: str = "",
        correlation_id: str = "",
        module: str = "",
        query: str = "",
        after_id: str = "",
        cursor: str = "",
        limit: int = 20,
        since: str = "",
    ) -> dict[str, Any]:
        return self.store.query_operational_events(
            severities=severities,
            username=username,
            ean=ean,
            job_id=job_id,
            correlation_id=correlation_id,
            module=module,
            query=query,
            after_id=after_id,
            cursor=cursor,
            limit=limit,
            since=since,
        )

    def upsert_job_run(self, job: dict[str, object]) -> dict[str, Any]:
        return self.store.upsert_job_run(job)

    def query_job_runs(
        self, *, cursor: str = "", limit: int = 20
    ) -> dict[str, Any]:
        return self.store.query_job_runs(cursor=cursor, limit=limit)

    def upsert_incident(self, incident: dict[str, object]) -> dict[str, Any]:
        return self.store.upsert_incident(incident)

    def find_open_incident(self, fingerprint: str) -> dict[str, Any] | None:
        return self.store.find_open_incident(fingerprint)

    def coalesce_incident(
        self,
        occurrence: dict[str, object],
        notification_window_seconds: int = 15 * 60,
        source_event: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        return self.store.coalesce_incident(
            occurrence,
            notification_window_seconds=notification_window_seconds,
            source_event=source_event,
        )

    def query_incidents(
        self, *, severity: str = "", cursor: str = "", limit: int = 20
    ) -> dict[str, Any]:
        return self.store.query_incidents(
            severity=severity, cursor=cursor, limit=limit
        )

    def query_incident_context(
        self,
        incident_id: str,
        *,
        problem_cursor: str = "",
        problem_limit: int = 20,
        before_limit: int = 5,
        after_limit: int = 5,
    ) -> dict[str, Any] | None:
        return self.store.query_incident_context(
            incident_id,
            problem_cursor=problem_cursor,
            problem_limit=problem_limit,
            before_limit=before_limit,
            after_limit=after_limit,
        )

    def release_incident_notification(
        self,
        incident_id: str,
        *,
        claimed_at: str,
        previous_at: str,
    ) -> bool:
        return self.store.release_incident_notification(
            incident_id,
            claimed_at=claimed_at,
            previous_at=previous_at,
        )

    def enqueue_notification_delivery(
        self, record: dict[str, object]
    ) -> dict[str, Any]:
        return self.store.enqueue_notification_delivery(record)

    def pending_notification_deliveries(
        self, limit: int = 20
    ) -> list[dict[str, Any]]:
        return self.store.pending_notification_deliveries(limit=limit)

    def update_notification_delivery(
        self,
        delivery_id: str,
        *,
        status: str,
        used_channel: str = "",
        attempts=None,
        updated_at: str,
        next_attempt_at: str = "",
    ) -> dict[str, Any]:
        return self.store.update_notification_delivery(
            delivery_id,
            status=status,
            used_channel=used_channel,
            attempts=attempts,
            updated_at=updated_at,
            next_attempt_at=next_attempt_at,
        )

    def query_notification_deliveries(
        self, *, incident_id: str = "", cursor: str = "", limit: int = 20
    ) -> dict[str, Any]:
        return self.store.query_notification_deliveries(
            incident_id=incident_id,
            cursor=cursor,
            limit=limit,
        )

    def notification_deliveries_for_incidents(
        self, incident_ids: list[str], *, per_incident_limit: int = 5
    ) -> list[dict[str, Any]]:
        return self.store.notification_deliveries_for_incidents(
            incident_ids, per_incident_limit=per_incident_limit
        )

    def mark_alerts_read(
        self, username: str, severity: str, event_id: str, created_at: str
    ) -> None:
        self.store.mark_alerts_read(username, severity, event_id, created_at)

    def unread_alert_summary(self, username: str) -> dict[str, object]:
        return self.store.unread_alert_summary(username)

    def prune_info_events(self, before: str) -> int:
        return self.store.prune_info_events(before)

    def clear_operational_data(self) -> dict[str, int]:
        return self.store.clear_operational_data()

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
