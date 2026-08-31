"""One-time adoption of PicSyncra data from the working product name."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import hashlib
import os
import shutil
import sqlite3
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from .brand import SQLITE_FILENAME
from .legacy_import import import_legacy_to_sqlite
from .sqlite_coordination import (
    clear_retired_database_marker,
    database_maintenance,
    maintenance_state,
    retire_database,
)


_LEGACY_SQLITE_FILENAME = "picorgftp_sql.sqlite"
_SQLITE_SIDECARS = ("-wal", "-shm")
_EMPTY_TARGET_TABLES = frozenset({"schema_version", "operational_event_stream"})
_EMPTY_TARGET_FTS_PREFIXES = ("product_entries_fts", "product_entries_short_fts")
_LEGACY_DATA_FILENAMES = (
    "config.json",
    "lists.xlsx",
    "web_users.json",
    "web_history.json",
    "file_index.json",
)
_TARGET_EXISTS = "target_exists"
_ADOPTION_IN_PROGRESS = "adoption_in_progress"
_SPLIT_FILE_SOURCES = "split_file_sources"
_ADOPTION_FAILED = "adoption_failed"
_PATH_LOCKS: dict[str, threading.Lock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


class _AdoptionInProgressError(RuntimeError):
    """The target is currently guarded by another PicSyncra import action."""


class _TargetAlreadyExistsError(FileExistsError):
    """The target appeared while a staged database was being prepared."""


@dataclass(frozen=True)
class MigrationResult:
    migrated: bool
    skipped: bool
    copied_paths: tuple[Path, ...] = ()
    error: str | None = None
    source_kind: str = ""
    archive_dir: Path | None = None
    error_code: str | None = None
    replaced_target: bool = False


def _unique_paths(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = path.resolve()
        key = str(resolved).casefold()
        if key not in seen:
            unique.append(resolved)
            seen.add(key)
    return tuple(unique)


def migrate_legacy_data(application_root: Path, data_root: Path) -> MigrationResult:
    """Copy the prior default SQLite database to the PicSyncra location once."""

    source_roots = _unique_paths((Path(data_root), Path(application_root)))
    target_root = Path(data_root).resolve()
    target = target_root / SQLITE_FILENAME
    if target.exists():
        return MigrationResult(migrated=False, skipped=True)

    source = next(
        (root / _LEGACY_SQLITE_FILENAME for root in source_roots if (root / _LEGACY_SQLITE_FILENAME).is_file()),
        None,
    )
    if source is None:
        return MigrationResult(migrated=False, skipped=True)

    files_to_copy = [source]
    files_to_copy.extend(
        sidecar for suffix in _SQLITE_SIDECARS if (sidecar := source.with_name(source.name + suffix)).is_file()
    )
    target_root.mkdir(parents=True, exist_ok=True)
    try:
        with TemporaryDirectory(prefix=".picsyncra-migration-", dir=target_root) as temporary_dir:
            staging_root = Path(temporary_dir)
            for source_file in files_to_copy:
                destination = staging_root / source_file.name.replace(
                    _LEGACY_SQLITE_FILENAME,
                    SQLITE_FILENAME,
                    1,
                )
                shutil.copy2(source_file, destination)
            copied_paths = tuple(target_root / staged.name for staged in staging_root.iterdir())
            if target.exists():
                return MigrationResult(migrated=False, skipped=True)
            for staged in staging_root.iterdir():
                staged.rename(target_root / staged.name)
    except OSError as exc:
        return MigrationResult(migrated=False, skipped=False, error=str(exc))
    return MigrationResult(migrated=True, skipped=False, copied_paths=copied_paths)


def _legacy_sqlite_source(
    application_root: Path,
    data_root: Path,
    legacy_database_path: Path | None = None,
) -> Path | None:
    configured = Path(legacy_database_path) if legacy_database_path else None
    if (
        configured is not None
        and configured.name.casefold() == _LEGACY_SQLITE_FILENAME.casefold()
        and configured.is_file()
    ):
        return configured
    for root in _unique_paths((Path(data_root), Path(application_root))):
        candidate = root / _LEGACY_SQLITE_FILENAME
        if candidate.is_file():
            return candidate
    return None


def adoption_database_path(database_path: Path) -> Path:
    """Return the current database name when settings still point to the old one."""

    candidate = Path(database_path)
    if candidate.name.casefold() == _LEGACY_SQLITE_FILENAME.casefold():
        return candidate.with_name(SQLITE_FILENAME)
    return candidate


def _legacy_file_source_sets(
    application_root: Path, data_root: Path
) -> tuple[tuple[Path, tuple[Path, ...]], ...]:
    """Return complete per-directory source sets without combining directories."""

    source_sets: list[tuple[Path, tuple[Path, ...]]] = []
    for root in _unique_paths((Path(data_root), Path(application_root))):
        sources = tuple(root / filename for filename in _LEGACY_DATA_FILENAMES if (root / filename).is_file())
        if sources:
            source_sets.append((root, sources))
    return tuple(source_sets)


def _sqlite_source_files(source: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in (source, *(source.with_name(source.name + suffix) for suffix in _SQLITE_SIDECARS))
        if path.is_file()
    )


def _legacy_archive_dir(backup_root: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return backup_root / "legacy-import" / f"{timestamp}-{uuid4().hex[:8]}"


def _latest_archived_legacy_files(backup_root: Path) -> Path | None:
    """Find an archived JSON/XLSX source left by a completed earlier import."""

    archive_root = Path(backup_root) / "legacy-import"
    try:
        candidates = sorted(
            (path for path in archive_root.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    for candidate in candidates:
        if any((candidate / filename).is_file() for filename in _LEGACY_DATA_FILENAMES):
            return candidate
    return None


def _copy_sqlite_database(source: Path, target: Path) -> None:
    connection = None
    target_connection = None
    try:
        connection = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
        target_connection = sqlite3.connect(str(target))
        connection.backup(target_connection)
        integrity = target_connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or str(integrity[0]).lower() != "ok":
            raise sqlite3.DatabaseError("SQLite integrity check failed")
    finally:
        if target_connection is not None:
            target_connection.close()
        if connection is not None:
            connection.close()


@contextmanager
def _locked_sqlite_source(source: Path) -> Iterator[None]:
    """Prevent new legacy SQLite writes while its data is copied and archived."""

    connection = sqlite3.connect(
        f"{source.resolve().as_uri()}?mode=rw",
        uri=True,
        timeout=5,
    )
    try:
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("BEGIN IMMEDIATE")
        yield
    finally:
        try:
            connection.rollback()
        except sqlite3.Error:
            pass
        connection.close()


def _validate_sqlite_database(path: Path) -> None:
    connection = None
    try:
        connection = sqlite3.connect(str(path))
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or str(integrity[0]).lower() != "ok":
            raise sqlite3.DatabaseError("SQLite integrity check failed")
    finally:
        if connection is not None:
            connection.close()


def _is_empty_picsyncra_database(path: Path) -> bool:
    """Return whether a target contains only the schema made during first start."""

    connection = None
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        table_rows = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        for table_name, definition in table_rows:
            table_name = str(table_name)
            if table_name in _EMPTY_TARGET_TABLES:
                continue
            if table_name.startswith(_EMPTY_TARGET_FTS_PREFIXES):
                continue
            if str(definition or "").lstrip().upper().startswith("CREATE VIRTUAL TABLE"):
                continue
            quoted_name = table_name.replace('"', '""')
            if connection.execute(f'SELECT 1 FROM "{quoted_name}" LIMIT 1').fetchone() is not None:
                return False
        return True
    except (OSError, sqlite3.Error):
        return False
    finally:
        if connection is not None:
            connection.close()


def _copy_sources_to_archive(
    sources: tuple[Path, ...],
    archive_dir: Path,
    *,
    sqlite_source: Path | None = None,
    sqlite_snapshot: Path | None = None,
) -> None:
    archive_dir.mkdir(parents=True, exist_ok=sqlite_source is not None)
    if sqlite_source is not None:
        if sqlite_snapshot is None:
            raise ValueError("Brakuje zweryfikowanego snapshotu SQLite do archiwizacji.")
        destination = archive_dir / sqlite_source.name
        shutil.copy2(sqlite_snapshot, destination)
        _validate_sqlite_database(destination)
    for source in sources:
        destination = archive_dir / source.name
        if destination.exists():
            destination = archive_dir / f"{source.stem}-{uuid4().hex[:8]}{source.suffix}"
        shutil.copy2(source, destination)
        if destination.stat().st_size != source.stat().st_size:
            raise OSError(f"Nie udalo sie zweryfikowac kopii archiwalnej: {source.name}")


def _archive_existing_target(target: Path, archive_dir: Path) -> Path:
    """Store a verified SQLite snapshot before a confirmed target replacement."""

    destination = archive_dir / f"previous-{target.name}"
    if destination.exists():
        raise FileExistsError(f"Archiwum docelowej bazy juz istnieje: {destination.name}")
    _copy_sqlite_database(target, destination)
    _validate_sqlite_database(destination)
    return destination


def _handover_sources_to_archive(
    sources: tuple[Path, ...],
    archive_dir: Path,
    *,
    sqlite_source: bool,
) -> str | None:
    """Move originals to the archive without a copy-then-delete race."""

    errors: list[str] = []
    source_files = tuple(source for source in sources if source.is_file())
    if not source_files:
        return "Nie znaleziono zrodlowych plikow do przeniesienia po imporcie."
    destination_root = archive_dir / "legacy-source-files" if sqlite_source else archive_dir
    destination_root.mkdir(parents=True, exist_ok=True)
    changed_files = [
        source.name
        for source in source_files
        if not sqlite_source
        and (destination := destination_root / source.name).is_file()
        and not _files_match(source, destination)
    ]
    try:
        same_volume = all(
            source.stat().st_dev == destination_root.stat().st_dev for source in source_files
        )
    except OSError as exc:
        return f"Nie udalo sie sprawdzic plikow przed przeniesieniem: {exc}"
    quarantine_dir: Path | None = None
    if not same_volume:
        quarantine_dir = source_files[0].parent / f".picsyncra-legacy-{uuid4().hex}"
        quarantine_dir.mkdir()
    moved_files: list[tuple[Path, Path]] = []
    for source in source_files:
        destination = (
            destination_root / source.name
            if quarantine_dir is None
            else quarantine_dir / source.name
        )
        try:
            os.replace(source, destination)
            moved_files.append((source, destination))
        except FileNotFoundError:
            errors.append(f"{source.name}: plik zniknal przed przeniesieniem")
        except OSError as exc:
            errors.append(f"{source.name}: {exc}")
    if quarantine_dir is not None and moved_files:
        for _source, staged in moved_files:
            destination = destination_root / staged.name
            try:
                shutil.copy2(staged, destination)
                if destination.stat().st_size != staged.stat().st_size:
                    raise OSError("nieudana weryfikacja kopii po przeniesieniu")
            except OSError as exc:
                errors.append(f"{staged.name}: {exc}")
        if os.name == "nt" and not errors:
            for _source, staged in moved_files:
                try:
                    staged.unlink()
                except OSError as exc:
                    errors.append(f"{staged.name}: {exc}")
            try:
                quarantine_dir.rmdir()
            except OSError as exc:
                errors.append(f"{quarantine_dir.name}: {exc}")
        elif os.name != "nt":
            errors.append(
                f"{quarantine_dir.name}: zachowano kwarantanne dla bezpieczenstwa danych"
            )
    if changed_files:
        errors.append(
            "Zrodlo zmienilo sie podczas importu; najnowsza wersja zostala przeniesiona do archiwum: "
            + ", ".join(changed_files)
        )
    return "; ".join(errors) or None


def _files_match(first: Path, second: Path) -> bool:
    try:
        if first.stat().st_size != second.stat().st_size:
            return False
        return hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()
    except OSError:
        return False


@contextmanager
def _exclusive_path_lock(
    *,
    backup_root: Path,
    scope: str,
    protected_path: Path,
) -> Iterator[None]:
    """Use process- and OS-level locks that are released when a process exits."""

    canonical_path = str(protected_path.resolve()).casefold()
    lock_key = f"{scope}:{canonical_path}"
    digest = hashlib.sha256(lock_key.encode("utf-8")).hexdigest()
    lock_path = Path(backup_root) / "legacy-import" / ".locks" / f"{scope}-{digest}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _PATH_LOCKS_GUARD:
        local_lock = _PATH_LOCKS.setdefault(lock_key, threading.Lock())
    with local_lock:
        descriptor = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
        locked = False
        try:
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    raise _AdoptionInProgressError(
                        "Trwa juz wczytywanie starej konfiguracji dla tej bazy."
                    ) from exc
                raise
            yield
        finally:
            try:
                if locked:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def _publish_staged_target(
    staging: Path,
    target: Path,
    *,
    replace_target: bool = False,
) -> None:
    """Publish a staged database without replacing an unapproved target."""

    if replace_target and target.exists():
        target.unlink()
    try:
        os.link(staging, target)
    except FileExistsError as exc:
        raise _TargetAlreadyExistsError("Docelowa baza PicSyncra juz istnieje.") from exc


def _restore_archived_legacy_data(
    *,
    archived_source: Path,
    target: Path,
    backup_root: Path,
    finalize: Callable[[Path], None] | None,
) -> MigrationResult:
    """Repair an earlier incomplete adoption from its immutable BACKUP copy."""

    archive_dir = _legacy_archive_dir(backup_root)
    archive_dir.mkdir(parents=True, exist_ok=False)
    archived_database = archived_source / _LEGACY_SQLITE_FILENAME
    source_kind = "backup-sqlite+files" if archived_database.is_file() else "backup-files"
    target_replaced = target.exists()
    try:
        with _exclusive_path_lock(
            backup_root=backup_root,
            scope="target",
            protected_path=target,
        ):
            with TemporaryDirectory(prefix=".picsyncra-legacy-recovery-", dir=target.parent) as temporary_dir:
                staging = Path(temporary_dir) / target.name
                if archived_database.is_file():
                    _copy_sqlite_database(archived_database, staging)
                elif target.exists():
                    _copy_sqlite_database(target, staging)
                import_legacy_to_sqlite(
                    str(archived_source),
                    str(staging),
                    merge_existing=True,
                )
                _validate_sqlite_database(staging)
                if target.exists():
                    _archive_existing_target(target, archive_dir)
                _publish_staged_target(staging, target, replace_target=target.exists())
                if finalize is not None:
                    finalize(target)
    except _AdoptionInProgressError as exc:
        return MigrationResult(
            migrated=False,
            skipped=False,
            error=str(exc),
            error_code=_ADOPTION_IN_PROGRESS,
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        return MigrationResult(
            migrated=False,
            skipped=False,
            error=str(exc),
            error_code=_ADOPTION_FAILED,
        )
    return MigrationResult(
        migrated=True,
        skipped=False,
        copied_paths=(target,),
        source_kind=source_kind,
        archive_dir=archive_dir,
        replaced_target=target_replaced,
    )


def adopt_legacy_data(
    *,
    application_root: Path,
    data_root: Path,
    database_path: Path,
    backup_root: Path,
    legacy_database_path: Path | None = None,
    finalize: Callable[[Path], None] | None = None,
    replace_existing_target: bool = False,
) -> MigrationResult:
    """Adopt historical data into one PicSyncra SQLite database and archive sources."""

    sqlite_source = _legacy_sqlite_source(
        application_root,
        data_root,
        legacy_database_path,
    )
    file_source_sets = _legacy_file_source_sets(application_root, data_root)
    if len(file_source_sets) > 1:
        return MigrationResult(
            migrated=False,
            skipped=False,
            error="Znaleziono stare pliki danych w wiecej niz jednej lokalizacji.",
            error_code=_SPLIT_FILE_SOURCES,
        )
    file_sources = file_source_sets[0][1] if file_source_sets else ()
    target = Path(database_path).resolve()
    backup_root = Path(backup_root).resolve()
    if sqlite_source is None and not file_sources:
        archived_source = _latest_archived_legacy_files(backup_root)
        if archived_source is not None:
            if target.exists() and not replace_existing_target:
                return MigrationResult(
                    migrated=False,
                    skipped=False,
                    error="Docelowa baza PicSyncra juz istnieje.",
                    error_code=_TARGET_EXISTS,
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            return _restore_archived_legacy_data(
                archived_source=archived_source,
                target=target,
                backup_root=backup_root,
                finalize=finalize,
            )
        return MigrationResult(migrated=False, skipped=True)

    resume_interrupted_adoption = (
        sqlite_source is not None
        and target.exists()
        and maintenance_state(sqlite_source) in {"active", "retired"}
    )
    if (
        target.exists()
        and not resume_interrupted_adoption
        and not _is_empty_picsyncra_database(target)
        and not replace_existing_target
    ):
        return MigrationResult(
            migrated=False,
            skipped=False,
            error="Docelowa baza PicSyncra juz istnieje.",
            error_code=_TARGET_EXISTS,
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    archive_dir = _legacy_archive_dir(backup_root)
    source_kind = (
        "sqlite+files" if sqlite_source is not None and file_sources
        else "sqlite" if sqlite_source is not None
        else "files"
    )
    sources = _sqlite_source_files(sqlite_source) if sqlite_source else file_sources
    source_lock_path = sqlite_source if sqlite_source is not None else file_source_sets[0][0]
    source_lock_scope = "sqlite-source" if sqlite_source is not None else "files-source"
    target_published = False
    target_replaced = False
    cleanup_error: str | None = None
    try:
        with _exclusive_path_lock(
            backup_root=backup_root,
            scope=source_lock_scope,
            protected_path=source_lock_path,
        ):
            if sqlite_source is not None and not sqlite_source.is_file():
                return MigrationResult(migrated=False, skipped=True)
            if sqlite_source is None and not all(source.is_file() for source in file_sources):
                return MigrationResult(migrated=False, skipped=True)
            with _exclusive_path_lock(
                backup_root=backup_root,
                scope="target",
                protected_path=target,
            ):
                replace_target = (
                    target.exists()
                    and not resume_interrupted_adoption
                    and (
                        replace_existing_target
                        or _is_empty_picsyncra_database(target)
                    )
                )
                if target.exists() and not resume_interrupted_adoption and not replace_target:
                    return MigrationResult(
                        migrated=False,
                        skipped=False,
                        error="Docelowa baza PicSyncra juz istnieje.",
                        error_code=_TARGET_EXISTS,
                )
                with TemporaryDirectory(prefix=".picsyncra-legacy-", dir=target.parent) as temporary_dir:
                    staging = Path(temporary_dir) / target.name
                    if sqlite_source is not None:
                        with database_maintenance(sqlite_source):
                            if resume_interrupted_adoption:
                                _validate_sqlite_database(target)
                                _copy_sources_to_archive(
                                    file_sources,
                                    archive_dir,
                                    sqlite_source=sqlite_source,
                                    sqlite_snapshot=target,
                                )
                                if finalize is not None:
                                    finalize(target)
                            else:
                                with _locked_sqlite_source(sqlite_source):
                                    _copy_sqlite_database(sqlite_source, staging)
                                    if file_sources:
                                        staging_sources = Path(temporary_dir) / "legacy-files"
                                        staging_sources.mkdir()
                                        for source in file_sources:
                                            shutil.copy2(source, staging_sources / source.name)
                                        import_legacy_to_sqlite(
                                            str(staging_sources),
                                            str(staging),
                                            merge_existing=True,
                                        )
                                        _validate_sqlite_database(staging)
                                    _copy_sources_to_archive(
                                        file_sources,
                                        archive_dir,
                                        sqlite_source=sqlite_source,
                                        sqlite_snapshot=staging,
                                    )
                                    if replace_existing_target and target.exists():
                                        _archive_existing_target(target, archive_dir)
                                        _publish_staged_target(
                                            staging,
                                            target,
                                            replace_target=True,
                                        )
                                        target_replaced = True
                                    else:
                                        _publish_staged_target(
                                            staging,
                                            target,
                                            replace_target=replace_target,
                                        )
                                    target_published = True
                                    if finalize is not None:
                                        finalize(target)
                            retire_database(sqlite_source)
                        cleanup_error = _handover_sources_to_archive(
                            _sqlite_source_files(sqlite_source),
                            archive_dir,
                            sqlite_source=True,
                        )
                        if file_sources:
                            supplemental_cleanup_error = _handover_sources_to_archive(
                                file_sources,
                                archive_dir,
                                sqlite_source=False,
                            )
                            cleanup_error = "; ".join(
                                error
                                for error in (cleanup_error, supplemental_cleanup_error)
                                if error
                            ) or None
                        residual_sqlite_files = _sqlite_source_files(sqlite_source)
                        if residual_sqlite_files:
                            residual_error = _handover_sources_to_archive(
                                residual_sqlite_files,
                                archive_dir,
                                sqlite_source=True,
                            )
                            residual_names = ", ".join(
                                source.name for source in _sqlite_source_files(sqlite_source)
                            )
                            residual_warning = (
                                f"Pozostaly zrodlowe pliki SQLite: {residual_names}"
                                if residual_names
                                else ""
                            )
                            cleanup_error = "; ".join(
                                error
                                for error in (cleanup_error, residual_error, residual_warning)
                                if error
                            ) or None
                        elif cleanup_error is None:
                            clear_retired_database_marker(sqlite_source)
                    else:
                        staging_sources = Path(temporary_dir) / "legacy-files"
                        staging_sources.mkdir()
                        for source in file_sources:
                            shutil.copy2(source, staging_sources / source.name)
                        import_legacy_to_sqlite(str(staging_sources), str(staging))
                        _validate_sqlite_database(staging)
                        _copy_sources_to_archive(sources, archive_dir)
                        if replace_existing_target and target.exists():
                            _archive_existing_target(target, archive_dir)
                            _publish_staged_target(staging, target, replace_target=True)
                            target_replaced = True
                        else:
                            _publish_staged_target(
                                staging,
                                target,
                                replace_target=replace_target,
                            )
                        target_published = True
                        if finalize is not None:
                            finalize(target)
                        cleanup_error = _handover_sources_to_archive(
                            sources,
                            archive_dir,
                            sqlite_source=False,
                        )
    except _AdoptionInProgressError as exc:
        return MigrationResult(
            migrated=False,
            skipped=False,
            error=str(exc),
            error_code=_ADOPTION_IN_PROGRESS,
        )
    except _TargetAlreadyExistsError as exc:
        return MigrationResult(
            migrated=False,
            skipped=False,
            error=str(exc),
            error_code=_TARGET_EXISTS,
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        if target_published:
            try:
                target.unlink()
            except OSError:
                pass
        return MigrationResult(
            migrated=False,
            skipped=False,
            error=str(exc),
            error_code=_ADOPTION_FAILED,
        )
    return MigrationResult(
        migrated=True,
        skipped=False,
        copied_paths=(target,),
        error=cleanup_error,
        source_kind=source_kind,
        archive_dir=archive_dir,
        replaced_target=target_replaced,
    )
