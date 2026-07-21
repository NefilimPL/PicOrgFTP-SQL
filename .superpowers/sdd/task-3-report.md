# Task 3 report: resource-monitor web integration

## Status and commit

- Status: complete on branch `dev`.
- Commit subject: `feat: expose backend resource diagnostics`.
- Task files: `picorgftp_sql/web/app.py`, `tests/test_observability_api.py`,
  `tests/test_web_smoke_ci.py`, and this report.

## Scope implemented

- Added the application `ResourceMonitor` singleton using normalized
  `resource_monitor` configuration, active/queued job counts, active-client count,
  and the structured observability emitter.
- Started the monitor after runtime initialization and stopped it before the
  notification worker during application shutdown.
- Added the cached public resource snapshot to `/api/health`; the request path
  never invokes `sample_once()` or a native metric reader.
- Added administrator-only, CSRF-protected safe-simulation and bounded real-test
  endpoints with the closed `ok`/`message`/`resources`/`test` response contract.
- Mapped unsupported or unreachable real tests to HTTP 400 and concurrent real
  workers to HTTP 409. The real endpoint calls only `start_real_test(kind)` and
  does not emit or inject an incident itself.
- Isolated the observability API fixture's shared login rate-limit state so the
  expanded authenticated suite remains order-independent.
- Did not change `picorgftp_sql/resource_monitor.py` or its Task 2 behavior.

## TDD evidence

### RED

```powershell
$env:PYTHONHOME = 'C:\Users\k.bober\AppData\Local\Programs\Python\Python314'
& 'C:\Python314\python.exe' -m pytest tests/test_observability_api.py -k 'resource or health' -v --basetemp 'tmp_test/task3_red_api'
```

Result: 10 failed and 4 passed. Failures were the expected missing
`_RESOURCE_MONITOR`, health projection, endpoints, and lifecycle integration.

### GREEN and related verification

- Focused API command with `tmp_test/task3_green_api`: 14 passed.
- Required API and smoke suites with `tmp_test/task3_related_retry`: 67 passed,
  3 subtests passed.
- Fresh full suite with `tmp_test/task3_full_retry`: 988 passed, 52 subtests
  passed, with 13 existing FastAPI/Starlette deprecation warnings.
- `git diff --check`: clean.

All pytest commands used the required Python 3.14 `PYTHONHOME` and
`C:\Python314\python.exe` invocation.

## Self-review

- Confirmed health reads only `latest_public_snapshot()` and still returns 200
  for cached unavailable host/backend metrics.
- Confirmed both mutating routes authenticate before invoking the monitor and
  rely on the existing middleware for CSRF rejection.
- Confirmed safe simulation persists exactly one event labelled
  `test_mode="safe"` through the monitor.
- Confirmed real-test execution is delegated through `start_real_test(kind)` in
  the request threadpool and contains no direct `emit_event()` call.
- Confirmed lifecycle tests enforce one start/stop call and the required runtime
  and notification-worker ordering.
- Confirmed the working diff contains no resource-monitor internal, plan, or
  ledger edits.

## Residual risks

- The test suite uses controlled monitor doubles for real-test HTTP execution;
  it intentionally does not launch a live CPU, memory, or disk load worker.
- Existing framework deprecation warnings remain unrelated to this task.
