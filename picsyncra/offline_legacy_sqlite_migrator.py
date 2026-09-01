"""Safe, offline migration of one explicitly configured pre-rebrand SQLite DB."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3
import json
import shutil
import tempfile
from collections.abc import Callable

from . import storage_settings
from .sqlite_store import SqliteStore


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


@dataclass(frozen=True)
class MigrationProgress:
    """One safe-to-display status update from the offline migration."""

    stage: str
    current: int | None
    total: int | None
    message: str


@dataclass(frozen=True)
class OfflineMigrationReport:
    """Validated outcome summary without credentials or account hashes."""

    source: Path
    target: Path
    table_counts: dict[str, int]
    product_count: int
    user_count: int


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


def _source_connection(source: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)


def _application_table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Count preserved application tables, excluding generated schema structures."""

    excluded = {"schema_version", "operational_events", "operational_event_stream"}
    names = [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    counts: dict[str, int] = {}
    for name in names:
        if name in excluded or name.startswith(("product_entries_fts", "product_entries_short_fts")):
            continue
        quoted_name = name.replace('"', '""')
        counts[name] = int(connection.execute(f'SELECT COUNT(*) FROM "{quoted_name}"').fetchone()[0])
    return counts


def _product_ids(connection: sqlite3.Connection) -> tuple[str, ...]:
    try:
        rows = connection.execute(
            "SELECT product_id FROM product_entries ORDER BY product_id"
        ).fetchall()
    except sqlite3.Error:
        return ()
    return tuple(str(row[0]) for row in rows)


def _web_users(connection: sqlite3.Connection) -> dict[str, tuple[str, bool, str]]:
    try:
        rows = connection.execute(
            "SELECT username, payload_json FROM web_users ORDER BY username"
        ).fetchall()
    except sqlite3.Error:
        return {}
    users = {}
    for username, payload_json in rows:
        try:
            payload = json.loads(str(payload_json))
        except (TypeError, ValueError):
            payload = {}
        users[str(username)] = (
            str(payload.get("role") or ""),
            bool(payload.get("enabled", False)),
            str(payload.get("password_hash") or ""),
        )
    return users


def _validate_short_search_triggers(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'trigger' "
        "AND name LIKE 'trg_product_entries_short_fts_%'"
    ).fetchall()
    statements = [str(row[0] or "") for row in rows]
    if len(statements) != 3 or any("picorg_product_short_grams" in sql for sql in statements):
        raise OfflineMigrationError(
            "staging_trigger_validation",
            "Migracja roboczej kopii nie odtworzyła poprawnych triggerów wyszukiwania.",
        )
    if any("picsyncra_product_short_grams" not in sql for sql in statements):
        raise OfflineMigrationError(
            "staging_trigger_validation",
            "Migracja roboczej kopii nie odtworzyła poprawnych triggerów wyszukiwania.",
        )


def _validate_staging_copy(
    staging: Path,
    source_counts: dict[str, int],
    source_product_ids: tuple[str, ...],
    source_users: dict[str, tuple[str, bool, str]],
) -> OfflineMigrationReport:
    with sqlite3.connect(staging) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchall()
        if not integrity or any(str(row[0]).lower() != "ok" for row in integrity):
            raise OfflineMigrationError(
                "staging_integrity",
                "Kontrola integralności roboczej kopii SQLite nie powiodła się.",
            )
        staging_counts = _application_table_counts(connection)
        for name, source_count in source_counts.items():
            if staging_counts.get(name) != source_count:
                raise OfflineMigrationError(
                    "staging_table_validation",
                    "Walidacja liczby rekordów roboczej kopii SQLite nie powiodła się.",
                )
        if _product_ids(connection) != source_product_ids:
            raise OfflineMigrationError(
                "staging_product_validation",
                "Walidacja produktów roboczej kopii SQLite nie powiodła się.",
            )
        if _web_users(connection) != source_users:
            raise OfflineMigrationError(
                "staging_user_validation",
                "Walidacja kont roboczej kopii SQLite nie powiodła się.",
            )
        _validate_short_search_triggers(connection)
    return OfflineMigrationReport(
        source=Path(),
        target=Path(),
        table_counts=source_counts,
        product_count=len(source_product_ids),
        user_count=len(source_users),
    )


def build_validated_legacy_sqlite_copy(
    paths: MigrationPaths,
    progress: Callable[[MigrationProgress], None],
) -> tuple[Path, OfflineMigrationReport]:
    """Copy, upgrade and verify source SQLite without opening it for writes."""

    progress(MigrationProgress("copy", 0, None, "Tworzenie roboczej kopii SQLite…"))
    work_dir = Path(
        tempfile.mkdtemp(prefix=".picsyncra-migrator-", dir=paths.target.parent)
    )
    staging = work_dir / TARGET_SQLITE_FILENAME
    try:
        with _source_connection(paths.source) as source_connection:
            source_counts = _application_table_counts(source_connection)
            source_product_ids = _product_ids(source_connection)
            source_users = _web_users(source_connection)
            with sqlite3.connect(staging) as staging_connection:
                def report_backup(status: int, remaining: int, total: int) -> None:
                    progress(
                        MigrationProgress(
                            "copy",
                            max(0, total - remaining),
                            total,
                            "Kopiowanie źródłowej SQLite…",
                        )
                    )

                source_connection.backup(staging_connection, pages=256, progress=report_backup)

        progress(MigrationProgress("schema", 0, None, "Aktualizacja schematu roboczej kopii…"))
        SqliteStore(str(staging)).initialize()
        progress(MigrationProgress("validation", 0, None, "Walidacja roboczej kopii SQLite…"))
        report = _validate_staging_copy(
            staging,
            source_counts,
            source_product_ids,
            source_users,
        )
        progress(MigrationProgress("validation", 1, 1, "Walidacja roboczej kopii zakończona."))
        return staging, OfflineMigrationReport(
            source=paths.source,
            target=paths.target,
            table_counts=report.table_counts,
            product_count=report.product_count,
            user_count=report.user_count,
        )
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
