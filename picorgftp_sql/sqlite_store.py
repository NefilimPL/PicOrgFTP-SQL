"""SQLite-backed persistence for PicOrgFTP-SQL data."""

from __future__ import annotations

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

SCHEMA_VERSION = 2
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
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

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
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
                    ts REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS file_index_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
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
            conn.execute("DELETE FROM app_settings WHERE key = 'config'")
            updated_at = _now_iso()
            for path, value in rows:
                conn.execute(
                    """
                    INSERT INTO app_config_values (path, value_json, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (path, _json_dumps(value), updated_at),
                )

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
                "SELECT payload_json FROM web_history ORDER BY ts, rowid"
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
                try:
                    ts = float(payload.get("ts") or 0.0)
                except (TypeError, ValueError):
                    ts = 0.0
                conn.execute(
                    """
                    INSERT INTO web_history (id, payload_json, ts)
                    VALUES (?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        ts = excluded.ts
                    """,
                    (record_id, _json_dumps(payload), ts),
                )

    def append_history(self, record: dict[str, object]) -> None:
        """Append or replace one web history record."""

        self.initialize()
        if not isinstance(record, dict):
            return
        record_id = _text(record.get("id")) or f"hist-{uuid.uuid4().hex}"
        payload = dict(record)
        payload["id"] = record_id
        try:
            ts = float(payload.get("ts") or 0.0)
        except (TypeError, ValueError):
            ts = 0.0
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO web_history (id, payload_json, ts)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    ts = excluded.ts
                """,
                (record_id, _json_dumps(payload), ts),
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
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO file_index_cache (cache_key, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (_text(key) or "default", _json_dumps(payload or {}), _now_iso()),
            )
