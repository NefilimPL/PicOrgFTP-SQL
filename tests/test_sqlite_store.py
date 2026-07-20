"""Tests for the SQLite-backed application data store."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from picorgftp_sql.excel_utils import ENTRY_RECORDS_KEY
from picorgftp_sql.sqlite_store import SqliteStore


def test_schema_creates_expected_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "data.sqlite"
    store = SqliteStore(str(db_path))

    store.initialize()

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {
        "schema_version",
        "app_config_values",
        "slot_definitions",
        "sql_column_map",
        "sql_available_columns",
        "list_values",
        "product_entries",
        "web_users",
        "web_history",
        "file_index_cache",
        "pimcore_submissions",
        "operational_events",
        "operational_event_stream",
        "job_runs",
        "incidents",
        "alert_reads",
        "pimcore_integration_contexts",
        "entra_secret_status",
        "entra_secret_reminders",
    } <= tables

    with sqlite3.connect(db_path) as conn:
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        stream_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(operational_event_stream)")
        ]
        stream_foreign_keys = conn.execute(
            "PRAGMA foreign_key_list(operational_event_stream)"
        ).fetchall()

    assert version == 7
    assert stream_columns == ["sequence", "event_id"]
    assert stream_foreign_keys == []


def test_entra_expiry_status_round_trip_returns_only_safe_metadata(
    tmp_path: Path,
) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))

    result = store.upsert_entra_secret_status(
        {
            "tenant_id": "tenant",
            "client_id": "client",
            "status": "ok",
            "expires_at": "2026-08-01T10:00:00.000Z",
            "credential_name": "Primary",
            "credential_key_id": "internal-key",
            "application_name": "PicOrg Mailer",
            "source": "graph",
            "last_checked_at": "2026-07-17T10:00:00.000Z",
            "last_success_at": "2026-07-17T10:00:00.000Z",
            "error_code": "",
            "error_message": "",
            "secret": "must-not-persist",
            "access_token": "must-not-persist",
            "authorization": "must-not-persist",
        }
    )

    assert result == store.get_entra_secret_status("tenant", "client")
    assert result == {
        "tenant_id": "tenant",
        "client_id": "client",
        "status": "ok",
        "expires_at": "2026-08-01T10:00:00.000Z",
        "credential_name": "Primary",
        "application_name": "PicOrg Mailer",
        "source": "graph",
        "last_checked_at": "2026-07-17T10:00:00.000Z",
        "last_success_at": "2026-07-17T10:00:00.000Z",
        "error_code": "",
        "error_message": "",
    }
    assert store.get_entra_secret_status("missing", "client") == {}
    with store.connection() as conn:
        persisted = conn.execute("SELECT * FROM entra_secret_status").fetchone()
    assert "must-not-persist" not in " ".join(str(value) for value in persisted)


def test_entra_expiry_internal_status_retains_key_id_without_public_projection(
    tmp_path: Path,
) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.upsert_entra_secret_status(
        {
            "tenant_id": "tenant",
            "client_id": "client",
            "status": "ok",
            "credential_key_id": "key-internal-only",
        }
    )

    internal = store.get_entra_secret_status_internal("tenant", "client")

    assert internal["credential_key_id"] == "key-internal-only"
    assert "credential_key_id" not in store.get_entra_secret_status("tenant", "client")


def test_entra_expiry_status_requires_canonical_timestamps(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))

    with pytest.raises(ValueError, match="expires_at must be a canonical timestamp"):
        store.upsert_entra_secret_status(
            {
                "tenant_id": "tenant",
                "client_id": "client",
                "status": "ok",
                "expires_at": "2026-08-01T10:00:00Z",
            }
        )


def test_entra_expiry_status_rejects_or_redacts_malformed_public_fields(
    tmp_path: Path,
) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.upsert_entra_secret_status(
        {
            "tenant_id": "tenant",
            "client_id": "client",
            "status": "ok",
        }
    )

    with pytest.raises(ValueError, match="tenant_id must be text"):
        store.upsert_entra_secret_status(
            {
                "tenant_id": {"access_token": "tenant-secret"},
                "client_id": ["client_secret=client-secret"],
                "status": "ok",
            }
        )

    result = store.upsert_entra_secret_status(
        {
            "tenant_id": "tenant",
            "client_id": "client",
            "status": {"Authorization": "Bearer status-secret"},
            "error_message": (
                "access_token=error-secret; client_secret=client-secret; "
                "Authorization: Bearer authorization-secret"
            ),
        }
    )

    assert result["status"] == "unknown"
    public_payload = json.dumps(store.get_entra_secret_status("tenant", "client"))
    with store.connection() as conn:
        persisted = conn.execute("SELECT * FROM entra_secret_status").fetchone()
    persisted_values = " ".join(str(value) for value in persisted)
    for secret in (
        "tenant-secret",
        "client-secret",
        "status-secret",
        "error-secret",
        "authorization-secret",
    ):
        assert secret not in public_payload
        assert secret not in persisted_values


def test_entra_expiry_reminder_claim_is_idempotent_and_identity_sensitive(
    tmp_path: Path,
) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    first_claim = (
        "tenant",
        "client",
        "key-a",
        "2026-08-01T00:00:00.000Z",
        7,
        "2026-07-25T00:00:00.000Z",
    )

    assert store.claim_entra_secret_reminder(*first_claim)
    assert not store.claim_entra_secret_reminder(
        *first_claim[:-1], "2026-07-25T00:00:01.000Z"
    )
    assert store.claim_entra_secret_reminder(
        "tenant",
        "client",
        "key-b",
        "2026-08-01T00:00:00.000Z",
        7,
        "2026-07-25T00:00:00.000Z",
    )
    assert store.claim_entra_secret_reminder(
        "tenant",
        "client",
        "key-a",
        "2026-09-01T00:00:00.000Z",
        7,
        "2026-08-25T00:00:00.000Z",
    )


def test_operational_clear_preserves_entra_expiry_status_and_reminder_claims(
    tmp_path: Path,
) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.upsert_entra_secret_status(
        {
            "tenant_id": "tenant",
            "client_id": "client",
            "status": "ok",
            "expires_at": "2026-08-01T00:00:00.000Z",
            "last_checked_at": "2026-07-17T00:00:00.000Z",
        }
    )
    assert store.claim_entra_secret_reminder(
        "tenant",
        "client",
        "key-a",
        "2026-08-01T00:00:00.000Z",
        7,
        "2026-07-25T00:00:00.000Z",
    )

    store.clear_operational_data()

    assert store.get_entra_secret_status("tenant", "client")["status"] == "ok"
    assert not store.claim_entra_secret_reminder(
        "tenant",
        "client",
        "key-a",
        "2026-08-01T00:00:00.000Z",
        7,
        "2026-07-25T00:00:01.000Z",
    )


def test_clear_entra_expiry_status_also_removes_matching_reminder_claims(
    tmp_path: Path,
) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.upsert_entra_secret_status(
        {
            "tenant_id": "tenant",
            "client_id": "client",
            "status": "ok",
            "expires_at": "2026-08-01T00:00:00.000Z",
        }
    )
    assert store.claim_entra_secret_reminder(
        "tenant",
        "client",
        "key-a",
        "2026-08-01T00:00:00.000Z",
        7,
        "2026-07-25T00:00:00.000Z",
    )

    assert store.clear_entra_secret_status("tenant", "client") == 1
    assert store.get_entra_secret_status("tenant", "client") == {}
    assert store.claim_entra_secret_reminder(
        "tenant",
        "client",
        "key-a",
        "2026-08-01T00:00:00.000Z",
        7,
        "2026-07-25T00:00:01.000Z",
    )


def test_pimcore_integration_context_is_bound_redacted_and_one_time(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    now = datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)
    context_id = store.create_pimcore_integration_context(
        username="alice",
        mode="edit",
        object_id=91,
        results={
            "sql_profiles": [
                {"profile_id": "stock", "status": "error", "error": "password=secret"}
            ]
        },
        ttl_seconds=600,
        now=now,
    )

    assert len(context_id) >= 32
    assert store.consume_pimcore_integration_context(
        context_id, username="mallory", mode="edit", object_id=91, now=now
    ) is None
    assert store.consume_pimcore_integration_context(
        context_id, username="alice", mode="create", object_id=None, now=now
    ) is None
    assert store.consume_pimcore_integration_context(
        context_id, username="alice", mode="edit", object_id=92, now=now
    ) is None
    result = store.consume_pimcore_integration_context(
        context_id, username="alice", mode="edit", object_id=91, now=now
    )
    assert result["sql_profiles"][0]["profile_id"] == "stock"
    assert "secret" not in json.dumps(result)
    assert store.consume_pimcore_integration_context(
        context_id, username="alice", mode="edit", object_id=91, now=now
    ) is None


def test_pimcore_integration_context_expiry_prune_and_clear(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    now = datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)
    context_id = store.create_pimcore_integration_context(
        username="alice", mode="create", object_id=None, results={}, ttl_seconds=1, now=now
    )

    assert store.consume_pimcore_integration_context(
        context_id,
        username="alice",
        mode="create",
        object_id=None,
        now=now + timedelta(seconds=31),
    ) is None
    assert store.prune_pimcore_integration_contexts(now=now + timedelta(seconds=31)) == 0
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pimcore_integration_contexts").fetchone()[0] == 0

    store.create_pimcore_integration_context(
        username="alice", mode="create", object_id=None, results={}, now=now
    )
    deleted = store.clear_operational_data()
    assert deleted["pimcore_integration_contexts"] == 1


def test_pimcore_integration_context_concurrent_consume_has_one_winner(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    now = datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)
    context_id = store.create_pimcore_integration_context(
        username="alice",
        mode="edit",
        object_id=91,
        results={"sql_profiles": [{"profile_id": "stock", "status": "success"}]},
        now=now,
    )

    def consume() -> object:
        return store.consume_pimcore_integration_context(
            context_id, username="alice", mode="edit", object_id=91, now=now
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _item: consume(), range(2)))

    assert sum(result is not None for result in results) == 1


def test_pimcore_submissions_roundtrip_and_filter(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()

    store.append_pimcore_submission(
        {
            "operation_id": "op-1",
            "operation_type": "manual_create",
            "username": "operator",
            "ean": "5901234567890",
            "object_id": "91",
            "object_path": "/Produkty/91",
            "status": "completed",
            "values": {"EAN": "5901234567890", "STOCK": "12"},
            "payload": {"className": "Product"},
            "result": {"object_id": 91},
            "warnings": [],
        }
    )

    rows = store.query_pimcore_submissions(user="operator", query="590123", limit=20)

    assert len(rows) == 1
    assert rows[0]["operation_id"] == "op-1"
    assert rows[0]["values"]["STOCK"] == "12"
    assert rows[0]["payload"]["className"] == "Product"
    assert rows[0]["created_at"].endswith("Z")


def test_config_roundtrip_preserves_payload(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()

    store.save_config({"db_type": "mysql", "enable_sql_update": True})

    assert store.load_config()["db_type"] == "mysql"
    assert store.load_config()["enable_sql_update"] is True


def test_config_is_stored_as_readable_path_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "data.sqlite"
    store = SqliteStore(str(db_path))
    store.initialize()

    store.save_config(
        {
            "db_type": "mysql",
            "enable_sql_update": True,
            "ftp": {"host": "ftp.example.com", "port": 21},
            "processing": {"formats": ["jpg", "png"]},
        }
    )

    with sqlite3.connect(db_path) as conn:
        rows = {
            row[0]: (row[1], row[2])
            for row in conn.execute(
                """
                SELECT path, value_json, updated_at
                FROM app_config_values
                ORDER BY path
                """
            )
        }
        legacy_config = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'app_settings'"
        ).fetchone()

    assert legacy_config is None
    assert rows["db_type"][0] == '"mysql"'
    assert rows["enable_sql_update"][0] == "true"
    assert rows["ftp.host"][0] == '"ftp.example.com"'
    assert rows["ftp.port"][0] == "21"
    assert rows["processing.formats"][0] == '["jpg", "png"]'
    assert rows["db_type"][1].endswith("Z")
    assert "T" in rows["db_type"][1]


def test_load_config_falls_back_to_legacy_json_blob(tmp_path: Path) -> None:
    db_path = tmp_path / "data.sqlite"
    store = SqliteStore(str(db_path))
    store.initialize()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES ('config', ?, ?)
            """,
            ('{"db_type": "mssql", "ftp": {"host": "legacy.example.com"}}', "2026-06-25T12:00:00.000Z"),
        )

    assert store.load_config() == {
        "db_type": "mssql",
        "ftp": {"host": "legacy.example.com"},
    }


def test_save_config_drops_legacy_app_settings_when_it_becomes_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "data.sqlite"
    store = SqliteStore(str(db_path))
    store.initialize()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES ('config', ?, ?)
            """,
            ('{"db_type": "mssql"}', "2026-06-25T12:00:00.000Z"),
        )

    store.save_config({"db_type": "mysql"})

    with sqlite3.connect(db_path) as conn:
        app_settings_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'app_settings'"
        ).fetchone()

    assert app_settings_exists is None


def test_sqlite_timestamps_are_iso_8601_text(tmp_path: Path) -> None:
    db_path = tmp_path / "data.sqlite"
    store = SqliteStore(str(db_path))
    store.initialize()

    store.save_sql_columns(["img_01"], table_name="object_query_1")
    store.save_product_entry(
        {
            "EAN": "5901234567890",
            "NAZWA": "MAGGIORE",
            "TYP": "KOMODA",
            "MODEL": "MA03",
            "KOLOR1": "BIALY",
            "KOLOR2": "",
            "KOLOR3": "",
            "DODATKI": "NO-LED",
            "PRODUCT_ID": "PRD-1",
        }
    )
    store.save_users([{"username": "operator", "role": "user"}])
    store.save_file_index_cache({"version": 1, "names": ["MAGGIORE"]})

    with sqlite3.connect(db_path) as conn:
        values = [
            conn.execute("SELECT applied_at FROM schema_version").fetchone()[0],
            conn.execute("SELECT detected_at FROM sql_available_columns").fetchone()[0],
            conn.execute("SELECT updated_at FROM product_entries").fetchone()[0],
            conn.execute("SELECT updated_at FROM web_users").fetchone()[0],
            conn.execute("SELECT updated_at FROM file_index_cache").fetchone()[0],
        ]

    for value in values:
        assert isinstance(value, str)
        assert value.endswith("Z")
        assert "T" in value


def test_web_history_schema_uses_iso_created_at(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()
    store.save_history(
        [
            {
                "id": "hist-1",
                "ts": 1782392554.3,
                "time": "2026-06-25 13:02:34",
                "user": "admin",
                "ean": "5901234567890",
            }
        ]
    )

    with sqlite3.connect(tmp_path / "data.sqlite") as conn:
        columns = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(web_history)")}
        row = conn.execute("SELECT created_at, payload_json FROM web_history WHERE id = 'hist-1'").fetchone()

    assert columns["created_at"].upper() == "TEXT"
    assert isinstance(row[0], str)
    assert row[0].endswith("Z")
    assert "T" in row[0]
    payload = json.loads(row[1])
    assert payload["created_at"] == row[0]


def test_migration_converts_legacy_web_history_ts_real(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_version (version INTEGER NOT NULL, applied_at TEXT NOT NULL);
            INSERT INTO schema_version VALUES (2, '2026-06-25T12:00:00.000Z');
            CREATE TABLE web_history (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, ts REAL NOT NULL);
            INSERT INTO web_history VALUES (
                'hist-1',
                '{"id":"hist-1","ts":1782392554.3,"user":"admin","ean":"5901234567890"}',
                1782392554.3
            );
            """
        )

    store = SqliteStore(str(db_path))
    store.initialize()

    with sqlite3.connect(db_path) as conn:
        columns = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(web_history)")}
        row = conn.execute("SELECT created_at, payload_json FROM web_history WHERE id = 'hist-1'").fetchone()

    assert "created_at" in columns
    assert row[0].endswith("Z")
    payload = json.loads(row[1])
    assert payload["created_at"] == row[0]
    assert isinstance(payload["ts"], str)
    assert payload["ts"].endswith("Z")


def test_file_index_segments_are_saved_by_name_prefix(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()
    snapshot = {
        "version": 1,
        "root": "C:/photos",
        "generated_at": "2026-06-25T13:02:34.300Z",
        "names": ["LUNA", "MAGGIORE"],
        "types": {"LUNA": ["SZAFKA"], "MAGGIORE": ["KOMODA"]},
        "models": {},
        "colors": {},
        "extras": {},
        "files": {},
    }

    store.save_file_index_cache(snapshot)

    with sqlite3.connect(tmp_path / "data.sqlite") as conn:
        rows = conn.execute(
            """
            SELECT segment_key, section, lookup_key, payload_json
            FROM file_index_segments
            ORDER BY segment_key, section, lookup_key
            """
        ).fetchall()

    assert ("L", "names", "LUNA", '"LUNA"') in rows
    assert ("M", "names", "MAGGIORE", '"MAGGIORE"') in rows


def test_slots_and_sql_columns_roundtrip(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()

    store.save_slots(
        [{"prefix": "01", "label": "MAIN", "filename_label": "MAIN_pic"}],
        {"01": "img_01"},
    )
    store.save_sql_columns(["img_01", "img_02"], table_name="object_query_1")

    slots, sql_map = store.load_slots()
    assert slots == [{"prefix": "01", "label": "MAIN", "filename_label": "MAIN_pic"}]
    assert sql_map == {"01": "img_01"}
    assert store.load_sql_columns() == ["img_01", "img_02"]


def test_lists_roundtrip_uses_excel_payload_shape(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()

    store.save_lists(
        {
            "NAZWY": ["MAGGIORE"],
            "TYPY": ["KOMODA"],
            "MODELE": ["MA03"],
            "KOLORY": ["BIALY"],
            "DODATKI": ["NO-LED"],
            ENTRY_RECORDS_KEY: [
                {
                    "EAN": "5901234567890",
                    "NAZWA": "MAGGIORE",
                    "TYP": "KOMODA",
                    "MODEL": "MA03",
                    "KOLOR1": "BIALY",
                    "KOLOR2": "",
                    "KOLOR3": "",
                    "DODATKI": "NO-LED",
                    "PRODUCT_ID": "PRD-1",
                }
            ],
        }
    )

    payload = store.load_lists()
    assert payload["NAZWY"] == ["MAGGIORE"]
    assert payload["TYPY"] == ["KOMODA"]
    assert payload[ENTRY_RECORDS_KEY][0]["PRODUCT_ID"] == "PRD-1"


def test_add_and_remove_list_value(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()

    assert store.add_list_value("NAZWY", "maggiore") is True
    assert store.add_list_value("NAZWY", "MAGGIORE") is False
    assert store.load_lists()["NAZWY"] == ["MAGGIORE"]

    store.remove_list_value("NAZWY", "maggiore")

    assert store.load_lists()["NAZWY"] == []


def test_save_product_entry_updates_by_product_id(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()

    first = store.save_product_entry(
        {
            "EAN": "5901234567890",
            "NAZWA": "MAGGIORE",
            "TYP": "KOMODA",
            "MODEL": "MA03",
            "KOLOR1": "BIALY",
            "KOLOR2": "",
            "KOLOR3": "",
            "DODATKI": "NO-LED",
            "PRODUCT_ID": "PRD-1",
        }
    )
    second = store.save_product_entry(
        {
            "EAN": "5901234567890",
            "NAZWA": "MAGGIORE",
            "TYP": "KOMODA",
            "MODEL": "MA04",
            "KOLOR1": "BIALY",
            "KOLOR2": "",
            "KOLOR3": "",
            "DODATKI": "NO-LED",
            "PRODUCT_ID": "PRD-1",
        }
    )

    records = store.load_lists()[ENTRY_RECORDS_KEY]
    assert first["updated"] is False
    assert second["updated"] is True
    assert len(records) == 1
    assert records[0]["MODEL"] == "MA04"
