"""One-time adoption of PicSyncra data from the working product name."""

from __future__ import annotations

from dataclasses import dataclass
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from .brand import SQLITE_FILENAME


_LEGACY_SQLITE_FILENAME = "picorgftp_sql.sqlite"
_SQLITE_SIDECARS = ("-wal", "-shm")


@dataclass(frozen=True)
class MigrationResult:
    migrated: bool
    skipped: bool
    copied_paths: tuple[Path, ...] = ()
    error: str | None = None


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
