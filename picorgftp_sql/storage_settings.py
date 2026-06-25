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
