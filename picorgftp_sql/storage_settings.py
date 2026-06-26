"""Bootstrap storage mode and SQLite database location helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from . import common, settings

DATA_MODE_KEY = "data_mode"
DATA_MODE_LEGACY = "legacy"
DATA_MODE_SQLITE = "sqlite"

DATABASE_LOCATION_MODE_KEY = "database_location_mode"
DATABASE_LOCATION_IMAGE_DIR = "image_dir"
DATABASE_LOCATION_CUSTOM = "custom"
DATABASE_LOCATION_EXE_DIR = "exe_dir"
DATABASE_PATH_KEY = "database_path"
DEFAULT_SQLITE_FILENAME = "picorgftp_sql.sqlite"
BACKUP_SETTINGS_KEY = "sqlite_backup"
BACKUP_DEFAULTS = {
    "enabled": False,
    "slots": [],
    "days": [],
    "hours": [],
    "max_copies": 10,
    "last_run_slots": [],
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
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
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
    return {
        "enabled": bool(payload.get("enabled", False)),
        "slots": slots,
        "days": days,
        "hours": sorted(hours),
        "max_copies": max_copies,
        "last_run_slots": [
            str(item) for item in payload.get("last_run_slots", []) if str(item).strip()
        ],
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
