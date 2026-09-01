"""Tests for selecting one explicit pre-rebrand SQLite source."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from picsyncra.offline_legacy_sqlite_migrator import (
    OfflineMigrationError,
    build_validated_legacy_sqlite_copy,
    resolve_offline_migration_paths,
    run_offline_legacy_migration,
)
from picsyncra.excel_utils import ENTRY_RECORDS_KEY
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


def _configured_legacy_paths(tmp_path: Path, *, products: int, users: int):
    app_root = tmp_path / "application"
    source_root = tmp_path / "legacy"
    app_root.mkdir()
    source_root.mkdir()
    source = source_root / "picorgftp_sql.sqlite"
    store = SqliteStore(str(source))
    store.save_lists(
        {
            ENTRY_RECORDS_KEY: [
                {
                    "PRODUCT_ID": f"P-{index}",
                    "EAN": f"5901234567{index:03d}",
                    "NAZWA": f"LEGACY PRODUCT {index}",
                }
                for index in range(products)
            ]
        }
    )
    store.save_users(
        [
            {
                "username": f"user{index}",
                "role": "admin" if index == 0 else "user",
                "enabled": index % 2 == 0,
                "password_hash": f"legacy-hash-{index}",
            }
            for index in range(users)
        ]
    )
    (app_root / "local_settings.json").write_text(
        json.dumps(
            {
                "database_location_mode": "custom",
                "database_path": str(source),
            }
        ),
        encoding="utf-8",
    )
    return resolve_offline_migration_paths(app_root)


def test_build_validated_copy_preserves_only_sqlite_data(tmp_path: Path) -> None:
    """Broken companion files cannot affect the independent SQLite migration."""

    paths = _configured_legacy_paths(tmp_path, products=2, users=1)
    source_before = paths.source.read_bytes()
    (paths.source.parent / "web_users.json").write_text("not valid JSON", encoding="utf-8")
    (paths.source.parent / "lists.xlsx").write_bytes(b"not an xlsx")
    progress_events = []

    staging, report = build_validated_legacy_sqlite_copy(paths, progress_events.append)

    assert staging.is_file()
    assert report.source == paths.source
    assert report.target == paths.target
    assert report.product_count == 2
    assert report.user_count == 1
    assert paths.source.read_bytes() == source_before
    assert {event.stage for event in progress_events} >= {"copy", "schema", "validation"}


def test_build_validated_copy_replaces_old_short_search_triggers(tmp_path: Path) -> None:
    """The copied DB must not retain trigger SQL that calls PicOrgFTP functions."""

    paths = _configured_legacy_paths(tmp_path, products=1, users=1)
    with sqlite3.connect(paths.source) as connection:
        connection.executescript(
            """
            DROP TRIGGER trg_product_entries_short_fts_insert;
            DROP TRIGGER trg_product_entries_short_fts_delete;
            DROP TRIGGER trg_product_entries_short_fts_update;

            CREATE TRIGGER trg_product_entries_short_fts_insert
            AFTER INSERT ON product_entries BEGIN
                INSERT INTO product_entries_short_fts(rowid, grams)
                VALUES (new.rowid, picorg_product_short_grams(new.search_text_key));
            END;
            CREATE TRIGGER trg_product_entries_short_fts_delete
            AFTER DELETE ON product_entries BEGIN
                INSERT INTO product_entries_short_fts(product_entries_short_fts, rowid, grams)
                VALUES ('delete', old.rowid, picorg_product_short_grams(old.search_text_key));
            END;
            CREATE TRIGGER trg_product_entries_short_fts_update
            AFTER UPDATE OF search_text_key ON product_entries BEGIN
                INSERT INTO product_entries_short_fts(product_entries_short_fts, rowid, grams)
                VALUES ('delete', old.rowid, picorg_product_short_grams(old.search_text_key));
                INSERT INTO product_entries_short_fts(rowid, grams)
                VALUES (new.rowid, picorg_product_short_grams(new.search_text_key));
            END;
            PRAGMA user_version = 15;
            """
        )

    staging, _report = build_validated_legacy_sqlite_copy(paths, lambda _event: None)

    with sqlite3.connect(staging) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 17
        trigger_sql = [
            row[0]
            for row in connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'trigger' "
                "AND name LIKE 'trg_product_entries_short_fts_%'"
            )
        ]
    assert len(trigger_sql) == 3
    assert all("picorg_product_short_grams" not in sql for sql in trigger_sql)
    assert all("picsyncra_product_short_grams" in sql for sql in trigger_sql)


def test_successful_offline_migration_publishes_target_and_switches_settings(
    tmp_path: Path,
) -> None:
    """Only a validated target becomes the next main application's database."""

    paths = _configured_legacy_paths(tmp_path, products=2, users=1)
    source_before = paths.source.read_bytes()

    report = run_offline_legacy_migration(paths.app_root, progress=lambda _event: None)

    assert report.target == paths.target
    assert paths.target.is_file()
    assert paths.source.read_bytes() == source_before
    settings = json.loads(paths.settings_path.read_text(encoding="utf-8"))
    assert settings["data_mode"] == "sqlite"
    assert settings["database_location_mode"] == "custom"
    assert settings["database_path"] == str(paths.target)


def test_settings_failure_removes_only_newly_published_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed final config write cannot leave a target the app will not select."""

    paths = _configured_legacy_paths(tmp_path, products=1, users=1)
    settings_before = paths.settings_path.read_bytes()
    from picsyncra import offline_legacy_sqlite_migrator

    def fail_settings_write(*_args, **_kwargs) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(
        offline_legacy_sqlite_migrator.storage_settings,
        "update_bootstrap_settings_file",
        fail_settings_write,
    )

    with pytest.raises(OfflineMigrationError) as error:
        run_offline_legacy_migration(paths.app_root, progress=lambda _event: None)

    assert error.value.code == "settings_update"
    assert not paths.target.exists()
    assert paths.settings_path.read_bytes() == settings_before
