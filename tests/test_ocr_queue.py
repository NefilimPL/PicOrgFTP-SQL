from picorgftp_sql.services.ocr_queue import OcrQueueScheduler
from picorgftp_sql.services.ocr_worker import OcrQueueWorker


def test_scheduler_waits_for_configured_user_idle_period():
    scheduler = OcrQueueScheduler(
        settings=lambda: {"background_enabled": True, "idle_seconds": 5, "max_cpu_percent": 50, "pause_cpu_percent": 85},
        has_active_requests=lambda: False,
        last_activity=lambda: 100,
        cpu_percent=lambda: 10,
        claim_job=lambda: None,
        process_job=lambda _job: None,
        now=lambda: 104,
    )

    assert scheduler.run_once() == "idle_wait"


def test_scheduler_pauses_above_hard_cpu_limit():
    scheduler = OcrQueueScheduler(
        settings=lambda: {"background_enabled": True, "idle_seconds": 0, "max_cpu_percent": 50, "pause_cpu_percent": 85},
        has_active_requests=lambda: False,
        last_activity=lambda: 0,
        cpu_percent=lambda: 90,
        claim_job=lambda: None,
        process_job=lambda _job: None,
        now=lambda: 100,
    )

    assert scheduler.run_once() == "cpu_pause"


def test_scheduler_does_not_claim_a_crop_above_configured_ocr_cpu_limit():
    claimed = []
    scheduler = OcrQueueScheduler(
        settings=lambda: {"background_enabled": True, "idle_seconds": 0, "max_cpu_percent": 50, "pause_cpu_percent": 85},
        has_active_requests=lambda: False,
        last_activity=lambda: 0,
        cpu_percent=lambda: 60,
        claim_job=lambda: claimed.append(True),
        process_job=lambda _job: None,
        now=lambda: 100,
    )

    assert scheduler.run_once() == "cpu_limit"
    assert claimed == []


def test_scheduler_requeues_claimed_crop_when_user_becomes_active():
    activity = {"active": False}
    requeued = []
    job = {"id": "ocr-1"}
    scheduler = OcrQueueScheduler(
        settings=lambda: {"background_enabled": True, "idle_seconds": 0, "max_cpu_percent": 50, "pause_cpu_percent": 85},
        has_active_requests=lambda: activity["active"],
        last_activity=lambda: 0,
        cpu_percent=lambda: 10,
        claim_job=lambda: job,
        process_job=lambda _job: activity.update(active=True),
        requeue_job=lambda item: requeued.append(item),
        now=lambda: 100,
    )

    assert scheduler.run_once() == "requeued"
    assert requeued == [job]


def test_scheduler_requeues_crop_when_refinement_fails():
    requeued = []
    job = {"id": "ocr-1"}
    scheduler = OcrQueueScheduler(
        settings=lambda: {"background_enabled": True, "idle_seconds": 0, "max_cpu_percent": 50, "pause_cpu_percent": 85},
        has_active_requests=lambda: False,
        last_activity=lambda: 0,
        cpu_percent=lambda: 10,
        claim_job=lambda: job,
        process_job=lambda _job: (_ for _ in ()).throw(RuntimeError("OCR error")),
        requeue_job=lambda item: requeued.append(item),
        now=lambda: 100,
    )

    assert scheduler.run_once() == "requeued_error"
    assert requeued == [job]


def test_background_worker_repeatedly_runs_scheduler_and_stops_cleanly():
    calls = []

    class FakeStopEvent:
        def __init__(self):
            self.waits = 0

        def is_set(self):
            return self.waits >= 2

        def wait(self, _seconds):
            self.waits += 1

    worker = OcrQueueWorker(
        run_once=lambda: calls.append("run") or "empty",
        poll_seconds=0.1,
        stop_event=FakeStopEvent(),
    )

    worker.run()

    assert calls == ["run", "run"]
