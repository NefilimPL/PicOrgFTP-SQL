from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import threading
import time

import pytest

from picorgftp_sql.resource_monitor import ResourceMonitor


MIB = 1024 * 1024
SETTINGS = {
    "cpu_percent_threshold": 25,
    "memory_percent_threshold": 20,
    "io_mib_per_second_threshold": 8,
}
CONTEXT = {"active_jobs": 0, "queued_jobs": 0, "active_clients": 0}


class _ReaderSequence:
    def __init__(
        self,
        *,
        cpu: list[float],
        memory: list[float] | None = None,
        io: list[float] | None = None,
        host: dict[str, object] | None = None,
    ) -> None:
        count = len(cpu)
        self._cpu = iter(cpu)
        self._memory = iter(memory if memory is not None else [2.0] * count)
        self._io = iter(io if io is not None else [0.0] * count)
        self._host = host or {
            "cpu_percent": 95.0,
            "memory_percent": 95.0,
            "memory_used_bytes": 950,
            "memory_total_bytes": 1000,
            "disk_busy_percent": 95.0,
        }

    def read_host(self) -> dict[str, object]:
        return dict(self._host)

    def read_backend(self, _worker_pid: int | None = None) -> dict[str, object]:
        return {
            "cpu_percent": next(self._cpu),
            "memory_percent": next(self._memory),
            "memory_working_set_bytes": 20,
            "memory_private_bytes": 10,
            "disk_read_bytes_per_second": 0.0,
            "disk_write_bytes_per_second": next(self._io),
            "disk_io_bytes_per_second": 0.0,
        }


class _IoReaderSequence(_ReaderSequence):
    def read_backend(self, _worker_pid: int | None = None) -> dict[str, object]:
        sample = super().read_backend(_worker_pid)
        sample["disk_io_bytes_per_second"] = sample["disk_write_bytes_per_second"]
        return sample


def _monitor(
    readers: object,
    events: list[tuple[str, str, dict[str, object]]],
    *,
    settings: dict[str, object] | None = None,
) -> ResourceMonitor:
    return ResourceMonitor(
        settings_provider=lambda: dict(settings or SETTINGS),
        context_provider=lambda: dict(CONTEXT),
        event_emitter=lambda severity, event_type, details: events.append(
            (severity, event_type, details)
        ),
        wall_clock=lambda: 1_700_000_000.0,
        readers=readers,
    )


def test_monitor_emits_one_alert_after_two_backend_cpu_breaches() -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    monitor = _monitor(
        _ReaderSequence(cpu=[24, 28, 31, 5, 6]),
        events,
    )

    monitor.sample_once()
    monitor.sample_once()
    assert events == []
    monitor.sample_once()

    assert events[0][0:2] == ("warning", "backend.resource_high")
    assert events[0][2]["trigger"]["metric"] == "cpu_percent"
    assert json.loads(json.dumps(events[0][2])) == events[0][2]


def test_monitor_preserves_explicit_unavailable_host_disk_metric() -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    monitor = _monitor(
        _ReaderSequence(
            cpu=[1],
            host={
                "cpu_percent": 1.0,
                "memory_percent": 2.0,
                "memory_used_bytes": 20,
                "memory_total_bytes": 1000,
                "disk_busy_percent": {"available": False},
            },
        ),
        events,
    )

    snapshot = monitor.sample_once()

    assert snapshot["host"]["disk_busy_percent"] == {"available": False}
    assert events == []


def test_host_only_load_never_triggers_backend_event() -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    monitor = _monitor(_ReaderSequence(cpu=[1, 2, 3]), events)

    for _ in range(3):
        monitor.sample_once()

    assert events == []


@pytest.mark.parametrize(
    ("readers", "metric"),
    [
        (_ReaderSequence(cpu=[1, 1], memory=[21, 22]), "memory_percent"),
        (_IoReaderSequence(cpu=[1, 1], io=[9 * MIB, 10 * MIB]), "disk_io_bytes_per_second"),
    ],
)
def test_memory_and_io_thresholds_trigger_independently(
    readers: object, metric: str
) -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    monitor = _monitor(readers, events)

    monitor.sample_once()
    monitor.sample_once()

    assert len(events) == 1
    assert events[0][2]["trigger"]["metric"] == metric


def test_simultaneous_metric_confirmations_emit_one_event_per_metric() -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    monitor = _monitor(
        _ReaderSequence(cpu=[30, 31], memory=[21, 22]),
        events,
    )

    monitor.sample_once()
    monitor.sample_once()

    assert {event[2]["trigger"]["metric"] for event in events} == {
        "cpu_percent",
        "memory_percent",
    }


def test_latch_resets_only_after_two_consecutive_normal_samples() -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    monitor = _monitor(
        _ReaderSequence(cpu=[30, 31, 5, 30, 31, 5, 6, 30, 31]),
        events,
    )

    for _ in range(5):
        monitor.sample_once()
    assert len(events) == 1
    assert monitor.latest_public_snapshot()["detector"]["latched_metrics"] == [
        "cpu_percent"
    ]

    for _ in range(4):
        monitor.sample_once()

    assert len(events) == 2


def test_unavailable_sample_breaks_high_and_recovery_streaks() -> None:
    unavailable = {"available": False}
    events: list[tuple[str, str, dict[str, object]]] = []
    monitor = _monitor(
        _ReaderSequence(cpu=[30, unavailable, 30, 31, 5, unavailable, 5, 6]),
        events,
    )

    for _ in range(3):
        monitor.sample_once()
    assert events == []

    monitor.sample_once()
    assert len(events) == 1
    for _ in range(3):
        monitor.sample_once()
    assert monitor.latest_public_snapshot()["detector"]["latched_metrics"] == [
        "cpu_percent"
    ]

    monitor.sample_once()
    assert monitor.latest_public_snapshot()["detector"]["latched_metrics"] == []


def test_diagnostic_history_is_capped_at_twelve_samples() -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    monitor = _monitor(
        _ReaderSequence(cpu=[30, 31] + [5] * 12 + [30, 31]),
        events,
    )

    for _ in range(16):
        monitor.sample_once()

    history = events[-1][2]["history"]
    assert len(history) == ResourceMonitor.HISTORY_SIZE == 12
    assert history[-1]["backend"]["cpu_percent"] == 31


def test_safe_simulation_emits_labelled_serializable_diagnostic() -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    monitor = _monitor(_ReaderSequence(cpu=[1]), events)
    monitor.sample_once()

    result = monitor.record_safe_simulation()

    assert result["ok"] is True
    assert result["test_mode"] == "safe"
    assert events[-1][0:2] == ("info", "backend.resource_test")
    assert events[-1][2]["test_mode"] == "safe"
    json.dumps(events[-1][2])


def test_real_cpu_test_rejects_threshold_beyond_hard_cap() -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    monitor = _monitor(
        _ReaderSequence(cpu=[0, 0]),
        events,
        settings={**SETTINGS, "cpu_percent_threshold": 26},
    )
    monitor.sample_once()

    with pytest.raises(ValueError, match="hard cap"):
        monitor.start_real_test("cpu")

    assert monitor.latest_public_snapshot()["backend"]["test_worker_registered"] is False


def test_worker_timeout_removes_registration_and_private_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from picorgftp_sql import resource_monitor

    events: list[tuple[str, str, dict[str, object]]] = []
    monitor = _monitor(
        _ReaderSequence(cpu=[0]),
        events,
        settings={**SETTINGS, "cpu_percent_threshold": 20},
    )
    monitor.sample_once()
    private_dir = tmp_path / "picorg_resource_test_timeout"
    process_instances: list[FakeProcess] = []

    class FakeEvent:
        def __init__(self) -> None:
            self.was_set = False

        def set(self) -> None:
            self.was_set = True

        def is_set(self) -> bool:
            return self.was_set

    class FakeProcess:
        def __init__(self, *, target, args, daemon) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon
            self.pid: int | None = None
            self.exitcode: int | None = None
            self._alive = False
            self._join_calls = 0
            self.closed = False
            process_instances.append(self)

        def start(self) -> None:
            self.pid = 4321
            self._alive = True
            worker_dir = Path(self.args[3])
            worker_dir.mkdir(parents=True, exist_ok=True)
            (worker_dir / "left-behind.tmp").write_bytes(b"temporary")

        def join(self, timeout: float | None = None) -> None:
            assert monitor._worker_process is self
            self._join_calls += 1
            if self._join_calls == 1:
                assert monitor.sample_once()["backend"]["test_worker_registered"] is True

        def is_alive(self) -> bool:
            return self._alive

        def terminate(self) -> None:
            self._alive = False
            self.exitcode = -15

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(resource_monitor.tempfile, "mkdtemp", lambda **_kwargs: str(private_dir))
    monkeypatch.setattr(resource_monitor.multiprocessing, "Event", FakeEvent)
    monkeypatch.setattr(resource_monitor.multiprocessing, "Process", FakeProcess)
    monkeypatch.setattr(monitor, "REAL_TEST_SECONDS", 0.01)

    result = monitor.start_real_test("cpu")

    assert result == {"ok": False, "kind": "cpu", "status": "timeout", "timed_out": True}
    assert monitor._worker_pid is None
    assert monitor._worker_process is None
    assert process_instances[0].closed is True
    assert not private_dir.exists()
    assert monitor.latest_public_snapshot()["backend"]["test_worker_registered"] is False


def test_public_snapshot_never_exposes_worker_handles_or_temporary_paths() -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    monitor = _monitor(_ReaderSequence(cpu=[1]), events)

    snapshot = monitor.sample_once()

    assert set(snapshot) == {"host", "backend", "detector", "observed_at"}
    serialized = json.dumps(snapshot)
    assert "Process" not in serialized
    assert "picorg_resource_test_" not in serialized


@pytest.mark.skipif(os.name != "nt", reason="Windows native reader contract")
def test_native_reader_reports_current_backend_process_memory() -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    monitor = ResourceMonitor(
        settings_provider=lambda: dict(SETTINGS),
        context_provider=lambda: dict(CONTEXT),
        event_emitter=lambda severity, event_type, details: events.append(
            (severity, event_type, details)
        ),
    )

    snapshot = monitor.sample_once()

    assert snapshot["backend"]["memory_working_set_bytes"] > 0
    assert snapshot["backend"]["memory_private_bytes"] > 0


def test_public_and_event_payloads_drop_undeclared_provider_values() -> None:
    events: list[tuple[str, str, dict[str, object]]] = []

    class UnsafeReader(_ReaderSequence):
        def read_host(self) -> dict[str, object]:
            return {**super().read_host(), "temporary_path": Path("private.tmp")}

        def read_backend(self, worker_pid: int | None = None) -> dict[str, object]:
            return {**super().read_backend(worker_pid), "process_handle": object()}

    monitor = ResourceMonitor(
        settings_provider=lambda: dict(SETTINGS),
        context_provider=lambda: {**CONTEXT, "secret": object()},
        event_emitter=lambda severity, event_type, details: events.append(
            (severity, event_type, details)
        ),
        readers=UnsafeReader(cpu=[30, 31]),
    )

    monitor.sample_once()
    snapshot = monitor.sample_once()

    assert "temporary_path" not in snapshot["host"]
    assert "process_handle" not in snapshot["backend"]
    assert "secret" not in snapshot["backend"]
    json.dumps(snapshot)
    json.dumps(events[0][2])


def test_stop_closes_native_reader_resources() -> None:
    class ClosableReader(_ReaderSequence):
        closed = False

        def close(self) -> None:
            self.closed = True

    readers = ClosableReader(cpu=[1])
    monitor = _monitor(readers, [])

    monitor.stop()

    assert readers.closed is True


def test_stop_during_worker_launch_cannot_leave_unregistered_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from picorgftp_sql import resource_monitor

    started = threading.Event()
    allow_start = threading.Event()
    private_dir = tmp_path / "picorg_resource_test_race"
    process_instances: list[FakeProcess] = []

    class FakeEvent:
        def __init__(self) -> None:
            self.was_set = False

        def set(self) -> None:
            self.was_set = True

        def is_set(self) -> bool:
            return self.was_set

    class FakeProcess:
        def __init__(self, *, target, args, daemon) -> None:
            self.pid: int | None = None
            self.exitcode: int | None = None
            self._alive = False
            self.closed = False
            process_instances.append(self)

        def start(self) -> None:
            started.set()
            assert allow_start.wait(2.0)
            self.pid = 9876
            self._alive = True
            private_dir.mkdir(parents=True, exist_ok=True)
            (private_dir / "race.tmp").write_bytes(b"temporary")

        def join(self, timeout: float | None = None) -> None:
            return None

        def is_alive(self) -> bool:
            return self._alive

        def terminate(self) -> None:
            self._alive = False
            self.exitcode = -15

        def kill(self) -> None:
            self._alive = False
            self.exitcode = -9

        def close(self) -> None:
            self.closed = True

    monitor = _monitor(
        _ReaderSequence(cpu=[0]),
        [],
        settings={**SETTINGS, "cpu_percent_threshold": 20},
    )
    monitor.sample_once()
    monkeypatch.setattr(resource_monitor.tempfile, "mkdtemp", lambda **_kwargs: str(private_dir))
    monkeypatch.setattr(resource_monitor.multiprocessing, "Event", FakeEvent)
    monkeypatch.setattr(resource_monitor.multiprocessing, "Process", FakeProcess)
    monkeypatch.setattr(monitor, "REAL_TEST_SECONDS", 0.01)
    results: list[dict[str, object]] = []
    launch_thread = threading.Thread(target=lambda: results.append(monitor.start_real_test("cpu")))
    launch_thread.start()
    assert started.wait(1.0)
    stop_thread = threading.Thread(target=monitor.stop)
    stop_thread.start()
    allow_start.set()
    launch_thread.join(2.0)
    stop_thread.join(2.0)

    assert not launch_thread.is_alive()
    assert not stop_thread.is_alive()
    assert process_instances and not process_instances[0].is_alive()
    assert process_instances[0].closed is True
    assert monitor._worker_process is None
    assert not private_dir.exists()


def test_accepted_cpu_test_uses_supervisor_grace_and_completes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from picorgftp_sql import resource_monitor

    joins: list[float | None] = []

    class FakeEvent:
        def set(self) -> None:
            return None

        def is_set(self) -> bool:
            return False

    class FakeProcess:
        pid = 2468
        exitcode = 0

        def __init__(self, *, target, args, daemon) -> None:
            self.closed = False

        def start(self) -> None:
            return None

        def join(self, timeout: float | None = None) -> None:
            joins.append(timeout)

        def is_alive(self) -> bool:
            return False

        def close(self) -> None:
            self.closed = True

    monitor = _monitor(
        _ReaderSequence(cpu=[0]),
        [],
        settings={**SETTINGS, "cpu_percent_threshold": 20},
    )
    monitor.sample_once()
    monkeypatch.setattr(
        resource_monitor.tempfile,
        "mkdtemp",
        lambda **_kwargs: str(tmp_path / "picorg_resource_test_complete"),
    )
    monkeypatch.setattr(resource_monitor.multiprocessing, "Event", FakeEvent)
    monkeypatch.setattr(resource_monitor.multiprocessing, "Process", FakeProcess)
    monkeypatch.setattr(monitor, "REAL_TEST_SECONDS", 0.25)
    monkeypatch.setattr(monitor, "REAL_TEST_GRACE_SECONDS", 0.5)

    result = monitor.start_real_test("cpu")

    assert result == {
        "ok": True,
        "kind": "cpu",
        "status": "completed",
        "timed_out": False,
    }
    assert joins[0] == pytest.approx(0.75)


def test_real_test_constructor_failure_removes_private_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from picorgftp_sql import resource_monitor

    private_dir = tmp_path / "picorg_resource_test_constructor_failure"
    monitor = _monitor(
        _ReaderSequence(cpu=[0]),
        [],
        settings={**SETTINGS, "cpu_percent_threshold": 20},
    )
    monitor.sample_once()

    def make_directory(**_kwargs) -> str:
        private_dir.mkdir()
        return str(private_dir)

    monkeypatch.setattr(resource_monitor.tempfile, "mkdtemp", make_directory)
    monkeypatch.setattr(
        resource_monitor.multiprocessing,
        "Event",
        lambda: (_ for _ in ()).throw(OSError("event construction failed")),
    )

    result = monitor.start_real_test("cpu")

    assert result == {
        "ok": False,
        "kind": "cpu",
        "status": "launch_failed",
        "timed_out": False,
    }
    assert monitor._worker_process is None
    assert not private_dir.exists()


def test_cpu_worker_uses_parallel_gil_releasing_hash_rounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from picorgftp_sql import resource_monitor

    calls = 0

    class StopAfterHash:
        def is_set(self) -> bool:
            return calls > 0

    class HashResult:
        def digest(self) -> bytes:
            return b"digest"

    def fake_sha256(payload: bytes) -> HashResult:
        nonlocal calls
        assert len(payload) > 2047
        calls += 1
        return HashResult()

    monkeypatch.setattr(resource_monitor.hashlib, "sha256", fake_sha256)

    resource_monitor._run_cpu_test(StopAfterHash(), time.monotonic() + 1.0, 8)

    assert calls >= 1


def test_cleanup_uses_kill_fallback_before_deregistering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from picorgftp_sql import resource_monitor

    private_dir = tmp_path / "picorg_resource_test_kill"
    process_instances: list[FakeProcess] = []

    class FakeEvent:
        def set(self) -> None:
            return None

        def is_set(self) -> bool:
            return False

    class FakeProcess:
        pid = 1357
        exitcode = None

        def __init__(self, *, target, args, daemon) -> None:
            self.alive = False
            self.killed = False
            self.closed = False
            process_instances.append(self)

        def start(self) -> None:
            self.alive = True
            private_dir.mkdir(parents=True, exist_ok=True)

        def join(self, timeout: float | None = None) -> None:
            assert monitor._worker_process is self

        def is_alive(self) -> bool:
            return self.alive

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            self.killed = True
            self.alive = False
            self.exitcode = -9

        def close(self) -> None:
            self.closed = True

    monitor = _monitor(
        _ReaderSequence(cpu=[0]),
        [],
        settings={**SETTINGS, "cpu_percent_threshold": 20},
    )
    monitor.sample_once()
    monkeypatch.setattr(resource_monitor.tempfile, "mkdtemp", lambda **_kwargs: str(private_dir))
    monkeypatch.setattr(resource_monitor.multiprocessing, "Event", FakeEvent)
    monkeypatch.setattr(resource_monitor.multiprocessing, "Process", FakeProcess)
    monkeypatch.setattr(monitor, "REAL_TEST_SECONDS", 0.01)

    result = monitor.start_real_test("cpu")

    assert result["status"] == "timeout"
    assert process_instances[0].killed is True
    assert process_instances[0].closed is True
    assert monitor._worker_process is None
    assert not private_dir.exists()


def test_pdh_invalid_status_is_unavailable_and_query_is_closed() -> None:
    from picorgftp_sql import resource_monitor

    reader = resource_monitor._WindowsResourceReaders()
    close_calls = 0

    class FakePdh:
        def PdhCollectQueryData(self, _query) -> int:
            return 0

        def PdhGetFormattedCounterValue(self, _counter, _format, _kind, value) -> int:
            formatted = ctypes.cast(
                value, ctypes.POINTER(resource_monitor._PDH_FMT_COUNTERVALUE)
            ).contents
            formatted.CStatus = 0xC0000BC6
            formatted.doubleValue = 99.0
            return 0

        def PdhCloseQuery(self, _query) -> int:
            nonlocal close_calls
            close_calls += 1
            return 0

    reader._pdh = FakePdh()
    reader._pdh_query = resource_monitor.wintypes.HANDLE(1)
    reader._pdh_counter = resource_monitor.wintypes.HANDLE(2)
    reader._pdh_ready = True

    assert reader._read_disk_busy() == {"available": False}
    reader.close()

    assert close_calls == 1
    assert reader._pdh_ready is False


def test_pdh_setup_failure_closes_and_resets_query() -> None:
    from picorgftp_sql import resource_monitor

    reader = resource_monitor._WindowsResourceReaders()
    close_calls = 0

    class FakePdh:
        def PdhOpenQueryW(self, _source, _data, query) -> int:
            ctypes.cast(query, ctypes.POINTER(resource_monitor.wintypes.HANDLE)).contents.value = 1
            return 0

        def PdhAddEnglishCounterW(self, _query, _path, _data, counter) -> int:
            ctypes.cast(counter, ctypes.POINTER(resource_monitor.wintypes.HANDLE)).contents.value = 2
            return 0

        def PdhCollectQueryData(self, _query) -> int:
            return 1

        def PdhCloseQuery(self, _query) -> int:
            nonlocal close_calls
            close_calls += 1
            return 0

    reader._pdh = FakePdh()

    assert reader._read_disk_busy() == {"available": False}
    assert close_calls == 1
    assert not reader._pdh_query
    assert not reader._pdh_counter
    assert reader._pdh_ready is False
