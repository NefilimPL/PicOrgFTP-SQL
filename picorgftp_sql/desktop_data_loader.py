"""Load desktop product data outside the Tk event thread."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable

from .excel_utils import ENTRY_RECORDS_KEY, prepare_excel_lists


@dataclass(frozen=True)
class DesktopDataSnapshot:
    """Complete product data published to the desktop UI."""

    lists: dict
    entries: tuple


def load_desktop_data() -> DesktopDataSnapshot:
    """Build a complete desktop snapshot without accessing Tk state."""

    lists = prepare_excel_lists()
    if not isinstance(lists, dict):
        lists = {}
    records = lists.get(ENTRY_RECORDS_KEY, [])
    if not isinstance(records, list):
        records = []
    return DesktopDataSnapshot(
        lists=lists,
        entries=tuple(record for record in records if isinstance(record, dict)),
    )


class DesktopDataLoader:
    """Run one desktop data load and publish its result through a scheduler."""

    def __init__(self, *, load: Callable, schedule: Callable) -> None:
        self._load = load
        self._schedule = schedule
        self._thread = None
        self._lock = threading.Lock()
        self._running = False

    def start(self, on_success: Callable, on_error: Callable) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True

        def worker() -> None:
            try:
                snapshot = self._load()
            except Exception as error:
                callback = lambda error=error: on_error(error)
            else:
                callback = lambda snapshot=snapshot: on_success(snapshot)
            finally:
                with self._lock:
                    self._running = False
            self._schedule(callback)

        thread = threading.Thread(
            target=worker,
            name="DesktopDataLoader",
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return True

    def join_for_test(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
