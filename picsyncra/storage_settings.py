"""Bootstrap storage mode and SQLite database location helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from . import common, settings
from .brand import SQLITE_FILENAME

DATA_MODE_KEY = "data_mode"
DATA_MODE_LEGACY = "legacy"
DATA_MODE_SQLITE = "sqlite"

DATABASE_LOCATION_MODE_KEY = "database_location_mode"
DATABASE_LOCATION_IMAGE_DIR = "image_dir"
DATABASE_LOCATION_CUSTOM = "custom"
DATABASE_LOCATION_EXE_DIR = "exe_dir"
DATABASE_PATH_KEY = "database_path"
DEFAULT_SQLITE_FILENAME = SQLITE_FILENAME
BACKUP_SETTINGS_KEY = "sqlite_backup"
BACKUP_DEFAULTS = {
    "enabled": False,
    "slots": [],
    "days": [],
    "hours": [],
    "max_copies": 10,
    "last_run_slots": [],
    "archive_dirs": [],
}
BACKUP_WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def _text(value: object) -> str:
    return str(value or "").strip()


def normalize_data_mode(value: object) -> str:
    """Return a supported data mode."""

    text = _text(value).lower()
    if text == DATA_MODE_SQLITE:
        return DATA_MODE_SQLITE
    return DATA_MODE_LEGACY


def normalize_database_location_mode(value: object) -> str:
    """Return a supported SQLite location mode."""

    text = _text(value).lower()
    if text in {
        DATABASE_LOCATION_IMAGE_DIR,
        DATABASE_LOCATION_CUSTOM,
        DATABASE_LOCATION_EXE_DIR,
    }:
        return text
    return DATABASE_LOCATION_IMAGE_DIR


def _settings_path() -> Path:
    return Path(settings.BASE_DIR_SETTINGS_PATH)


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    """Replace ``path`` atomically while retaining the exact supplied bytes."""

    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".picsyncra-settings-",
        suffix=".json.tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            try:
                os.unlink(temporary_path)
            except OSError:
                pass


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Publish bootstrap settings without exposing a partial JSON document."""

    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".picsyncra-settings-",
        suffix=".json.tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=4, ensure_ascii=False)
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            try:
                os.unlink(temporary_path)
            except OSError:
                pass


def capture_bootstrap_settings() -> bytes | None:
    """Capture the precise settings file before an activation transaction."""

    path = _settings_path()
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def restore_bootstrap_settings(snapshot: bytes | None) -> None:
    """Restore a bootstrap snapshot after an activation transaction fails."""

    path = _settings_path()
    if snapshot is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_bytes_atomic(path, snapshot)
    from .data_store import reset_active_store_cache

    reset_active_store_cache()


def load_bootstrap_settings() -> dict[str, Any]:
    """Load startup-only settings from ``local_settings.json``."""

    data: dict[str, Any] = dict(common.BASE_DIR_SETTINGS_TEMPLATE)
    path = _settings_path()
    try:
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
    except (OSError, ValueError, TypeError):
        pass
    data[DATA_MODE_KEY] = normalize_data_mode(data.get(DATA_MODE_KEY))
    data[DATABASE_LOCATION_MODE_KEY] = normalize_database_location_mode(
        data.get(DATABASE_LOCATION_MODE_KEY)
    )
    data.setdefault(DATABASE_PATH_KEY, "")
    return data


def save_bootstrap_settings(updates: dict[str, object]) -> dict[str, Any]:
    """Persist startup-only settings while keeping existing unknown keys."""

    data = load_bootstrap_settings()
    if isinstance(updates, dict):
        data.update(updates)
    data[DATA_MODE_KEY] = normalize_data_mode(data.get(DATA_MODE_KEY))
    data[DATABASE_LOCATION_MODE_KEY] = normalize_database_location_mode(
        data.get(DATABASE_LOCATION_MODE_KEY)
    )
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(path, data)
    from .data_store import reset_active_store_cache

    reset_active_store_cache()
    return data


def _normalize_backup_settings(raw: object) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    days = []
    for day in payload.get("days", []):
        text = str(day).lower()
        if text in BACKUP_WEEKDAYS:
            days.append(text)
    hours = set()
    for hour in payload.get("hours", []):
        try:
            hours.add(max(0, min(23, int(hour))))
        except (TypeError, ValueError):
            continue
    slots = []
    seen_slots = set()
    for slot in payload.get("slots", []):
        parts = str(slot or "").lower().split(":", 1)
        if len(parts) != 2 or parts[0] not in BACKUP_WEEKDAYS:
            continue
        try:
            hour = max(0, min(23, int(parts[1])))
        except (TypeError, ValueError):
            continue
        normalized = f"{parts[0]}:{hour}"
        if normalized not in seen_slots:
            slots.append(normalized)
            seen_slots.add(normalized)
    if not slots and days and hours:
        for day in days:
            for hour in sorted(hours):
                slots.append(f"{day}:{hour}")
    if slots:
        days = []
        hours = set()
        for slot in slots:
            day, hour_text = slot.split(":", 1)
            if day not in days:
                days.append(day)
            hours.add(int(hour_text))
    try:
        max_copies = max(1, min(999, int(payload.get("max_copies", 10))))
    except (TypeError, ValueError):
        max_copies = 10
    archive_dirs = []
    seen_archive_dirs = set()
    raw_archive_dirs = payload.get("archive_dirs", [])
    if not isinstance(raw_archive_dirs, (list, tuple, set)):
        raw_archive_dirs = []
    for raw_dir in raw_archive_dirs:
        resolved = _resolve_path(raw_dir)
        if not resolved:
            continue
        key = os.path.normcase(resolved)
        if key in seen_archive_dirs:
            continue
        archive_dirs.append(resolved)
        seen_archive_dirs.add(key)
    return {
        "enabled": bool(payload.get("enabled", False)),
        "slots": slots,
        "days": days,
        "hours": sorted(hours),
        "max_copies": max_copies,
        "last_run_slots": [
            str(item) for item in payload.get("last_run_slots", []) if str(item).strip()
        ],
        "archive_dirs": archive_dirs,
    }


def load_backup_settings() -> dict[str, Any]:
    data = load_bootstrap_settings()
    return _normalize_backup_settings(data.get(BACKUP_SETTINGS_KEY, BACKUP_DEFAULTS))


def save_backup_settings(updates: dict[str, object]) -> dict[str, Any]:
    settings_payload = _normalize_backup_settings(updates)
    save_bootstrap_settings({BACKUP_SETTINGS_KEY: settings_payload})
    return settings_payload


def resolve_backup_dir() -> str:
    return str(_settings_path().resolve().parent / "BACKUP")


def resolve_backup_dirs() -> list[str]:
    """Return the primary and explicitly registered backup archive roots."""

    roots = [str(Path(resolve_backup_dir()).resolve())]
    seen = {os.path.normcase(roots[0])}
    for archive_dir in load_backup_settings().get("archive_dirs", []):
        resolved = str(Path(str(archive_dir)).resolve())
        key = os.path.normcase(resolved)
        if key not in seen:
            roots.append(resolved)
            seen.add(key)
    return roots


def _resolve_path(value: object) -> str:
    raw = _text(value).strip("\"'")
    if not raw:
        return ""
    expanded = os.path.expandvars(os.path.expanduser(raw))
    return str(Path(expanded).resolve())


def resolve_sqlite_path(payload: dict[str, object] | None = None) -> str:
    """Return the active SQLite database path for ``payload`` or settings."""

    data = payload if isinstance(payload, dict) else load_bootstrap_settings()
    mode = normalize_database_location_mode(data.get(DATABASE_LOCATION_MODE_KEY))
    if mode == DATABASE_LOCATION_CUSTOM:
        return _resolve_path(data.get(DATABASE_PATH_KEY))
    if mode == DATABASE_LOCATION_EXE_DIR:
        return str(_settings_path().resolve().parent / DEFAULT_SQLITE_FILENAME)
    return str(Path(settings.AC).resolve() / DEFAULT_SQLITE_FILENAME)


def storage_summary() -> dict[str, Any]:
    """Return a web/desktop friendly summary of active storage bootstrap state."""

    data = load_bootstrap_settings()
    return {
        "data_mode": normalize_data_mode(data.get(DATA_MODE_KEY)),
        "image_dir": settings.AC,
        "database_location_mode": normalize_database_location_mode(
            data.get(DATABASE_LOCATION_MODE_KEY)
        ),
        "database_path": resolve_sqlite_path(data),
    }
