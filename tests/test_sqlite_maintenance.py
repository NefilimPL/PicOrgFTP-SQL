from __future__ import annotations

import sqlite3
from pathlib import Path

from picorgftp_sql.sqlite_maintenance import repair_sqlite_database
from picorgftp_sql.sqlite_store import SqliteStore


def test_repair_creates_backup_and_migrates_legacy_history(tmp_path: Path) -> None:
    db_path = tmp_path / "data.sqlite"
    backup_dir = tmp_path / "BACKUP"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_version (version INTEGER NOT NULL, applied_at TEXT NOT NULL);
            INSERT INTO schema_version VALUES (2, '2026-06-25T12:00:00.000Z');
            CREATE TABLE web_history (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, ts REAL NOT NULL);
            INSERT INTO web_history VALUES ('hist-1', '{"id":"hist-1","ts":1782392554.3,"user":"admin"}', 1782392554.3);
            """
        )

    result = repair_sqlite_database(str(db_path), str(backup_dir))

    assert result["ok"] is True
    assert Path(result["backup"]["backup_path"]).exists()
    assert result["integrity_check"] == "ok"
    assert result["schema_version"] >= 3
    payload = SqliteStore(str(db_path)).load_history()[0]
    assert payload["created_at"].endswith("Z")


def test_repair_preserves_config_and_user_data(tmp_path: Path) -> None:
    db_path = tmp_path / "data.sqlite"
    store = SqliteStore(str(db_path))
    store.initialize()
    store.save_config({"sql_query": "UPDATE product SET img = {filename}", "db_type": "mysql"})
    store.save_users([{"username": "admin", "password_hash": "hash", "role": "admin"}])

    result = repair_sqlite_database(str(db_path), str(tmp_path / "BACKUP"))

    repaired = SqliteStore(str(db_path))
    assert result["ok"] is True
    assert repaired.load_config()["sql_query"] == "UPDATE product SET img = {filename}"
    assert repaired.load_users()[0]["username"] == "admin"
