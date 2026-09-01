"""Tests for selecting one explicit pre-rebrand SQLite source."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from picsyncra.offline_legacy_sqlite_migrator import (
    OfflineMigrationError,
    resolve_offline_migration_paths,
)
from picsyncra.sqlite_store import SqliteStore


def _create_sqlite_database(path: Path) -> Path:
    SqliteStore(str(path)).initialize()
    return path


def test_resolve_paths_uses_only_database_referenced_by_local_settings(
    tmp_path: Path,
) -> None:
    """A stale sibling database must not replace the configured source."""

    app_root = tmp_path / "application"
    source_root = tmp_path / "current-legacy"
    stale_root = tmp_path / "stale-legacy"
    app_root.mkdir()
    source_root.mkdir()
    stale_root.mkdir()
    source = _create_sqlite_database(source_root / "picorgftp_sql.sqlite")
    _create_sqlite_database(stale_root / "picorgftp_sql.sqlite")
    (app_root / "local_settings.json").write_text(
        json.dumps(
            {
                "database_location_mode": "custom",
                "database_path": str(source),
            }
        ),
        encoding="utf-8",
    )

    paths = resolve_offline_migration_paths(app_root)

    assert paths.app_root == app_root.resolve()
    assert paths.settings_path == (app_root / "local_settings.json").resolve()
    assert paths.source == source.resolve()
    assert paths.target == source_root / "picsyncra.sqlite"


def test_resolve_paths_honours_explicit_legacy_path_from_old_exe_dir_settings(
    tmp_path: Path,
) -> None:
    """Old exe_dir profiles retain their explicit picorgftp SQLite selection."""

    app_root = tmp_path / "application"
    source_root = tmp_path / "server-copy"
    app_root.mkdir()
    source_root.mkdir()
    source = _create_sqlite_database(source_root / "picorgftp_sql.sqlite")
    (app_root / "local_settings.json").write_text(
        json.dumps(
            {
                "database_location_mode": "exe_dir",
                "database_path": str(source),
            }
        ),
        encoding="utf-8",
    )

    paths = resolve_offline_migration_paths(app_root)

    assert paths.source == source.resolve()


@pytest.mark.parametrize(
    ("settings_payload", "expected_code"),
    [
        (None, "settings_missing"),
        ({"database_location_mode": "custom", "database_path": "other.sqlite"}, "source_name"),
        (
            {
                "database_location_mode": "custom",
                "database_path": "missing/picorgftp_sql.sqlite",
            },
            "source_missing",
        ),
    ],
)
def test_resolve_paths_rejects_invalid_configured_source_without_scanning(
    tmp_path: Path,
    settings_payload: dict[str, str] | None,
    expected_code: str,
) -> None:
    """A bad configuration fails even when another legacy-named DB exists nearby."""

    app_root = tmp_path / "application"
    app_root.mkdir()
    _create_sqlite_database(app_root / "picorgftp_sql.sqlite")
    if settings_payload is not None:
        (app_root / "local_settings.json").write_text(
            json.dumps(settings_payload), encoding="utf-8"
        )

    with pytest.raises(OfflineMigrationError) as error:
        resolve_offline_migration_paths(app_root)

    assert error.value.code == expected_code


def test_resolve_paths_refuses_to_replace_an_existing_target(tmp_path: Path) -> None:
    """Preflight must stop before migration when picsyncra.sqlite already exists."""

    app_root = tmp_path / "application"
    source_root = tmp_path / "legacy"
    app_root.mkdir()
    source_root.mkdir()
    source = _create_sqlite_database(source_root / "picorgftp_sql.sqlite")
    _create_sqlite_database(source_root / "picsyncra.sqlite")
    (app_root / "local_settings.json").write_text(
        json.dumps(
            {
                "database_location_mode": "custom",
                "database_path": str(source),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(OfflineMigrationError) as error:
        resolve_offline_migration_paths(app_root)

    assert error.value.code == "target_exists"
