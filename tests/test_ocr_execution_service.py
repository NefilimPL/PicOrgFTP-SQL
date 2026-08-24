from picorgftp_sql.services.ocr_execution_service import OcrExecutionService
from picorgftp_sql.services.ocr_progress import OcrProgressRegistry
from picorgftp_sql.services.ocr_resource_policy import ResourceTelemetry


class _FakeWorker:
    def __init__(self) -> None:
        self.started = False
        self.submissions: list[dict[str, object]] = []
        self.events: list[dict[str, object]] = []
        self.cancelled: list[str] = []
        self.cpu_limits: list[int] = []
        self.telemetry = []

    def start(self) -> None:
        self.started = True

    def submit(self, **payload: object) -> None:
        self.submissions.append(payload)

    def poll_events(self) -> list[dict[str, object]]:
        events, self.events = self.events, []
        return events

    def cancel(self, run_id: str) -> None:
        self.cancelled.append(run_id)

    def update_limits(self, *, cpu_percent: int) -> None:
        self.cpu_limits.append(cpu_percent)

    def update_telemetry(self, telemetry: ResourceTelemetry) -> None:
        self.telemetry.append(telemetry)


def _telemetry(cpu: float = 10) -> ResourceTelemetry:
    return ResourceTelemetry(cpu, 2_000, 10_000, 10)


def test_execution_service_submits_selected_profiles_and_forwards_live_events():
    worker = _FakeWorker()
    service = OcrExecutionService(
        worker=worker,
        registry=OcrProgressRegistry(),
        settings=lambda: {"model_profiles": ["accurate", "fast"], "pause_cpu_percent": 85},
        telemetry=lambda: _telemetry(),
    )
    service.start()

    run_id = service.submit_test(path="C:/cache/test.png")
    worker.events = [
        {"kind": "stage_started", "run_id": run_id, "stage": "fast_full_image"},
        {
            "kind": "result",
            "run_id": run_id,
            "diagnostics": {"available": True, "candidates": []},
        },
    ]
    service.pump()

    assert worker.started is True
    assert worker.submissions == [
        {
            "run_id": run_id,
            "path": "C:/cache/test.png",
            "profile_ids": ["accurate", "fast"],
            "resource_settings": {"model_profiles": ["accurate", "fast"], "pause_cpu_percent": 85},
        }
    ]
    assert worker.cpu_limits == [35]
    snapshot = service.snapshot(run_id)
    assert snapshot.state == "completed"
    assert [(event.kind, event.payload["stage"]) for event in snapshot.events[:2]] == [
        ("queued", "waiting_for_worker"),
        ("stage_started", "fast_full_image"),
    ]


def test_execution_service_pauses_tester_at_admission_gate_without_submitting_or_queueing():
    worker = _FakeWorker()
    service = OcrExecutionService(
        worker=worker,
        registry=OcrProgressRegistry(),
        settings=lambda: {"model_profiles": ["fast"], "pause_cpu_percent": 85},
        telemetry=lambda: _telemetry(cpu=90),
    )

    run_id = service.submit_test(path="C:/cache/test.png")

    assert worker.submissions == []
    snapshot = service.snapshot(run_id)
    assert snapshot.state == "paused"
    assert snapshot.events[-1].kind == "paused"


def test_execution_service_requests_safe_boundary_cancellation():
    worker = _FakeWorker()
    service = OcrExecutionService(
        worker=worker,
        registry=OcrProgressRegistry(),
        settings=lambda: {"model_profiles": ["fast"], "pause_cpu_percent": 85},
        telemetry=lambda: _telemetry(),
    )
    run_id = service.submit_test(path="C:/cache/test.png")

    service.cancel(run_id)

    assert worker.cancelled == [run_id]
    assert service.snapshot(run_id).cancel_requested is True


def test_execution_service_registers_worker_pid_from_ready_event():
    worker = _FakeWorker()
    registered: list[int] = []
    service = OcrExecutionService(
        worker=worker,
        registry=OcrProgressRegistry(),
        settings=lambda: {"model_profiles": ["fast"], "pause_cpu_percent": 85},
        telemetry=lambda: _telemetry(),
        on_worker_ready=registered.append,
    )
    worker.events = [{"kind": "ready", "pid": 4321}]

    service.pump()

    assert registered == [4321]


def test_execution_service_uses_the_same_worker_pipeline_for_background_job():
    worker = _FakeWorker()
    service = OcrExecutionService(
        worker=worker,
        registry=OcrProgressRegistry(),
        settings=lambda: {"model_profiles": ["fast"], "pause_cpu_percent": 85},
        telemetry=lambda: _telemetry(),
    )

    run_id = service.submit_queue(job_id="ocr-1", path="C:/cache/crop.png")

    assert worker.submissions[0]["run_id"] == run_id
    assert worker.submissions[0]["path"] == "C:/cache/crop.png"
    assert service.snapshot(run_id).kind == "queue"
