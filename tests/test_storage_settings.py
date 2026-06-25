"""Tests for bootstrap storage mode and SQLite location settings."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from picorgftp_sql import storage_settings


def test_sqlite_path_in_image_dir(tmp_path: Path) -> None:
    image_dir = tmp_path / "photos"
    image_dir.mkdir()

    with patch.object(storage_settings.settings, "AC", str(image_dir)):
        resolved = storage_settings.resolve_sqlite_path(
            {"database_location_mode": "image_dir"}
        )

    assert resolved == str(image_dir / "picorgftp_sql.sqlite")


def test_sqlite_path_in_custom_location(tmp_path: Path) -> None:
    target = tmp_path / "custom" / "data.sqlite"

    resolved = storage_settings.resolve_sqlite_path(
        {"database_location_mode": "custom", "database_path": str(target)}
    )

    assert resolved == str(target.resolve())


def test_sqlite_path_in_exe_dir(tmp_path: Path) -> None:
    settings_file = tmp_path / "local_settings.json"

    with patch.object(
        storage_settings.settings, "BASE_DIR_SETTINGS_PATH", str(settings_file)
    ):
        resolved = storage_settings.resolve_sqlite_path(
            {"database_location_mode": "exe_dir"}
        )

    assert resolved == str(tmp_path / "picorgftp_sql.sqlite")


def test_load_bootstrap_settings_defaults_to_legacy(tmp_path: Path) -> None:
    settings_file = tmp_path / "local_settings.json"

    with patch.object(
        storage_settings.settings, "BASE_DIR_SETTINGS_PATH", str(settings_file)
    ):
        payload = storage_settings.load_bootstrap_settings()

    assert payload["data_mode"] == "legacy"
    assert payload["database_location_mode"] == "image_dir"


def test_save_bootstrap_settings_merges_existing_values(tmp_path: Path) -> None:
    settings_file = tmp_path / "local_settings.json"
    settings_file.write_text(
        json.dumps({"language": "pl", "base_dir_override": "C:/Photos"}),
        encoding="utf-8",
    )

    with patch.object(
        storage_settings.settings, "BASE_DIR_SETTINGS_PATH", str(settings_file)
    ):
        payload = storage_settings.save_bootstrap_settings(
            {"data_mode": "sqlite", "database_location_mode": "exe_dir"}
        )

    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    assert payload["language"] == "pl"
    assert saved["base_dir_override"] == "C:/Photos"
    assert saved["data_mode"] == "sqlite"
    assert saved["database_location_mode"] == "exe_dir"
