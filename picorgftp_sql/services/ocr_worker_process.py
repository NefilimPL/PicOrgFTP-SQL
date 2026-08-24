"""A single-job, spawned OCR worker with a serializable message protocol."""

from __future__ import annotations

from collections.abc import Iterable
import multiprocessing
from queue import Empty
import os
from typing import Any

from .ocr_resource_policy import OcrResourcePolicy, ResourceTelemetry
from .windows_job_limits import WindowsJobLimits


def _worker_main(commands: Any, events: Any, cpu_percent: int, telemetry: Any) -> None:
    """Run inside the child process; keep model imports out of the web process."""

    limits = WindowsJobLimits()
    capability = limits.apply_to_process(pid=os.getpid(), cpu_percent=cpu_percent)
    events.put(
        {
            "kind": "ready",
            "pid": os.getpid(),
            "cpu_limit": capability.cpu_percent,
            "cpu_limit_available": capability.available,
            "cpu_limit_message": capability.message,
        }
    )
    try:
        while True:
            command = commands.get()
            if not isinstance(command, dict):
                continue
            if command.get("kind") == "stop":
                return
            if command.get("kind") == "update_limits":
                try:
                    cpu_percent = int(command.get("cpu_percent", cpu_percent))
                except (TypeError, ValueError):
                    pass
                capability = limits.apply_to_process(pid=os.getpid(), cpu_percent=cpu_percent)
                events.put(
                    {
                        "kind": "limits_updated",
                        "cpu_limit": capability.cpu_percent,
                        "cpu_limit_available": capability.available,
                        "cpu_limit_message": capability.message,
                    }
                )
                continue
            if command.get("kind") != "job":
                continue
            run_id = str(command.get("run_id") or "")
            events.put(
                {
                    "kind": "stage_started",
                    "run_id": run_id,
                    "stage": "full_image",
                }
            )
            try:
                from .image_dimensions import (
                    ImageDimensionUnavailable,
                    ImageOcrDiagnostics,
                    diagnostics_for_boxes,
                )
                from .ocr_pipeline import run_ocr_pipeline

                try:
                    boxes = run_ocr_pipeline(
                        str(command.get("path") or ""),
                        profile_ids=command.get("profile_ids") or [],
                        before_stage=lambda _stage: OcrResourcePolicy(
                            command.get("resource_settings")
                            if isinstance(command.get("resource_settings"), dict)
                            else {}
                        ).before_stage(
                            ResourceTelemetry(
                                cpu_percent=float(telemetry[0]),
                                memory_used_bytes=int(telemetry[1]),
                                memory_total_bytes=int(telemetry[2]),
                                disk_busy_percent=float(telemetry[3]),
                            )
                        ),
                        on_event=lambda kind, **payload: events.put(
                            {"kind": kind, "run_id": run_id, **payload}
                        ),
                    )
                    diagnostics = diagnostics_for_boxes(boxes)
                except ImageDimensionUnavailable as exc:
                    diagnostics = ImageOcrDiagnostics(
                        available=False,
                        dimensions={},
                        candidates=[],
                        message=str(exc) or "Local OCR is unavailable.",
                    )
                except Exception as exc:
                    diagnostics = ImageOcrDiagnostics(
                        available=False,
                        dimensions={},
                        candidates=[],
                        message=f"Local OCR failed: {exc}",
                    )
                payload = {
                    "available": diagnostics.available,
                    "dimensions": diagnostics.dimensions,
                    "message": diagnostics.message,
                    "candidates": [
                        {
                            "text": candidate.text,
                            "confidence": candidate.confidence,
                            "bbox": list(candidate.bbox),
                            "dimension": candidate.dimension,
                            "value": candidate.value,
                            "accepted": candidate.accepted,
                            "reason": candidate.reason,
                            "selected": candidate.selected,
                        }
                        for candidate in diagnostics.candidates
                    ],
                }
                events.put(
                    {
                        "kind": "result",
                        "run_id": run_id,
                        "diagnostics": payload,
                    }
                )
            except Exception as exc:
                events.put({"kind": "error", "run_id": run_id, "message": str(exc)})
    finally:
        limits.close()


class OcrWorkerProcess:
    """Parent-side lifecycle wrapper around the dedicated local OCR process."""

    def __init__(self, *, cpu_percent: int, context: multiprocessing.context.BaseContext | None = None) -> None:
        self._cpu_percent = int(cpu_percent)
        self._context = context or multiprocessing.get_context("spawn")
        self._commands: Any | None = None
        self._events: Any | None = None
        self._telemetry = self._context.Array("d", [0.0, 0.0, 0.0, 0.0])
        self._process: Any | None = None

    @property
    def pid(self) -> int | None:
        return int(self._process.pid) if self._process and self._process.pid else None

    def start(self) -> None:
        if self._process is not None and self._process.is_alive():
            return
        self._commands = self._context.Queue()
        self._events = self._context.Queue()
        self._process = self._context.Process(
            target=_worker_main,
            args=(self._commands, self._events, self._cpu_percent, self._telemetry),
            name="PicOrg-OCR",
            daemon=True,
        )
        self._process.start()

    def update_limits(self, *, cpu_percent: int) -> None:
        self._cpu_percent = int(cpu_percent)
        self._require_commands().put({"kind": "update_limits", "cpu_percent": self._cpu_percent})

    def submit(
        self,
        *,
        run_id: str,
        path: str,
        profile_ids: Iterable[object],
        resource_settings: dict[str, object] | None = None,
    ) -> None:
        """Queue one OCR command using only process-safe primitive values."""

        self._require_commands().put(
            {
                "kind": "job",
                "run_id": str(run_id),
                "path": str(path),
                "profile_ids": [str(profile_id) for profile_id in profile_ids],
                "resource_settings": dict(resource_settings or {}),
            }
        )

    def update_telemetry(self, telemetry: ResourceTelemetry) -> None:
        """Share latest host usage for checks at the worker's next safe boundary."""

        self._telemetry[0] = float(telemetry.cpu_percent)
        self._telemetry[1] = float(telemetry.memory_used_bytes)
        self._telemetry[2] = float(telemetry.memory_total_bytes)
        self._telemetry[3] = float(telemetry.disk_busy_percent)

    def cancel(self, run_id: str) -> None:
        """Request cancellation; the worker observes it at a later safe boundary."""

        self._require_commands().put({"kind": "cancel", "run_id": str(run_id)})

    def poll_events(self) -> list[dict[str, object]]:
        events: list[dict[str, object]] = []
        queue = self._events
        if queue is None:
            return events
        while True:
            try:
                event = queue.get_nowait()
            except Empty:
                return events
            if isinstance(event, dict):
                events.append({str(key): value for key, value in event.items()})

    def stop(self, *, timeout: float) -> None:
        process = self._process
        if process is None:
            return
        if process.is_alive():
            try:
                self._require_commands().put({"kind": "stop"})
            except Exception:
                pass
            process.join(max(0.0, float(timeout)))
        if process.is_alive():
            process.terminate()
            process.join(max(0.0, float(timeout)))
        self._process = None
        self._commands = None
        self._events = None

    def _require_commands(self) -> Any:
        if self._commands is None:
            raise RuntimeError("OCR worker has not been started.")
        return self._commands
