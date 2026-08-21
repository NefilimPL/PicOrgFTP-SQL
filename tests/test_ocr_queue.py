from picorgftp_sql.services.ocr_queue import OcrQueueScheduler


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
