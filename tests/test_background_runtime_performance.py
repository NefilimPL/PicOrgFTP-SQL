from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import threading
import time

from picorgftp_sql import notification_service
from picorgftp_sql.notification_scheduler import WakeableDeadlineScheduler
from picorgftp_sql.web.active_clients import ActiveClientRegistry


UTC = timezone.utc


class _FakeWorkerClock:
    def __init__(self) -> None:
        self.elapsed_seconds = 0.0
        self._origin = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._origin + timedelta(seconds=self.elapsed_seconds)

    def advance(self, seconds: float) -> None:
        self.elapsed_seconds += seconds


def test_worker_idle_minute_and_wake_use_bounded_cycles(monkeypatch) -> None:
    """Returning to a tight poll or dropping a wake would violate the idle budget."""
    clock = _FakeWorkerClock()
    stop = threading.Event()
    pending = []
    cycle_times = []
    attempt_times = []

    class Scheduler:
        def __init__(self) -> None:
            self.generation = 0
            self.wait_count = 0

        def capture_generation(self) -> int:
            return self.generation

        def wake(self) -> None:
            self.generation += 1

        def wait(
            self,
            stop_event,
            delay_seconds,
            *,
            since_generation=None,
        ) -> str:
            self.wait_count += 1
            if self.wait_count == 1:
                clock.advance(min(60.0, float(delay_seconds)))
                return "deadline"
            if self.wait_count == 2:
                clock.advance(1.0)
                pending.append("delivery")
                self.wake()
                assert self.generation != since_generation
                return "wake"
            stop_event.set()
            return "stop"

    scheduler = Scheduler()

    class Store:
        @staticmethod
        def next_notification_due_at() -> str:
            return ""

    class Service:
        store = Store()

        @staticmethod
        def _settings() -> dict[str, str]:
            return {"daily_summary_time": "16:00"}

        @staticmethod
        def process_pending_batch(limit: int) -> int:
            del limit
            cycle_times.append(clock.elapsed_seconds)
            if not pending:
                return 0
            pending.pop()
            attempt_times.append(clock.elapsed_seconds)
            return 1

    monkeypatch.setattr(notification_service, "_WORKER_SCHEDULER", scheduler)
    monkeypatch.setattr(notification_service, "_utc_now", clock.now)
    monkeypatch.setattr(
        notification_service,
        "_WORKER_LAST_ENTRA_MONITOR_AT",
        clock.now(),
    )

    notification_service._worker_loop(Service(), stop)

    idle_cycles = [value for value in cycle_times if value <= 60.0]
    assert len(idle_cycles) <= 2
    assert attempt_times == [61.0]
    assert attempt_times[0] < 120.0


def test_real_scheduler_stop_interrupts_sixty_second_wait_in_under_one_second() -> None:
    """Shutdown must notify the real condition instead of waiting for fallback."""
    scheduler = WakeableDeadlineScheduler(max_idle_seconds=60.0)
    stop = threading.Event()
    outcomes = []
    waiter = threading.Thread(
        target=lambda: outcomes.append(scheduler.wait(stop, delay_seconds=60.0))
    )
    waiter.start()
    assert scheduler.wait_until_waiting(timeout=1.0)

    started = time.perf_counter()
    stop.set()
    scheduler.wake()
    waiter.join(timeout=1.0)
    stop_elapsed = time.perf_counter() - started

    assert not waiter.is_alive()
    assert outcomes == ["stop"]
    assert stop_elapsed < 1.0


def test_five_real_javascript_pollers_stay_within_active_and_hidden_budgets() -> None:
    """Duplicate timers or unchanged-version refreshes would exceed request budgets."""
    node = shutil.which("node")
    assert node is not None, "Node.js is required for the runtime poller benchmark"
    module_path = (
        Path(__file__).parents[1]
        / "picorgftp_sql"
        / "web"
        / "static"
        / "runtime-status.js"
    )
    script = """
global.window = { PicOrg: {} };
require(__MODULE__);

class FakeTimer {
  constructor() {
    this.now = 0;
    this.nextId = 0;
    this.pending = new Map();
  }

  setTimeout(callback, delay) {
    const id = ++this.nextId;
    this.pending.set(id, { callback, due: this.now + Number(delay) });
    return id;
  }

  clearTimeout(id) {
    this.pending.delete(id);
  }

  async runUntil(target, inclusive, poller) {
    while (true) {
      const ready = [...this.pending.entries()]
        .filter(([, item]) => inclusive ? item.due <= target : item.due < target)
        .sort((left, right) => left[1].due - right[1].due)[0];
      if (!ready) break;
      const [id, item] = ready;
      this.pending.delete(id);
      this.now = item.due;
      item.callback();
      if (poller.inFlight) await poller.inFlight;
    }
    this.now = target;
  }
}

async function simulateClient() {
  const timerApi = new FakeTimer();
  let hidden = false;
  let visibilityHandler;
  let activeRequests = 0;
  let hiddenRequests = 0;
  let inFlight = 0;
  let maxInFlight = 0;
  let detailRefreshes = 0;
  const poller = new window.PicOrg.RuntimeStatusPoller({
    fetchStatus: async () => {
      if (hidden) hiddenRequests += 1;
      else activeRequests += 1;
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await Promise.resolve();
      inFlight -= 1;
      return {
        versions: {
          file_index: "index-1",
          process_queue: 7,
          active_clients: 3,
        },
      };
    },
    onVersionChanged: async () => {
      detailRefreshes += 1;
    },
    activeIntervalMs: 5000,
    hiddenIntervalMs: 30000,
    isHidden: () => hidden,
    timerApi,
    visibilityTarget: {
      addEventListener: (_name, callback) => {
        visibilityHandler = callback;
      },
    },
  });

  await poller.start();
  await timerApi.runUntil(60000, false, poller);
  hidden = true;
  visibilityHandler();
  await timerApi.runUntil(120000, true, poller);
  return {
    activeRequests,
    hiddenRequests,
    maxInFlight,
    detailRefreshes,
  };
}

(async () => {
  const clients = [];
  for (let index = 0; index < 5; index += 1) {
    clients.push(await simulateClient());
  }
  process.stdout.write(JSON.stringify(clients));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
""".replace("__MODULE__", json.dumps(str(module_path)))

    completed = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    clients = json.loads(completed.stdout)
    assert len(clients) == 5
    assert all(client["activeRequests"] <= 12 for client in clients)
    assert all(client["hiddenRequests"] <= 2 for client in clients)
    assert all(client["maxInFlight"] == 1 for client in clients)
    assert all(client["detailRefreshes"] == 0 for client in clients)


def _client_record(index: int, *, sequence: int) -> dict[str, object]:
    return {
        "username": f"user-{index}",
        "client_id": f"browser-{index}",
        "last_seen_epoch": float(index + 1),
        "last_seen": "2026-07-27 10:00:00",
        "method": "GET",
        "path": "/",
        "status_code": 200,
        "remote_address": "127.0.0.1",
        "remote_port": 12345,
        "user_agent": "benchmark",
        "sequence": sequence,
    }


def test_registry_records_one_hundred_updates_while_serialization_is_blocked(
    tmp_path,
) -> None:
    """Holding the registry lock during JSON work would stall all 100 updates."""
    write_started = threading.Event()
    release_write = threading.Event()
    updates_finished = threading.Event()
    serialized_payloads = []
    record_waits = []
    update_errors = []

    def serializer(payload):
        serialized_payloads.append(payload)
        if len(serialized_payloads) == 1:
            write_started.set()
            assert release_write.wait(timeout=5.0)
        return json.dumps(payload)

    path = tmp_path / "active.json"
    registry = ActiveClientRegistry(path, serializer=serializer)

    def record_updates() -> None:
        try:
            for index in range(100):
                started = time.perf_counter()
                registry.record(_client_record(index, sequence=index))
                record_waits.append(time.perf_counter() - started)
        except Exception as exc:  # pragma: no cover - asserted below
            update_errors.append(exc)
        finally:
            updates_finished.set()

    updater = threading.Thread(target=record_updates)
    try:
        registry.record(_client_record(0, sequence=-1))
        assert registry.schedule_flush(force=True)
        assert write_started.wait(timeout=1.0)

        updater.start()
        completed_while_writer_was_blocked = updates_finished.wait(timeout=1.0)
        generation_after_updates = registry.generation
    finally:
        release_write.set()
        updater.join(timeout=5.0)

    try:
        assert registry.flush(force=True, timeout=5.0)
    finally:
        registry.close(timeout=5.0)

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert completed_while_writer_was_blocked
    assert update_errors == []
    assert len(record_waits) == 100
    assert max(record_waits) < 0.1
    assert generation_after_updates == 101
    assert {item["username"] for item in persisted} == {
        f"user-{index}" for index in range(100)
    }
    assert len(serialized_payloads) == 2
