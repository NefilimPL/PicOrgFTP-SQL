"""Thread-safe delivery control for desktop FTP preview requests."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class DesktopFtpPreviewController:
    """Publish FTP preview work only while its request remains current."""

    def __init__(
        self,
        *,
        downloader: Callable[[int, str, threading.Event, Callable[[Any], None]], None],
        temp_manager: Any,
        schedule: Callable[[Callable[[], None]], Any],
    ) -> None:
        self._downloader = downloader
        self._temp_manager = temp_manager
        self._schedule = schedule
        self._lock = threading.Lock()
        self._request_id = 0
        self._cancel_event: threading.Event | None = None
        self._closed = False

    def request(
        self,
        ean: str,
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
        on_discard: Callable[[Any], None] | None = None,
    ) -> int:
        """Start one request and make every older request stale."""

        with self._lock:
            if self._closed:
                raise RuntimeError("desktop FTP preview controller is closed")
            if self._cancel_event is not None:
                self._cancel_event.set()
            self._request_id += 1
            request_id = self._request_id
            cancel_event = threading.Event()
            self._cancel_event = cancel_event

        def complete(result: Any) -> None:
            def deliver() -> None:
                with self._lock:
                    is_closed = self._closed
                    is_current = (
                        not is_closed
                        and self._request_id == request_id
                        and self._cancel_event is cancel_event
                        and not cancel_event.is_set()
                    )
                if is_current:
                    on_success(result)
                elif not is_closed and on_discard is not None:
                    on_discard(result)

            self._schedule(deliver)

        try:
            self._downloader(request_id, ean, cancel_event, complete)
        except Exception as exc:
            def deliver_error() -> None:
                with self._lock:
                    is_current = (
                        not self._closed
                        and self._request_id == request_id
                        and self._cancel_event is cancel_event
                        and not cancel_event.is_set()
                    )
                if is_current:
                    on_error(exc)

            self._schedule(deliver_error)
        return request_id

    def cancel_current(self) -> None:
        """Cancel the outstanding request and invalidate scheduled delivery."""

        with self._lock:
            if self._cancel_event is not None:
                self._cancel_event.set()
            self._request_id += 1
            self._cancel_event = None

    def close(self) -> None:
        """Cancel outstanding work and release manager-owned preview files once."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._cancel_event is not None:
                self._cancel_event.set()
            self._request_id += 1
            self._cancel_event = None
        self._temp_manager.close()
