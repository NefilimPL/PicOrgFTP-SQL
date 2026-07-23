# Reliable Resource Tests and Header Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make bounded real CPU/RAM/disk tests usable with normal production thresholds, report worker failures through the existing operational-event and mail path, and separate the long photo location from header status controls.

**Architecture:** `ResourceMonitor` keeps production configuration immutable and adds a per-worker effective threshold derived from the launch snapshot and existing bounded test envelope. A child worker catches its own exception and sends a bounded report through a multiprocessing pipe; the parent invokes an injected reporter without exposing traceback data in the API result. The web application adapts that report to an `error` operational event and log entry, while the static header becomes a two-row grid that gives the location its own truncatable row.

**Tech Stack:** Python 3 standard library (`multiprocessing`, `traceback`, `threading`), FastAPI, SQLite observability/outbox, vanilla HTML/CSS, pytest.

## Global Constraints

- Preserve the existing hard limits: 25% aggregate CPU, 256 MiB RAM, 128 MiB temporary disk data and the current disk-rate calculation.
- Do not persist or change a production resource-monitor threshold when a real test runs.
- A real test still needs two consecutive normal monitor samples before it is `detected`.
- Production sampling must use only persisted thresholds whenever no test worker is registered.
- Never return a worker traceback from `/api/resource-monitor/real-test`.
- Report an unexpected worker failure as `backend.resource_test_failed` with `error` severity, an application-log entry and the existing notification path.
- Keep existing status IDs, keyboard popovers and narrow-screen navigation behavior.
- Add no dependency.

---

## File structure

| File | Responsibility |
| --- | --- |
| `picorgftp_sql/resource_monitor.py` | Scoped effective test thresholds, worker failure pipe, safe disk pacing and private failure callback. |
| `picorgftp_sql/web/app.py` | Convert a private worker failure report into a redacted operational event and application log. |
| `picorgftp_sql/web/static/index.html` | Two-row header markup: title/status row and location row. |
| `picorgftp_sql/web/static/app.css` | Header grid sizing, location-only truncation and responsive wrap behavior. |
| `tests/test_resource_monitor.py` | Deterministic unit coverage for pacing, thresholds and worker-failure transport. |
| `tests/test_observability_api.py` | Web adapter coverage for persisted/logged private worker errors and safe public results. |
| `tests/test_web_ui_integrity.py` | Static contract for the two-row header and protected navigation/status elements. |

## Task 1: Make bounded real tests reachable without changing production settings

**Files:**
- Modify: `picorgftp_sql/resource_monitor.py:89-173,175-501,618-956`
- Modify: `tests/test_resource_monitor.py:440-540,1423-1526,1569-1854`

**Interfaces:**
- Produces `_effective_real_test_thresholds(kind: str, snapshot: Mapping[str, object]) -> dict[str, float]`, keyed by backend metric and retained only with the registered worker.
- Changes `_ResourceAlertDetector.observe(self, backend: Mapping[str, object], settings: Mapping[str, object], observed_at: str, effective_thresholds: Mapping[str, float] | None = None) -> list[dict[str, object]]`; trigger details retain `configured_threshold` and add `effective_threshold` plus `test_mode: "real"` when an override was used.

- [ ] **Step 1: Write failing threshold and disk-pacing tests**

Add this parameterized launch test. It replaces `test_real_cpu_test_rejects_threshold_beyond_hard_cap`, `test_real_cpu_test_rejects_threshold_exactly_at_hard_cap`, and `test_transient_ambient_load_cannot_admit_unreachable_real_test` because persisted threshold size no longer decides test reachability.

```python
@pytest.mark.parametrize("kind", ["cpu", "memory"])
def test_real_tests_accept_default_production_thresholds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    from picorgftp_sql import resource_monitor

    class FakeEvent:
        def is_set(self) -> bool:
            return False
        def set(self) -> None:
            return None

    class FakeProcess:
        pid = 4242
        exitcode = 0
        def __init__(self, *, target, args, daemon) -> None:
            return None
        def start(self) -> None:
            return None
        def join(self, timeout: float | None = None) -> None:
            return None
        def is_alive(self) -> bool:
            return False
        def close(self) -> None:
            return None

    monitor = _monitor(
        _ReaderSequence(
            cpu=[0],
            host={
                "cpu_percent": 15.0,
                "memory_percent": 84.0,
                "memory_used_bytes": 13_606 * MIB,
                "memory_total_bytes": 16_168 * MIB,
                "disk_busy_percent": 100.0,
            },
        ),
        [],
    )
    monitor.sample_once()
    monkeypatch.setattr(resource_monitor.tempfile, "mkdtemp", lambda **_: str(tmp_path / kind))
    monkeypatch.setattr(resource_monitor.multiprocessing, "Event", FakeEvent)
    monkeypatch.setattr(resource_monitor.multiprocessing, "Process", FakeProcess)

    assert monitor.start_real_test(kind)["status"] == "not_detected"
```

Add this self-contained clock-jump test alongside `test_disk_worker_never_exceeds_total_byte_budget_over_long_deadline`.

```python
def test_disk_worker_skips_sleep_when_clock_passes_write_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from picorgftp_sql import resource_monitor

    class StopEvent:
        def is_set(self) -> bool:
            return False

    class FakeFile:
        def open(self, *_args, **_kwargs):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *_args) -> None:
            return None
        def write(self, chunk: bytes) -> int:
            return len(chunk)
        def unlink(self, *, missing_ok: bool = False) -> None:
            return None

    class FakeRoot:
        def mkdir(self, **_kwargs) -> None:
            return None
        def __truediv__(self, _name: str) -> FakeFile:
            return FakeFile()

    moments = iter((0.0, 0.0, 0.0, 0.0, 0.11))
    sleeps: list[float] = []
    monkeypatch.setattr(resource_monitor.time, "monotonic", lambda: next(moments))
    monkeypatch.setattr(resource_monitor.time, "sleep", sleeps.append)

    resource_monitor._run_disk_test(StopEvent(), 1.0, FakeRoot(), 1, 10.0)

    assert not [value for value in sleeps if value <= 0]
```

Add a detector test that calls `observe` with `effective_thresholds={"memory_percent": 1.5}` and persisted `memory_percent_threshold=20`. Assert the emitted trigger has `configured_threshold == 20`, `effective_threshold == 1.5`, and `test_mode == "real"`. Call it a second time with no override and assert the normal 20% production threshold applies. Add a 16 GiB host-snapshot test that asserts the RAM override is above the backend baseline and below baseline plus the 256 MiB percentage contribution.

- [ ] **Step 2: Run the tests and verify they fail first**

Run:

```powershell
pytest tests/test_resource_monitor.py -k "default_production_thresholds or clock_passes_write_deadline or effective_threshold" -v
```

Expected: CPU fails with `configured cpu threshold exceeds the real-test hard cap`, RAM fails with `configured memory threshold exceeds the real-test hard cap`; the detector has no `effective_thresholds` argument; the disk case raises `ValueError: sleep length must be non-negative`.

- [ ] **Step 3: Implement worker-scoped threshold calculation**

Replace `_validate_real_test_reachable`; do not use transient external host load to admit a test. Store the result in `_worker_effective_thresholds` while holding `_state_lock`, copy it only when the sampled worker generation still matches, and clear it in every successful cleanup path.

```python
_REAL_TEST_THRESHOLD_SETTINGS = {
    "cpu": ("cpu_percent", "cpu_percent_threshold"),
    "memory": ("memory_percent", "memory_percent_threshold"),
    "disk": ("disk_io_bytes_per_second", "io_mib_per_second_threshold"),
}
REAL_TEST_TARGET_FRACTION = 0.75

def _effective_real_test_thresholds(
    self, kind: str, snapshot: Mapping[str, object]
) -> dict[str, float]:
    backend = snapshot.get("backend") if isinstance(snapshot, Mapping) else {}
    host = snapshot.get("host") if isinstance(snapshot, Mapping) else {}
    metric, _setting = _REAL_TEST_THRESHOLD_SETTINGS[kind]
    baseline = _number(backend.get(metric)) if isinstance(backend, Mapping) else None
    baseline = max(0.0, baseline or 0.0)
    if kind == "cpu":
        addition = self.MAX_TEST_CPU_PERCENT
    elif kind == "memory":
        total = _number(host.get("memory_total_bytes")) if isinstance(host, Mapping) else None
        if total is None or total <= 0:
            raise ValueError("memory data is unavailable for the real test")
        addition = self.MAX_TEST_MEMORY_BYTES / total * 100.0
    else:
        addition = self.MAX_TEST_DISK_RATE_BYTES_PER_SECOND
    return {metric: baseline + addition * self.REAL_TEST_TARGET_FRACTION}
```

Pass that map to the detector. When a metric uses it, retain the persisted `configured_threshold` and add `effective_threshold=threshold` plus `test_mode="real"` before returning the trigger. Do not include the private map in `latest_public_snapshot` and do not modify `config.py`.

- [ ] **Step 4: Implement race-safe disk pacing**

Replace the inner `while time.monotonic() < write_at` loop with one freshly calculated duration. It is essential that `sleep` is called only when `remaining_wait > 0`.

```python
while True:
    remaining_wait = write_at - time.monotonic()
    if remaining_wait <= 0:
        break
    if _should_stop(stop_event, deadline):
        return False
    if detection_event is not None and _event_is_set(detection_event):
        return True
    time.sleep(min(0.05, remaining_wait))
```

- [ ] **Step 5: Run focused monitor tests and commit**

Run:

```powershell
pytest tests/test_resource_monitor.py -k "real_test or disk_worker or effective_threshold" -v
```

Expected: PASS. Existing byte-budget, baseline, detector-ack, timeout, cancellation and cleanup cases stay green.

Commit `picorgftp_sql/resource_monitor.py` and `tests/test_resource_monitor.py` with message `fix: make bounded real resource tests reachable`.

## Task 2: Capture worker exceptions in the parent and persist them through web observability

**Files:**
- Modify: `picorgftp_sql/resource_monitor.py:175-501,671-835`
- Modify: `picorgftp_sql/web/app.py:64-75,208-219,4010-4022,4903-4933`
- Modify: `tests/test_resource_monitor.py:976-1010,1283-1338`
- Modify: `tests/test_observability_api.py:439-498,1701-1785`

**Interfaces:**
- Changes `ResourceMonitor(settings_provider, context_provider, event_emitter, clock=time.monotonic, wall_clock=time.time, readers=None, real_test_failure_reporter: Callable[[dict[str, str]], bool] | None = None)`; the parent-only callback receives exactly `kind`, `exception_type`, `message`, and `traceback`.
- `ResourceMonitor` owns `_worker_failure_receiver`; it is not included in a public resource snapshot or test result.
- Changes `_resource_test_worker(kind, stop_event, seconds, temp_dir, memory_bytes, disk_bytes, disk_rate_bytes_per_second, disk_baseline_event, detection_event, disk_baseline_wait_seconds, logical_cpus, failure_sender)`; it sends one bounded failure report and closes normally.
- Produces `web.app._report_real_test_worker_failure(failure: dict[str, str]) -> bool`.

- [ ] **Step 1: Write failing worker transport and web-adapter tests**

Add a direct-worker test that replaces `_run_disk_test` with a function raising `ValueError("sleep length must be non-negative")`, passes a fake sender, and asserts that `_resource_test_worker` returns normally, removes its temporary directory, and sends this payload:

```python
assert failure["kind"] == "disk"
assert failure["exception_type"] == "ValueError"
assert failure["message"] == "sleep length must be non-negative"
assert "_run_disk_test" in failure["traceback"]
```

Add a `start_real_test` supervision test using a fake pipe receiver which returns that payload after `join`. Construct the monitor with `real_test_failure_reporter=reported.append` and assert:

```python
assert result == {"ok": False, "kind": "disk", "status": "failed", "timed_out": False}
assert reported[0]["exception_type"] == "ValueError"
assert "traceback" not in result
```

In `tests/test_observability_api.py`, add a test that monkeypatches `web_app.emit_event` and `web_app.log_error`, calls `_report_real_test_worker_failure`, and asserts the event contract below. The existing `emit_event` code owns the notification outbox; passing `error` severity and a real exception preserves its tested queue behavior.

```python
assert emitted["severity"] == "error"
assert emitted["event_type"] == "backend.resource_test_failed"
assert emitted["module"] == "resource_monitor"
assert emitted["exception"].__class__.__name__ == "RealTestWorkerError"
assert "sleep length" in log_messages[0]
```

Extend the real-test endpoint stub result with an internal `traceback` key and assert the JSON response preserves the current top-level shape and never exposes that key.

- [ ] **Step 2: Run the new tests and verify they fail first**

Run:

```powershell
pytest tests/test_resource_monitor.py tests/test_observability_api.py -k "worker_failure or real_test_worker_failure or real_resource_test" -v
```

Expected: FAIL because the worker re-raises, no pipe/reporter exists, and the web adapter is absent.

- [ ] **Step 3: Implement a one-way, bounded child-to-parent failure report**

Import `traceback` and `sanitize_free_text` in `picorgftp_sql/resource_monitor.py`; import `Mapping` from `typing` in `picorgftp_sql/web/app.py`. Create `failure_receiver, failure_sender = multiprocessing.Pipe(duplex=False)` with the other worker events. Retain only the receive end on the monitor, pass the sender as the final process argument, and close the receive end in `_cleanup_registered_worker` after it has been read.

```python
def _take_worker_failure(self, expected_process: object) -> dict[str, str] | None:
    with self._state_lock:
        if self._worker_process is not expected_process:
            return None
        receiver = self._worker_failure_receiver
    try:
        if receiver is None or not receiver.poll():
            return None
        value = receiver.recv()
    except (EOFError, OSError):
        return None
    return _safe_worker_failure(value)
```

`_safe_worker_failure` requires the four string keys and bounds `message` and `traceback`. After `join` and before cleanup, consume the report before the exit-code branches. If present, call the reporter best-effort and return the pre-existing safe `failed` result; do not put the report in that result.

Wrap the worker dispatch without moving its cleanup:

```python
try:
    if kind == "cpu":
        _run_cpu_test(stop_event, deadline, logical_cpus, detection_event)
    elif kind == "memory":
        _run_memory_test(stop_event, deadline, memory_bytes, detection_event)
    elif kind == "disk":
        _run_disk_test(
            stop_event, deadline, Path(temp_dir), disk_bytes,
            disk_rate_bytes_per_second, disk_baseline_event,
            detection_event, disk_baseline_wait_seconds,
        )
except Exception as exc:
    _send_worker_failure(failure_sender, kind, exc)
finally:
    shutil.rmtree(temp_dir, ignore_errors=True)
    try:
        failure_sender.close()
    except Exception:
        pass
```

`_send_worker_failure` builds `traceback.format_exception(type(exc), exc, exc.__traceback__)`, passes the joined text through `sanitize_free_text(value, limit=24 * 1024)`, catches send errors, and never re-raises. Therefore `multiprocessing` cannot print an unhandled child traceback to the windowed EXE's absent `stderr`.

- [ ] **Step 4: Implement the web reporter and connect the singleton monitor**

Add the exception and adapter beside `_emit_resource_event`. It deliberately carries the redacted remote traceback through the established `emit_event(exception=...)` attachment path, but it is never serialized by the endpoint.

```python
class RealTestWorkerError(RuntimeError):
    def __init__(self, failure: Mapping[str, str]) -> None:
        self.kind = str(failure["kind"])
        self.remote_traceback = str(failure["traceback"])
        super().__init__(
            f"Real {self.kind} resource-test worker failed: "
            f"{failure['exception_type']}: {failure['message']}\n"
            f"Worker traceback:\n{self.remote_traceback}"
        )

def _report_real_test_worker_failure(failure: dict[str, str]) -> bool:
    error = RealTestWorkerError(failure)
    try:
        event = emit_event(
            severity="error",
            event_type="backend.resource_test_failed",
            module="resource_monitor",
            stage="real_test",
            summary=f"Real {failure['kind']} resource test worker failed.",
            details={"test_mode": "real", "kind": failure["kind"]},
            exception=error,
            strict=True,
        )
    except Exception:
        log_error(f"WEB resource test worker failure: {error}")
        return False
    log_error(f"WEB resource test worker failure: {error}")
    return bool(event)
```

Pass `real_test_failure_reporter=_report_real_test_worker_failure` in `_RESOURCE_MONITOR`. Keep the endpoint's generic `failed` message and its current response fields.

- [ ] **Step 5: Run focused failure-path tests and commit**

Run:

```powershell
pytest tests/test_resource_monitor.py tests/test_observability_api.py -k "worker_failure or real_test_worker_failure or real_resource_test" -v
```

Expected: PASS. A worker error produces one parent callback and safe HTTP result; launch, timeout, cancellation, and cleanup behaviors remain green.

Commit `picorgftp_sql/resource_monitor.py`, `picorgftp_sql/web/app.py`, `tests/test_resource_monitor.py`, and `tests/test_observability_api.py` with message `fix: report real resource test worker failures`.

## Task 3: Restore a two-row header that protects navigation space

**Files:**
- Modify: `picorgftp_sql/web/static/index.html:10-72`
- Modify: `picorgftp_sql/web/static/app.css:156-201,323-364,3597-3618,3666-3692`
- Modify: `tests/test_web_ui_integrity.py:62-69,482-535`

**Interfaces:**
- Keeps `versionInfo`, `serverInfo`, `backendHealthStatus`, `resourceStatus`, `activeUsersPresence`, and every existing popover ID unchanged.
- Produces `.topbar-title-row` for the first row and `.header-location` for the second; only `.header-location` owns location truncation.

- [ ] **Step 1: Write a failing static header contract**

Replace the compact-header test with the following structural assertion. Keep existing checks for status IDs, ARIA controls, keyboard expansion, and real-test controls elsewhere in the class.

```python
def test_header_keeps_title_and_statuses_above_a_dedicated_location_row(self) -> None:
    markup = INDEX_HTML.read_text(encoding="utf-8")
    css = (ROOT / "picorgftp_sql" / "web" / "static" / "app.css").read_text(encoding="utf-8")

    self.assertIn('class="topbar-title-row"', markup)
    self.assertIn('class="header-location"', markup)
    self.assertLess(markup.index("PicOrgFTP-SQL Web"), markup.index('id="serverInfo"'))
    self.assertLess(markup.index('id="backendHealthStatus"'), markup.index('id="serverInfo"'))
    self.assertLess(markup.index('id="resourceStatus"'), markup.index('id="serverInfo"'))
    self.assertIn(".header-location #serverInfo", css)
    self.assertIn("text-overflow: ellipsis", css)
```

- [ ] **Step 2: Run the header contract and verify it fails**

Run:

```powershell
pytest tests/test_web_ui_integrity.py -k "header_keeps_title or compact_header" -v
```

Expected: FAIL because neither `topbar-title-row` nor `header-location` exists.

- [ ] **Step 3: Restructure header markup without changing IDs**

Keep the existing `githubStatusButton` (including its SVG) as the first child of `.topbar-brand`. Replace the current brand-info plus sibling observability arrangement with this exact nesting; it preserves every health/resource ID and popover element.

```html
<div class="topbar-brand">
  <div class="topbar-title-row">
    <div class="topbar-brand-info">
      <strong>PicOrgFTP-SQL Web</strong>
      <span id="versionInfo"></span>
    </div>
    <div class="header-observability">
      <div class="backend-health-indicator">
        <button id="backendHealthStatus" type="button" class="backend-health-status" data-level="checking" aria-live="polite" aria-controls="backendHealthDetails" aria-describedby="backendHealthDetails" aria-expanded="false">
          <span class="backend-health-dot" aria-hidden="true"></span>
          <span id="backendHealthText">Sprawdzanie...</span>
        </button>
        <div id="backendHealthDetails" class="backend-health-details" role="tooltip" hidden>
          <strong>Stan komponentow</strong>
          <ul id="backendHealthDetailsList">
            <li><span>Backend</span><strong>Sprawdzanie...</strong></li>
            <li><span>SQLite</span><strong>Sprawdzanie...</strong></li>
            <li><span>Proces zadan</span><strong>Sprawdzanie...</strong></li>
            <li><span>Powiadomienia</span><strong>Sprawdzanie...</strong></li>
            <li><span>FTP</span><strong>Brak danych</strong></li>
            <li><span>SQL</span><strong>Brak danych</strong></li>
            <li><span>Profile SQL</span><strong>Brak danych</strong></li>
            <li><span>Pimcore</span><strong>Brak danych</strong></li>
          </ul>
        </div>
      </div>
      <div class="resource-status-indicator">
        <button id="resourceStatus" type="button" class="resource-status" data-level="normal" aria-live="polite" aria-controls="resourceDetails" aria-describedby="resourceDetails" aria-expanded="false">
          <span class="resource-status-dot" aria-hidden="true"></span>
          <span id="resourceStatusText">System: CPU brak danych · RAM brak danych · DYSK brak danych · Backend: CPU brak danych · RAM brak danych · I/O brak danych</span>
        </button>
        <div id="resourceDetails" class="resource-details" role="tooltip" hidden>
          <strong>Szczegoly zasobow</strong>
          <ul id="resourceDetailsList">
            <li><span>Probka</span><strong>Brak danych</strong></li>
          </ul>
        </div>
      </div>
    </div>
  </div>
  <div class="header-location">
    <span id="serverInfo"></span>
  </div>
</div>
```

Move only `serverInfo` to `.header-location`; do not move the top navigation or rename any status/popover element.

- [ ] **Step 4: Implement the responsive grid and location-only truncation**

Replace the three-column brand grid with the two-row layout below. Retain existing status colors and popover styles.

```css
.topbar-brand {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  grid-template-rows: auto auto;
  align-items: center;
  gap: 3px 12px;
  min-width: 0;
}
.github-status-button { grid-row: 1 / span 2; }
.topbar-title-row {
  display: grid;
  grid-template-columns: minmax(150px, max-content) minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.header-location { grid-column: 2; min-width: 0; }
.header-location #serverInfo {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.header-observability { min-width: 0; }
.resource-status { max-width: min(440px, 100%); }
```

At the existing `1180px` breakpoint, keep the brand at full width but make `.topbar-title-row` one column and let `.header-observability` wrap inside it. At `540px`, preserve the vertical topbar/navigation layout and keep this one-column title-row behavior so status buttons wrap before navigation.

- [ ] **Step 5: Run UI/source checks and commit**

Run:

```powershell
pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py -v
```

Expected: PASS. Existing accessibility contracts pass, and the new test proves the location follows both statuses in markup.

Commit `picorgftp_sql/web/static/index.html`, `picorgftp_sql/web/static/app.css`, and `tests/test_web_ui_integrity.py` with message `fix: protect header navigation from long locations`.

## Task 4: Document the final test contract and verify the integration

**Files:**
- Modify: `docs/web-panel.md:104-109`
- Modify: `tests/test_source_integrity.py`
- Test: `tests/test_resource_monitor.py`
- Test: `tests/test_observability_api.py`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Documents the distinction between production thresholds and a real-test-only effective threshold, plus the logged/emailed worker-failure behavior.

- [ ] **Step 1: Write a failing documentation contract**

Locate the existing resource-monitor documentation check in `tests/test_source_integrity.py`. If it exists, extend that test; otherwise add `test_web_panel_documents_real_test_threshold_and_worker_failure`. It must read `docs/web-panel.md` and assert:

```python
panel = (ROOT / "docs" / "web-panel.md").read_text(encoding="utf-8")
assert "progu testowego" in panel
assert "progów produkcyjnych" in panel
assert "błąd procesu roboczego" in panel
```

- [ ] **Step 2: Run the documentation test and verify it fails**

Run:

```powershell
pytest tests/test_source_integrity.py -k resource_monitor -v
```

Expected: FAIL because the current paragraph says that a test is rejected when its configured threshold cannot be reached.

- [ ] **Step 3: Update the user-facing real-test description**

In the real-test paragraph of `docs/web-panel.md`, replace only the final reachability sentence with this text:

```markdown
Progi alarmów używane podczas zwykłej pracy nie zmieniają się. Dla aktywnego
testu monitor wylicza osobny, ograniczony próg testowy możliwy do osiągnięcia
w bezpiecznym limicie; zapisane progi znów obowiązują natychmiast po jego
zakończeniu. Alert testu jest wyraźnie oznaczony jako test rzeczywisty.
Nieoczekiwany błąd procesu roboczego jest zapisywany jako błąd monitora,
pojawia się w logu i korzysta z normalnej kolejki powiadomień; traceback nie
jest zwracany do przeglądarki.
```

- [ ] **Step 4: Run the full relevant suite**

Run:

```powershell
pytest tests/test_resource_monitor.py tests/test_observability_api.py tests/test_web_ui_integrity.py tests/test_source_integrity.py -v
```

Expected: PASS. No case leaves a process or `picorg_resource_test_*` directory behind.

- [ ] **Step 5: Inspect and commit documentation**

Run `git diff --check`, `git status --short`, and `git diff -- docs/web-panel.md tests/test_source_integrity.py`. Expect no whitespace errors and only documentation/test changes unstaged. Commit `docs/web-panel.md` and any changed documentation test with message `docs: clarify bounded real resource tests`.
