# Backend Resource Monitor and RAM Guards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect high CPU, RAM and disk-I/O use by the backend, make it visible in the web UI, record only backend-caused incidents, provide bounded diagnostic tests, and cap audited memory-growth paths.

**Architecture:** A Windows-native `ResourceMonitor` owns five-second samples, a bounded history and a two-sample threshold latch. `web.app` starts it with the backend, projects its cached public state through `/api/health`, and supplies runtime context plus an observability event sink. A focused web UI consumes that projection; memory safeguards cap local queues, JavaScript preview cache entries and server helper maps without changing active jobs.

**Tech Stack:** Python 3 standard library (`ctypes`, `multiprocessing`, `threading`, `queue`, `time`), FastAPI, SQLite observability store, vanilla JavaScript/CSS, pytest.

## Global Constraints

- Do not add `psutil` or any other runtime dependency.
- Sample in a daemon thread every five seconds; `/api/health` must return cached metrics only.
- Raise a resource incident only after two consecutive backend threshold breaches; host-only load is context, never a trigger.
- Preserve existing durable observability redaction and notification behavior.
- Real tests must use a registered helper process, have a hard 20-second deadline, and cap CPU at 25% aggregate host capacity, RAM at 256 MiB and temporary disk data at 128 MiB.
- The real-test endpoint must not create an alert itself; normal monitor detection must create it or return a no-breach result.
- Keep all existing active process jobs and upload files; bounds may evict only display/cache/finished-job state.
- Maintain Windows behavior with explicit unavailable metric values when a native counter cannot be read.

---

## File structure

| File | Responsibility |
| --- | --- |
| `picorgftp_sql/resource_monitor.py` | Native metric readers, sample normalization, threshold latch, bounded history and test-worker lifecycle. |
| `picorgftp_sql/common.py` | Resource-monitor configuration key and defaults. |
| `picorgftp_sql/config.py` | Strict normalization and bounds for persisted resource-monitor configuration. |
| `picorgftp_sql/web_data.py` | Persist and project non-secret resource-monitor settings. |
| `picorgftp_sql/web/app.py` | Monitor lifecycle, cached health projection, context/event adapters and protected test endpoints. |
| `picorgftp_sql/web/static/index.html` | Header resource indicator and Monitor settings tab. |
| `picorgftp_sql/web/static/app.js` | Rendering, accessible popover, settings form and test controls. |
| `picorgftp_sql/web/static/app.css` | Compact two-row indicator and resource details styles. |
| `picorgftp_sql/app.py` | Bounded thumbnail request/result queues with retry-safe overflow handling. |
| `tests/test_resource_monitor.py` | Unit tests for readers, latches, history and bounded test worker. |
| `tests/test_config.py` | Resource-monitor setting normalization tests. |
| `tests/test_observability_api.py` | Health projection, authorization, safe/real test endpoint and alert integration tests. |
| `tests/test_app_performance_helpers.py` | Desktop thumbnail overflow/retry behavior. |
| `tests/test_web_ui_integrity.py` | Static UI contracts for indicator, settings and cache LRU. |
| `docs/web-panel.md` | User-facing status, warning and test behavior. |

## Task 1: Persist validated resource-monitor settings

**Files:**
- Modify: `picorgftp_sql/common.py:209-283`
- Modify: `picorgftp_sql/config.py:214-249,329-333,497-499,556-560,775-777`
- Modify: `picorgftp_sql/web_data.py:2895-3102,3105-3185`
- Test: `tests/test_config.py`
- Test: `tests/test_web_data_users.py`

**Interfaces:**
- Produces `RESOURCE_MONITOR_SETTINGS_KEY = "resource_monitor"`.
- Produces `config._normalize_resource_monitor_settings(raw) -> dict[str, object]` with keys `show_status`, `cpu_percent_threshold`, `memory_percent_threshold` and `io_mib_per_second_threshold`.
- Produces a non-secret `resource_monitor` section in `web_data.settings_snapshot()` and accepts the same section in `web_data.update_settings()`.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_normalize_resource_monitor_settings_uses_safe_defaults_and_bounds() -> None:
    settings = _normalize_resource_monitor_settings(
        {
            "show_status": "yes",
            "cpu_percent_threshold": "0",
            "memory_percent_threshold": "1000",
            "io_mib_per_second_threshold": "-4",
        }
    )

    assert settings == {
        "show_status": True,
        "cpu_percent_threshold": 10,
        "memory_percent_threshold": 90,
        "io_mib_per_second_threshold": 1,
    }
```

Add a `tests/test_web_data_users.py` test that calls `web_data.update_settings({"resource_monitor": {"show_status": False, "cpu_percent_threshold": 35, "memory_percent_threshold": 25, "io_mib_per_second_threshold": 8}})`, then asserts the returned snapshot exposes exactly those normalized values.

- [ ] **Step 2: Run the focused tests and confirm they fail because the key and normalizer do not exist**

Run: `pytest tests/test_config.py -k resource_monitor -v`

Expected: FAIL with an import or attribute error for `_normalize_resource_monitor_settings`.

- [ ] **Step 3: Add defaults, normalization and settings projection**

```python
# common.py
RESOURCE_MONITOR_SETTINGS_KEY = "resource_monitor"
DEFAULT_CONFIG.setdefault(
    RESOURCE_MONITOR_SETTINGS_KEY,
    {
        "show_status": True,
        "cpu_percent_threshold": 25,
        "memory_percent_threshold": 20,
        "io_mib_per_second_threshold": 8,
    },
)

# config.py
def _normalize_resource_monitor_settings(raw_settings):
    raw = raw_settings if Aq(raw_settings, dict) else {}
    defaults = DEFAULT_CONFIG[RESOURCE_MONITOR_SETTINGS_KEY]

    def bounded_int(key, minimum, maximum):
        try:
            value = int(raw.get(key, defaults[key]))
        except (TypeError, ValueError):
            value = int(defaults[key])
        return max(minimum, min(maximum, value))

    return {
        "show_status": bool(raw.get("show_status", defaults["show_status"])),
        "cpu_percent_threshold": bounded_int("cpu_percent_threshold", 10, 90),
        "memory_percent_threshold": bounded_int("memory_percent_threshold", 1, 90),
        "io_mib_per_second_threshold": bounded_int("io_mib_per_second_threshold", 1, 256),
    }
```

Call the normalizer at every existing configuration merge/save boundary used by `PROCESSING_SETTINGS_KEY`. In `web_data.update_settings`, merge only the submitted `resource_monitor` fields into the current normalized configuration. In `settings_snapshot`, include the normalized public section.

- [ ] **Step 4: Run focused and related configuration tests**

Run: `pytest tests/test_config.py tests/test_settings.py tests/test_web_data_users.py -v`

Expected: PASS with all configuration tests green.

- [ ] **Step 5: Commit the settings contract**

```bash
git add picorgftp_sql/common.py picorgftp_sql/config.py picorgftp_sql/web_data.py tests/test_config.py tests/test_settings.py tests/test_web_data_users.py
git commit -m "feat: persist resource monitor settings"
```

## Task 2: Build native sampling, latching and bounded real-test worker

**Files:**
- Create: `picorgftp_sql/resource_monitor.py`
- Test: `tests/test_resource_monitor.py`

**Interfaces:**
- Produces `ResourceMonitor(settings_provider, context_provider, event_emitter, clock=time.monotonic, wall_clock=time.time, readers=None)`.
- Produces `start()`, `stop()`, `latest_public_snapshot()`, `sample_once()`, `record_safe_simulation()` and `start_real_test(kind: str)`.
- `latest_public_snapshot()` returns `{"host": dict, "backend": dict, "detector": dict, "observed_at": str}` without process handles or temporary paths.
- `event_emitter(severity: str, event_type: str, details: dict[str, object]) -> None` receives only serializable, redacted-safe diagnostic values.

- [ ] **Step 1: Write failing monitor tests with deterministic clocks and readers**

```python
class _ReaderSequence:
    def __init__(self, cpu):
        self.cpu = iter(cpu)

    def read_host(self):
        return {"cpu_percent": 95, "memory_percent": 95, "disk_busy_percent": 95}

    def read_backend(self, _worker_pid=None):
        return {
            "cpu_percent": next(self.cpu),
            "memory_percent": 2,
            "disk_io_bytes_per_second": 0,
        }

def test_monitor_emits_one_alert_after_two_backend_cpu_breaches() -> None:
    events = []
    monitor = ResourceMonitor(
        settings_provider=lambda: {
            "cpu_percent_threshold": 25,
            "memory_percent_threshold": 20,
            "io_mib_per_second_threshold": 8,
        },
        context_provider=lambda: {"active_jobs": 0, "queued_jobs": 0, "active_clients": 0},
        event_emitter=lambda severity, event_type, details: events.append((severity, event_type, details)),
        readers=_ReaderSequence(cpu=[24, 28, 31, 5, 6]),
    )

    monitor.sample_once()
    monitor.sample_once()
    assert events == []
    monitor.sample_once()
    assert events[0][0:2] == ("warning", "backend.resource_high")
    assert events[0][2]["trigger"]["metric"] == "cpu_percent"
```

Add independent tests for: unavailable host disk metric; host-only load producing no event; memory and I/O triggers; recovery resetting the latch only after two normal samples; history capped at 12 samples; safe simulation labelled `test_mode: "safe"`; real-test rejection when a threshold exceeds the hard cap; worker timeout removing its registration and temporary file.

- [ ] **Step 2: Run the monitor test file and confirm it fails because the module is absent**

Run: `pytest tests/test_resource_monitor.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'picorgftp_sql.resource_monitor'`.

- [ ] **Step 3: Implement the monitor with injected readers and Windows readers**

```python
class ResourceMonitor:
    SAMPLE_SECONDS = 5.0
    HISTORY_SIZE = 12
    CONFIRMING_SAMPLES = 2
    REAL_TEST_SECONDS = 20.0
    MAX_TEST_MEMORY_BYTES = 256 * 1024 * 1024
    MAX_TEST_DISK_BYTES = 128 * 1024 * 1024

    def sample_once(self) -> dict[str, object]:
        host = self._read_host()
        backend = self._read_backend_with_registered_worker()
        backend.update(self._context_provider())
        sample = {"host": host, "backend": backend, "observed_at": self._utc_now()}
        self._history.append(sample)
        trigger = self._detector.observe(backend, self._settings_provider())
        if trigger is not None:
            self._event_emitter("warning", "backend.resource_high", self._diagnostic_details(sample, trigger))
        self._latest = {**sample, "detector": self._detector.public_state()}
        return self._latest
```

Use `ctypes` wrappers for `GlobalMemoryStatusEx`, `GetSystemTimes`, `GetProcessTimes`, `GetProcessMemoryInfo` and `GetProcessIoCounters`. Read aggregate physical-disk active time through `PdhAddEnglishCounterW` for `\\PhysicalDisk(_Total)\\% Disk Time`; convert failures to `{ "available": False }`. Keep all native reader functions injectable through a `readers` constructor argument so unit tests never depend on host load.

Implement `_ResourceAlertDetector` with per-metric consecutive-high and consecutive-normal counters. It must emit once while latched and expose `latched_metrics`, `pending_metrics` and `last_trigger_at` through `public_state()`.

Implement the real worker with `multiprocessing.Process`, a `multiprocessing.Event` and an application-private temporary directory. Register its PID before start; aggregate its CPU, memory and I/O into backend metrics while alive; stop it in `finally`; remove its directory and registration on normal completion, launch failure, timeout and `ResourceMonitor.stop()`. The worker accepts only `cpu`, `memory` or `disk`; it uses bounded allocations and writes/deletes fixed-size chunks with a deadline check.

- [ ] **Step 4: Run the monitor test file and full unit group**

Run: `pytest tests/test_resource_monitor.py tests/test_config.py -v`

Expected: PASS with no live process, temporary file or temporary directory left by tests.

- [ ] **Step 5: Commit the monitoring core**

```bash
git add picorgftp_sql/resource_monitor.py tests/test_resource_monitor.py
git commit -m "feat: add bounded backend resource monitor"
```

## Task 3: Integrate monitor lifecycle, health data and protected diagnostic APIs

**Files:**
- Modify: `picorgftp_sql/web/app.py:180-208,4440-4757,5032-5075,6427-6460`
- Modify: `tests/test_observability_api.py`
- Modify: `tests/test_web_smoke_ci.py`

**Interfaces:**
- Consumes `ResourceMonitor` from Task 2 and normalized configuration from Task 1.
- Produces `resources` in `_health_payload()`.
- Produces `POST /api/resource-monitor/simulate-safe` and `POST /api/resource-monitor/real-test`.
- Both endpoints return `{"ok": bool, "message": str, "resources": dict, "test": dict}` and require an authenticated web administrator plus existing CSRF middleware.

- [ ] **Step 1: Write failing API tests**

```python
def test_health_returns_cached_resource_projection_without_sampling(api_environment, monkeypatch) -> None:
    client, _store = api_environment
    _login(client)
    monitor = _MonitorStub({"host": {"cpu_percent": 60}, "backend": {"cpu_percent": 4}})
    monkeypatch.setattr(web_app, "_RESOURCE_MONITOR", monitor)

    payload = client.get("/api/health").json()

    assert payload["resources"]["backend"]["cpu_percent"] == 4
    assert monitor.sample_calls == 0
```

Add tests proving anonymous and non-admin users receive `401`/`403`, missing CSRF receives `403`, safe simulation records one labelled test event, real-test returns the monitor result without directly calling `emit_event`, and startup/shutdown call `start`/`stop` exactly once.

- [ ] **Step 2: Run the focused API tests and confirm they fail because the resource projection/endpoints are absent**

Run: `pytest tests/test_observability_api.py -k "resource or health" -v`

Expected: FAIL with missing `resources` payload key or missing endpoint.

- [ ] **Step 3: Wire the monitor into the existing app lifecycle**

```python
def _resource_monitor_context() -> dict[str, int]:
    active = _active_process_jobs_snapshot()
    with _ACTIVE_CLIENTS_LOCK:
        active_clients = len(_ACTIVE_CLIENTS)
    return {
        "active_jobs": int(active["active_count"]),
        "queued_jobs": int(active["queued_count"]),
        "active_clients": active_clients,
    }

def _emit_resource_event(severity: str, event_type: str, details: dict[str, object]) -> None:
    emit_event(
        severity=severity,
        event_type=event_type,
        module="resource_monitor",
        stage="threshold",
        summary="Backend resource threshold exceeded.",
        details=details,
    )
```

Create the singleton after imports, start it after runtime initialization in the FastAPI startup callback, stop it before notification worker shutdown completes, and add `"resources": _RESOURCE_MONITOR.latest_public_snapshot()` to `_health_payload()`. Add the two endpoints beside health/diagnostics routes; invoke `record_safe_simulation()` or `start_real_test(kind)` only after `_require_admin(request)`. Return `400` for an unsupported kind or an unreachable threshold and `409` while a real worker is running.

- [ ] **Step 4: Run API and smoke suites**

Run: `pytest tests/test_observability_api.py tests/test_web_smoke_ci.py -v`

Expected: PASS; health remains available when a metric reader reports unavailable.

- [ ] **Step 5: Commit the web integration**

```bash
git add picorgftp_sql/web/app.py tests/test_observability_api.py tests/test_web_smoke_ci.py
git commit -m "feat: expose backend resource diagnostics"
```

## Task 4: Add the compact resource indicator and Monitor settings UI

**Files:**
- Modify: `picorgftp_sql/web/static/index.html:18-35,435-450`
- Modify: `picorgftp_sql/web/static/app.js:1-165,5350-5580,7860-8000,11761-11795`
- Modify: `picorgftp_sql/web/static/app.css:184-303`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Consumes `payload.resources` from Task 3 and `state.settings.resource_monitor` from Task 1.
- Produces `renderResourceStatus(resources)`, `renderSettingsResourceMonitor()` and `runResourceMonitorTest(mode)`.
- Uses IDs `resourceStatus`, `resourceStatusText`, `resourceDetails`, `resourceDetailsList` and the tab key `monitor`.

- [ ] **Step 1: Write failing static UI tests**

```python
def test_resource_indicator_has_compact_and_accessible_detail_contract(self) -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")

    assert 'id="resourceStatus"' in html
    assert 'id="resourceDetails"' in html
    assert 'data-settings-tab="monitor"' in html
    assert "function renderResourceStatus" in source
    assert "function renderSettingsResourceMonitor" in source
    assert "/api/resource-monitor/simulate-safe" in source
    assert "/api/resource-monitor/real-test" in source
```

Add assertions that `replaceChildren` is used for detailed rows, details are controlled by `aria-expanded`, `show_status` hides only the indicator, and FTP cache writes go through `setFtpPreviewCache` from Task 5.

- [ ] **Step 2: Run the focused UI test and confirm it fails on missing markup/functions**

Run: `pytest tests/test_web_ui_integrity.py -k resource -v`

Expected: FAIL with the missing resource indicator assertion.

- [ ] **Step 3: Implement status rendering and controls**

```javascript
function renderResourceStatus(resources = {}) {
  const host = resources.host || {};
  const backend = resources.backend || {};
  if (!resourceStatus || !resourceStatusText) return;
  resourceStatus.hidden = state.settings?.resource_monitor?.show_status === false;
  resourceStatusText.textContent =
    `System: CPU ${formatPercent(host.cpu_percent)} · RAM ${formatPercent(host.memory_percent)} · DYSK ${formatPercent(host.disk_busy_percent)}\n` +
    `Backend: CPU ${formatPercent(backend.cpu_percent)} · RAM ${formatPercent(backend.memory_percent)} · I/O ${formatMib(backend.disk_io_bytes_per_second)}/s`;
  resourceStatus.dataset.level = resourceLevel(resources.detector || {});
  renderResourceDetails(resources);
}
```

Define the formatting helpers next to the existing `formatFileSize` helper so unavailable values do not become `NaN` in the header:

```javascript
function formatPercent(value) {
  return Number.isFinite(Number(value)) ? `${Math.round(Number(value))}%` : "brak danych";
}

function formatMib(bytes) {
  return Number.isFinite(Number(bytes)) ? (Number(bytes) / (1024 * 1024)).toFixed(1) + " MB" : "brak danych";
}

function resourceLevel(detector = {}) {
  return Array.isArray(detector.latched_metrics) && detector.latched_metrics.length ? "critical" : "normal";
}
```

Place the two-line control immediately below `.backend-health-indicator`; use a button and tooltip markup mirroring the accessible health control. Render detailed raw values, thresholds, sample timestamp, unavailable explanations and latch state using DOM nodes and `textContent`. Update it after every successful health poll and show an explicit unavailable state before the first sample.

Add a `Monitor` settings tab that saves `resource_monitor` through the existing `/api/settings` action. Its form contains the visibility checkbox, three numeric thresholds, a safe-simulation button and CPU/RAM/disk real-test buttons. Disable real-test buttons while a request is pending; display the server response verbatim through `textContent`, then call `pollBackendHealth()` to refresh the indicator. Style the compact status beneath health without widening the top bar, and make detail popovers work on hover, focus and click.

- [ ] **Step 4: Run UI integrity tests**

Run: `pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py -v`

Expected: PASS with existing backend-health accessibility tests unchanged.

- [ ] **Step 5: Commit the UI**

```bash
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py
git commit -m "feat: show backend resource status"
```

## Task 5: Bound audited memory-growth paths

**Files:**
- Modify: `picorgftp_sql/app.py:161-170,320-329,2438-2502,5024-5042`
- Modify: `picorgftp_sql/web/static/app.js:150-165,2876-3000`
- Modify: `picorgftp_sql/web/app.py:184-205,671-685,1106-1125,3495-3502`
- Modify: `tests/test_app_performance_helpers.py`
- Modify: `tests/test_web_ui_integrity.py`
- Test: `tests/test_observability_api.py`

**Interfaces:**
- Produces `THUMBNAIL_QUEUE_MAXSIZE` and non-blocking enqueue semantics that only mark a path pending after enqueue succeeds.
- Produces `setFtpPreviewCache(key, value)` with `FTP_PREVIEW_CACHE_LIMIT = 120`.
- Produces bounded cleanup of `_PROCESS_JOBS`, `_UPLOAD_SCAN_RESULTS` and `_RATE_LIMITS`.

- [ ] **Step 1: Write failing bounded-memory behavior tests**

```python
def test_queue_thumbnail_does_not_mark_path_pending_when_request_queue_is_full() -> None:
    harness = _ThumbnailHarness(maxsize=1)
    harness._thumb_request_queue.put_nowait((0, "old.png", 1, False))

    App._queue_thumbnail(harness, 2, "new.png")

    assert harness._thumb_pending_paths == {}
    assert harness._thumb_tokens[2] == 1
```

Add a retry assertion after removing the old queue entry. Add server tests that completed jobs above the retention/count bound are removed while a queued job remains, expired scan entries are removed after their backing file disappears, and expired rate-limit keys are pruned. Add static assertions for the FTP cache limit helper and all cache writes using it.

- [ ] **Step 2: Run focused tests and confirm current unbounded behavior fails them**

Run: `pytest tests/test_app_performance_helpers.py tests/test_observability_api.py -k "thumbnail or process_jobs or rate_limit" -v`

Expected: FAIL because thumbnail enqueue marks pending before a successful put and helper bounds do not exist.

- [ ] **Step 3: Implement caps without discarding active work**

```python
# app.py
THUMBNAIL_QUEUE_MAXSIZE = SLOT_GRID_COLUMNS * THUMBNAIL_MEMORY_ROWS * 2
B._thumb_request_queue = queue.Queue(maxsize=THUMBNAIL_QUEUE_MAXSIZE)
B._thumb_result_queue = queue.Queue(maxsize=THUMBNAIL_QUEUE_MAXSIZE)

try:
    B._thumb_request_queue.put_nowait((idx, path, token, content_fit))
except queue.Full:
    return
B._thumb_pending_paths[idx] = pending_key
```

Use `put_nowait` for thumbnail results as well; dropped results are stale display work and the next visible-window pass requeues them. Keep the destroy sentinel non-blocking.

```javascript
const FTP_PREVIEW_CACHE_LIMIT = 120;
function setFtpPreviewCache(key, value) {
  if (!key) return;
  state.ftpPreviewCache.delete(key);
  state.ftpPreviewCache.set(key, value);
  while (state.ftpPreviewCache.size > FTP_PREVIEW_CACHE_LIMIT) {
    state.ftpPreviewCache.delete(state.ftpPreviewCache.keys().next().value);
  }
}
```

Touch entries through this helper on cache read and replace direct `Map.set` calls. In web backend cleanup, preserve queued/running jobs, then keep only the newest completed jobs up to a documented maximum; prune expired rate-limit key lists and scan-result entries whose files no longer exist or whose timestamp is older than the upload-cache maximum age.

- [ ] **Step 4: Run safeguards and related workflow tests**

Run: `pytest tests/test_app_performance_helpers.py tests/test_observability_api.py tests/test_web_ui_integrity.py tests/test_web_workflow.py -v`

Expected: PASS; active jobs remain visible and cache bounds are exercised.

- [ ] **Step 5: Commit memory safeguards**

```bash
git add picorgftp_sql/app.py picorgftp_sql/web/app.py picorgftp_sql/web/static/app.js tests/test_app_performance_helpers.py tests/test_observability_api.py tests/test_web_ui_integrity.py
git commit -m "fix: bound resource monitoring caches"
```

## Task 6: Document and verify the complete feature

**Files:**
- Modify: `docs/web-panel.md:83-88`
- Test: `tests/test_web_smoke_ci.py`

**Interfaces:**
- Documents the resource badge, backend-only alert rule, unavailable disk metric and safe/real test semantics from Tasks 1–5.

- [ ] **Step 1: Write a failing documentation/source-integrity assertion**

```python
def test_web_panel_documents_backend_only_resource_alerts() -> None:
    docs = (ROOT / "docs" / "web-panel.md").read_text(encoding="utf-8").lower()

    assert "zasoby systemu" in docs
    assert "backendu" in docs
    assert "dwie kolejne próbki" in docs
    assert "test rzeczywisty" in docs
```

- [ ] **Step 2: Run the focused assertion and confirm the new documentation wording is absent**

Run: `pytest tests/test_source_integrity.py -k resource -v`

Expected: FAIL with missing documentation text.

- [ ] **Step 3: Document operational behavior**

Add a `## Zasoby backendu` section to `docs/web-panel.md`. State the five-second cadence, compact system/backend lines, backend-only two-sample alert rule, `brak danych` behavior for unavailable disk counters, administrative authorization, safe simulation semantics and hard limits/automatic cleanup of the real test. Include that the real test produces an alert only if the normal monitor detects a genuine threshold breach.

- [ ] **Step 4: Run all verification commands**

Run: `pytest -q`

Expected: PASS with zero failures.

Run: `python -m compileall -q picorgftp_sql`

Expected: exit code 0.

On Windows, start the web backend and run CPU, RAM and disk real tests separately. Confirm each has stopped, no `picorg_resource_test_*` directory remains, and the incident appears only when the ordinary sampler crosses its configured threshold.

- [ ] **Step 5: Commit documentation and final verification state**

```bash
git add docs/web-panel.md tests/test_source_integrity.py
git commit -m "docs: explain backend resource monitoring"
```
