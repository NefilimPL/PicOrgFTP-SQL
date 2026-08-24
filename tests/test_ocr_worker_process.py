import time

from picorgftp_sql.services.ocr_worker_process import OcrWorkerProcess
from picorgftp_sql.services.windows_job_limits import WindowsJobLimits


class _FakeWindowsJobApi:
    def __init__(self) -> None:
        self.assigned: list[tuple[int, int]] = []
        self.cpu_rates: list[tuple[int, int]] = []
        self.closed: list[int] = []

    def create_job(self) -> int:
        return 101

    def assign_process(self, job_handle: int, pid: int) -> None:
        self.assigned.append((job_handle, pid))

    def set_cpu_hard_cap(self, job_handle: int, cpu_rate: int) -> None:
        self.cpu_rates.append((job_handle, cpu_rate))

    def close_handle(self, handle: int) -> None:
        self.closed.append(handle)


def test_windows_job_limits_assigns_worker_and_applies_continuous_cpu_hard_cap():
    api = _FakeWindowsJobApi()
    limits = WindowsJobLimits(api=api)

    capability = limits.apply_to_process(pid=4321, cpu_percent=35)

    assert capability.available is True
    assert capability.cpu_percent == 35
    assert api.assigned == [(101, 4321)]
    assert api.cpu_rates == [(101, 3_500)]


def test_windows_job_limits_reports_unavailable_without_breaking_ocr_when_api_fails():
    class _FailingApi:
        def create_job(self) -> int:
            raise OSError("unsupported")

    capability = WindowsJobLimits(api=_FailingApi()).apply_to_process(
        pid=4321, cpu_percent=35
    )

    assert capability.available is False
    assert "unsupported" in capability.message


def test_windows_job_limits_keeps_handle_until_worker_shutdown():
    api = _FakeWindowsJobApi()
    limits = WindowsJobLimits(api=api)
    limits.apply_to_process(pid=4321, cpu_percent=35)

    limits.close()

    assert api.closed == [101]


def test_worker_process_reports_ready_and_stops_without_loading_an_ocr_model():
    worker = OcrWorkerProcess(cpu_percent=35)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        events: list[dict[str, object]] = []
        while time.monotonic() < deadline and not events:
            events.extend(worker.poll_events())
            time.sleep(0.02)
    finally:
        worker.stop(timeout=5)

    assert events[0]["kind"] == "ready"
    assert isinstance(events[0]["pid"], int)


def test_worker_process_forwards_a_serializable_job_result():
    worker = OcrWorkerProcess(cpu_percent=35)
    worker.start()
    try:
        worker.submit(run_id="run-1", path="missing-image.png", profile_ids=["fast"])
        deadline = time.monotonic() + 5
        events: list[dict[str, object]] = []
        while time.monotonic() < deadline:
            events.extend(worker.poll_events())
            if any(event["kind"] == "result" for event in events):
                break
            time.sleep(0.02)
    finally:
        worker.stop(timeout=5)

    started = next(event for event in events if event["kind"] == "stage_started")
    assert isinstance(started["worker_pid"], int)
    result = next(event for event in events if event["kind"] == "result")
    assert result["run_id"] == "run-1"
    assert result["diagnostics"]["available"] is False
