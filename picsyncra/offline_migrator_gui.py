"""Tkinter front end for the standalone pre-rebrand SQLite migrator."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import sys
import threading

from .offline_legacy_sqlite_migrator import (
    MigrationPaths,
    MigrationProgress,
    OfflineMigrationError,
    OfflineMigrationReport,
    resolve_offline_migration_paths,
    run_offline_legacy_migration,
)


def migration_confirmation_message(paths: MigrationPaths) -> str:
    """Describe the target and the post-activation legacy archive handover."""

    archive_root = paths.app_root / "BACKUP" / "legacy-import"
    return (
        f"Źródło:\n{paths.source}\n\n"
        f"Nowy plik docelowy:\n{paths.target}\n\n"
        "Po poprawnej aktywacji plik źródłowy SQLite i obecne pliki -wal/-shm "
        f"zostaną przeniesione do:\n{archive_root}\n\n"
        "Kontynuować?"
    )


class OfflineMigratorController:
    """Marshal worker notifications through Tk's scheduler."""

    def __init__(
        self,
        after: Callable[[int, Callable[[], None]], object],
        on_progress: Callable[[MigrationProgress], None],
        on_status: Callable[[str], None],
    ) -> None:
        self._after = after
        self._on_progress = on_progress
        self._on_status = on_status

    def receive_progress(self, event: MigrationProgress) -> None:
        self._after(0, lambda: self._on_progress(event))

    def receive_success(self, report: OfflineMigrationReport) -> None:
        archive_status = (
            f" Archiwum plików legacy: {report.archive_dir}."
            if report.archive_dir is not None
            else ""
        )
        warning_status = (
            f" Ostrzeżenie: {report.archive_warning}"
            if report.archive_warning
            else ""
        )
        self._after(
            0,
            lambda: self._on_status(
                f"Migracja zakończona. Nowa baza: {report.target}; "
                f"produkty: {report.product_count}, konta: {report.user_count}."
                f"{archive_status}{warning_status}"
            ),
        )

    def receive_failure(self, error: Exception) -> None:
        self._after(0, lambda: self._on_status(str(error)))


class OfflineMigratorWindow:
    """Small confirmation-first GUI for one explicitly selected app folder."""

    def __init__(self, root) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.root = root
        root.title("PicSyncra — migrator SQLite")
        root.minsize(700, 310)
        self.tk = tk
        self.ttk = ttk
        default_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
        self.app_root = tk.StringVar(value=str(default_root))
        self.status = tk.StringVar(value="Wskaż katalog głównej aplikacji i rozpocznij weryfikację.")
        self.source = tk.StringVar(value="Źródło: —")
        self.target = tk.StringVar(value="Cel: —")
        self.progress = tk.IntVar(value=0)
        self.controller = OfflineMigratorController(root.after, self._apply_progress, self.status.set)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Katalog głównej aplikacji:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.app_root, width=76).grid(row=1, column=0, sticky="ew", pady=(2, 8))
        ttk.Button(frame, text="Wybierz…", command=self._browse).grid(row=1, column=1, padx=(8, 0))
        ttk.Label(frame, textvariable=self.source, wraplength=650).grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(frame, textvariable=self.target, wraplength=650).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        self.start_button = ttk.Button(frame, text="Rozpocznij migrację", command=self._confirm_and_start)
        self.start_button.grid(row=4, column=0, sticky="w", pady=(12, 6))
        ttk.Progressbar(frame, maximum=100, variable=self.progress).grid(row=5, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Label(frame, textvariable=self.status, wraplength=650).grid(row=6, column=0, columnspan=2, sticky="w", pady=4)
        frame.columnconfigure(0, weight=1)

    def _browse(self) -> None:
        from tkinter import filedialog

        chosen = filedialog.askdirectory(initialdir=self.app_root.get() or str(Path.cwd()))
        if chosen:
            self.app_root.set(chosen)

    def _confirm_and_start(self) -> None:
        from tkinter import messagebox

        try:
            paths = resolve_offline_migration_paths(Path(self.app_root.get()))
        except OfflineMigrationError as error:
            messagebox.showerror("Migrator SQLite", str(error), parent=self.root)
            return
        self.source.set(f"Źródło: {paths.source}")
        self.target.set(f"Cel: {paths.target}")
        if not messagebox.askyesno(
            "Potwierdź migrację",
            migration_confirmation_message(paths),
            parent=self.root,
        ):
            return
        self.start_button.state(["disabled"])
        threading.Thread(target=self._worker, args=(paths.app_root,), daemon=True).start()

    def _worker(self, app_root: Path) -> None:
        try:
            report = run_offline_legacy_migration(app_root, self.controller.receive_progress)
        except Exception as error:
            self.controller.receive_failure(error)
        else:
            self.controller.receive_success(report)
        finally:
            self.root.after(0, lambda: self.start_button.state(["!disabled"]))

    def _apply_progress(self, event: MigrationProgress) -> None:
        self.status.set(event.message)
        if event.current is not None and event.total:
            self.progress.set(round(event.current * 100 / event.total))


def main() -> None:
    import tkinter as tk

    root = tk.Tk()
    OfflineMigratorWindow(root)
    root.mainloop()
