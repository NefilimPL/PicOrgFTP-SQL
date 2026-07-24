"""SQLite-backed persistence for PicOrgFTP-SQL data."""

from __future__ import annotations

import base64
import binascii
import json
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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
from .redaction import redact_sensitive_value, sanitize_free_text

SCHEMA_VERSION = 11
_NOTIFICATION_DELIVERY_STATUSES = frozenset(
    {"pending", "sending", "sent", "fallback", "skipped", "error"}
)
_NOTIFICATION_DELIVERY_CHANNELS = frozenset({"entra", "smtp"})
_NOTIFICATION_DELIVERY_SEVERITIES = frozenset(
    {"info", "warning", "error", "critical"}
)
_ENTRA_SECRET_STATUS_VALUES = frozenset({"ok", "unavailable", "unknown"})
_ENTRA_SECRET_STATUS_PUBLIC_COLUMNS = (
    "tenant_id",
    "client_id",
    "status",
    "expires_at",
    "credential_name",
    "application_name",
    "source",
    "last_checked_at",
    "last_success_at",
    "error_code",
    "error_message",
)
_OPERATIONAL_EVENT_STREAM_ORIGIN_ID = (
    "sys-4e680c0b1c744a0e82e385cad10b47d1"
)
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

_INCIDENT_CONTEXT_BEFORE_SQL = """
    SELECT * FROM operational_events
    WHERE {scope_column} = ? AND (created_at, id) < (?, ?)
    ORDER BY created_at DESC, id DESC
    LIMIT ?
"""
_INCIDENT_CONTEXT_PROBLEM_SQL = """
    SELECT * FROM operational_events
    WHERE {scope_column} = ?
      AND (created_at, id) >= (?, ?)
      AND (created_at, id) <= (?, ?)
      {cursor_clause}
    ORDER BY created_at ASC, id ASC
    LIMIT ?
"""
_INCIDENT_CONTEXT_AFTER_SQL = """
    SELECT * FROM operational_events
    WHERE {scope_column} = ? AND (created_at, id) > (?, ?)
    ORDER BY created_at ASC, id ASC
    LIMIT ?
"""
_OPERATIONAL_EVENT_QUERY_COLUMNS = (
    "created_at",
    "id",
    "severity",
    "event_type",
    "module",
    "stage",
    "username",
    "ean",
    "product_id",
    "slot",
    "job_id",
    "correlation_id",
    "incident_id",
    "summary",
    "recommended_action",
    "details_json",
    "exception_type",
    "traceback_text",
)


def _text(value: object) -> str:
    return str(value or "").strip()


def _bounded_scalar_text(
    value: object,
    *,
    field: str,
    limit: int,
    required: bool = False,
) -> str:
    """Accept only bounded, redacted text without coercing structured values."""

    if value is None:
        text = ""
    elif not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    else:
        text = sanitize_free_text(value, limit=limit).strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    return text


def _entra_secret_status_value(value: object) -> str:
    """Return a safe, stable Entra status rather than stringifying input."""

    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower()
    return normalized if normalized in _ENTRA_SECRET_STATUS_VALUES else "unknown"


def _unicode_lower(value: object) -> str:
    """Normalize SQLite text with Python's Unicode-aware case mapping."""

    return str(value or "").lower()


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


def _literal_like_pattern(value: object) -> str:
    needle = _text(value)
    escaped = (
        needle.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


def _append_operational_event_filters(
    clauses: list[str],
    params: list[object],
    *,
    severities=(),
    username: str = "",
    ean: str = "",
    job_id: str = "",
    module: str = "",
    query: str = "",
    since: str = "",
    prefix: str = "",
) -> None:
    severity_values = (
        [_text(severities)]
        if isinstance(severities, str)
        else [_text(value) for value in severities]
    )
    severity_values = [value for value in severity_values if value]
    if severity_values:
        clauses.append(
            f"{prefix}severity IN ({', '.join('?' for _ in severity_values)})"
        )
        params.extend(severity_values)
    for column, value in (("username", username), ("ean", ean), ("module", module)):
        if _text(value):
            clauses.append(
                f"picorg_lower({prefix}{column}) "
                "LIKE picorg_lower(?) ESCAPE '\\'"
            )
            params.append(_literal_like_pattern(value))
    if _text(job_id):
        clauses.append(
            f"picorg_lower(CASE WHEN {prefix}job_id <> '' THEN {prefix}job_id "
            f"ELSE {prefix}id END) LIKE picorg_lower(?) ESCAPE '\\'"
        )
        pattern = _literal_like_pattern(job_id)
        params.append(pattern)
    if _text(query):
        pattern = _literal_like_pattern(query)
        query_clauses = " OR ".join(
                f"picorg_lower({prefix}{column}) "
                "LIKE picorg_lower(?) ESCAPE '\\'"
                for column in _OPERATIONAL_EVENT_QUERY_COLUMNS
        )
        clauses.append(f"({query_clauses})")
        params.extend([pattern] * len(_OPERATIONAL_EVENT_QUERY_COLUMNS))
    if _text(since):
        clauses.append(f"{prefix}created_at >= ?")
        params.append(_text(since))


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


def _canonical_timestamp(
    value: object, *, field: str, required: bool = True
) -> str:
    if value is None:
        text = ""
    elif isinstance(value, str):
        text = value
    else:
        raise ValueError(f"{field} must be a canonical timestamp")
    if not text:
        if required:
            raise ValueError(f"{field} is required")
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a canonical timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be a canonical timestamp")
    canonical = parsed.astimezone(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")
    if text != canonical:
        raise ValueError(f"{field} must be a canonical timestamp")
    return canonical


def _delivery_status(value: object) -> str:
    status = _text(value)
    if status not in _NOTIFICATION_DELIVERY_STATUSES:
        raise ValueError("invalid notification delivery status")
    return status


def _delivery_channel(value: object, *, allow_empty: bool) -> str:
    channel = _text(value)
    if (not channel and allow_empty) or channel in _NOTIFICATION_DELIVERY_CHANNELS:
        return channel
    raise ValueError("invalid notification delivery channel")


def _history_created_at(payload: dict[str, object]) -> str:
    return _iso_from_timestamp(
        payload.get("created_at") or payload.get("ts") or payload.get("time")
    )


def _history_index_projection(
    payload: dict[str, object], *, record_id: object, created_at: object
) -> tuple[str, str, str, str, str, str, str, str, str]:
    """Return the redacted, queryable fields kept beside a history payload."""

    redacted = redact_sensitive_value(payload)
    record = dict(redacted) if isinstance(redacted, dict) else {}
    ean = _text(record.get("ean")) or "BRAK-EAN"
    username = _text(record.get("user"))
    product_id = _text(record.get("product_id"))
    action = _text(record.get("action"))
    summary = _text(record.get("summary"))
    details = record.get("details")
    entry = details.get("entry") if isinstance(details, dict) else None
    safe_entry = redact_sensitive_value(entry) if isinstance(entry, dict) else {}
    entry = dict(safe_entry) if isinstance(safe_entry, dict) else {}
    search_parts = [ean, product_id, summary, action, username]
    search_parts.extend(
        _text(value)
        for value in entry.values()
        if isinstance(value, (str, int, float, bool)) and _text(value)
    )
    return (
        _text(record_id),
        ean,
        username,
        product_id,
        action,
        summary,
        _json_dumps(entry),
        " ".join(search_parts).casefold(),
        _text(created_at),
    )


def _upsert_web_history_index(
    conn: sqlite3.Connection,
    payload: dict[str, object],
    *,
    record_id: object,
    created_at: object,
) -> None:
    conn.execute(
        """
        INSERT INTO web_history_index (
            id, ean, username, product_id, action, summary, entry_json,
            search_text, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            ean = excluded.ean,
            username = excluded.username,
            product_id = excluded.product_id,
            action = excluded.action,
            summary = excluded.summary,
            entry_json = excluded.entry_json,
            search_text = excluded.search_text,
            created_at = excluded.created_at
        """,
        _history_index_projection(
            payload, record_id=record_id, created_at=created_at
        ),
    )


def _prune_web_history(conn: sqlite3.Connection) -> None:
    """Keep the payload and read index limited to the newest history records."""

    conn.execute(
        """
        DELETE FROM web_history_index
        WHERE id NOT IN (
            SELECT id FROM web_history_index
            ORDER BY created_at DESC, id DESC
            LIMIT 2000
        )
        """
    )
    conn.execute(
        """
        DELETE FROM web_history
        WHERE id NOT IN (SELECT id FROM web_history_index)
        """
    )


def _rebuild_web_history_index_if_needed(conn: sqlite3.Connection) -> None:
    """Backfill the read index when a pre-index payload table is detected."""

    history_count = int(
        conn.execute("SELECT COUNT(*) FROM web_history").fetchone()[0] or 0
    )
    index_count = int(
        conn.execute("SELECT COUNT(*) FROM web_history_index").fetchone()[0] or 0
    )
    if history_count == index_count:
        return
    conn.execute("DELETE FROM web_history_index")
    rows = conn.execute(
        "SELECT id, payload_json, created_at FROM web_history"
    ).fetchall()
    for row in rows:
        payload = _json_loads(row["payload_json"], {})
        if not isinstance(payload, dict):
            continue
        _upsert_web_history_index(
            conn,
            payload,
            record_id=row["id"],
            created_at=row["created_at"],
        )


def _append_history_index_filters(
    clauses: list[str], params: list[object], *, user: str = "", query: str = ""
) -> None:
    if _text(user):
        clauses.append("picorg_lower(username) = picorg_lower(?)")
        params.append(_text(user))
    if _text(query):
        clauses.append("search_text LIKE ? ESCAPE '\\'")
        params.append(_literal_like_pattern(_text(query).casefold()))


def _history_timestamp_from_created_at(value: object) -> float:
    try:
        return datetime.fromisoformat(_text(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


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


def _migrate_daily_change_summary_reports(conn: sqlite3.Connection) -> None:
    """Add retry scheduling to databases created by the first v8 release."""

    if not _table_exists(conn, "daily_change_summary_reports"):
        return
    columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(daily_change_summary_reports)"
        ).fetchall()
    }
    if "next_attempt_at" not in columns:
        conn.execute(
            """
            ALTER TABLE daily_change_summary_reports
            ADD COLUMN next_attempt_at TEXT NOT NULL DEFAULT ''
            """
        )
    if "claim_token" not in columns:
        conn.execute(
            """
            ALTER TABLE daily_change_summary_reports
            ADD COLUMN claim_token TEXT NOT NULL DEFAULT ''
            """
        )


def _severity_rank(value: object) -> int:
    severities = ("info", "warning", "error", "critical")
    text = _text(value)
    return severities.index(text) if text in severities else -1


def _incident_context_from_row(row: sqlite3.Row) -> dict[str, object]:
    context = _json_loads(row["context_json"], {})
    return dict(context) if isinstance(context, dict) else {}


def _reconcile_duplicate_open_incidents(conn: sqlite3.Connection) -> None:
    """Merge duplicate v5 open incidents before adding the unique index."""

    fingerprints = conn.execute(
        """
        SELECT fingerprint FROM incidents
        WHERE status = 'open'
        GROUP BY fingerprint
        HAVING COUNT(*) > 1
        ORDER BY fingerprint
        """
    ).fetchall()
    for group in fingerprints:
        rows = conn.execute(
            """
            SELECT * FROM incidents
            WHERE fingerprint = ? AND status = 'open'
            ORDER BY id
            """,
            (group["fingerprint"],),
        ).fetchall()
        first = min(
            rows,
            key=lambda row: (
                row["first_seen_at"], row["first_event_id"], row["id"]
            ),
        )
        latest = max(
            rows,
            key=lambda row: (
                row["last_seen_at"], row["latest_event_id"], row["id"]
            ),
        )
        keeper_id = first["id"]
        contexts: dict[str, object] = {}
        for row in sorted(
            rows,
            key=lambda item: (
                item["last_seen_at"], item["latest_event_id"], item["id"]
            ),
        ):
            contexts.update(_incident_context_from_row(row))
        merged_ids = sorted(row["id"] for row in rows if row["id"] != keeper_id)
        contexts["merged_incident_ids"] = merged_ids
        severity = max(rows, key=lambda row: _severity_rank(row["severity"]))[
            "severity"
        ]
        occurrence_count = sum(max(0, int(row["occurrence_count"] or 0)) for row in rows)
        notification_window_at = max(
            (_text(row["notification_window_at"]) for row in rows), default=""
        )
        conn.execute(
            """
            UPDATE incidents SET
                severity = ?, event_type = ?, status = 'open',
                first_seen_at = ?, last_seen_at = ?, occurrence_count = ?,
                first_event_id = ?, latest_event_id = ?, job_id = ?,
                correlation_id = ?, notification_window_at = ?, context_json = ?
            WHERE id = ?
            """,
            (
                severity, latest["event_type"], first["first_seen_at"],
                latest["last_seen_at"], occurrence_count,
                first["first_event_id"], latest["latest_event_id"],
                latest["job_id"], latest["correlation_id"],
                notification_window_at, _json_dumps(contexts), keeper_id,
            ),
        )
        for row in rows:
            if row["id"] == keeper_id:
                continue
            merged_context = _incident_context_from_row(row)
            merged_context["merged_into_incident_id"] = keeper_id
            conn.execute(
                "UPDATE incidents SET status = 'merged', context_json = ? WHERE id = ?",
                (_json_dumps(merged_context), row["id"]),
            )


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

    supports_atomic_incident_event = True
    supports_notification_outbox = True

    def __init__(self, path: str):
        self.path = str(Path(path))

    def connect(self) -> sqlite3.Connection:
        directory = Path(self.path).parent
        directory.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.create_function(
            "picorg_lower",
            1,
            _unicode_lower,
            deterministic=True,
        )
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
            previous_user_version_row = conn.execute("PRAGMA user_version").fetchone()
            previous_user_version = (
                int(previous_user_version_row[0] or 0)
                if previous_user_version_row
                else 0
            )
            stream_table_existed = (
                conn.execute(
                    """
                    SELECT 1 FROM sqlite_master
                    WHERE type = 'table' AND name = 'operational_event_stream'
                    """
                ).fetchone()
                is not None
            )
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

                CREATE TABLE IF NOT EXISTS web_history_index (
                    id TEXT PRIMARY KEY,
                    ean TEXT NOT NULL,
                    username TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    entry_json TEXT NOT NULL,
                    search_text TEXT NOT NULL,
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

                CREATE TABLE IF NOT EXISTS pimcore_integration_contexts (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    mode TEXT NOT NULL CHECK (mode IN ('create', 'edit')),
                    object_id TEXT NOT NULL DEFAULT '',
                    results_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT NOT NULL DEFAULT ''
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

                CREATE TABLE IF NOT EXISTS operational_event_stream (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE
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

                CREATE TABLE IF NOT EXISTS notification_deliveries (
                    id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL DEFAULT '',
                    event_id TEXT NOT NULL DEFAULT '',
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    primary_channel TEXT NOT NULL,
                    used_channel TEXT NOT NULL DEFAULT '',
                    recipients_json TEXT NOT NULL DEFAULT '[]',
                    message_json TEXT NOT NULL,
                    attempts_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    next_attempt_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS notification_outbox (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    incident_id TEXT NOT NULL DEFAULT '',
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS entra_secret_status (
                    tenant_id TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expires_at TEXT NOT NULL DEFAULT '',
                    credential_name TEXT NOT NULL DEFAULT '',
                    credential_key_id TEXT NOT NULL DEFAULT '',
                    application_name TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    last_checked_at TEXT NOT NULL DEFAULT '',
                    last_success_at TEXT NOT NULL DEFAULT '',
                    error_code TEXT NOT NULL DEFAULT '',
                    error_message TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (tenant_id, client_id)
                );

                CREATE TABLE IF NOT EXISTS entra_secret_reminders (
                    tenant_id TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    credential_key_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    threshold_days INTEGER NOT NULL,
                    claimed_at TEXT NOT NULL,
                    PRIMARY KEY (
                        tenant_id, client_id, credential_key_id, expires_at,
                        threshold_days
                    )
                );

                CREATE TABLE IF NOT EXISTS daily_change_summary_reports (
                    window_end TEXT PRIMARY KEY,
                    window_start TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('pending', 'sending', 'sent')),
                    claimed_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sent_at TEXT NOT NULL DEFAULT '',
                    next_attempt_at TEXT NOT NULL DEFAULT '',
                    claim_token TEXT NOT NULL DEFAULT ''
                );
                """
            )
            _migrate_web_history_created_at(conn)
            _migrate_daily_change_summary_reports(conn)
            _rebuild_web_history_index_if_needed(conn)
            _reconcile_duplicate_open_incidents(conn)
            conn.execute(
                """
                DELETE FROM operational_event_stream
                WHERE sequence = 0 AND event_id <> ?
                """,
                (_OPERATIONAL_EVENT_STREAM_ORIGIN_ID,),
            )
            conn.execute(
                """
                DELETE FROM operational_event_stream
                WHERE event_id = ? AND sequence <> 0
                """,
                (_OPERATIONAL_EVENT_STREAM_ORIGIN_ID,),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO operational_event_stream (sequence, event_id)
                VALUES (0, ?)
                """,
                (_OPERATIONAL_EVENT_STREAM_ORIGIN_ID,),
            )
            if previous_user_version < SCHEMA_VERSION or not stream_table_existed:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO operational_event_stream (event_id)
                    SELECT id FROM operational_events ORDER BY rowid
                    """
                )
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_web_history_created_at
                    ON web_history(created_at);
                CREATE INDEX IF NOT EXISTS idx_web_history_index_ean_created_at_id
                    ON web_history_index(ean, created_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_web_history_index_username_created_at_id
                    ON web_history_index(username, created_at DESC, id DESC);
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
                CREATE INDEX IF NOT EXISTS idx_pimcore_integration_contexts_expiry
                    ON pimcore_integration_contexts(expires_at, consumed_at);
                CREATE INDEX IF NOT EXISTS idx_operational_events_created_at_id
                    ON operational_events(created_at, id);
                CREATE INDEX IF NOT EXISTS idx_operational_events_severity_created_at
                    ON operational_events(severity, created_at);
                CREATE INDEX IF NOT EXISTS idx_operational_events_job_id
                    ON operational_events(job_id);
                CREATE INDEX IF NOT EXISTS idx_operational_events_correlation_id
                    ON operational_events(correlation_id);
                CREATE INDEX IF NOT EXISTS idx_operational_events_job_created_at_id
                    ON operational_events(job_id, created_at, id);
                CREATE INDEX IF NOT EXISTS idx_operational_events_correlation_created_at_id
                    ON operational_events(correlation_id, created_at, id);
                CREATE INDEX IF NOT EXISTS idx_incidents_fingerprint_last_seen_at
                    ON incidents(fingerprint, last_seen_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_incidents_one_open_fingerprint
                    ON incidents(fingerprint) WHERE status = 'open';
                CREATE INDEX IF NOT EXISTS idx_job_runs_started_at_id
                    ON job_runs(started_at, id);
                CREATE INDEX IF NOT EXISTS idx_notification_deliveries_pending
                    ON notification_deliveries(status, next_attempt_at, created_at);
                CREATE INDEX IF NOT EXISTS idx_notification_deliveries_incident
                    ON notification_deliveries(incident_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_notification_outbox_pending
                    ON notification_outbox(status, created_at, id);
                CREATE INDEX IF NOT EXISTS idx_entra_secret_status_last_checked_at
                    ON entra_secret_status(last_checked_at);
                CREATE INDEX IF NOT EXISTS idx_daily_change_summary_reports_status
                    ON daily_change_summary_reports(status, window_end);
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
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["details"] = _json_loads(payload.pop("details_json", "{}"), {})
        redacted = redact_sensitive_value(payload, text_limit=32 * 1024)
        return redacted if isinstance(redacted, dict) else {}

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["stages"] = _json_loads(payload.pop("stages_json", "[]"), [])
        payload["details"] = _json_loads(payload.pop("details_json", "{}"), {})
        redacted = redact_sensitive_value(payload)
        return redacted if isinstance(redacted, dict) else {}

    @staticmethod
    def _incident_from_row(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["context"] = _json_loads(payload.pop("context_json", "{}"), {})
        redacted = redact_sensitive_value(payload)
        return redacted if isinstance(redacted, dict) else {}

    @staticmethod
    def _delivery_from_row(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["recipients"] = _json_loads(
            payload.pop("recipients_json", "[]"), []
        )
        payload["message"] = _json_loads(payload.pop("message_json", "{}"), {})
        payload["attempts"] = _json_loads(
            payload.pop("attempts_json", "[]"), []
        )
        return payload

    @staticmethod
    def _public_entra_secret_status(row: sqlite3.Row) -> dict[str, str]:
        """Project persisted Entra status to fields that are safe to expose."""

        limits = {
            "tenant_id": 256,
            "client_id": 256,
            "expires_at": 64,
            "credential_name": 512,
            "application_name": 512,
            "source": 128,
            "last_checked_at": 64,
            "last_success_at": 64,
            "error_code": 128,
            "error_message": 8 * 1024,
        }
        return {
            column: (
                _entra_secret_status_value(row[column])
                if column == "status"
                else sanitize_free_text(row[column], limit=limits[column]).strip()
            )
            for column in _ENTRA_SECRET_STATUS_PUBLIC_COLUMNS
        }

    def get_entra_secret_status(self, tenant_id: str, client_id: str) -> dict[str, str]:
        """Return the safe Entra expiry status for one tenant and application."""

        self.initialize()
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT tenant_id, client_id, status, expires_at, credential_name,
                       application_name, source, last_checked_at, last_success_at,
                       error_code, error_message
                FROM entra_secret_status
                WHERE tenant_id = ? AND client_id = ?
                """,
                (
                    _bounded_scalar_text(
                        tenant_id, field="tenant_id", limit=256, required=True
                    ),
                    _bounded_scalar_text(
                        client_id, field="client_id", limit=256, required=True
                    ),
                ),
            ).fetchone()
        return self._public_entra_secret_status(row) if row else {}

    def get_entra_secret_status_internal(
        self, tenant_id: str, client_id: str
    ) -> dict[str, str]:
        """Return monitor-only status including the Graph credential key ID.

        This accessor is intentionally separate from the public projection used
        by web/API callers.  It never accepts or returns client secrets/tokens.
        """

        self.initialize()
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT tenant_id, client_id, status, expires_at, credential_name,
                       credential_key_id, application_name, source, last_checked_at,
                       last_success_at, error_code, error_message
                FROM entra_secret_status
                WHERE tenant_id = ? AND client_id = ?
                """,
                (
                    _bounded_scalar_text(
                        tenant_id, field="tenant_id", limit=256, required=True
                    ),
                    _bounded_scalar_text(
                        client_id, field="client_id", limit=256, required=True
                    ),
                ),
            ).fetchone()
        if row is None:
            return {}
        result = self._public_entra_secret_status(row)
        result["credential_key_id"] = sanitize_free_text(
            row["credential_key_id"], limit=256
        ).strip()
        return result

    def clear_entra_secret_status(self, tenant_id: str, client_id: str) -> int:
        """Remove an Entra status record and all reminder claims for its identity."""

        self.initialize()
        identity = (
            _bounded_scalar_text(
                tenant_id, field="tenant_id", limit=256, required=True
            ),
            _bounded_scalar_text(
                client_id, field="client_id", limit=256, required=True
            ),
        )
        with self.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM entra_secret_status WHERE tenant_id = ? AND client_id = ?",
                identity,
            )
            conn.execute(
                "DELETE FROM entra_secret_reminders "
                "WHERE tenant_id = ? AND client_id = ?",
                identity,
            )
        return max(0, cursor.rowcount)

    def upsert_entra_secret_status(
        self, status: dict[str, object]
    ) -> dict[str, str]:
        """Persist an Entra expiry status without accepting secret-bearing fields."""

        if not isinstance(status, dict):
            raise ValueError("status must be a mapping")
        tenant_id = _bounded_scalar_text(
            status.get("tenant_id"), field="tenant_id", limit=256, required=True
        )
        client_id = _bounded_scalar_text(
            status.get("client_id"), field="client_id", limit=256, required=True
        )
        normalized_status = _entra_secret_status_value(status.get("status"))
        payload = {
            "tenant_id": tenant_id,
            "client_id": client_id,
            "status": normalized_status,
            "expires_at": _canonical_timestamp(
                status.get("expires_at"), field="expires_at", required=False
            ),
            "credential_name": _bounded_scalar_text(
                status.get("credential_name"), field="credential_name", limit=512
            ),
            "credential_key_id": _bounded_scalar_text(
                status.get("credential_key_id"), field="credential_key_id", limit=256
            ),
            "application_name": _bounded_scalar_text(
                status.get("application_name"), field="application_name", limit=512
            ),
            "source": _bounded_scalar_text(
                status.get("source"), field="source", limit=128
            ),
            "last_checked_at": _canonical_timestamp(
                status.get("last_checked_at"), field="last_checked_at", required=False
            ),
            "last_success_at": _canonical_timestamp(
                status.get("last_success_at"), field="last_success_at", required=False
            ),
            "error_code": _bounded_scalar_text(
                status.get("error_code"), field="error_code", limit=128
            ),
            "error_message": _bounded_scalar_text(
                status.get("error_message"), field="error_message", limit=8 * 1024
            ),
        }
        self.initialize()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO entra_secret_status (
                    tenant_id, client_id, status, expires_at, credential_name,
                    credential_key_id, application_name, source, last_checked_at,
                    last_success_at, error_code, error_message
                ) VALUES (
                    :tenant_id, :client_id, :status, :expires_at, :credential_name,
                    :credential_key_id, :application_name, :source, :last_checked_at,
                    :last_success_at, :error_code, :error_message
                )
                ON CONFLICT(tenant_id, client_id) DO UPDATE SET
                    status = excluded.status,
                    expires_at = excluded.expires_at,
                    credential_name = excluded.credential_name,
                    credential_key_id = excluded.credential_key_id,
                    application_name = excluded.application_name,
                    source = excluded.source,
                    last_checked_at = excluded.last_checked_at,
                    last_success_at = excluded.last_success_at,
                    error_code = excluded.error_code,
                    error_message = excluded.error_message
                """,
                payload,
            )
            row = conn.execute(
                """
                SELECT tenant_id, client_id, status, expires_at, credential_name,
                       application_name, source, last_checked_at, last_success_at,
                       error_code, error_message
                FROM entra_secret_status
                WHERE tenant_id = ? AND client_id = ?
                """,
                (tenant_id, client_id),
            ).fetchone()
        return self._public_entra_secret_status(row)

    def claim_entra_secret_reminder(
        self,
        tenant_id: str,
        client_id: str,
        credential_key_id: str,
        expires_at: str,
        threshold_days: int,
        claimed_at: str,
    ) -> bool:
        """Atomically claim one Entra secret-expiry reminder threshold."""

        tenant = _bounded_scalar_text(
            tenant_id, field="tenant_id", limit=256, required=True
        )
        client = _bounded_scalar_text(
            client_id, field="client_id", limit=256, required=True
        )
        credential = _bounded_scalar_text(
            credential_key_id, field="credential_key_id", limit=256, required=True
        )
        try:
            threshold = int(threshold_days)
        except (TypeError, ValueError) as exc:
            raise ValueError("threshold_days must be an integer") from exc
        if threshold < 0:
            raise ValueError("threshold_days must be non-negative")
        expiry = _canonical_timestamp(expires_at, field="expires_at")
        claimed = _canonical_timestamp(claimed_at, field="claimed_at")
        self.initialize()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                INSERT INTO entra_secret_reminders (
                    tenant_id, client_id, credential_key_id, expires_at,
                    threshold_days, claimed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                (tenant, client, credential, expiry, threshold, claimed),
            )
        return cursor.rowcount == 1

    def entra_secret_reminder_claimed(
        self,
        tenant_id: str,
        client_id: str,
        credential_key_id: str,
        expires_at: str,
        threshold_days: int,
    ) -> bool:
        """Return whether the exact Entra reminder has already been claimed."""

        tenant = _bounded_scalar_text(tenant_id, field="tenant_id", limit=256, required=True)
        client = _bounded_scalar_text(client_id, field="client_id", limit=256, required=True)
        credential = _bounded_scalar_text(
            credential_key_id, field="credential_key_id", limit=256, required=True
        )
        try:
            threshold = int(threshold_days)
        except (TypeError, ValueError) as exc:
            raise ValueError("threshold_days must be an integer") from exc
        if threshold < 0:
            raise ValueError("threshold_days must be non-negative")
        expiry = _canonical_timestamp(expires_at, field="expires_at")
        self.initialize()
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM entra_secret_reminders
                WHERE tenant_id = ? AND client_id = ? AND credential_key_id = ?
                  AND expires_at = ? AND threshold_days = ?
                """,
                (tenant, client, credential, expiry, threshold),
            ).fetchone()
        return row is not None

    def append_operational_event(
        self,
        event: dict[str, object],
        *,
        create_notification_intent: bool = False,
    ) -> dict[str, Any]:
        """Persist one structured operational event."""

        self.initialize()
        payload = self._normalize_operational_event(event)
        with self.connection() as conn:
            self._insert_operational_event(conn, payload)
            if create_notification_intent:
                self._insert_notification_intent(
                    conn,
                    event_id=payload["id"],
                    incident_id=payload["incident_id"],
                    severity=payload["severity"],
                    created_at=payload["created_at"],
                )
        return payload

    @staticmethod
    def _insert_notification_intent(
        conn: sqlite3.Connection,
        *,
        event_id: object,
        incident_id: object,
        severity: object,
        created_at: object,
    ) -> None:
        normalized_event_id = _text(event_id)
        if not normalized_event_id:
            raise ValueError("notification intent event id is required")
        normalized_severity = _text(severity).lower()
        if normalized_severity not in _NOTIFICATION_DELIVERY_SEVERITIES:
            raise ValueError("invalid notification intent severity")
        timestamp = _canonical_timestamp(created_at, field="created_at")
        expected_id = f"intent-{normalized_event_id}"
        conn.execute(
            """
            INSERT INTO notification_outbox (
                id, event_id, incident_id, severity, status,
                created_at, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, ?, '')
            ON CONFLICT(event_id) DO NOTHING
            """,
            (
                expected_id,
                normalized_event_id,
                _text(incident_id),
                normalized_severity,
                timestamp,
                timestamp,
            ),
        )
        row = conn.execute(
            "SELECT id FROM notification_outbox WHERE event_id = ?",
            (normalized_event_id,),
        ).fetchone()
        if row is None or _text(row["id"]) != expected_id:
            raise RuntimeError("notification intent identity conflict")

    @staticmethod
    def _normalize_operational_event(
        event: dict[str, object],
    ) -> dict[str, Any]:
        details = redact_sensitive_value(event.get("details"))
        return {
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
            "summary": sanitize_free_text(event.get("summary")).strip(),
            "recommended_action": sanitize_free_text(
                event.get("recommended_action")
            ).strip(),
            "details": details if isinstance(details, dict) else {},
            "exception_type": sanitize_free_text(event.get("exception_type")).strip(),
            "traceback_text": sanitize_free_text(
                event.get("traceback_text"), limit=32 * 1024
            ).strip(),
        }

    @staticmethod
    def _insert_operational_event(
        conn: sqlite3.Connection, payload: dict[str, Any]
    ) -> None:
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
        conn.execute(
            """
            INSERT OR IGNORE INTO operational_event_stream (event_id)
            VALUES (?)
            """,
            (payload["id"],),
        )

    @staticmethod
    def _stream_event_from_row(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload.pop("_stream_sequence", None)
        payload["details"] = _json_loads(payload.pop("details_json", "{}"), {})
        redacted = redact_sensitive_value(payload, text_limit=32 * 1024)
        return redacted if isinstance(redacted, dict) else {}

    @staticmethod
    def _stream_high_water(conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'operational_event_stream'"
        ).fetchone()
        return max(0, int(row[0] or 0)) if row else 0

    def start_operational_event_stream(
        self, *, after_id: str = "", initial_limit: int = 100
    ) -> dict[str, Any]:
        """Resolve a reconnect marker or return a bounded initial snapshot."""

        self.initialize()
        page_limit = _bounded_page_limit(initial_limit)
        with self.connection() as conn:
            high_water = self._stream_high_water(conn)
            marker_id = _text(after_id)
            if marker_id:
                marker = conn.execute(
                    """
                    SELECT sequence FROM operational_event_stream
                    WHERE event_id = ?
                    """,
                    (marker_id,),
                ).fetchone()
                return {
                    "items": [],
                    "position": int(marker[0]) if marker else high_water,
                }
            rows = conn.execute(
                """
                SELECT s.sequence AS _stream_sequence, e.*
                FROM operational_event_stream AS s
                JOIN operational_events AS e ON e.id = s.event_id
                WHERE s.sequence <= ?
                ORDER BY s.sequence DESC
                LIMIT ?
                """,
                (high_water, page_limit),
            ).fetchall()
        return {
            "items": [self._stream_event_from_row(row) for row in reversed(rows)],
            "position": high_water,
        }

    def snapshot_operational_event_stream(
        self,
        *,
        since: str,
        limit: int = 200,
        severities=(),
        username: str = "",
        ean: str = "",
        job_id: str = "",
        module: str = "",
        query: str = "",
    ) -> dict[str, Any]:
        """Return a bounded live snapshot, archive cursor and atomic checkpoint."""

        self.initialize()
        try:
            snapshot_limit = max(1, min(500, int(limit or 200)))
        except (TypeError, ValueError):
            snapshot_limit = 200
        archive_since = _text(since)
        clauses = ["s.sequence <= ?"]
        params: list[object] = []
        _append_operational_event_filters(
            clauses,
            params,
            severities=severities,
            username=username,
            ean=ean,
            job_id=job_id,
            module=module,
            query=query,
            since=archive_since,
            prefix="e.",
        )
        with self.connection() as conn:
            conn.execute("BEGIN")
            marker = conn.execute(
                """
                SELECT sequence, event_id
                FROM operational_event_stream
                ORDER BY sequence DESC
                LIMIT 1
                """
            ).fetchone()
            if marker is None:
                return {
                    "items": [],
                    "stream_after_id": "",
                    "next_cursor": "",
                    "archive_since": archive_since,
                }
            rows = conn.execute(
                f"""
                SELECT s.sequence AS _stream_sequence, e.*
                FROM operational_event_stream AS s
                JOIN operational_events AS e ON e.id = s.event_id
                WHERE {' AND '.join(clauses)}
                ORDER BY e.created_at DESC, e.id DESC
                LIMIT ?
                """,
                (int(marker["sequence"]), *params, snapshot_limit + 1),
            ).fetchall()
        has_more = len(rows) > snapshot_limit
        selected = rows[:snapshot_limit]
        items = [self._stream_event_from_row(row) for row in reversed(selected)]
        return {
            "items": items,
            "stream_after_id": _text(marker["event_id"]),
            "next_cursor": (
                _page_cursor(items[0]["created_at"], items[0]["id"])
                if has_more and items
                else ""
            ),
            "archive_since": archive_since,
        }

    def poll_operational_event_stream(
        self, *, position: int, limit: int = 100
    ) -> dict[str, Any]:
        """Return later inserted events in durable ascending sequence order."""

        self.initialize()
        try:
            current_position = max(0, int(position))
        except (TypeError, ValueError):
            current_position = 0
        page_limit = _bounded_page_limit(limit)
        with self.connection() as conn:
            high_water = self._stream_high_water(conn)
            rows = conn.execute(
                """
                SELECT s.sequence AS _stream_sequence, e.*
                FROM operational_event_stream AS s
                JOIN operational_events AS e ON e.id = s.event_id
                WHERE s.sequence > ? AND s.sequence <= ?
                ORDER BY s.sequence ASC
                LIMIT ?
                """,
                (current_position, high_water, page_limit),
            ).fetchall()
        if len(rows) >= page_limit:
            next_position = int(rows[-1]["_stream_sequence"])
        else:
            next_position = max(current_position, high_water)
        return {
            "items": [self._stream_event_from_row(row) for row in rows],
            "position": next_position,
        }

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
        """Return a descending cursor page of operational events."""

        self.initialize()
        clauses: list[str] = []
        params: list[object] = []
        _append_operational_event_filters(
            clauses,
            params,
            severities=severities,
            username=username,
            ean=ean,
            job_id=job_id,
            module=module,
            query=query,
            since=since,
        )
        if _text(correlation_id):
            clauses.append("correlation_id = ?")
            params.append(_text(correlation_id))
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
        stages = redact_sensitive_value(job.get("stages"))
        details = redact_sensitive_value(job.get("details"))
        payload: dict[str, Any] = {
            "id": _text(job.get("id")) or f"job-{uuid.uuid4().hex}",
            "username": _text(job.get("username")),
            "ean": _text(job.get("ean")),
            "status": _text(job.get("status")),
            "summary": sanitize_free_text(job.get("summary")).strip(),
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
        context = redact_sensitive_value(incident.get("context"))
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

    def coalesce_incident(
        self,
        occurrence: dict[str, object],
        notification_window_seconds: int = 15 * 60,
        source_event: dict[str, object] | None = None,
        create_notification_intent: bool = False,
    ) -> dict[str, Any]:
        """Atomically coalesce an incident and optionally publish its event."""

        self.initialize()
        context = redact_sensitive_value(occurrence.get("context"))
        candidate: dict[str, Any] = {
            "id": _text(occurrence.get("id")) or f"inc-{uuid.uuid4().hex}",
            "fingerprint": _text(occurrence.get("fingerprint")),
            "severity": _text(occurrence.get("severity")),
            "event_type": _text(occurrence.get("event_type")),
            "status": "open",
            "first_seen_at": _iso_from_timestamp(
                occurrence.get("first_seen_at") or _now_iso()
            ),
            "last_seen_at": _iso_from_timestamp(
                occurrence.get("last_seen_at") or _now_iso()
            ),
            "occurrence_count": 1,
            "first_event_id": _text(occurrence.get("first_event_id")),
            "latest_event_id": _text(occurrence.get("latest_event_id")),
            "job_id": _text(occurrence.get("job_id")),
            "correlation_id": _text(occurrence.get("correlation_id")),
            "notification_window_at": _iso_from_timestamp(
                occurrence.get("notification_window_at")
                or occurrence.get("last_seen_at")
                or _now_iso()
            ),
            "context": context if isinstance(context, dict) else {},
        }
        try:
            window_seconds = max(0, int(notification_window_seconds))
        except (TypeError, ValueError):
            window_seconds = 15 * 60

        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM incidents
                WHERE fingerprint = ? AND status = 'open'
                ORDER BY last_seen_at DESC, id DESC
                LIMIT 1
                """,
                (candidate["fingerprint"],),
            ).fetchone()
            notification_due = row is None
            notification_previous_window_at = ""
            notification_claim_at = ""
            if row is None:
                conn.execute(
                    """
                    INSERT INTO incidents (
                        id, fingerprint, severity, event_type, status,
                        first_seen_at, last_seen_at, occurrence_count,
                        first_event_id, latest_event_id, job_id, correlation_id,
                        notification_window_at, context_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate["id"], candidate["fingerprint"],
                        candidate["severity"], candidate["event_type"],
                        candidate["status"], candidate["first_seen_at"],
                        candidate["last_seen_at"], 1,
                        candidate["first_event_id"], candidate["latest_event_id"],
                        candidate["job_id"], candidate["correlation_id"],
                        candidate["notification_window_at"],
                        _json_dumps(candidate["context"]),
                    ),
                )
                incident_id = candidate["id"]
                notification_claim_at = candidate["notification_window_at"]
            else:
                existing = self._incident_from_row(row)
                old_severity = _text(existing.get("severity"))
                new_severity = candidate["severity"]
                severity = (
                    old_severity
                    if _severity_rank(old_severity) >= _severity_rank(new_severity)
                    else new_severity
                )
                candidate_is_latest = (
                    candidate["last_seen_at"], candidate["latest_event_id"]
                ) >= (
                    _text(existing.get("last_seen_at")),
                    _text(existing.get("latest_event_id")),
                )
                candidate_is_first = (
                    candidate["first_seen_at"],
                    candidate["first_event_id"],
                    candidate["id"],
                ) < (
                    _text(existing.get("first_seen_at")),
                    _text(existing.get("first_event_id")),
                    _text(existing.get("id")),
                )
                first_seen_at = (
                    candidate["first_seen_at"]
                    if candidate_is_first
                    else _text(existing.get("first_seen_at"))
                )
                first_event_id = (
                    candidate["first_event_id"]
                    if candidate_is_first
                    else _text(existing.get("first_event_id"))
                )
                notification_window_at = _text(
                    existing.get("notification_window_at")
                )
                notification_previous_window_at = notification_window_at
                notification_due = False
                if candidate_is_latest:
                    try:
                        current = datetime.fromisoformat(
                            candidate["last_seen_at"].replace("Z", "+00:00")
                        )
                        window_started = datetime.fromisoformat(
                            notification_window_at.replace("Z", "+00:00")
                        )
                        notification_due = (
                            current - window_started
                            >= timedelta(seconds=window_seconds)
                        )
                    except (TypeError, ValueError):
                        notification_due = True
                    if notification_due:
                        notification_window_at = candidate["last_seen_at"]
                        notification_claim_at = notification_window_at
                    latest_job_id = candidate["job_id"]
                    latest_correlation_id = candidate["correlation_id"]
                    if not latest_job_id and not latest_correlation_id:
                        latest_job_id = _text(existing.get("job_id"))
                        latest_correlation_id = _text(
                            existing.get("correlation_id")
                        )
                    merged_context = dict(existing.get("context") or {})
                    merged_context.update(candidate["context"])
                    sanitized_context = redact_sensitive_value(merged_context)
                    merged_context = (
                        sanitized_context
                        if isinstance(sanitized_context, dict)
                        else {}
                    )
                    event_type = candidate["event_type"]
                    last_seen_at = candidate["last_seen_at"]
                    latest_event_id = candidate["latest_event_id"]
                else:
                    latest_job_id = _text(existing.get("job_id"))
                    latest_correlation_id = _text(existing.get("correlation_id"))
                    merged_context = dict(existing.get("context") or {})
                    event_type = _text(existing.get("event_type"))
                    last_seen_at = _text(existing.get("last_seen_at"))
                    latest_event_id = _text(existing.get("latest_event_id"))
                incident_id = _text(existing.get("id"))
                conn.execute(
                    """
                    UPDATE incidents SET
                        severity = ?, event_type = ?, first_seen_at = ?,
                        last_seen_at = ?, first_event_id = ?,
                        occurrence_count = occurrence_count + 1,
                        latest_event_id = ?, job_id = ?, correlation_id = ?,
                        notification_window_at = ?, context_json = ?
                    WHERE id = ?
                    """,
                    (
                        severity, event_type, first_seen_at, last_seen_at,
                        first_event_id, latest_event_id, latest_job_id,
                        latest_correlation_id, notification_window_at,
                        _json_dumps(merged_context), incident_id,
                    ),
                )
            persisted_row = conn.execute(
                "SELECT * FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
            if source_event is not None:
                event_payload = self._normalize_operational_event(source_event)
                event_payload["incident_id"] = incident_id
                self._insert_operational_event(conn, event_payload)
                if create_notification_intent and notification_due:
                    self._insert_notification_intent(
                        conn,
                        event_id=event_payload["id"],
                        incident_id=incident_id,
                        severity=event_payload["severity"],
                        created_at=event_payload["created_at"],
                    )

        result = self._incident_from_row(persisted_row)
        result["notification_due"] = notification_due
        result["notification_claim_at"] = notification_claim_at
        result["notification_previous_window_at"] = (
            notification_previous_window_at
        )
        return result

    def release_incident_notification(
        self,
        incident_id: str,
        *,
        claimed_at: str,
        previous_at: str,
    ) -> bool:
        """Release one notification-window claim using compare-and-swap."""

        self.initialize()
        normalized_id = _text(incident_id)
        normalized_claim = _canonical_timestamp(
            claimed_at, field="claimed_at"
        )
        normalized_previous = _canonical_timestamp(
            previous_at, field="previous_at", required=False
        )
        if not normalized_id:
            return False
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE incidents
                SET notification_window_at = ?
                WHERE id = ? AND status = 'open'
                  AND notification_window_at = ?
                """,
                (normalized_previous, normalized_id, normalized_claim),
            )
        return cursor.rowcount == 1

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

    def query_incident_context(
        self,
        incident_id: str,
        *,
        problem_cursor: str = "",
        problem_limit: int = 20,
        before_limit: int = 5,
        after_limit: int = 5,
    ) -> dict[str, Any] | None:
        """Return one bounded chronological incident context without scanning."""

        self.initialize()
        normalized_id = _text(incident_id)
        if not normalized_id:
            return None
        page_limit = _bounded_page_limit(problem_limit)
        try:
            bounded_before = max(0, min(5, int(before_limit)))
        except (TypeError, ValueError):
            bounded_before = 5
        try:
            bounded_after = max(0, min(5, int(after_limit)))
        except (TypeError, ValueError):
            bounded_after = 5

        with self.connection() as conn:
            incident_row = conn.execute(
                "SELECT * FROM incidents WHERE id = ?", (normalized_id,)
            ).fetchone()
            if incident_row is None:
                return None
            incident = self._incident_from_row(incident_row)
            job_id = _text(incident.get("job_id"))
            correlation_id = _text(incident.get("correlation_id"))
            if job_id:
                scope_column, scope_value = "job_id", job_id
            elif correlation_id:
                scope_column, scope_value = "correlation_id", correlation_id
            else:
                return {
                    "before": [],
                    "problem": [],
                    "after": [],
                    "problem_next_cursor": "",
                }
            boundary_rows = conn.execute(
                """
                SELECT id, created_at, job_id, correlation_id
                FROM operational_events
                WHERE id IN (?, ?)
                """,
                (
                    _text(incident.get("first_event_id")),
                    _text(incident.get("latest_event_id")),
                ),
            ).fetchall()
            boundaries = {_text(row["id"]): row for row in boundary_rows}
            first_row = boundaries.get(_text(incident.get("first_event_id")))
            latest_row = boundaries.get(_text(incident.get("latest_event_id")))
            if (
                latest_row is None
                or _text(latest_row[scope_column]) != scope_value
            ):
                return {
                    "before": [],
                    "problem": [],
                    "after": [],
                    "problem_next_cursor": "",
                }
            if (
                first_row is None
                or _text(first_row[scope_column]) != scope_value
            ):
                first_row = latest_row
            first = (_text(first_row["created_at"]), _text(first_row["id"]))
            latest = (_text(latest_row["created_at"]), _text(latest_row["id"]))
            if latest < first:
                first, latest = latest, first

            before_rows = conn.execute(
                _INCIDENT_CONTEXT_BEFORE_SQL.format(scope_column=scope_column),
                (scope_value, first[0], first[1], bounded_before),
            ).fetchall()

            problem_params: list[object] = [
                scope_value,
                first[0],
                first[1],
                latest[0],
                latest[1],
            ]
            cursor_at, cursor_id = _decode_page_cursor(problem_cursor)
            if _text(problem_cursor) and not (cursor_at and cursor_id):
                raise ValueError("invalid incident context cursor")
            cursor_clause = ""
            if cursor_at and cursor_id:
                cursor_clause = "AND (created_at, id) > (?, ?)"
                problem_params.extend([cursor_at, cursor_id])
            problem_rows = conn.execute(
                _INCIDENT_CONTEXT_PROBLEM_SQL.format(
                    scope_column=scope_column,
                    cursor_clause=cursor_clause,
                ),
                (*problem_params, page_limit + 1),
            ).fetchall()
            after_rows = conn.execute(
                _INCIDENT_CONTEXT_AFTER_SQL.format(scope_column=scope_column),
                (scope_value, latest[0], latest[1], bounded_after),
            ).fetchall()

        has_more = len(problem_rows) > page_limit
        problem = [self._event_from_row(row) for row in problem_rows[:page_limit]]
        return {
            "before": [
                self._event_from_row(row) for row in reversed(before_rows)
            ],
            "problem": problem,
            "after": [self._event_from_row(row) for row in after_rows],
            "problem_next_cursor": (
                _page_cursor(problem[-1]["created_at"], problem[-1]["id"])
                if has_more and problem
                else ""
            ),
        }

    @staticmethod
    def _notification_delivery_payload(
        record: dict[str, object],
    ) -> dict[str, Any]:
        delivery_id = _text(record.get("id"))
        if not delivery_id:
            raise ValueError("notification delivery id is required")
        status = _delivery_status(record.get("status"))
        primary_channel = _delivery_channel(
            record.get("primary_channel"), allow_empty=False
        )
        used_channel = _delivery_channel(
            record.get("used_channel"), allow_empty=True
        )
        severity = _text(record.get("severity"))
        if severity not in _NOTIFICATION_DELIVERY_SEVERITIES:
            raise ValueError("invalid notification delivery severity")
        created_at = _canonical_timestamp(
            record.get("created_at"), field="created_at"
        )
        updated_at = _canonical_timestamp(
            record.get("updated_at"), field="updated_at"
        )
        next_attempt_at = _canonical_timestamp(
            record.get("next_attempt_at"),
            field="next_attempt_at",
            required=False,
        )
        recipients = record.get("recipients", [])
        if not isinstance(recipients, list):
            raise ValueError("notification delivery recipients must be a list")
        message = record.get("message", {})
        if not isinstance(message, dict):
            raise ValueError("notification delivery message must be an object")
        attempts = record.get("attempts", [])
        if not isinstance(attempts, list):
            raise ValueError("notification delivery attempts must be a list")
        return {
            "id": delivery_id,
            "incident_id": _text(record.get("incident_id")),
            "event_id": _text(record.get("event_id")),
            "severity": severity,
            "status": status,
            "primary_channel": primary_channel,
            "used_channel": used_channel,
            "recipients": recipients,
            "message": message,
            "attempts": attempts,
            "created_at": created_at,
            "updated_at": updated_at,
            "next_attempt_at": next_attempt_at,
        }

    @staticmethod
    def _insert_notification_delivery(
        conn: sqlite3.Connection, payload: dict[str, Any]
    ) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO notification_deliveries (
                id, incident_id, event_id, severity, status,
                primary_channel, used_channel, recipients_json,
                message_json, attempts_json, created_at, updated_at,
                next_attempt_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"], payload["incident_id"], payload["event_id"],
                payload["severity"], payload["status"],
                payload["primary_channel"], payload["used_channel"],
                _json_dumps(payload["recipients"]),
                _json_dumps(payload["message"]),
                _json_dumps(payload["attempts"]), payload["created_at"],
                payload["updated_at"], payload["next_attempt_at"],
            ),
        )

    def enqueue_notification_delivery(
        self, record: dict[str, object]
    ) -> dict[str, Any]:
        """Insert one durable notification delivery and return its stored form."""

        self.initialize()
        payload = self._notification_delivery_payload(record)
        with self.connection() as conn:
            self._insert_notification_delivery(conn, payload)
            row = conn.execute(
                "SELECT * FROM notification_deliveries WHERE id = ?",
                (payload["id"],),
            ).fetchone()
        return self._delivery_from_row(row)

    def pending_notification_intents(
        self, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return a bounded deterministic batch of pending outbox intents."""

        self.initialize()
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, event_id, incident_id, severity, status,
                       created_at, updated_at, completed_at
                FROM notification_outbox
                WHERE status = 'pending'
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                (_bounded_page_limit(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def notification_intent_context(
        self, intent_id: str
    ) -> dict[str, Any] | None:
        """Load the durable event and optional incident needed to materialize an intent."""

        self.initialize()
        with self.connection() as conn:
            intent = conn.execute(
                "SELECT * FROM notification_outbox WHERE id = ? AND status = 'pending'",
                (_text(intent_id),),
            ).fetchone()
            if intent is None:
                return None
            event_row = conn.execute(
                "SELECT * FROM operational_events WHERE id = ?",
                (intent["event_id"],),
            ).fetchone()
            incident_row = None
            if _text(intent["incident_id"]):
                incident_row = conn.execute(
                    "SELECT * FROM incidents WHERE id = ?",
                    (intent["incident_id"],),
                ).fetchone()
        if event_row is None:
            raise RuntimeError("notification intent source event is unavailable")
        return {
            "intent": dict(intent),
            "event": self._event_from_row(event_row),
            "incident": self._incident_from_row(incident_row) if incident_row else {},
        }

    def materialize_notification_intent(
        self,
        intent_id: str,
        *,
        delivery: dict[str, object] | None,
        completed_at: str,
    ) -> dict[str, Any]:
        """Atomically create at most one delivery and complete an outbox intent."""

        self.initialize()
        normalized_id = _text(intent_id)
        completed = _canonical_timestamp(completed_at, field="completed_at")
        payload = (
            self._notification_delivery_payload(delivery)
            if isinstance(delivery, dict)
            else None
        )
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            intent = conn.execute(
                "SELECT * FROM notification_outbox WHERE id = ?",
                (normalized_id,),
            ).fetchone()
            if intent is None:
                return {}
            if payload is not None:
                if payload["event_id"] != _text(intent["event_id"]):
                    raise ValueError("delivery event does not match notification intent")
                existing = conn.execute(
                    """
                    SELECT * FROM notification_deliveries
                    WHERE event_id = ?
                    ORDER BY created_at, id LIMIT 1
                    """,
                    (payload["event_id"],),
                ).fetchone()
                if existing is None and intent["status"] == "pending":
                    self._insert_notification_delivery(conn, payload)
                    existing = conn.execute(
                        "SELECT * FROM notification_deliveries WHERE id = ?",
                        (payload["id"],),
                    ).fetchone()
                    if (
                        existing is None
                        or _text(existing["event_id"]) != payload["event_id"]
                    ):
                        raise RuntimeError(
                            "notification delivery identity conflict"
                        )
            else:
                existing = None
            if intent["status"] == "pending":
                conn.execute(
                    """
                    UPDATE notification_outbox
                    SET status = 'done', updated_at = ?, completed_at = ?
                    WHERE id = ? AND status = 'pending'
                    """,
                    (completed, completed, normalized_id),
                )
        return self._delivery_from_row(existing) if existing is not None else {}

    def prune_done_notification_intents(self, before: str) -> int:
        """Delete completed intents older than the idempotency retention boundary."""

        self.initialize()
        boundary = _canonical_timestamp(before, field="before")
        with self.connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM notification_outbox
                WHERE status = 'done' AND completed_at < ?
                """,
                (boundary,),
            )
        return max(0, cursor.rowcount)

    def pending_notification_deliveries(
        self, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return due pending deliveries in deterministic queue order."""

        self.initialize()
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM notification_deliveries
                WHERE status = 'pending'
                  AND (next_attempt_at = '' OR next_attempt_at <= ?)
                ORDER BY COALESCE(NULLIF(next_attempt_at, ''), created_at) ASC,
                         created_at ASC, id ASC
                LIMIT ?
                """,
                (_now_iso(), _bounded_page_limit(limit)),
            ).fetchall()
        return [self._delivery_from_row(row) for row in rows]

    def update_notification_delivery(
        self,
        delivery_id: str,
        *,
        status: str,
        used_channel: str = "",
        attempts: object = None,
        updated_at: str,
        next_attempt_at: str = "",
    ) -> dict[str, Any]:
        """Update mutable delivery state and return the decoded row."""

        self.initialize()
        normalized_id = _text(delivery_id)
        if not normalized_id:
            raise ValueError("notification delivery id is required")
        normalized_status = _delivery_status(status)
        normalized_channel = _delivery_channel(used_channel, allow_empty=True)
        normalized_updated_at = _canonical_timestamp(
            updated_at, field="updated_at"
        )
        normalized_next_attempt = _canonical_timestamp(
            next_attempt_at, field="next_attempt_at", required=False
        )
        if attempts is not None and not isinstance(attempts, list):
            raise ValueError("notification delivery attempts must be a list")
        expected_status = "pending" if normalized_status == "sending" else "sending"
        with self.connection() as conn:
            assignments = [
                "status = ?",
                "used_channel = ?",
                "updated_at = ?",
                "next_attempt_at = ?",
            ]
            params: list[object] = [
                normalized_status,
                normalized_channel,
                normalized_updated_at,
                normalized_next_attempt,
            ]
            if attempts is not None:
                assignments.append("attempts_json = ?")
                params.append(_json_dumps(attempts))
            params.extend([normalized_id, expected_status])
            cursor = conn.execute(
                f"""
                UPDATE notification_deliveries
                SET {", ".join(assignments)}
                WHERE id = ? AND status = ?
                """,
                params,
            )
            if cursor.rowcount == 0:
                row = conn.execute(
                    "SELECT status FROM notification_deliveries WHERE id = ?",
                    (normalized_id,),
                ).fetchone()
                if normalized_status == "sending" or row is None:
                    return {}
                raise ValueError(
                    f"invalid notification delivery transition: "
                    f"{row['status']} -> {normalized_status}"
                )
            row = conn.execute(
                "SELECT * FROM notification_deliveries WHERE id = ?",
                (normalized_id,),
            ).fetchone()
        return self._delivery_from_row(row) if row else {}

    def query_notification_deliveries(
        self, *, incident_id: str = "", cursor: str = "", limit: int = 20
    ) -> dict[str, Any]:
        """Return a descending cursor page of notification deliveries."""

        self.initialize()
        clauses: list[str] = []
        params: list[object] = []
        if _text(incident_id):
            clauses.append("incident_id = ?")
            params.append(_text(incident_id))
        cursor_at, cursor_id = _decode_page_cursor(cursor)
        if cursor_at and cursor_id:
            clauses.append("(created_at < ? OR (created_at = ? AND id < ?))")
            params.extend([cursor_at, cursor_at, cursor_id])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        page_limit = _bounded_page_limit(limit)
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM notification_deliveries
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (*params, page_limit + 1),
            ).fetchall()
        has_more = len(rows) > page_limit
        items = [self._delivery_from_row(row) for row in rows[:page_limit]]
        next_cursor = (
            _page_cursor(items[-1]["created_at"], items[-1]["id"])
            if has_more and items
            else ""
        )
        return {"items": items, "next_cursor": next_cursor}

    def notification_deliveries_for_incidents(
        self, incident_ids: list[str], *, per_incident_limit: int = 5
    ) -> list[dict[str, Any]]:
        """Return a bounded recent delivery set for a bounded incident page."""

        self.initialize()
        normalized_ids = list(
            dict.fromkeys(_text(value) for value in incident_ids if _text(value))
        )[:100]
        if not normalized_ids:
            return []
        bounded_limit = max(1, min(10, int(per_incident_limit or 5)))
        placeholders = ", ".join("?" for _value in normalized_ids)
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM (
                    SELECT notification_deliveries.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY incident_id
                               ORDER BY created_at DESC, id DESC
                           ) AS delivery_rank
                    FROM notification_deliveries
                    WHERE incident_id IN ({placeholders})
                )
                WHERE delivery_rank <= ?
                ORDER BY created_at DESC, id DESC
                """,
                (*normalized_ids, bounded_limit),
            ).fetchall()
        deliveries = [self._delivery_from_row(row) for row in rows]
        for delivery in deliveries:
            delivery.pop("delivery_rank", None)
        return deliveries

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
        """Delete old info events and compact obsolete pre-checkpoint markers.

        A marker older than retention is intentionally no longer resolvable and
        reconnects at the current high-water; retained history comes from the
        bounded archive snapshot. Sequence zero and the newest checkpoint stay.
        """

        self.initialize()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM operational_events
                WHERE severity = 'info' AND created_at < ?
                  AND id NOT IN (
                      SELECT event_id FROM notification_outbox
                      WHERE status = 'pending'
                  )
                """,
                (_text(before),),
            )
            removed = max(0, cursor.rowcount)
            conn.execute(
                """
                DELETE FROM operational_event_stream
                WHERE sequence <> 0
                  AND sequence < (
                      SELECT COALESCE(MAX(sequence), 0)
                      FROM operational_event_stream
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM operational_events AS e
                      WHERE e.id = operational_event_stream.event_id
                  )
                """
            )
            now = _now_iso()
            conn.execute(
                "DELETE FROM pimcore_integration_contexts WHERE expires_at <= ?",
                (now,),
            )
            return removed

    def create_pimcore_integration_context(
        self,
        *,
        username: str,
        mode: str,
        object_id: object,
        results: object,
        ttl_seconds: int = 10 * 60,
        now: datetime | None = None,
    ) -> str:
        """Persist redacted SQL-profile evidence behind an opaque short-lived ID."""

        self.initialize()
        bound_user = _text(username)
        bound_mode = _text(mode).lower()
        bound_object_id = _text(object_id)
        if not bound_user:
            raise ValueError("Pimcore integration context requires a user")
        if bound_mode not in {"create", "edit"}:
            raise ValueError("Pimcore integration context mode is invalid")
        if bound_mode == "create":
            bound_object_id = ""
        elif not bound_object_id:
            raise ValueError("Pimcore edit integration context requires an object")
        try:
            bounded_ttl = max(30, min(int(ttl_seconds), 30 * 60))
        except (TypeError, ValueError):
            bounded_ttl = 10 * 60
        created = now or datetime.now(timezone.utc)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        created = created.astimezone(timezone.utc)
        created_at = _iso_from_timestamp(created)
        expires_at = _iso_from_timestamp(created + timedelta(seconds=bounded_ttl))
        safe_results = redact_sensitive_value(
            results if isinstance(results, dict) else {}, text_limit=32 * 1024
        )
        if not isinstance(safe_results, dict):
            safe_results = {}
        context_id = secrets.token_urlsafe(32)
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM pimcore_integration_contexts WHERE expires_at <= ?",
                (created_at,),
            )
            conn.execute(
                """
                INSERT INTO pimcore_integration_contexts (
                    id, username, mode, object_id, results_json,
                    created_at, expires_at, consumed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '')
                """,
                (
                    context_id,
                    bound_user,
                    bound_mode,
                    bound_object_id,
                    _json_dumps(safe_results),
                    created_at,
                    expires_at,
                ),
            )
        return context_id

    def consume_pimcore_integration_context(
        self,
        context_id: object,
        *,
        username: str,
        mode: str,
        object_id: object,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Atomically consume evidence only when every server binding matches."""

        self.initialize()
        identity = _text(context_id)
        bound_user = _text(username)
        bound_mode = _text(mode).lower()
        bound_object_id = "" if bound_mode == "create" else _text(object_id)
        if not identity or not bound_user or bound_mode not in {"create", "edit"}:
            return None
        consumed_at = _iso_from_timestamp(now or datetime.now(timezone.utc))
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM pimcore_integration_contexts WHERE expires_at <= ?",
                (consumed_at,),
            )
            row = conn.execute(
                """
                SELECT results_json FROM pimcore_integration_contexts
                WHERE id = ? AND username = ? AND mode = ? AND object_id = ?
                  AND consumed_at = '' AND expires_at > ?
                """,
                (
                    identity,
                    bound_user,
                    bound_mode,
                    bound_object_id,
                    consumed_at,
                ),
            ).fetchone()
            if row is None:
                return None
            cursor = conn.execute(
                """
                UPDATE pimcore_integration_contexts SET consumed_at = ?
                WHERE id = ? AND consumed_at = ''
                """,
                (consumed_at, identity),
            )
            if cursor.rowcount != 1:
                return None
            payload = _json_loads(row["results_json"], {})
            return dict(payload) if isinstance(payload, dict) else {}

    def prune_pimcore_integration_contexts(
        self, *, now: datetime | None = None
    ) -> int:
        """Bound retained integration contexts during regular maintenance."""

        self.initialize()
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        current = current.astimezone(timezone.utc)
        current_at = _iso_from_timestamp(current)
        consumed_before = _iso_from_timestamp(current - timedelta(days=1))
        with self.connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM pimcore_integration_contexts
                WHERE expires_at <= ?
                   OR (consumed_at <> '' AND consumed_at <= ?)
                """,
                (current_at, consumed_before),
            )
            return max(0, cursor.rowcount)

    def clear_operational_data(self) -> dict[str, int]:
        """Clear structured operational tables without touching product history."""

        self.initialize()
        deleted: dict[str, int] = {}
        with self.connection() as conn:
            for table in (
                "operational_events", "job_runs", "incidents", "alert_reads",
                "notification_deliveries", "notification_outbox",
                "pimcore_integration_contexts",
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
        safe_record = redact_sensitive_value(record)
        record = safe_record if isinstance(safe_record, dict) else {}
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
            item = redact_sensitive_value(
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
            if isinstance(item, dict):
                result.append(item)
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

    def history_summary_snapshot(
        self, *, user: str = "", query: str = "", page: int = 1, page_size: int = 50
    ) -> dict[str, Any]:
        """Return a paged history-group summary without loading full payloads."""

        self.initialize()
        try:
            bounded_page_size = max(1, min(50, int(page_size or 50)))
        except (TypeError, ValueError):
            bounded_page_size = 50
        try:
            requested_page = max(1, int(page or 1))
        except (TypeError, ValueError):
            requested_page = 1
        clauses: list[str] = []
        params: list[object] = []
        _append_history_index_filters(clauses, params, user=user, query=query)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connection() as conn:
            counts = conn.execute(
                f"""
                SELECT COUNT(*) AS record_count, COUNT(DISTINCT ean) AS group_count
                FROM web_history_index {where_clause}
                """,
                params,
            ).fetchone()
            total_records = int(counts["record_count"] or 0) if counts else 0
            total_groups = int(counts["group_count"] or 0) if counts else 0
            total_pages = max(1, (total_groups + bounded_page_size - 1) // bounded_page_size)
            current_page = min(requested_page, total_pages)
            rows = conn.execute(
                f"""
                WITH filtered AS (
                    SELECT id, ean, entry_json, created_at
                    FROM web_history_index {where_clause}
                ), grouped AS (
                    SELECT ean, COUNT(*) AS change_count, MAX(created_at) AS latest_created_at
                    FROM filtered
                    GROUP BY ean
                ), page_groups AS (
                    SELECT grouped.ean, grouped.change_count, grouped.latest_created_at,
                        (
                            SELECT latest.id
                            FROM filtered AS latest
                            WHERE latest.ean = grouped.ean
                              AND latest.created_at = grouped.latest_created_at
                            ORDER BY latest.id DESC
                            LIMIT 1
                        ) AS latest_id
                    FROM grouped
                    ORDER BY grouped.latest_created_at DESC, latest_id DESC
                    LIMIT ? OFFSET ?
                )
                SELECT page_groups.ean, page_groups.change_count,
                    page_groups.latest_created_at, filtered.entry_json
                FROM page_groups
                JOIN filtered ON filtered.id = page_groups.latest_id
                ORDER BY page_groups.latest_created_at DESC, page_groups.latest_id DESC
                """,
                [*params, bounded_page_size, (current_page - 1) * bounded_page_size],
            ).fetchall()
            users = [
                _text(row["username"])
                for row in conn.execute(
                    """
                    SELECT DISTINCT username FROM web_history_index
                    WHERE username <> '' ORDER BY username
                    """
                ).fetchall()
            ]
        groups = []
        for row in rows:
            try:
                entry = json.loads(_text(row["entry_json"]))
            except (TypeError, ValueError):
                entry = {}
            groups.append(
                {
                    "ean": _text(row["ean"]) or "BRAK-EAN",
                    "latest_ts": _history_timestamp_from_created_at(
                        row["latest_created_at"]
                    ),
                    "change_count": int(row["change_count"] or 0),
                    "entry": entry if isinstance(entry, dict) else {},
                }
            )
        return {
            "groups": groups,
            "users": users,
            "count": total_records,
            "total_groups": total_groups,
            "page": current_page,
            "page_size": bounded_page_size,
            "total_pages": total_pages,
            "query": _text(query),
        }

    def history_group_snapshot(
        self,
        *,
        ean: str,
        user: str = "",
        query: str = "",
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any] | None:
        """Return one bounded, filtered history group from the payload table."""

        self.initialize()
        try:
            bounded_page_size = max(1, min(25, int(page_size or 25)))
        except (TypeError, ValueError):
            bounded_page_size = 25
        try:
            requested_page = max(1, int(page or 1))
        except (TypeError, ValueError):
            requested_page = 1
        normalized_ean = _text(ean) or "BRAK-EAN"
        clauses = ["ean = ?"]
        params: list[object] = [normalized_ean]
        _append_history_index_filters(clauses, params, user=user, query=query)
        where_clause = f"WHERE {' AND '.join(clauses)}"
        with self.connection() as conn:
            count_row = conn.execute(
                f"SELECT COUNT(*) AS item_count FROM web_history_index {where_clause}",
                params,
            ).fetchone()
            total_items = int(count_row["item_count"] or 0) if count_row else 0
            if not total_items:
                return None
            total_pages = max(1, (total_items + bounded_page_size - 1) // bounded_page_size)
            current_page = min(requested_page, total_pages)
            rows = conn.execute(
                f"""
                WITH page_ids AS (
                    SELECT id, created_at
                    FROM web_history_index {where_clause}
                    ORDER BY created_at DESC, id DESC
                    LIMIT ? OFFSET ?
                )
                SELECT web_history.payload_json, page_ids.created_at
                FROM page_ids
                JOIN web_history ON web_history.id = page_ids.id
                ORDER BY page_ids.created_at DESC, page_ids.id DESC
                """,
                [*params, bounded_page_size, (current_page - 1) * bounded_page_size],
            ).fetchall()
            latest_row = conn.execute(
                f"""
                SELECT created_at FROM web_history_index {where_clause}
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                params,
            ).fetchone()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = _json_loads(row["payload_json"], {})
            if not isinstance(payload, dict):
                continue
            redacted = redact_sensitive_value(payload)
            if isinstance(redacted, dict):
                items.append(redacted)
        return {
            "ean": normalized_ean,
            "latest_ts": _history_timestamp_from_created_at(
                latest_row["created_at"] if latest_row else ""
            ),
            "items": items,
            "total_items": total_items,
            "page": current_page,
            "page_size": bounded_page_size,
            "total_pages": total_pages,
        }

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
                redacted = redact_sensitive_value(payload)
                if isinstance(redacted, dict):
                    records.append(redacted)
        return records

    def save_history(self, records: list[dict[str, object]]) -> None:
        """Replace stored web history records."""

        self.initialize()
        with self.connection() as conn:
            conn.execute("DELETE FROM web_history")
            conn.execute("DELETE FROM web_history_index")
            for item in records or []:
                if not isinstance(item, dict):
                    continue
                record_id = _text(item.get("id")) or f"hist-{uuid.uuid4().hex}"
                safe_item = redact_sensitive_value(item)
                payload = dict(safe_item) if isinstance(safe_item, dict) else {}
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
                _upsert_web_history_index(
                    conn,
                    payload,
                    record_id=record_id,
                    created_at=created_at,
                )
            _prune_web_history(conn)

    def append_history(self, record: dict[str, object]) -> None:
        """Append or replace one web history record."""

        self.initialize()
        if not isinstance(record, dict):
            return
        record_id = _text(record.get("id")) or f"hist-{uuid.uuid4().hex}"
        safe_record = redact_sensitive_value(record)
        payload = dict(safe_record) if isinstance(safe_record, dict) else {}
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
            _upsert_web_history_index(
                conn,
                payload,
                record_id=record_id,
                created_at=created_at,
            )
            _prune_web_history(conn)

    def claim_daily_change_summary(
        self, window_end: str, *, claimed_at: str
    ) -> dict[str, str] | None:
        """Claim one scheduled report while preserving the last successful window."""

        end = _canonical_timestamp(window_end, field="window_end")
        claimed = _canonical_timestamp(claimed_at, field="claimed_at")
        claim_token = uuid.uuid4().hex
        self.initialize()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            # A later scheduled interval must never jump ahead of a failed
            # one; it would otherwise overlap the same history range.
            outstanding = conn.execute(
                """
                SELECT window_start, window_end, status, next_attempt_at
                FROM daily_change_summary_reports
                WHERE status IN ('pending', 'sending')
                ORDER BY window_end ASC
                LIMIT 1
                """
            ).fetchone()
            if outstanding is not None:
                if _text(outstanding["status"]) != "pending":
                    return None
                retry_at = _text(outstanding["next_attempt_at"])
                if retry_at and retry_at > claimed:
                    return None
                pending_end = _text(outstanding["window_end"])
                result = conn.execute(
                    """
                    UPDATE daily_change_summary_reports
                    SET status = 'sending', claimed_at = ?, updated_at = ?, claim_token = ?
                    WHERE window_end = ? AND status = 'pending'
                      AND (next_attempt_at = '' OR next_attempt_at <= ?)
                    """,
                    (claimed, claimed, claim_token, pending_end, claimed),
                )
                if result.rowcount != 1:
                    return None
                return {
                    "window_start": _text(outstanding["window_start"]),
                    "window_end": pending_end,
                    "status": "sending",
                    "claim_token": claim_token,
                }
            existing = conn.execute(
                "SELECT window_start, status FROM daily_change_summary_reports WHERE window_end = ?",
                (end,),
            ).fetchone()
            if existing is not None:
                return None
            previous = conn.execute(
                """
                SELECT window_end FROM daily_change_summary_reports
                WHERE status = 'sent' AND window_end < ?
                ORDER BY window_end DESC LIMIT 1
                """,
                (end,),
            ).fetchone()
            if previous is None:
                end_datetime = datetime.fromisoformat(end.replace("Z", "+00:00"))
                start = (end_datetime - timedelta(days=1)).isoformat(
                    timespec="milliseconds"
                ).replace("+00:00", "Z")
            else:
                start = _text(previous["window_end"])
            result = conn.execute(
                """
                INSERT OR IGNORE INTO daily_change_summary_reports (
                    window_end, window_start, status, claimed_at, created_at, updated_at,
                    claim_token
                ) VALUES (?, ?, 'sending', ?, ?, ?, ?)
                """,
                (end, start, claimed, claimed, claimed, claim_token),
            )
            if result.rowcount != 1:
                return None
            return {
                "window_start": start,
                "window_end": end,
                "status": "sending",
                "claim_token": claim_token,
            }

    def finalize_daily_change_summary(
        self,
        window_end: str,
        *,
        status: str,
        claim_token: str,
        next_attempt_at: str = "",
    ) -> bool:
        """Finalize a claimed report; pending reports are safe to retry."""

        end = _canonical_timestamp(window_end, field="window_end")
        normalized = _text(status)
        if normalized not in {"pending", "sent"}:
            raise ValueError("invalid daily change summary status")
        token = _bounded_scalar_text(
            claim_token, field="claim_token", limit=128, required=True
        )
        retry_at = (
            _canonical_timestamp(next_attempt_at, field="next_attempt_at")
            if normalized == "pending" and _text(next_attempt_at)
            else ""
        )
        now = _now_iso()
        self.initialize()
        with self.connection() as conn:
            result = conn.execute(
                """
                UPDATE daily_change_summary_reports
                SET status = ?, updated_at = ?, sent_at = CASE WHEN ? = 'sent' THEN ? ELSE '' END,
                    claimed_at = CASE WHEN ? = 'pending' THEN '' ELSE claimed_at END,
                    next_attempt_at = ?, claim_token = ''
                WHERE window_end = ? AND status = 'sending' AND claim_token = ?
                """,
                (normalized, now, normalized, now, normalized, retry_at, end, token),
            )
        return result.rowcount == 1

    def recover_daily_change_summaries(self, *, stale_before: str) -> int:
        """Release interrupted report sends when a worker starts again."""

        boundary = _canonical_timestamp(stale_before, field="stale_before")
        self.initialize()
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT window_end, claimed_at, claim_token
                FROM daily_change_summary_reports
                WHERE status = 'sending' AND claimed_at <> '' AND claimed_at <= ?
                """,
                (boundary,),
            ).fetchall()
            recovered = 0
            for row in rows:
                result = conn.execute(
                    """
                    UPDATE daily_change_summary_reports
                    SET status = 'pending', claimed_at = '', claim_token = '', updated_at = ?
                    WHERE window_end = ? AND status = 'sending'
                      AND claimed_at = ? AND claim_token = ?
                    """,
                    (
                        _now_iso(),
                        _text(row["window_end"]),
                        _text(row["claimed_at"]),
                        _text(row["claim_token"]),
                    ),
                )
                recovered += result.rowcount == 1
        return recovered

    def daily_change_history(
        self, *, window_start: str, window_end: str
    ) -> list[dict[str, Any]]:
        """Return history belonging strictly to one durable report interval."""

        start = _canonical_timestamp(window_start, field="window_start")
        end = _canonical_timestamp(window_end, field="window_end")
        self.initialize()
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM web_history
                WHERE created_at > ? AND created_at <= ?
                ORDER BY created_at, rowid
                """,
                (start, end),
            ).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            payload = _json_loads(row["payload_json"], {})
            if isinstance(payload, dict):
                safe = redact_sensitive_value(payload)
                if isinstance(safe, dict):
                    records.append(safe)
        return records

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
