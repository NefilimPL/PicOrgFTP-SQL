"""Cooperative idle-time scheduler for persisted OCR crop jobs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class OcrQueueScheduler:
    """Process at most one crop while user activity and CPU allow it."""

    def __init__(
        self,
        *,
        settings: Callable[[], dict[str, object]],
        has_active_requests: Callable[[], bool],
        last_activity: Callable[[], float],
        cpu_percent: Callable[[], float],
        claim_job: Callable[[], dict[str, object] | None],
        process_job: Callable[[dict[str, object]], Any],
        now: Callable[[], float],
    ) -> None:
        self._settings = settings
        self._has_active_requests = has_active_requests
        self._last_activity = last_activity
        self._cpu_percent = cpu_percent
        self._claim_job = claim_job
        self._process_job = process_job
        self._now = now

    def run_once(self) -> str:
        settings = self._settings()
        if not bool(settings.get("background_enabled")):
            return "disabled"
        if self._has_active_requests():
            return "busy"
        if self._now() - self._last_activity() < float(settings.get("idle_seconds", 0)):
            return "idle_wait"
        if self._cpu_percent() >= float(settings.get("pause_cpu_percent", 100)):
            return "cpu_pause"
        job = self._claim_job()
        if job is None:
            return "empty"
        self._process_job(job)
        return "processed"
