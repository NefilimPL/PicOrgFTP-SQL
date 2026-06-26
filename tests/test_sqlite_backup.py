from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from picorgftp_sql import sqlite_backup, storage_settings


def _create_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL, applied_at TEXT NOT NULL)")
        conn.execute("INSERT INTO schema_version VALUES (3, '2026-06-25T13:02:34.300Z')")
        conn.execute("CREATE TABLE app_config_values (path TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL)")
        conn.execute("INSERT INTO app_config_values VALUES ('database.query', '\"secret query\"', '2026-06-25T13:02:34.300Z')")


def test_backup_creates_sqlite_copy_and_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "data.sqlite"
    backup_dir = tmp_path / "BACKUP"
    _create_db(db_path)

    result = sqlite_backup.create_backup(
        str(db_path),
        str(backup_dir),
        reason="manual",
        now=datetime(2026, 6, 25, 13, 2, 34, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    backup_path = Path(result["backup_path"])
    meta_path = backup_path.with_suffix(".json")
    assert backup_path.exists()
    assert meta_path.exists()
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    assert metadata["reason"] == "manual"
    assert metadata["schema_version"] == 3


def test_backup_retention_keeps_newest_manual_and_scheduled(tmp_path: Path) -> None:
    backup_dir = tmp_path / "BACKUP"
    backup_dir.mkdir()
    for index in range(4):
        db = backup_dir / f"picorgftp_sql-20260625-130{index}00-manual.sqlite"
        db.write_text("x", encoding="utf-8")
        db.with_suffix(".json").write_text(
            json.dumps(
                {
                    "created_at": f"2026-06-25T13:0{index}:00.000Z",
                    "reason": "manual",
                }
            ),
            encoding="utf-8",
        )

    removed = sqlite_backup.enforce_retention(str(backup_dir), max_copies=2)

    assert removed["removed"] == 2
    remaining = sorted(path.name for path in backup_dir.glob("*.sqlite"))
    assert remaining == [
        "picorgftp_sql-20260625-130200-manual.sqlite",
        "picorgftp_sql-20260625-130300-manual.sqlite",
    ]


def test_backup_settings_roundtrip(tmp_path: Path) -> None:
    settings_path = tmp_path / "local_settings.json"
    with patch.object(storage_settings.settings, "BASE_DIR_SETTINGS_PATH", str(settings_path)):
        saved = storage_settings.save_backup_settings(
            {"enabled": True, "days": ["mon"], "hours": [8, 13], "max_copies": 4}
        )
        loaded = storage_settings.load_backup_settings()

    assert saved["enabled"] is True
    assert loaded["days"] == ["mon"]
    assert loaded["hours"] == [8, 13]
    assert loaded["max_copies"] == 4


def test_due_schedule_slots_respects_day_hour_and_last_run() -> None:
    now = datetime(2026, 6, 22, 8, 15, tzinfo=timezone.utc)  # Monday
    settings_payload = {
        "enabled": True,
        "days": ["mon", "tue"],
        "hours": [8, 13],
        "max_copies": 5,
        "last_run_slots": [],
    }

    due = sqlite_backup.due_schedule_slots(settings_payload, now)

    assert due == ["2026-06-22T08"]

    settings_payload["last_run_slots"] = ["2026-06-22T08"]
    assert sqlite_backup.due_schedule_slots(settings_payload, now) == []


def test_mark_schedule_slots_run_keeps_recent_slots() -> None:
    updated = sqlite_backup.mark_schedule_slots_run(
        {"last_run_slots": ["2026-06-21T08"]},
        ["2026-06-22T08"],
    )

    assert updated["last_run_slots"] == ["2026-06-21T08", "2026-06-22T08"]


def test_restore_backup_creates_pre_restore_backup_and_replaces_database(tmp_path: Path) -> None:
    active = tmp_path / "active.sqlite"
    backup = tmp_path / "BACKUP" / "picorgftp_sql-20260625-130234-manual.sqlite"
    backup.parent.mkdir()
    _create_db(active)
    _create_db(backup)
    with sqlite3.connect(backup) as conn:
        conn.execute("UPDATE app_config_values SET value_json = '\"restored\"' WHERE path = 'database.query'")

    result = sqlite_backup.restore_backup(str(active), str(backup), str(backup.parent))

    assert result["ok"] is True
    assert Path(result["pre_restore_backup"]["backup_path"]).exists()
    with sqlite3.connect(active) as conn:
        value = conn.execute("SELECT value_json FROM app_config_values WHERE path = 'database.query'").fetchone()[0]
    assert value == '"restored"'


def test_diff_databases_masks_secret_values(tmp_path: Path) -> None:
    left = tmp_path / "left.sqlite"
    right = tmp_path / "right.sqlite"
    _create_db(left)
    _create_db(right)
    with sqlite3.connect(right) as conn:
        conn.execute("INSERT INTO app_config_values VALUES ('ftp.password', '\"secret\"', '2026-06-25T13:02:34.300Z')")

    diff = sqlite_backup.diff_databases(str(left), str(right))

    assert diff["tables"]["app_config_values"]["added"] >= 1
    assert "secret" not in json.dumps(diff)
    assert "ftp.password" in json.dumps(diff)
    assert "present" in json.dumps(diff)
