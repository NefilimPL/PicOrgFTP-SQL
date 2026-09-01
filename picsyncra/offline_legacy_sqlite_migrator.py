"""Safe, offline migration of one explicitly configured pre-rebrand SQLite DB."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3

from . import storage_settings


LEGACY_SQLITE_FILENAME = "picorgftp_sql.sqlite"
TARGET_SQLITE_FILENAME = "picsyncra.sqlite"


class OfflineMigrationError(RuntimeError):
    """A user-actionable migration failure which leaves source data untouched."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MigrationPaths:
    """Explicit paths approved for one offline SQLite migration."""

    app_root: Path
    settings_path: Path
    source: Path
    target: Path


def _configured_legacy_source(settings_path: Path, payload: dict[str, object]) -> Path:
    """Prefer the explicit old DB path retained in pre-rebrand configurations."""

    configured = str(payload.get(storage_settings.DATABASE_PATH_KEY) or "").strip()
    if configured:
        expanded = os.path.expandvars(os.path.expanduser(configured.strip("\"'")))
        candidate = Path(expanded)
        if not candidate.is_absolute():
            candidate = settings_path.parent / candidate
        candidate = candidate.resolve()
        if candidate.name == LEGACY_SQLITE_FILENAME:
            return candidate
    return Path(
        storage_settings.resolve_sqlite_path_for_settings_file(settings_path, payload)
    ).resolve()


def _check_sqlite_integrity(source: Path) -> None:
    try:
        with sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True) as connection:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error as error:
        raise OfflineMigrationError(
            "source_unreadable",
            "Nie można odczytać wskazanej źródłowej bazy SQLite. Zamknij główną aplikację i spróbuj ponownie.",
        ) from error
    if not rows or any(str(row[0]).lower() != "ok" for row in rows):
        raise OfflineMigrationError(
            "source_integrity",
            "Kontrola integralności wskazanej źródłowej bazy SQLite nie powiodła się.",
        )


def resolve_offline_migration_paths(app_root: Path) -> MigrationPaths:
    """Resolve and validate the one legacy database selected by app settings."""

    resolved_app_root = Path(app_root).resolve()
    settings_path = resolved_app_root / "local_settings.json"
    if not settings_path.is_file():
        raise OfflineMigrationError(
            "settings_missing",
            "W wybranym katalogu aplikacji nie znaleziono pliku local_settings.json.",
        )

    payload = storage_settings.load_bootstrap_settings_file(settings_path)
    source = _configured_legacy_source(settings_path, payload)
    if source.name != LEGACY_SQLITE_FILENAME:
        raise OfflineMigrationError(
            "source_name",
            "Konfiguracja nie wskazuje pliku picorgftp_sql.sqlite sprzed rebrandingu.",
        )
    if not source.is_file():
        raise OfflineMigrationError(
            "source_missing",
            "Skonfigurowany plik picorgftp_sql.sqlite nie istnieje.",
        )

    target = source.with_name(TARGET_SQLITE_FILENAME)
    if target.exists():
        raise OfflineMigrationError(
            "target_exists",
            "Plik picsyncra.sqlite już istnieje. Migrator nie nadpisuje istniejącej bazy.",
        )

    _check_sqlite_integrity(source)
    return MigrationPaths(
        app_root=resolved_app_root,
        settings_path=settings_path.resolve(),
        source=source,
        target=target,
    )
