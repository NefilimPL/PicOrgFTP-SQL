"""SQLite maintenance and repair workflow helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .sqlite_backup import create_backup
from .sqlite_store import SCHEMA_VERSION, SqliteStore


def integrity_check(database_path: str) -> str:
    with sqlite3.connect(database_path) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0] if row else "")


def current_schema_version(database_path: str) -> int:
    try:
        with sqlite3.connect(database_path) as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_version"
            ).fetchone()
        return int(row[0] or 0) if row else 0
    except sqlite3.Error:
        return 0


def rebuild_file_index_segments(store: SqliteStore) -> int:
    snapshot = store.load_file_index_cache()
    if not snapshot:
        return 0
    return store.save_file_index_segments(snapshot)


def repair_sqlite_database(database_path: str, backup_dir: str) -> dict[str, Any]:
    db_path = Path(database_path)
    if not db_path.exists():
        raise FileNotFoundError(str(db_path))
    backup = create_backup(str(db_path), backup_dir, reason="pre-repair")
    check = integrity_check(str(db_path))
    before_version = current_schema_version(str(db_path))
    if check.lower() != "ok":
        return {
            "ok": False,
            "backup": backup,
            "integrity_check": check,
            "schema_version": before_version,
            "warnings": ["integrity_check_failed"],
        }
    store = SqliteStore(str(db_path))
    store.initialize()
    segments = rebuild_file_index_segments(store)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("ANALYZE")
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("VACUUM")
    return {
        "ok": True,
        "backup": backup,
        "integrity_check": "ok",
        "schema_version": current_schema_version(str(db_path)),
        "previous_schema_version": before_version,
        "target_schema_version": SCHEMA_VERSION,
        "segments_rebuilt": segments,
        "warnings": [],
    }
