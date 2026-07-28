import threading

from picorgftp_sql.notification_scheduler import WakeableDeadlineScheduler


def test_scheduler_wake_interrupts_wait():
    """A missing generation change would leave newly scheduled work delayed."""
    scheduler = WakeableDeadlineScheduler(max_idle_seconds=60)
    stop = threading.Event()
    result = []
    thread = threading.Thread(
        target=lambda: result.append(scheduler.wait(stop, delay_seconds=60))
    )

    thread.start()
    assert scheduler.wait_until_waiting(timeout=1.0)
    scheduler.wake()
    thread.join(timeout=1.0)

    assert result == ["wake"]


def test_scheduler_stop_interrupts_wait():
    """A shutdown signal must not wait for the scheduler's fallback timeout."""
    scheduler = WakeableDeadlineScheduler(max_idle_seconds=60)
    stop = threading.Event()
    result = []
    thread = threading.Thread(
        target=lambda: result.append(scheduler.wait(stop, delay_seconds=60))
    )

    thread.start()
    assert scheduler.wait_until_waiting(timeout=1.0)
    stop.set()
    scheduler.wake()
    thread.join(timeout=1.0)

    assert result == ["stop"]


def test_scheduler_caps_long_deadline_at_maximum_idle_timeout():
    """A long deadline must still provide a periodic 60-second fallback."""
    condition = FakeCondition()
    scheduler = WakeableDeadlineScheduler(max_idle_seconds=60, condition=condition)

    result = scheduler.wait(threading.Event(), delay_seconds=120)

    assert result == "deadline"
    assert condition.timeouts == [60.0]


class FakeCondition:
    def __init__(self):
        self.timeouts = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def notify_all(self):
        return None

    def wait_for(self, predicate, timeout):
        self.timeouts.append(timeout)
        return predicate()
