"""Thread-boundary tests for the standalone migrator GUI."""

from __future__ import annotations

from pathlib import Path

from picsyncra.offline_legacy_sqlite_migrator import (
    MigrationProgress,
    OfflineMigrationReport,
)
from picsyncra.offline_migrator_gui import OfflineMigratorController


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


def test_controller_success_report_does_not_include_account_hashes() -> None:
    scheduler = RecordingScheduler()
    status = []
    controller = OfflineMigratorController(scheduler.after, lambda _event: None, status.append)

    controller.receive_success(
        OfflineMigrationReport(Path("source.sqlite"), Path("picsyncra.sqlite"), {"web_users": 1}, 2, 1)
    )

    scheduler.callbacks[0]()
    assert "picsyncra.sqlite" in status[0]
    assert "hash" not in status[0].lower()
