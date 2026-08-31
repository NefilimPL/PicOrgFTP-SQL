from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import picsyncra.legacy_migration as legacy_migration
import pytest
from picsyncra import bootstrap
from picsyncra.sqlite_coordination import RetiredDatabaseError
from picsyncra.sqlite_store import SqliteStore

from picsyncra.legacy_migration import migrate_legacy_data


def _write(path: Path, content: bytes) -> None:
    path.write_bytes(content)


def test_migration_copies_legacy_sqlite_database_and_sidecars_once(tmp_path: Path) -> None:
    legacy_database = tmp_path / "picorgftp_sql.sqlite"
    _write(legacy_database, b"database")
    _write(tmp_path / "picorgftp_sql.sqlite-wal", b"wal")
    _write(tmp_path / "picorgftp_sql.sqlite-shm", b"shm")

    result = migrate_legacy_data(tmp_path, tmp_path)

    assert result.migrated is True
    assert result.skipped is False
    assert (tmp_path / "picsyncra.sqlite").read_bytes() == b"database"
    assert (tmp_path / "picsyncra.sqlite-wal").read_bytes() == b"wal"
    assert (tmp_path / "picsyncra.sqlite-shm").read_bytes() == b"shm"
    assert legacy_database.read_bytes() == b"database"

    repeated = migrate_legacy_data(tmp_path, tmp_path)

    assert repeated.migrated is False
    assert repeated.skipped is True
    assert (tmp_path / "picsyncra.sqlite").read_bytes() == b"database"


def test_migration_preserves_existing_picsyncra_database(tmp_path: Path) -> None:
    _write(tmp_path / "picorgftp_sql.sqlite", b"legacy")
    _write(tmp_path / "picsyncra.sqlite", b"current")

    result = migrate_legacy_data(tmp_path, tmp_path)

    assert result.migrated is False
    assert result.skipped is True
    assert (tmp_path / "picsyncra.sqlite").read_bytes() == b"current"


def test_migration_reports_copy_failure_without_creating_a_target(
    tmp_path: Path, monkeypatch
) -> None:
    _write(tmp_path / "picorgftp_sql.sqlite", b"legacy")

    def fail_copy(source, target):
        raise OSError("disk unavailable")

    monkeypatch.setattr(legacy_migration.shutil, "copy2", fail_copy)

    result = migrate_legacy_data(tmp_path, tmp_path)

    assert result.migrated is False
    assert result.skipped is False
    assert result.error == "disk unavailable"
    assert not (tmp_path / "picsyncra.sqlite").exists()


def test_adoption_copies_legacy_sqlite_and_archives_its_source(tmp_path: Path) -> None:
    """A copied legacy database must become the active PicSyncra database."""

    application_root = tmp_path / "application"
    data_root = tmp_path / "data"
    backup_root = tmp_path / "BACKUP"
    application_root.mkdir()
    data_root.mkdir()
    source = application_root / "picorgftp_sql.sqlite"
    target = data_root / "picsyncra.sqlite"
    source_store = SqliteStore(str(source))
    source_store.save_config({"migration_marker": "legacy-sqlite"})
    source_store.save_users(
        [
            {
                "username": "legacy-operator",
                "role": "user",
                "enabled": True,
                "password_hash": "hash",
            }
        ]
    )

    result = legacy_migration.adopt_legacy_data(
        application_root=application_root,
        data_root=data_root,
        database_path=target,
        backup_root=backup_root,
    )

    assert result.migrated is True
    assert result.source_kind == "sqlite"
    assert SqliteStore(str(target)).load_config()["migration_marker"] == "legacy-sqlite"
    assert SqliteStore(str(target)).load_users()[0]["username"] == "legacy-operator"
    assert not source.exists()
    assert not source.with_name(f".{source.name}.picsyncra-adoption").exists()
    assert (result.archive_dir / source.name).is_file()


def test_adoption_prevents_pic_syncra_from_recreating_a_retired_source(tmp_path: Path) -> None:
    """Queued in-process work cannot recreate an empty old SQLite database."""

    source = tmp_path / legacy_migration._LEGACY_SQLITE_FILENAME
    target = tmp_path / "picsyncra.sqlite"
    SqliteStore(str(source)).save_config({"migration_marker": "retired"})

    result = legacy_migration.adopt_legacy_data(
        application_root=tmp_path,
        data_root=tmp_path,
        database_path=target,
        backup_root=tmp_path / "BACKUP",
    )

    assert result.migrated is True
    with pytest.raises(RetiredDatabaseError):
        SqliteStore(str(source)).load_config()
    assert not source.exists()


def test_adoption_does_not_overwrite_an_existing_picsyncra_database(tmp_path: Path) -> None:
    """A populated PicSyncra target must keep its data and legacy files."""

    source = tmp_path / "picorgftp_sql.sqlite"
    target = tmp_path / "picsyncra.sqlite"
    SqliteStore(str(source)).save_config({"migration_marker": "legacy"})
    SqliteStore(str(target)).save_config({"migration_marker": "current"})

    result = legacy_migration.adopt_legacy_data(
        application_root=tmp_path,
        data_root=tmp_path,
        database_path=target,
        backup_root=tmp_path / "BACKUP",
    )

    assert result.migrated is False
    assert result.error == "Docelowa baza PicSyncra juz istnieje."
    assert SqliteStore(str(target)).load_config()["migration_marker"] == "current"
    assert source.exists()


def test_adoption_archives_and_replaces_existing_target_after_explicit_confirmation(
    tmp_path: Path,
) -> None:
    """A confirmed import must preserve the replaced database in the import archive."""

    source = tmp_path / "picorgftp_sql.sqlite"
    target = tmp_path / "picsyncra.sqlite"
    SqliteStore(str(source)).save_config({"migration_marker": "legacy"})
    SqliteStore(str(target)).save_config({"migration_marker": "current"})

    result = legacy_migration.adopt_legacy_data(
        application_root=tmp_path,
        data_root=tmp_path,
        database_path=target,
        backup_root=tmp_path / "BACKUP",
        replace_existing_target=True,
    )

    assert result.migrated is True
    assert SqliteStore(str(target)).load_config()["migration_marker"] == "legacy"
    assert (
        SqliteStore(str(result.archive_dir / "previous-picsyncra.sqlite")).load_config()[
            "migration_marker"
        ]
        == "current"
    )
    assert not source.exists()


def test_adoption_replaces_an_empty_picsyncra_database(tmp_path: Path) -> None:
    """A database containing only PicSyncra's schema must not block first import."""

    source = tmp_path / legacy_migration._LEGACY_SQLITE_FILENAME
    target = tmp_path / "picsyncra.sqlite"
    SqliteStore(str(source)).save_config({"migration_marker": "legacy"})
    SqliteStore(str(target)).initialize()

    result = legacy_migration.adopt_legacy_data(
        application_root=tmp_path,
        data_root=tmp_path,
        database_path=target,
        backup_root=tmp_path / "BACKUP",
    )

    assert result.migrated is True
    assert SqliteStore(str(target)).load_config()["migration_marker"] == "legacy"
    assert not source.exists()


def test_adoption_imports_legacy_files_and_archives_them(tmp_path: Path) -> None:
    """File-backed legacy data must move into SQLite before its source is archived."""

    data_root = tmp_path / "data"
    data_root.mkdir()
    config_path = data_root / "config.json"
    index_path = data_root / "file_index.json"
    config_path.write_text(
        json.dumps({"migration_marker": "legacy-files"}), encoding="utf-8"
    )
    index_path.write_text(json.dumps({"version": 1, "names": ["LEGACY"]}), encoding="utf-8")

    result = legacy_migration.adopt_legacy_data(
        application_root=tmp_path / "application",
        data_root=data_root,
        database_path=data_root / "picsyncra.sqlite",
        backup_root=tmp_path / "BACKUP",
    )

    assert result.migrated is True
    assert result.source_kind == "files"
    assert SqliteStore(str(data_root / "picsyncra.sqlite")).load_config()["migration_marker"] == "legacy-files"
    assert not config_path.exists()
    assert not index_path.exists()
    assert (result.archive_dir / "config.json").is_file()
    assert (result.archive_dir / "file_index.json").is_file()


def test_adoption_uses_legacy_sqlite_and_imports_supplemental_legacy_files(
    tmp_path: Path,
) -> None:
    """Supplemental JSON data must not be archived before it reaches SQLite."""

    source = tmp_path / legacy_migration._LEGACY_SQLITE_FILENAME
    users_path = tmp_path / "web_users.json"
    target = tmp_path / "picsyncra.sqlite"
    SqliteStore(str(source)).save_config({"migration_marker": "legacy-sqlite"})
    users_path.write_text(
        json.dumps(
            [
                {
                    "username": "admin",
                    "role": "admin",
                    "enabled": True,
                    "password_hash": "legacy-password-hash",
                }
            ]
        ),
        encoding="utf-8",
    )

    result = legacy_migration.adopt_legacy_data(
        application_root=tmp_path,
        data_root=tmp_path,
        database_path=target,
        backup_root=tmp_path / "BACKUP",
    )

    assert result.migrated is True
    assert result.source_kind == "sqlite+files"
    assert SqliteStore(str(target)).load_config()["migration_marker"] == "legacy-sqlite"
    imported_users = SqliteStore(str(target)).load_users()
    assert imported_users[0]["username"] == "admin"
    assert imported_users[0]["role"] == "admin"
    assert not source.exists()
    assert not users_path.exists()
    assert (result.archive_dir / source.name).is_file()
    assert (result.archive_dir / users_path.name).is_file()


def test_adoption_archives_a_file_changed_during_handover(
    tmp_path: Path, monkeypatch
) -> None:
    """A late legacy-file write is moved to the archive rather than deleted."""

    data_root = tmp_path / "data"
    data_root.mkdir()
    config_path = data_root / "config.json"
    config_path.write_text(json.dumps({"migration_marker": "snapshot"}), encoding="utf-8")
    original_handover = legacy_migration._handover_sources_to_archive

    def write_then_handover(
        sources: tuple[Path, ...],
        archive_dir: Path,
        *,
        sqlite_source: bool,
    ) -> str | None:
        config_path.write_text(json.dumps({"migration_marker": "late-write"}), encoding="utf-8")
        return original_handover(sources, archive_dir, sqlite_source=sqlite_source)

    monkeypatch.setattr(legacy_migration, "_handover_sources_to_archive", write_then_handover)

    result = legacy_migration.adopt_legacy_data(
        application_root=tmp_path / "application",
        data_root=data_root,
        database_path=data_root / "picsyncra.sqlite",
        backup_root=tmp_path / "BACKUP",
    )

    assert result.migrated is True
    assert result.error is not None
    assert not config_path.exists()
    assert SqliteStore(str(data_root / "picsyncra.sqlite")).load_config()["migration_marker"] == "snapshot"
    assert json.loads((result.archive_dir / "config.json").read_text(encoding="utf-8"))[
        "migration_marker"
    ] == "late-write"


def test_adoption_reads_a_legacy_database_from_the_configured_custom_path(
    tmp_path: Path,
) -> None:
    """A configured old SQLite path must work even outside the standard roots."""

    source = tmp_path / "previous-location" / "picorgftp_sql.sqlite"
    source.parent.mkdir()
    target = tmp_path / "current-location" / "picsyncra.sqlite"
    SqliteStore(str(source)).save_config({"migration_marker": "custom-path"})

    result = legacy_migration.adopt_legacy_data(
        application_root=tmp_path / "application",
        data_root=tmp_path / "data",
        database_path=target,
        backup_root=tmp_path / "BACKUP",
        legacy_database_path=source,
    )

    assert result.migrated is True
    assert SqliteStore(str(target)).load_config()["migration_marker"] == "custom-path"
    assert not source.exists()


def test_adoption_keeps_legacy_data_in_place_when_archive_copy_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """A failed archive copy must not publish a target or delete the source."""

    source = tmp_path / "picorgftp_sql.sqlite"
    target = tmp_path / "picsyncra.sqlite"
    SqliteStore(str(source)).save_config({"migration_marker": "archive-failure"})

    def fail_archive_copy(_source, _target):
        raise OSError("archive unavailable")

    monkeypatch.setattr(legacy_migration.shutil, "copy2", fail_archive_copy)

    result = legacy_migration.adopt_legacy_data(
        application_root=tmp_path,
        data_root=tmp_path,
        database_path=target,
        backup_root=tmp_path / "BACKUP",
    )

    assert result.migrated is False
    assert result.error == "archive unavailable"
    assert source.exists()
    assert not target.exists()


def test_adoption_rejects_file_sources_split_between_roots(tmp_path: Path) -> None:
    """A coherent legacy file set must come from one location only."""

    application_root = tmp_path / "application"
    data_root = tmp_path / "data"
    application_root.mkdir()
    data_root.mkdir()
    (application_root / "config.json").write_text("{}", encoding="utf-8")
    (data_root / "file_index.json").write_text("{}", encoding="utf-8")
    target = data_root / "picsyncra.sqlite"

    result = legacy_migration.adopt_legacy_data(
        application_root=application_root,
        data_root=data_root,
        database_path=target,
        backup_root=tmp_path / "BACKUP",
    )

    assert result.migrated is False
    assert result.error is not None
    assert (application_root / "config.json").exists()
    assert (data_root / "file_index.json").exists()
    assert not target.exists()


def test_adoption_keeps_sources_when_settings_finalization_fails(tmp_path: Path) -> None:
    """The old configuration remains usable if its replacement cannot be activated."""

    source = tmp_path / legacy_migration._LEGACY_SQLITE_FILENAME
    target = tmp_path / "picsyncra.sqlite"
    SqliteStore(str(source)).save_config({"migration_marker": "settings-failure"})

    def fail_finalization(_target: Path) -> None:
        raise OSError("settings unavailable")

    result = legacy_migration.adopt_legacy_data(
        application_root=tmp_path,
        data_root=tmp_path,
        database_path=target,
        backup_root=tmp_path / "BACKUP",
        finalize=fail_finalization,
    )

    assert result.migrated is False
    assert result.error == "settings unavailable"
    assert source.exists()
    assert not target.exists()


def test_adoption_recovers_after_a_crash_between_publish_and_handover(tmp_path: Path) -> None:
    """A valid published target and active handover marker can be safely resumed."""

    source = tmp_path / legacy_migration._LEGACY_SQLITE_FILENAME
    target = tmp_path / "picsyncra.sqlite"
    SqliteStore(str(source)).save_config({"migration_marker": "resume-handover"})
    legacy_migration._copy_sqlite_database(source, target)
    source.with_name(f".{source.name}.picsyncra-adoption").write_text("active", encoding="ascii")
    finalized: list[Path] = []

    result = legacy_migration.adopt_legacy_data(
        application_root=tmp_path,
        data_root=tmp_path,
        database_path=target,
        backup_root=tmp_path / "BACKUP",
        finalize=finalized.append,
    )

    assert result.migrated is True
    assert finalized == [target]
    assert SqliteStore(str(target)).load_config()["migration_marker"] == "resume-handover"
    assert not source.exists()
    assert (result.archive_dir / source.name).is_file()
    assert not source.with_name(f".{source.name}.picsyncra-adoption").exists()


def test_adoption_publish_failure_does_not_leave_an_empty_target(
    tmp_path: Path, monkeypatch
) -> None:
    """An interrupted publish must remain retryable without manual file cleanup."""

    source = tmp_path / legacy_migration._LEGACY_SQLITE_FILENAME
    target = tmp_path / "picsyncra.sqlite"
    SqliteStore(str(source)).save_config({"migration_marker": "publish-failure"})

    def fail_publish(_source: Path, _target: Path) -> None:
        raise OSError("publish unavailable")

    monkeypatch.setattr(legacy_migration.os, "link", fail_publish)

    result = legacy_migration.adopt_legacy_data(
        application_root=tmp_path,
        data_root=tmp_path,
        database_path=target,
        backup_root=tmp_path / "BACKUP",
    )

    assert result.migrated is False
    assert result.error == "publish unavailable"
    assert source.exists()
    assert not target.exists()


def test_adoption_serializes_simultaneous_requests_for_the_same_target(
    tmp_path: Path, monkeypatch
) -> None:
    """A second action must not replace a database published by the first action."""

    source = tmp_path / legacy_migration._LEGACY_SQLITE_FILENAME
    target = tmp_path / "picsyncra.sqlite"
    SqliteStore(str(source)).save_config({"migration_marker": "one-winner"})
    first_copy_started = threading.Event()
    allow_first_copy = threading.Event()
    original_copy = legacy_migration._copy_sqlite_database

    def paused_copy(source_path: Path, target_path: Path, *args) -> None:
        first_copy_started.set()
        assert allow_first_copy.wait(timeout=5)
        original_copy(source_path, target_path, *args)

    monkeypatch.setattr(legacy_migration, "_copy_sqlite_database", paused_copy)
    kwargs = {
        "application_root": tmp_path,
        "data_root": tmp_path,
        "database_path": target,
        "backup_root": tmp_path / "BACKUP",
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(legacy_migration.adopt_legacy_data, **kwargs)
        assert first_copy_started.wait(timeout=5)
        second = executor.submit(legacy_migration.adopt_legacy_data, **kwargs)
        allow_first_copy.set()
        results = (first.result(timeout=10), second.result(timeout=10))

    assert sum(result.migrated for result in results) == 1
    assert SqliteStore(str(target)).load_config()["migration_marker"] == "one-winner"
    assert not source.exists()


def test_adoption_serializes_requests_for_one_source_and_different_targets(
    tmp_path: Path, monkeypatch
) -> None:
    """The source must not be recreated as an empty DB by a second adoption action."""

    source = tmp_path / legacy_migration._LEGACY_SQLITE_FILENAME
    first_target = tmp_path / "picsyncra-first.sqlite"
    second_target = tmp_path / "picsyncra-second.sqlite"
    SqliteStore(str(source)).save_config({"migration_marker": "single-source"})
    first_copy_started = threading.Event()
    allow_first_copy = threading.Event()
    first_finished = threading.Event()
    second_detection_started = threading.Event()
    copy_calls = 0
    original_copy = legacy_migration._copy_sqlite_database
    original_source_lookup = legacy_migration._legacy_sqlite_source

    def stale_second_source_lookup(*args, **kwargs):
        source_path = original_source_lookup(*args, **kwargs)
        if second_detection_started.is_set():
            return source_path
        if first_copy_started.is_set():
            second_detection_started.set()
            assert first_finished.wait(timeout=5)
        return source_path

    def paused_copy(source_path: Path, target_path: Path) -> None:
        nonlocal copy_calls
        copy_calls += 1
        if copy_calls == 1:
            first_copy_started.set()
            assert allow_first_copy.wait(timeout=5)
        else:
            assert first_finished.wait(timeout=5)
        original_copy(source_path, target_path)

    monkeypatch.setattr(legacy_migration, "_copy_sqlite_database", paused_copy)
    monkeypatch.setattr(legacy_migration, "_legacy_sqlite_source", stale_second_source_lookup)
    common_kwargs = {
        "application_root": tmp_path,
        "data_root": tmp_path,
        "backup_root": tmp_path / "BACKUP",
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            legacy_migration.adopt_legacy_data,
            database_path=first_target,
            **common_kwargs,
        )
        assert first_copy_started.wait(timeout=5)
        second = executor.submit(
            legacy_migration.adopt_legacy_data,
            database_path=second_target,
            **common_kwargs,
        )
        assert second_detection_started.wait(timeout=5)
        allow_first_copy.set()
        first_result = first.result(timeout=10)
        first_finished.set()
        results = (first_result, second.result(timeout=10))

    assert sum(result.migrated for result in results) == 1
    assert SqliteStore(str(first_target)).load_config()["migration_marker"] == "single-source"
    assert not second_target.exists()


def test_adoption_keeps_sqlite_source_when_its_cleanup_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """A verified snapshot stays available when the original cannot be removed."""

    source = tmp_path / legacy_migration._LEGACY_SQLITE_FILENAME
    target = tmp_path / "picsyncra.sqlite"
    SqliteStore(str(source)).save_config({"migration_marker": "cleanup-failure"})

    def fail_cleanup(
        _sources: tuple[Path, ...],
        _archive_dir: Path,
        *,
        sqlite_source: bool,
    ) -> str:
        return "source busy"

    monkeypatch.setattr(legacy_migration, "_handover_sources_to_archive", fail_cleanup)

    result = legacy_migration.adopt_legacy_data(
        application_root=tmp_path,
        data_root=tmp_path,
        database_path=target,
        backup_root=tmp_path / "BACKUP",
    )

    assert result.migrated is True
    assert result.error is not None
    assert "source busy" in result.error
    assert source.exists()
    assert SqliteStore(str(target)).load_config()["migration_marker"] == "cleanup-failure"
    assert SqliteStore(str(result.archive_dir / source.name)).load_config()["migration_marker"] == "cleanup-failure"


def test_adoption_recovers_archived_legacy_users_after_an_earlier_import(
    tmp_path: Path,
) -> None:
    """A confirmed retry can repair an already-created target from BACKUP."""

    target = tmp_path / "picsyncra.sqlite"
    SqliteStore(str(target)).save_users(
        [
            {
                "username": "admin",
                "role": "user",
                "enabled": True,
                "password_hash": "default-password-hash",
            }
        ]
    )
    archived_source = tmp_path / "BACKUP" / "legacy-import" / "20260831-previous"
    archived_source.mkdir(parents=True)
    (archived_source / "web_users.json").write_text(
        json.dumps(
            [
                {
                    "username": "admin",
                    "role": "admin",
                    "enabled": True,
                    "password_hash": "legacy-password-hash",
                }
            ]
        ),
        encoding="utf-8",
    )

    initial = legacy_migration.adopt_legacy_data(
        application_root=tmp_path,
        data_root=tmp_path,
        database_path=target,
        backup_root=tmp_path / "BACKUP",
    )
    result = legacy_migration.adopt_legacy_data(
        application_root=tmp_path,
        data_root=tmp_path,
        database_path=target,
        backup_root=tmp_path / "BACKUP",
        replace_existing_target=True,
    )

    assert initial.error_code == "target_exists"
    assert result.migrated is True
    assert result.replaced_target is True
    assert result.source_kind == "backup-files"
    imported_user = SqliteStore(str(target)).load_users()[0]
    assert imported_user["role"] == "admin"
    assert imported_user["password_hash"] == "legacy-password-hash"
    assert (result.archive_dir / "previous-picsyncra.sqlite").is_file()


def test_runtime_does_not_migrate_legacy_data_before_the_user_chooses_the_action(
    tmp_path: Path, monkeypatch
) -> None:
    """Opening the application must leave data adoption to the settings action."""

    data_root = tmp_path / "data"
    data_root.mkdir()
    source = data_root / "picorgftp_sql.sqlite"
    SqliteStore(str(source)).save_config({"migration_marker": "manual-only"})

    monkeypatch.setattr(bootstrap.settings, "initialize_runtime", lambda **_kwargs: None)
    monkeypatch.setattr(bootstrap.settings, "BASE_DIR_SETTINGS_PATH", str(tmp_path / "local_settings.json"))
    monkeypatch.setattr(bootstrap.settings, "AC", str(data_root))
    monkeypatch.setattr(bootstrap.config, "initialize_config", lambda **_kwargs: {})

    result = bootstrap.initialize_application_runtime(interactive=False)

    assert source.exists()
    assert not (data_root / "picsyncra.sqlite").exists()
    assert "migration" not in result
