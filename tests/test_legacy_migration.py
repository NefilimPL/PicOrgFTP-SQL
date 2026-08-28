from __future__ import annotations

from pathlib import Path

import picsyncra.legacy_migration as legacy_migration

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
