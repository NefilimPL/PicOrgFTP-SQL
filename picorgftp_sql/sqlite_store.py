"""SQLite-backed persistence for PicOrgFTP-SQL data."""

from __future__ import annotations

import base64
import binascii
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .excel_utils import (
    COLOR1_HEADER,
    COLOR2_HEADER,
    COLOR3_HEADER,
    EAN_HEADER,
    ENTRY_RECORDS_KEY,
    EXTRA_HEADER,
    MODEL_HEADER,
    NAME_HEADER,
    PRODUCT_ID_HEADER,
    TYPE_HEADER,
)

SCHEMA_VERSION = 5
LIST_SHEETS = ("NAZWY", "TYPY", "MODELE", "KOLORY", "DODATKI")
ENTRY_HEADERS = (
    EAN_HEADER,
    NAME_HEADER,
    TYPE_HEADER,
    MODEL_HEADER,
    COLOR1_HEADER,
    COLOR2_HEADER,
    COLOR3_HEADER,
    EXTRA_HEADER,
    PRODUCT_ID_HEADER,
)


def _text(value: object) -> str:
    return str(value or "").strip()


def _upper(value: object) -> str:
    return _text(value).upper()


def _json_dumps(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _json_loads(payload: object, fallback: object) -> object:
    try:
        return json.loads(str(payload or ""))
    except (TypeError, ValueError):
        return fallback


def _page_cursor(created_at: object, identity: object) -> str:
    raw = _json_dumps([_text(created_at), _text(identity)]).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_page_cursor(value: object) -> tuple[str, str]:
    text = _text(value)
    if not text:
        return "", ""
    padded = text + "=" * (-len(text) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return "", ""
    payload = _json_loads(decoded, [])
    if not isinstance(payload, list) or len(payload) != 2:
        return "", ""
    return _text(payload[0]), _text(payload[1])


def _bounded_page_limit(value: object) -> int:
    try:
        parsed = int(value or 20)
    except (TypeError, ValueError):
        parsed = 20
    return max(1, min(100, parsed))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _iso_from_timestamp(value: object) -> str:
    parsed: datetime | None = None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            value = text
    if parsed is None:
        try:
            parsed = datetime.fromtimestamp(float(value), timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            return _now_iso()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def _history_created_at(payload: dict[str, object]) -> str:
    return _iso_from_timestamp(
        payload.get("created_at") or payload.get("ts") or payload.get("time")
    )


def _segment_key(value: object) -> str:
    text = _upper(value)
    for ch in text:
        if ch.isalnum():
            return ch if ch.isascii() else "_"
    return "_"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _migrate_web_history_created_at(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(web_history)").fetchall()
    }
    if "ts" not in columns or "created_at" in columns:
        return
    conn.execute("ALTER TABLE web_history RENAME TO web_history_legacy_ts")
    conn.execute(
        """
        CREATE TABLE web_history (
            id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    for row in conn.execute(
        "SELECT id, payload_json, ts FROM web_history_legacy_ts"
    ).fetchall():
        payload = _json_loads(row["payload_json"], {})
        if not isinstance(payload, dict):
            payload = {}
        created_at = _iso_from_timestamp(
            payload.get("created_at") or payload.get("ts") or row["ts"]
        )
        payload["id"] = _text(row["id"]) or f"hist-{uuid.uuid4().hex}"
        payload["created_at"] = created_at
        payload["ts"] = created_at
        conn.execute(
            """
            INSERT INTO web_history (id, payload_json, created_at)
            VALUES (?, ?, ?)
            """,
            (payload["id"], _json_dumps(payload), created_at),
        )
    conn.execute("DROP TABLE web_history_legacy_ts")


def _flatten_config(payload: dict[str, object]) -> list[tuple[str, object]]:
    rows: list[tuple[str, object]] = []

    def walk(prefix: str, value: object) -> None:
        if isinstance(value, dict) and value:
            for key in sorted(value):
                text_key = _text(key)
                if text_key:
                    walk(f"{prefix}.{text_key}" if prefix else text_key, value[key])
            return
        rows.append((prefix, value))

    for key in sorted(payload or {}):
        text_key = _text(key)
        if text_key:
            walk(text_key, payload[key])
    return rows


def _unflatten_config(rows: list[sqlite3.Row]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for row in rows:
        path = _text(row["path"])
        if not path:
            continue
        parts = [part for part in path.split(".") if part]
        if not parts:
            continue
        cursor = payload
        for part in parts[:-1]:
            existing = cursor.get(part)
            if not isinstance(existing, dict):
                existing = {}
                cursor[part] = existing
            cursor = existing
        cursor[parts[-1]] = _json_loads(row["value_json"], None)
    return payload


def _list_value(sheet: str, value: object) -> str:
    text = _upper(value)
    if sheet == "DODATKI":
        text = text.replace("_", "-")
    return text


def _entry_payload(payload: dict[str, object]) -> dict[str, str]:
    entry = {header: _upper(payload.get(header)) for header in ENTRY_HEADERS}
    entry[COLOR2_HEADER] = _upper(payload.get(COLOR2_HEADER)) if payload.get(COLOR2_HEADER) else ""
    entry[COLOR3_HEADER] = _upper(payload.get(COLOR3_HEADER)) if payload.get(COLOR3_HEADER) else ""
    extra = _upper(payload.get(EXTRA_HEADER)).replace("_", "-")
    entry[EXTRA_HEADER] = extra or "NO-LED"
    entry[PRODUCT_ID_HEADER] = _upper(payload.get(PRODUCT_ID_HEADER))
    return entry


class SqliteStore:
    """Small SQLite persistence wrapper used by the active data store layer."""

    def __init__(self, path: str):
        self.path = str(Path(path))

    def connect(self) -> sqlite3.Connection:
        directory = Path(self.path).parent
        directory.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connection(self):
        """Yield a SQLite connection and always close it afterwards."""

        conn = self.connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        """Create schema tables when the database is first used."""

        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER NOT NULL,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS app_config_values (
                    path TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS slot_definitions (
                    prefix TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    filename_label TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS sql_column_map (
                    prefix TEXT PRIMARY KEY,
                    column_name TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS sql_available_columns (
                    column_name TEXT PRIMARY KEY,
                    table_name TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    detected_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS list_values (
                    list_key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (list_key, value)
                );

                CREATE TABLE IF NOT EXISTS product_entries (
                    product_id TEXT PRIMARY KEY,
                    ean TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL DEFAULT '',
                    type_name TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    color1 TEXT NOT NULL DEFAULT '',
                    color2 TEXT NOT NULL DEFAULT '',
                    color3 TEXT NOT NULL DEFAULT '',
                    extra TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS web_users (
                    username TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS web_history (
                    id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS file_index_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS file_index_segments (
                    segment_key TEXT NOT NULL,
                    section TEXT NOT NULL,
                    lookup_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (segment_key, section, lookup_key)
                );

                CREATE TABLE IF NOT EXISTS pimcore_submissions (
                    id TEXT PRIMARY KEY,
                    operation_id TEXT NOT NULL DEFAULT '',
                    operation_type TEXT NOT NULL,
                    username TEXT NOT NULL DEFAULT '',
                    ean TEXT NOT NULL DEFAULT '',
                    object_id TEXT NOT NULL DEFAULT '',
                    object_path TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    values_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    warnings_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS operational_events (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    module TEXT NOT NULL DEFAULT '',
                    stage TEXT NOT NULL DEFAULT '',
                    username TEXT NOT NULL DEFAULT '',
                    ean TEXT NOT NULL DEFAULT '',
                    product_id TEXT NOT NULL DEFAULT '',
                    slot TEXT NOT NULL DEFAULT '',
                    job_id TEXT NOT NULL DEFAULT '',
                    correlation_id TEXT NOT NULL DEFAULT '',
                    incident_id TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL,
                    recommended_action TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    exception_type TEXT NOT NULL DEFAULT '',
                    traceback_text TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS job_runs (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL DEFAULT '',
                    ean TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL DEFAULT '',
                    stages_json TEXT NOT NULL DEFAULT '[]',
                    details_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    occurrence_count INTEGER NOT NULL DEFAULT 1,
                    first_event_id TEXT NOT NULL,
                    latest_event_id TEXT NOT NULL,
                    job_id TEXT NOT NULL DEFAULT '',
                    correlation_id TEXT NOT NULL DEFAULT '',
                    notification_window_at TEXT NOT NULL DEFAULT '',
                    context_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS alert_reads (
                    username TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (username, severity)
                );
                """
            )
            _migrate_web_history_created_at(conn)
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_web_history_created_at
                    ON web_history(created_at);
                CREATE INDEX IF NOT EXISTS idx_product_entries_ean
                    ON product_entries(ean);
                CREATE INDEX IF NOT EXISTS idx_product_entries_identity
                    ON product_entries(name, type_name, model);
                CREATE INDEX IF NOT EXISTS idx_app_config_values_updated_at
                    ON app_config_values(updated_at);
                CREATE INDEX IF NOT EXISTS idx_file_index_segments_lookup
                    ON file_index_segments(segment_key, section, lookup_key);
                CREATE INDEX IF NOT EXISTS idx_file_index_segments_updated_at
                    ON file_index_segments(updated_at);
                CREATE INDEX IF NOT EXISTS idx_pimcore_submissions_created_at
                    ON pimcore_submissions(created_at);
                CREATE INDEX IF NOT EXISTS idx_pimcore_submissions_ean
                    ON pimcore_submissions(ean);
                CREATE INDEX IF NOT EXISTS idx_pimcore_submissions_user
                    ON pimcore_submissions(username);
                CREATE INDEX IF NOT EXISTS idx_operational_events_created_at_id
                    ON operational_events(created_at, id);
                CREATE INDEX IF NOT EXISTS idx_operational_events_severity_created_at
                    ON operational_events(severity, created_at);
                CREATE INDEX IF NOT EXISTS idx_operational_events_job_id
                    ON operational_events(job_id);
                CREATE INDEX IF NOT EXISTS idx_operational_events_correlation_id
                    ON operational_events(correlation_id);
                CREATE INDEX IF NOT EXISTS idx_incidents_fingerprint_last_seen_at
                    ON incidents(fingerprint, last_seen_at);
                CREATE INDEX IF NOT EXISTS idx_job_runs_started_at_id
                    ON job_runs(started_at, id);
                """
            )
            version_row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_version"
            ).fetchone()
            current_version = int(version_row[0] or 0) if version_row else 0
            if current_version < SCHEMA_VERSION:
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, _now_iso()),
                )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["details"] = _json_loads(payload.pop("details_json", "{}"), {})
        return payload

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["stages"] = _json_loads(payload.pop("stages_json", "[]"), [])
        payload["details"] = _json_loads(payload.pop("details_json", "{}"), {})
        return payload

    @staticmethod
    def _incident_from_row(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["context"] = _json_loads(payload.pop("context_json", "{}"), {})
        return payload

    def append_operational_event(
        self, event: dict[str, object]
    ) -> dict[str, Any]:
        """Persist one structured operational event."""

        self.initialize()
        details = event.get("details")
        payload: dict[str, Any] = {
            "id": _text(event.get("id")) or f"evt-{uuid.uuid4().hex}",
            "created_at": _iso_from_timestamp(event.get("created_at") or _now_iso()),
            "severity": _text(event.get("severity")),
            "event_type": _text(event.get("event_type")),
            "module": _text(event.get("module")),
            "stage": _text(event.get("stage")),
            "username": _text(event.get("username")),
            "ean": _text(event.get("ean")),
            "product_id": _text(event.get("product_id")),
            "slot": _text(event.get("slot")),
            "job_id": _text(event.get("job_id")),
            "correlation_id": _text(event.get("correlation_id")),
            "incident_id": _text(event.get("incident_id")),
            "summary": _text(event.get("summary")),
            "recommended_action": _text(event.get("recommended_action")),
            "details": details if isinstance(details, dict) else {},
            "exception_type": _text(event.get("exception_type")),
            "traceback_text": _text(event.get("traceback_text")),
        }
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO operational_events (
                    id, created_at, severity, event_type, module, stage,
                    username, ean, product_id, slot, job_id, correlation_id,
                    incident_id, summary, recommended_action, details_json,
                    exception_type, traceback_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    created_at = excluded.created_at,
                    severity = excluded.severity,
                    event_type = excluded.event_type,
                    module = excluded.module,
                    stage = excluded.stage,
                    username = excluded.username,
                    ean = excluded.ean,
                    product_id = excluded.product_id,
                    slot = excluded.slot,
                    job_id = excluded.job_id,
                    correlation_id = excluded.correlation_id,
                    incident_id = excluded.incident_id,
                    summary = excluded.summary,
                    recommended_action = excluded.recommended_action,
                    details_json = excluded.details_json,
                    exception_type = excluded.exception_type,
                    traceback_text = excluded.traceback_text
                """,
                (
                    payload["id"], payload["created_at"], payload["severity"],
                    payload["event_type"], payload["module"], payload["stage"],
                    payload["username"], payload["ean"], payload["product_id"],
                    payload["slot"], payload["job_id"], payload["correlation_id"],
                    payload["incident_id"], payload["summary"],
                    payload["recommended_action"], _json_dumps(payload["details"]),
                    payload["exception_type"], payload["traceback_text"],
                ),
            )
        return payload

    def query_operational_events(
        self,
        *,
        severities=(),
        username: str = "",
        ean: str = "",
        job_id: str = "",
        module: str = "",
        query: str = "",
        after_id: str = "",
        cursor: str = "",
        limit: int = 20,
        since: str = "",
    ) -> dict[str, Any]:
        """Return a descending cursor page of operational events."""

        self.initialize()
        clauses: list[str] = []
        params: list[object] = []
        severity_values = (
            [_text(severities)]
            if isinstance(severities, str)
            else [_text(value) for value in severities]
        )
        severity_values = [value for value in severity_values if value]
        if severity_values:
            clauses.append(
                f"severity IN ({', '.join('?' for _ in severity_values)})"
            )
            params.extend(severity_values)
        for column, value in (
            ("username", username),
            ("ean", ean),
            ("job_id", job_id),
            ("module", module),
        ):
            if _text(value):
                clauses.append(f"{column} = ?")
                params.append(_text(value))
        if _text(query):
            needle = f"%{_text(query)}%"
            clauses.append(
                "(summary LIKE ? OR event_type LIKE ? OR details_json LIKE ? "
                "OR exception_type LIKE ? OR traceback_text LIKE ?)"
            )
            params.extend([needle] * 5)
        if _text(since):
            clauses.append("created_at >= ?")
            params.append(_text(since))
        cursor_at, cursor_id = _decode_page_cursor(cursor)
        if cursor_at and cursor_id:
            clauses.append("(created_at < ? OR (created_at = ? AND id < ?))")
            params.extend([cursor_at, cursor_at, cursor_id])
        with self.connection() as conn:
            if _text(after_id):
                marker = conn.execute(
                    "SELECT created_at, id FROM operational_events WHERE id = ?",
                    (_text(after_id),),
                ).fetchone()
                if marker:
                    clauses.append(
                        "(created_at > ? OR (created_at = ? AND id > ?))"
                    )
                    params.extend(
                        [marker["created_at"], marker["created_at"], marker["id"]]
                    )
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            page_limit = _bounded_page_limit(limit)
            rows = conn.execute(
                f"""
                SELECT * FROM operational_events
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (*params, page_limit + 1),
            ).fetchall()
        has_more = len(rows) > page_limit
        items = [self._event_from_row(row) for row in rows[:page_limit]]
        next_cursor = (
            _page_cursor(items[-1]["created_at"], items[-1]["id"])
            if has_more and items
            else ""
        )
        return {"items": items, "next_cursor": next_cursor}

    def upsert_job_run(self, job: dict[str, object]) -> dict[str, Any]:
        """Insert or update a durable job summary."""

        self.initialize()
        stages = job.get("stages")
        details = job.get("details")
        payload: dict[str, Any] = {
            "id": _text(job.get("id")) or f"job-{uuid.uuid4().hex}",
            "username": _text(job.get("username")),
            "ean": _text(job.get("ean")),
            "status": _text(job.get("status")),
            "summary": _text(job.get("summary")),
            "started_at": _iso_from_timestamp(job.get("started_at") or _now_iso()),
            "finished_at": _text(job.get("finished_at")),
            "stages": stages if isinstance(stages, list) else [],
            "details": details if isinstance(details, dict) else {},
        }
        if payload["finished_at"]:
            payload["finished_at"] = _iso_from_timestamp(payload["finished_at"])
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO job_runs (
                    id, username, ean, status, summary, started_at,
                    finished_at, stages_json, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    username = excluded.username,
                    ean = excluded.ean,
                    status = excluded.status,
                    summary = excluded.summary,
                    started_at = excluded.started_at,
                    finished_at = excluded.finished_at,
                    stages_json = excluded.stages_json,
                    details_json = excluded.details_json
                """,
                (
                    payload["id"], payload["username"], payload["ean"],
                    payload["status"], payload["summary"], payload["started_at"],
                    payload["finished_at"], _json_dumps(payload["stages"]),
                    _json_dumps(payload["details"]),
                ),
            )
        return payload

    def query_job_runs(self, *, cursor: str = "", limit: int = 20) -> dict[str, Any]:
        """Return a descending cursor page of job summaries."""

        self.initialize()
        clauses: list[str] = []
        params: list[object] = []
        cursor_at, cursor_id = _decode_page_cursor(cursor)
        if cursor_at and cursor_id:
            clauses.append("(started_at < ? OR (started_at = ? AND id < ?))")
            params.extend([cursor_at, cursor_at, cursor_id])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        page_limit = _bounded_page_limit(limit)
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM job_runs
                {where}
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (*params, page_limit + 1),
            ).fetchall()
        has_more = len(rows) > page_limit
        items = [self._job_from_row(row) for row in rows[:page_limit]]
        next_cursor = (
            _page_cursor(items[-1]["started_at"], items[-1]["id"])
            if has_more and items
            else ""
        )
        return {"items": items, "next_cursor": next_cursor}

    def upsert_incident(self, incident: dict[str, object]) -> dict[str, Any]:
        """Insert or update an incident aggregate."""

        self.initialize()
        context = incident.get("context")
        try:
            occurrence_count = int(incident.get("occurrence_count") or 1)
        except (TypeError, ValueError):
            occurrence_count = 1
        payload: dict[str, Any] = {
            "id": _text(incident.get("id")) or f"inc-{uuid.uuid4().hex}",
            "fingerprint": _text(incident.get("fingerprint")),
            "severity": _text(incident.get("severity")),
            "event_type": _text(incident.get("event_type")),
            "status": _text(incident.get("status")) or "open",
            "first_seen_at": _iso_from_timestamp(
                incident.get("first_seen_at") or _now_iso()
            ),
            "last_seen_at": _iso_from_timestamp(
                incident.get("last_seen_at") or _now_iso()
            ),
            "occurrence_count": occurrence_count,
            "first_event_id": _text(incident.get("first_event_id")),
            "latest_event_id": _text(incident.get("latest_event_id")),
            "job_id": _text(incident.get("job_id")),
            "correlation_id": _text(incident.get("correlation_id")),
            "notification_window_at": _text(incident.get("notification_window_at")),
            "context": context if isinstance(context, dict) else {},
        }
        if payload["notification_window_at"]:
            payload["notification_window_at"] = _iso_from_timestamp(
                payload["notification_window_at"]
            )
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO incidents (
                    id, fingerprint, severity, event_type, status, first_seen_at,
                    last_seen_at, occurrence_count, first_event_id,
                    latest_event_id, job_id, correlation_id,
                    notification_window_at, context_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    fingerprint = excluded.fingerprint,
                    severity = excluded.severity,
                    event_type = excluded.event_type,
                    status = excluded.status,
                    first_seen_at = excluded.first_seen_at,
                    last_seen_at = excluded.last_seen_at,
                    occurrence_count = excluded.occurrence_count,
                    first_event_id = excluded.first_event_id,
                    latest_event_id = excluded.latest_event_id,
                    job_id = excluded.job_id,
                    correlation_id = excluded.correlation_id,
                    notification_window_at = excluded.notification_window_at,
                    context_json = excluded.context_json
                """,
                (
                    payload["id"], payload["fingerprint"], payload["severity"],
                    payload["event_type"], payload["status"],
                    payload["first_seen_at"], payload["last_seen_at"],
                    payload["occurrence_count"], payload["first_event_id"],
                    payload["latest_event_id"], payload["job_id"],
                    payload["correlation_id"], payload["notification_window_at"],
                    _json_dumps(payload["context"]),
                ),
            )
        return payload

    def find_open_incident(self, fingerprint: str) -> dict[str, Any] | None:
        """Return the newest open incident matching a fingerprint."""

        self.initialize()
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM incidents
                WHERE fingerprint = ? AND status = 'open'
                ORDER BY last_seen_at DESC, id DESC
                LIMIT 1
                """,
                (_text(fingerprint),),
            ).fetchone()
        return self._incident_from_row(row) if row else None

    def query_incidents(
        self, *, severity: str = "", cursor: str = "", limit: int = 20
    ) -> dict[str, Any]:
        """Return a descending cursor page of incidents."""

        self.initialize()
        clauses: list[str] = []
        params: list[object] = []
        if _text(severity):
            clauses.append("severity = ?")
            params.append(_text(severity))
        cursor_at, cursor_id = _decode_page_cursor(cursor)
        if cursor_at and cursor_id:
            clauses.append("(last_seen_at < ? OR (last_seen_at = ? AND id < ?))")
            params.extend([cursor_at, cursor_at, cursor_id])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        page_limit = _bounded_page_limit(limit)
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM incidents
                {where}
                ORDER BY last_seen_at DESC, id DESC
                LIMIT ?
                """,
                (*params, page_limit + 1),
            ).fetchall()
        has_more = len(rows) > page_limit
        items = [self._incident_from_row(row) for row in rows[:page_limit]]
        next_cursor = (
            _page_cursor(items[-1]["last_seen_at"], items[-1]["id"])
            if has_more and items
            else ""
        )
        return {"items": items, "next_cursor": next_cursor}

    def mark_alerts_read(
        self, username: str, severity: str, event_id: str, created_at: str
    ) -> None:
        """Store a user's latest read marker for one alert severity."""

        self.initialize()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO alert_reads (username, severity, event_id, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(username, severity) DO UPDATE SET
                    event_id = excluded.event_id,
                    created_at = excluded.created_at
                WHERE excluded.created_at > alert_reads.created_at
                    OR (
                        excluded.created_at = alert_reads.created_at
                        AND excluded.event_id > alert_reads.event_id
                    )
                """,
                (
                    _text(username), _text(severity), _text(event_id),
                    _iso_from_timestamp(created_at),
                ),
            )

    def unread_alert_summary(self, username: str) -> dict[str, object]:
        """Return unread counts and highest alert severity for one user."""

        self.initialize()
        counts: dict[str, int] = {}
        with self.connection() as conn:
            for severity in ("warning", "error", "critical"):
                marker = conn.execute(
                    """
                    SELECT event_id, created_at FROM alert_reads
                    WHERE username = ? AND severity = ?
                    """,
                    (_text(username), severity),
                ).fetchone()
                if marker:
                    row = conn.execute(
                        """
                        SELECT COUNT(*) FROM operational_events
                        WHERE severity = ? AND (
                            created_at > ? OR (created_at = ? AND id > ?)
                        )
                        """,
                        (
                            severity, marker["created_at"], marker["created_at"],
                            marker["event_id"],
                        ),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM operational_events WHERE severity = ?",
                        (severity,),
                    ).fetchone()
                counts[severity] = int(row[0] or 0) if row else 0
        highest = ""
        for severity in ("critical", "error", "warning"):
            if counts[severity]:
                highest = severity
                break
        return {
            **counts,
            "total": sum(counts.values()),
            "highest": highest,
        }

    def prune_info_events(self, before: str) -> int:
        """Delete informational events older than the supplied boundary."""

        self.initialize()
        with self.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM operational_events WHERE severity = 'info' AND created_at < ?",
                (_text(before),),
            )
            return max(0, cursor.rowcount)

    def clear_operational_data(self) -> dict[str, int]:
        """Clear structured operational tables without touching product history."""

        self.initialize()
        deleted: dict[str, int] = {}
        with self.connection() as conn:
            for table in (
                "operational_events", "job_runs", "incidents", "alert_reads"
            ):
                cursor = conn.execute(f"DELETE FROM {table}")
                deleted[table] = max(0, cursor.rowcount)
        return deleted

    def load_config(self) -> dict[str, Any]:
        """Return the stored config payload."""

        self.initialize()
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT path, value_json
                FROM app_config_values
                ORDER BY path
                """
            ).fetchall()
            if rows:
                return _unflatten_config(rows)
            row = None
            if _table_exists(conn, "app_settings"):
                row = conn.execute(
                    "SELECT value_json FROM app_settings WHERE key = 'config'"
                ).fetchone()
        if not row:
            return {}
        payload = _json_loads(row["value_json"], {})
        return dict(payload) if isinstance(payload, dict) else {}

    def save_config(self, payload: dict[str, object]) -> None:
        """Store the normalized config payload."""

        self.initialize()
        rows = _flatten_config(dict(payload or {}))
        with self.connection() as conn:
            conn.execute("DELETE FROM app_config_values")
            if _table_exists(conn, "app_settings"):
                conn.execute("DELETE FROM app_settings WHERE key = 'config'")
                row = conn.execute("SELECT COUNT(*) FROM app_settings").fetchone()
                if int(row[0] or 0) == 0:
                    conn.execute("DROP TABLE app_settings")
            updated_at = _now_iso()
            for path, value in rows:
                conn.execute(
                    """
                    INSERT INTO app_config_values (path, value_json, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (path, _json_dumps(value), updated_at),
                )

    def append_pimcore_submission(self, record: dict[str, object]) -> dict[str, Any]:
        """Persist one Pimcore submission audit record."""

        self.initialize()
        record_id = _text(record.get("id")) or f"pim-{uuid.uuid4().hex}"
        created_at = _iso_from_timestamp(record.get("created_at") or _now_iso())
        payload = {
            "id": record_id,
            "operation_id": _text(record.get("operation_id")),
            "operation_type": _text(record.get("operation_type")),
            "username": _text(record.get("username")),
            "ean": _text(record.get("ean")),
            "object_id": _text(record.get("object_id")),
            "object_path": _text(record.get("object_path")),
            "status": _text(record.get("status")),
            "values": record.get("values") if isinstance(record.get("values"), dict) else {},
            "payload": record.get("payload") if isinstance(record.get("payload"), dict) else {},
            "result": record.get("result") if isinstance(record.get("result"), dict) else {},
            "warnings": record.get("warnings") if isinstance(record.get("warnings"), list) else [],
            "created_at": created_at,
        }
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO pimcore_submissions (
                    id, operation_id, operation_type, username, ean, object_id,
                    object_path, status, values_json, payload_json, result_json,
                    warnings_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    operation_id = excluded.operation_id,
                    operation_type = excluded.operation_type,
                    username = excluded.username,
                    ean = excluded.ean,
                    object_id = excluded.object_id,
                    object_path = excluded.object_path,
                    status = excluded.status,
                    values_json = excluded.values_json,
                    payload_json = excluded.payload_json,
                    result_json = excluded.result_json,
                    warnings_json = excluded.warnings_json,
                    created_at = excluded.created_at
                """,
                (
                    payload["id"],
                    payload["operation_id"],
                    payload["operation_type"],
                    payload["username"],
                    payload["ean"],
                    payload["object_id"],
                    payload["object_path"],
                    payload["status"],
                    _json_dumps(payload["values"]),
                    _json_dumps(payload["payload"]),
                    _json_dumps(payload["result"]),
                    _json_dumps(payload["warnings"]),
                    payload["created_at"],
                ),
            )
        return payload

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
        """Return persisted Pimcore submission audit records."""

        self.initialize()
        clauses = []
        params: list[object] = []
        if _text(operation_type):
            clauses.append("operation_type = ?")
            params.append(_text(operation_type))
        if _text(status):
            clauses.append("status = ?")
            params.append(_text(status))
        if _text(user):
            clauses.append("LOWER(username) = LOWER(?)")
            params.append(_text(user))
        if _text(date_from):
            clauses.append("created_at >= ?")
            params.append(_text(date_from))
        if _text(date_to):
            clauses.append("created_at <= ?")
            params.append(_text(date_to))
        if _text(query):
            needle = f"%{_text(query)}%"
            clauses.append(
                "(ean LIKE ? OR object_id LIKE ? OR object_path LIKE ? OR values_json LIKE ?)"
            )
            params.extend([needle, needle, needle, needle])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        try:
            limit_value = int(limit or 200)
        except (TypeError, ValueError):
            limit_value = 200
        bounded_limit = max(1, min(1000, limit_value))
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM pimcore_submissions
                {where}
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (*params, bounded_limit),
            ).fetchall()
        result = []
        for row in rows:
            result.append(
                {
                    "id": row["id"],
                    "operation_id": row["operation_id"],
                    "operation_type": row["operation_type"],
                    "username": row["username"],
                    "ean": row["ean"],
                    "object_id": row["object_id"],
                    "object_path": row["object_path"],
                    "status": row["status"],
                    "values": _json_loads(row["values_json"], {}),
                    "payload": _json_loads(row["payload_json"], {}),
                    "result": _json_loads(row["result_json"], {}),
                    "warnings": _json_loads(row["warnings_json"], []),
                    "created_at": row["created_at"],
                }
            )
        return result

    def load_slots(self) -> tuple[list[dict[str, str]], dict[str, str]]:
        """Return slot definitions and SQL column mappings."""

        self.initialize()
        with self.connection() as conn:
            slot_rows = conn.execute(
                """
                SELECT prefix, label, filename_label
                FROM slot_definitions
                ORDER BY sort_order, prefix
                """
            ).fetchall()
            map_rows = conn.execute(
                "SELECT prefix, column_name FROM sql_column_map ORDER BY prefix"
            ).fetchall()
        slots = [
            {
                "prefix": row["prefix"],
                "label": row["label"],
                "filename_label": row["filename_label"],
            }
            for row in slot_rows
        ]
        sql_map = {row["prefix"]: row["column_name"] for row in map_rows}
        return slots, sql_map

    def save_slots(
        self,
        slot_definitions: list[dict[str, object]],
        sql_column_map: dict[str, object],
    ) -> None:
        """Replace slot definitions and SQL column mappings."""

        self.initialize()
        with self.connection() as conn:
            conn.execute("DELETE FROM slot_definitions")
            conn.execute("DELETE FROM sql_column_map")
            for index, slot in enumerate(slot_definitions or []):
                prefix = _text(slot.get("prefix"))
                label = _text(slot.get("label"))
                if not prefix or not label:
                    continue
                conn.execute(
                    """
                    INSERT INTO slot_definitions
                        (prefix, label, filename_label, sort_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        prefix,
                        label,
                        _text(slot.get("filename_label")),
                        index,
                    ),
                )
            for prefix, column_name in dict(sql_column_map or {}).items():
                conn.execute(
                    """
                    INSERT INTO sql_column_map (prefix, column_name)
                    VALUES (?, ?)
                    """,
                    (_text(prefix), _text(column_name)),
                )

    def load_sql_columns(self) -> list[str]:
        """Return detected SQL columns in display order."""

        self.initialize()
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT column_name
                FROM sql_available_columns
                ORDER BY sort_order, column_name
                """
            ).fetchall()
        return [row["column_name"] for row in rows]

    def save_sql_columns(self, columns: list[object], table_name: str = "") -> None:
        """Replace detected SQL columns."""

        self.initialize()
        seen = set()
        cleaned = []
        for column in columns or []:
            text = _text(column)
            if not text or text.lower() in seen:
                continue
            cleaned.append(text)
            seen.add(text.lower())
        with self.connection() as conn:
            conn.execute("DELETE FROM sql_available_columns")
            detected_at = _now_iso()
            for index, column in enumerate(cleaned):
                conn.execute(
                    """
                    INSERT INTO sql_available_columns
                        (column_name, table_name, sort_order, detected_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (column, _text(table_name), index, detected_at),
                )

    def load_lists(self) -> dict[str, Any]:
        """Return data in the same shape as ``prepare_excel_lists``."""

        self.initialize()
        payload: dict[str, Any] = {sheet: [] for sheet in LIST_SHEETS}
        with self.connection() as conn:
            list_rows = conn.execute(
                """
                SELECT list_key, value
                FROM list_values
                ORDER BY list_key, sort_order, value
                """
            ).fetchall()
            entry_rows = conn.execute(
                """
                SELECT ean, name, type_name, model, color1, color2, color3, extra, product_id
                FROM product_entries
                ORDER BY rowid
                """
            ).fetchall()
        for row in list_rows:
            payload.setdefault(row["list_key"], []).append(row["value"])
        records = []
        entries = {}
        for row in entry_rows:
            entry = {
                EAN_HEADER: row["ean"],
                NAME_HEADER: row["name"],
                TYPE_HEADER: row["type_name"],
                MODEL_HEADER: row["model"],
                COLOR1_HEADER: row["color1"],
                COLOR2_HEADER: row["color2"],
                COLOR3_HEADER: row["color3"],
                EXTRA_HEADER: row["extra"],
                PRODUCT_ID_HEADER: row["product_id"],
            }
            records.append(entry)
            if row["ean"]:
                entries[row["ean"]] = {
                    NAME_HEADER: row["name"],
                    TYPE_HEADER: row["type_name"],
                    MODEL_HEADER: row["model"],
                    COLOR1_HEADER: row["color1"],
                    COLOR2_HEADER: row["color2"],
                    COLOR3_HEADER: row["color3"],
                    EXTRA_HEADER: row["extra"],
                    PRODUCT_ID_HEADER: row["product_id"],
                }
        payload["ENTRIES"] = entries
        payload[ENTRY_RECORDS_KEY] = records
        return payload

    def save_lists(self, payload: dict[str, object]) -> None:
        """Replace list values and product entries from an Excel-shaped payload."""

        self.initialize()
        with self.connection() as conn:
            conn.execute("DELETE FROM list_values")
            conn.execute("DELETE FROM product_entries")
            for sheet in LIST_SHEETS:
                values = payload.get(sheet, []) if isinstance(payload, dict) else []
                for index, value in enumerate(values if isinstance(values, list) else []):
                    cleaned = _list_value(sheet, value)
                    if not cleaned:
                        continue
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO list_values
                            (list_key, value, sort_order)
                        VALUES (?, ?, ?)
                        """,
                        (sheet, cleaned, index),
                    )
            records = payload.get(ENTRY_RECORDS_KEY, []) if isinstance(payload, dict) else []
            for record in records if isinstance(records, list) else []:
                if isinstance(record, dict):
                    self._save_product_entry_conn(conn, record)

    def add_list_value(self, sheet: str, value: object) -> bool:
        """Add a normalized value to one list. Return False for duplicates."""

        self.initialize()
        cleaned = _list_value(sheet, value)
        if not sheet or not cleaned:
            return False
        with self.connection() as conn:
            existing = conn.execute(
                "SELECT 1 FROM list_values WHERE list_key = ? AND value = ?",
                (sheet, cleaned),
            ).fetchone()
            if existing:
                return False
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) FROM list_values WHERE list_key = ?",
                (sheet,),
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO list_values (list_key, value, sort_order)
                VALUES (?, ?, ?)
                """,
                (sheet, cleaned, int(max_order) + 1),
            )
        return True

    def remove_list_value(self, sheet: str, value: object) -> None:
        """Remove a normalized value from one list."""

        self.initialize()
        cleaned = _list_value(sheet, value)
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM list_values WHERE list_key = ? AND value = ?",
                (sheet, cleaned),
            )

    def _save_product_entry_conn(
        self, conn: sqlite3.Connection, payload: dict[str, object]
    ) -> dict[str, Any]:
        entry = _entry_payload(payload)
        product_id = entry[PRODUCT_ID_HEADER] or f"PRD-{uuid.uuid4().hex[:12].upper()}"
        entry[PRODUCT_ID_HEADER] = product_id
        existing = conn.execute(
            "SELECT 1 FROM product_entries WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        updated = existing is not None
        conn.execute(
            """
            INSERT INTO product_entries (
                product_id, ean, name, type_name, model,
                color1, color2, color3, extra, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                ean = excluded.ean,
                name = excluded.name,
                type_name = excluded.type_name,
                model = excluded.model,
                color1 = excluded.color1,
                color2 = excluded.color2,
                color3 = excluded.color3,
                extra = excluded.extra,
                updated_at = excluded.updated_at
            """,
            (
                entry[PRODUCT_ID_HEADER],
                entry[EAN_HEADER],
                entry[NAME_HEADER],
                entry[TYPE_HEADER],
                entry[MODEL_HEADER],
                entry[COLOR1_HEADER],
                entry[COLOR2_HEADER],
                entry[COLOR3_HEADER],
                entry[EXTRA_HEADER],
                _now_iso(),
            ),
        )
        return {"updated": updated, "product_id": product_id, "entry": entry}

    def save_product_entry(self, payload: dict[str, object]) -> dict[str, Any]:
        """Insert or update one product entry."""

        self.initialize()
        with self.connection() as conn:
            return self._save_product_entry_conn(conn, payload)

    def load_users(self) -> list[dict[str, Any]]:
        """Return stored web user records."""

        self.initialize()
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM web_users ORDER BY rowid"
            ).fetchall()
        users = []
        for row in rows:
            payload = _json_loads(row["payload_json"], {})
            if isinstance(payload, dict):
                users.append(payload)
        return users

    def save_users(self, users: list[dict[str, object]]) -> None:
        """Replace stored web user records."""

        self.initialize()
        with self.connection() as conn:
            conn.execute("DELETE FROM web_users")
            for item in users or []:
                if not isinstance(item, dict):
                    continue
                username = _text(item.get("username"))
                if not username:
                    continue
                conn.execute(
                    """
                    INSERT INTO web_users (username, payload_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    (username, _json_dumps(item), _now_iso()),
                )

    def load_history(self) -> list[dict[str, Any]]:
        """Return stored web history records."""

        self.initialize()
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM web_history ORDER BY created_at, rowid"
            ).fetchall()
        records = []
        for row in rows:
            payload = _json_loads(row["payload_json"], {})
            if isinstance(payload, dict):
                records.append(payload)
        return records

    def save_history(self, records: list[dict[str, object]]) -> None:
        """Replace stored web history records."""

        self.initialize()
        with self.connection() as conn:
            conn.execute("DELETE FROM web_history")
            for item in records or []:
                if not isinstance(item, dict):
                    continue
                record_id = _text(item.get("id")) or f"hist-{uuid.uuid4().hex}"
                payload = dict(item)
                payload["id"] = record_id
                created_at = _history_created_at(payload)
                payload["created_at"] = created_at
                payload["ts"] = created_at
                conn.execute(
                    """
                    INSERT INTO web_history (id, payload_json, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        created_at = excluded.created_at
                    """,
                    (record_id, _json_dumps(payload), created_at),
                )

    def append_history(self, record: dict[str, object]) -> None:
        """Append or replace one web history record."""

        self.initialize()
        if not isinstance(record, dict):
            return
        record_id = _text(record.get("id")) or f"hist-{uuid.uuid4().hex}"
        payload = dict(record)
        payload["id"] = record_id
        created_at = _history_created_at(payload)
        payload["created_at"] = created_at
        payload["ts"] = created_at
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO web_history (id, payload_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at
                """,
                (record_id, _json_dumps(payload), created_at),
            )

    def load_file_index_cache(self, key: str = "default") -> dict[str, Any]:
        """Return stored local file index cache payload."""

        self.initialize()
        with self.connection() as conn:
            row = conn.execute(
                "SELECT payload_json FROM file_index_cache WHERE cache_key = ?",
                (_text(key) or "default",),
            ).fetchone()
        if not row:
            return {}
        payload = _json_loads(row["payload_json"], {})
        return dict(payload) if isinstance(payload, dict) else {}

    def save_file_index_cache(
        self, payload: dict[str, object], key: str = "default"
    ) -> None:
        """Store local file index cache payload."""

        self.initialize()
        snapshot = dict(payload or {})
        snapshot["generated_at"] = _iso_from_timestamp(snapshot.get("generated_at"))
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO file_index_cache (cache_key, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    _text(key) or "default",
                    _json_dumps(snapshot),
                    snapshot["generated_at"],
                ),
            )
        self.save_file_index_segments(snapshot)

    def save_file_index_segments(self, snapshot: dict[str, object]) -> int:
        """Store segmented lookup rows for the local file index cache."""

        self.initialize()
        generated_at = _iso_from_timestamp(snapshot.get("generated_at"))
        rows = []
        names = snapshot.get("names", [])
        for name in names if isinstance(names, list) else []:
            rows.append((_segment_key(name), "names", _upper(name), name))
        for section in ("types", "models", "colors", "extras", "files"):
            section_payload = snapshot.get(section, {})
            if not isinstance(section_payload, dict):
                continue
            for lookup_key, value in section_payload.items():
                segment = _segment_key(str(lookup_key).split("\x1f", 1)[0])
                rows.append((segment, section, str(lookup_key), value))
        with self.connection() as conn:
            conn.execute("DELETE FROM file_index_segments")
            for segment, section, lookup_key, value in rows:
                conn.execute(
                    """
                    INSERT INTO file_index_segments
                        (segment_key, section, lookup_key, payload_json, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (segment, section, lookup_key, _json_dumps(value), generated_at),
                )
        return len(rows)

    def load_file_index_segment(self, segment_key: str, section: str, lookup_key: str):
        """Return one segmented local file index payload, or None."""

        self.initialize()
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM file_index_segments
                WHERE segment_key = ? AND section = ? AND lookup_key = ?
                """,
                (
                    _segment_key(segment_key) if segment_key else "_",
                    _text(section),
                    _text(lookup_key),
                ),
            ).fetchone()
        if not row:
            return None
        return _json_loads(row["payload_json"], None)
