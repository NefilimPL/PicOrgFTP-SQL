"""SQLite backup, history, and retention helpers."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _utc_datetime(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def now_iso(now: datetime | None = None) -> str:
    return _utc_datetime(now).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _backup_name(now: datetime, reason: str) -> str:
    safe_reason = (
        "".join(
            ch
            for ch in str(reason or "manual").lower()
            if ch.isalnum() or ch in {"-", "_"}
        )
        or "manual"
    )
    return (
        f"picorgftp_sql-{_utc_datetime(now).strftime('%Y%m%d-%H%M%S')}-"
        f"{safe_reason}.sqlite"
    )


def _schema_version(path: str) -> int:
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_version"
            ).fetchone()
        return int(row[0] or 0) if row else 0
    except Exception:
        return 0


def _integrity_check(path: str) -> str:
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0] if row else "")
    except Exception as exc:
        return str(exc)


def create_backup(
    source_path: str,
    backup_dir: str,
    *,
    reason: str = "manual",
    now: datetime | None = None,
) -> dict[str, Any]:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(str(source))
    timestamp = _utc_datetime(now)
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / _backup_name(timestamp, reason)
    method = "sqlite_backup"
    try:
        with sqlite3.connect(str(source)) as src, sqlite3.connect(str(target)) as dst:
            src.backup(dst)
    except sqlite3.Error:
        method = "raw_copy"
        target.write_bytes(source.read_bytes())
    metadata = {
        "source_path": str(source),
        "backup_path": str(target),
        "created_at": now_iso(timestamp),
        "reason": reason,
        "size_bytes": target.stat().st_size,
        "schema_version": _schema_version(str(target)),
        "integrity_check": _integrity_check(str(target)),
        "method": method,
    }
    target.with_suffix(".json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {"ok": True, **metadata}


def list_backups(backup_dir: str) -> list[dict[str, Any]]:
    items = []
    for db_path in Path(backup_dir).glob("*.sqlite"):
        meta_path = db_path.with_suffix(".json")
        metadata: dict[str, Any] = {}
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                metadata = {}
        metadata.setdefault("backup_path", str(db_path))
        metadata.setdefault("created_at", "")
        metadata.setdefault("reason", "")
        metadata.setdefault("size_bytes", db_path.stat().st_size)
        items.append(metadata)
    return sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def enforce_retention(backup_dir: str, max_copies: int) -> dict[str, Any]:
    keep = max(1, int(max_copies or 1))
    candidates = [
        item
        for item in list_backups(backup_dir)
        if item.get("reason") in {"manual", "scheduled"}
    ]
    remove = candidates[keep:]
    removed = 0
    for item in remove:
        db_path = Path(str(item["backup_path"]))
        for path in (db_path, db_path.with_suffix(".json")):
            try:
                path.unlink()
                if path.suffix == ".sqlite":
                    removed += 1
            except FileNotFoundError:
                pass
    return {"removed": removed}


def schedule_slot(now: datetime) -> str:
    return _utc_datetime(now).strftime("%Y-%m-%dT%H")


def due_schedule_slots(
    settings_payload: dict[str, Any],
    now: datetime | None = None,
) -> list[str]:
    value = _utc_datetime(now)
    if not settings_payload.get("enabled"):
        return []
    day = WEEKDAY_KEYS[value.weekday()]
    hour = value.hour
    if day not in set(settings_payload.get("days") or []):
        return []
    try:
        hours = {int(item) for item in settings_payload.get("hours") or []}
    except (TypeError, ValueError):
        hours = set()
    if hour not in hours:
        return []
    slot = schedule_slot(value)
    if slot in set(settings_payload.get("last_run_slots") or []):
        return []
    return [slot]


def mark_schedule_slots_run(
    settings_payload: dict[str, Any],
    slots: list[str],
) -> dict[str, Any]:
    updated = dict(settings_payload or {})
    existing = [str(item) for item in updated.get("last_run_slots", [])]
    merged = existing + [slot for slot in slots if slot not in existing]
    updated["last_run_slots"] = merged[-500:]
    return updated
