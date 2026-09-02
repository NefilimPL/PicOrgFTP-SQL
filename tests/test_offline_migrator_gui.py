"""Thread-boundary tests for the standalone migrator GUI."""

from __future__ import annotations

from pathlib import Path

from picsyncra.offline_legacy_sqlite_migrator import (
    MigrationPaths,
    MigrationProgress,
    OfflineMigrationReport,
)
from picsyncra.offline_migrator_gui import (
    OfflineMigratorController,
    migration_confirmation_message,
)


class RecordingScheduler:
    def __init__(self) -> None:
        self.callbacks = []

    def after(self, _delay: int, callback) -> None:
        self.callbacks.append(callback)


def test_controller_schedules_progress_without_updating_tk_from_worker_thread() -> None:
    scheduler = RecordingScheduler()
    events = []
    controller = OfflineMigratorController(scheduler.after, events.append, lambda _text: None)

    controller.receive_progress(MigrationProgress("copy", 10, 100, "Kopia SQLite"))

    assert len(scheduler.callbacks) == 1
    assert events == []
    scheduler.callbacks[0]()
    assert events[0].message == "Kopia SQLite"


def test_confirmation_explains_legacy_sqlite_archiving() -> None:
    paths = MigrationPaths(
        app_root=Path("application"),
        settings_path=Path("application/local_settings.json"),
        source=Path("legacy/picorgftp_sql.sqlite"),
        target=Path("legacy/picsyncra.sqlite"),
    )

    message = migration_confirmation_message(paths)

    assert str(paths.source) in message
    assert str(paths.target) in message
    assert "zostaną przeniesione" in message
    assert str(paths.app_root / "BACKUP" / "legacy-import") in message


def test_controller_success_report_includes_archive_without_account_hashes() -> None:
    scheduler = RecordingScheduler()
    status = []
    controller = OfflineMigratorController(scheduler.after, lambda _event: None, status.append)
    archive_dir = Path("BACKUP/legacy-import/20260902-run")

    controller.receive_success(
        OfflineMigrationReport(
            Path("source.sqlite"),
            Path("picsyncra.sqlite"),
            {"web_users": 1},
            2,
            1,
            archive_dir=archive_dir,
            archive_warning="Plik picorgftp_sql.sqlite-wal oczekuje na przeniesienie.",
        )
    )

    scheduler.callbacks[0]()
    assert "picsyncra.sqlite" in status[0]
    assert str(archive_dir) in status[0]
    assert "oczekuje na przeniesienie" in status[0]
    assert "hash" not in status[0].lower()
