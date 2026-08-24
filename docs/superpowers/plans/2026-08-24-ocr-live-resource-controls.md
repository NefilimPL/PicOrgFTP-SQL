# OCR live resource controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make both the OCR tester and background slot scanning use the selected OCR profiles through one worker pipeline, expose its stage-by-stage progress live, and keep OCR within practical CPU, RAM and disk-I/O limits without discarding work unnecessarily.

**Architecture:** The web process owns settings, queue persistence and HTTP APIs. A dedicated OCR worker process owns Paddle/OpenCV model lifetime and receives one staged job at a time through an IPC command queue. It publishes serializable progress events to the web process. A Windows Job Object continuously caps its CPU; a controller evaluates RAM, disk-I/O and admission limits at safe stage boundaries. The fast profile produces candidate regions; where both profiles are selected, only those regions are sent to the accurate profile. Queue lease expiry is based on the last user activity and is extended after each completed OCR job.

**Tech Stack:** Python 3.12, FastAPI, multiprocessing, ctypes/Windows Job Object APIs, psutil/resource monitor abstractions, SQLite, vanilla JavaScript and CSS, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-ocr-live-resource-controls-design.md`

## Global Constraints

- Preserve the existing OCR profile-selection semantics: fast only = full image fast; accurate only = full image accurate; both = fast full image, then accurate only for fast candidate crops.
- Do not interrupt a running Paddle inference. Apply RAM and disk controls before the next stage/crop; CPU must be capped continuously for the worker process.
- The existing `pause_cpu_percent` is an admission gate only. It never means the configured CPU target and it does not kill active inference.
- Browser progress must describe facts observed at stage boundaries; never simulate token-level OCR progress that Paddle does not expose.
- The tester is ephemeral: on admission failure it returns/streams a paused state and is never persisted in the crop-job queue.
- Background jobs remain persistent, recoverable after web-process restart, and may only be requeued at a safe boundary.
- Add migrations compatibly; existing databases and existing `ocr_crop_jobs` data must remain readable.
- Treat Windows-specific controls as optional runtime capabilities with an explicit diagnostic fallback for non-Windows/test environments.

---

## File map

| Area | Files | Purpose |
| --- | --- | --- |
| OCR settings/policy | `picorgftp_sql/ocr_settings.py`, `picorgftp_sql/services/ocr_resource_policy.py` | Persist new limits and turn telemetry into deterministic admission/throttle decisions. |
| Worker and Windows controls | `picorgftp_sql/services/ocr_worker_process.py`, `picorgftp_sql/services/windows_job_limits.py` | Isolated model process, IPC protocol, continuous CPU cap and low-I/O priority. |
| OCR pipeline | `picorgftp_sql/services/image_dimensions.py`, `picorgftp_sql/services/ocr_pipeline.py` | Stage-aware profile orchestration and visual candidate/crop events. |
| Progress and queue lease | `picorgftp_sql/services/ocr_progress.py`, `picorgftp_sql/services/ocr_queue.py`, `picorgftp_sql/sqlite_store.py` | Run snapshots/events, cancellation, persistent job transitions and activity-based lease. |
| Web integration | `picorgftp_sql/web/app.py`, `picorgftp_sql/resource_monitor.py` | Start/stop worker, telemetry registration, HTTP APIs and scheduler wiring. |
| UI | `picorgftp_sql/web/static/app.js`, `picorgftp_sql/web/static/app.css` | Settings sliders/units, test event polling, overlays, crop gallery and pause/cancel state. |
| Tests | `tests/test_ocr_settings.py`, `tests/test_ocr_resource_policy.py`, `tests/test_ocr_worker_process.py`, `tests/test_image_dimensions.py`, `tests/test_ocr_queue.py`, `tests/test_ocr_progress.py`, `tests/test_pimcore_web.py`, `tests/test_web_ui_integrity.py` | Unit, integration, migration and UI-contract coverage. |

## Task 1: Add durable resource-control settings and a pure policy evaluator

**Files:**
- Modify: `picorgftp_sql/ocr_settings.py`
- Create: `picorgftp_sql/services/ocr_resource_policy.py`
- Modify: `tests/test_ocr_settings.py`
- Create: `tests/test_ocr_resource_policy.py`

- [ ] **Step 1: Write the failing settings and policy tests.**

  Cover defaults and normalization for:
  - `max_cpu_percent` (continuous worker target, default 35),
  - `pause_cpu_percent` (host admission gate, default 85),
  - `max_memory_mode` (`percent` or `gigabytes`), `max_memory_percent` (default 30), `max_memory_gb` (default derived from host total when rendering, persisted as explicit positive number),
  - `max_disk_busy_percent` (default 80; disk active-time percentage, not free capacity),
  - profile selection and legacy OCR-settings documents.

  Specify a small immutable telemetry input and decision output so tests do not depend on psutil:

  ```python
  ResourceTelemetry(cpu_percent=90, memory_used_bytes=..., memory_total_bytes=..., disk_busy_percent=82)
  ResourceDecision(action="defer", reason="host_cpu_admission", retry_after_seconds=...)
  ```

  Test the required distinctions: an over-RAM or over-disk state returns `throttle`; over `pause_cpu_percent` before a stage returns `defer`; a currently executing stage is never represented by an interrupt decision; below all limits returns `run`.

  Run: `.venv-build\Scripts\python.exe -m pytest tests\test_ocr_settings.py tests\test_ocr_resource_policy.py -q`  
  Expected: FAIL because fields and policy module do not exist.

- [ ] **Step 2: Implement normalized settings with backwards-compatible defaults.**

  Extend `normalize_ocr_settings`, storage serialization and public settings response. Reject/normalize invalid unit names, NaN, negative values and thresholds above 100 where applicable. Keep the existing field names and their behavior for clients that do not send the new fields.

  Add helpers that make conversion explicit, for example `memory_limit_bytes(settings, total_memory_bytes)` and `memory_limit_display(settings, total_memory_bytes)`, rather than putting conversion logic in JavaScript or the worker.

- [ ] **Step 3: Implement `OcrResourcePolicy`.**

  Give it only settings and `ResourceTelemetry`; it returns `run`, `throttle`, or `defer` plus a machine-readable reason. CPU admission is evaluated before beginning a new stage/job. RAM and disk are soft limits evaluated between stages/crops and recommend a backoff duration. The policy must not inspect global process state or sleep itself.

- [ ] **Step 4: Re-run targeted tests and commit.**

  Run the command from Step 1; expected PASS.  
  Commit: `feat: add OCR resource control settings and policy`

## Task 2: Create a live, serializable OCR progress model

**Files:**
- Create: `picorgftp_sql/services/ocr_progress.py`
- Create: `tests/test_ocr_progress.py`
- Modify: `picorgftp_sql/sqlite_store.py`
- Modify: `tests/test_ocr_cache.py`

- [ ] **Step 1: Write failing progress-store tests.**

  Define a run model usable by both a test and a queued crop job. Tests should verify monotonically increasing sequence numbers, capped event retention, current snapshot, cancellation request, and redacted error storage. Exercise events such as:

  ```python
  {"kind": "stage_started", "stage": "fast_full_image"}
  {"kind": "candidate_regions", "regions": [{"bbox": [x, y, w, h], "label": "fast", "confidence": 0.91}]}
  {"kind": "crop_started", "stage": "accurate_crop", "crop_index": 2, "crop_total": 5, "bbox": [...]}
  {"kind": "throttled", "resource": "memory", "limit": ..., "observed": ...}
  ```

  Include an SQLite migration test that opens a pre-existing schema, migrates it, and leaves prior `ocr_crop_jobs` rows intact. Persist only background-job run summaries/events needed after restart; allow tester runs to reside in bounded in-memory storage with a short TTL.

  Run: `.venv-build\Scripts\python.exe -m pytest tests\test_ocr_progress.py tests\test_ocr_cache.py -q`  
  Expected: FAIL.

- [ ] **Step 2: Implement `OcrProgressRegistry` and storage migration.**

  Introduce explicit types/dataclasses for `OcrRunSnapshot` and `OcrProgressEvent`. The registry API should be small:

  ```python
  create_run(kind: Literal["test", "queue"], job_id: int | None) -> str
  publish(run_id: str, kind: str, **payload) -> OcrProgressEvent
  snapshot(run_id: str, after_sequence: int = 0) -> OcrRunSnapshot
  request_cancel(run_id: str) -> None
  is_cancel_requested(run_id: str) -> bool
  finalize(run_id: str, state: str, result: dict | None = None, error: str | None = None) -> None
  ```

  Keep image payloads out of events. Events refer to a crop by bbox and a signed/temporary thumbnail route generated by the web layer. Add a migration table keyed by `run_id`/`sequence` only if completed queue-job history needs persistence; do not overload `result_json` with unbounded event arrays.

- [ ] **Step 3: Implement pruning and recovery rules.**

  Bound retained test events (for example the latest 200, 15-minute TTL) and prune completed queue-event history according to the existing cache/maintenance cadence. On restart, mark orphaned in-progress runs as recoverable and let the queue job re-enter `pending` instead of showing a permanently running state.

- [ ] **Step 4: Re-run tests and commit.**

  Run the command from Step 1; expected PASS.  
  Commit: `feat: track live OCR progress and cancellation`

## Task 3: Add Windows worker controls and an IPC-safe worker process

**Files:**
- Create: `picorgftp_sql/services/windows_job_limits.py`
- Create: `picorgftp_sql/services/ocr_worker_process.py`
- Create: `tests/test_ocr_worker_process.py`
- Modify: `picorgftp_sql/resource_monitor.py`

- [ ] **Step 1: Write failing platform-adapter and worker-protocol tests.**

  Mock the Win32 adapter to assert that the worker is assigned to a Job Object and receives a CPU hard-cap configuration equal to `max_cpu_percent`. Test non-Windows/API failure fallback returns a capability warning instead of failing OCR.

  For the worker protocol, use a deterministic fake pipeline and assert: command acceptance, PID publication, progress forwarding, result forwarding, cancellation observed only between stages, and clean shutdown. Do not load Paddle in these tests.

  Run: `.venv-build\Scripts\python.exe -m pytest tests\test_ocr_worker_process.py -q`  
  Expected: FAIL.

- [ ] **Step 2: Implement `WindowsJobLimits` behind a narrow adapter.**

  In `windows_job_limits.py`, isolate all `ctypes` structs/constants and expose a testable API such as:

  ```python
  apply_to_process(pid: int, cpu_percent: int) -> JobLimitCapability
  set_low_io_priority(pid: int) -> None
  close() -> None
  ```

  Use `SetInformationJobObject(...JobObjectCpuRateControlInformation...)` with hard-cap mode. Keep the Job Object handle alive for the worker lifetime. Assign I/O priority only as a best-effort Windows optimization; it is not a substitute for the disk-busy policy. Record the actual capability/status for diagnostics.

- [ ] **Step 3: Implement a single-job `OcrWorkerProcess`.**

  Create the process with the `spawn` context so Windows behavior matches packaged execution. The parent-facing API is `start()`, `submit(WorkerJob)`, `poll_events()`, `cancel(run_id)`, `update_limits(settings)`, and `stop(timeout)`. All messages must be basic dict/list/string/number values so no model or `Path` object crosses process boundaries.

  The child imports/initializes OCR lazily after startup, applies Windows limits to itself, executes one job at a time, and emits `ready`, `stage_started`, `stage_finished`, `throttled`, `result`, and `error` messages. It polls cancellation and resource-policy commands only at declared safe boundaries.

- [ ] **Step 4: Register worker PID with resource monitoring.**

  Add a focused registration API to `ResourceMonitor` for the external OCR worker PID. Reuse existing backend metric readers, but do not reuse or overwrite the monitor's simulation-worker ownership fields. Snapshot data must expose both host metrics (including disk busy) and worker process CPU/RAM/I/O rates to the policy and diagnostics route.

- [ ] **Step 5: Re-run tests and commit.**

  Run the command from Step 1; expected PASS.  
  Commit: `feat: run OCR in a controlled worker process`

## Task 4: Make OCR execution explicitly stage-aware and visualizable

**Files:**
- Modify: `picorgftp_sql/services/image_dimensions.py`
- Create: `picorgftp_sql/services/ocr_pipeline.py`
- Modify: `tests/test_image_dimensions.py`
- Modify: `tests/test_ocr_worker_process.py`

- [ ] **Step 1: Write failing pipeline tests for each profile combination.**

  With fake recognizers/images, assert exact calls and events:

  - `fast`: one full-image fast inference and candidate/recognized-region events;
  - `accurate`: one full-image accurate inference;
  - `fast + accurate`: full-image fast inference, then accurate inference only on fast candidate crop images;
  - no profiles: a validation error, never a hidden default recognizer.

  Verify stable coordinate translation from crop-local accurate boxes back to source-image boxes, duplicate merge behavior, and a `crop_started` event that identifies every crop sent to the accurate model.

  Run: `.venv-build\Scripts\python.exe -m pytest tests\test_image_dimensions.py tests\test_ocr_worker_process.py -q`  
  Expected: FAIL.

- [ ] **Step 2: Extract the pipeline from synchronous convenience APIs.**

  Keep `analyze_image_values` as a backward-compatible synchronous wrapper, but implement it via `run_ocr_pipeline(...)`. The pipeline accepts `profile_ids`, an optional `on_event` callback, a `should_cancel` callback, and a `before_stage` callback that returns a resource decision.

  Ensure that an accurate crop is encoded from the source image in a bounded, temporary location and released immediately after its inference. Avoid materializing every enlarged crop in memory at once. Emit source-coordinate regions and model name for overlays; do not emit raw OCR internals.

- [ ] **Step 3: Integrate resource-safe boundaries.**

  Before full-image stages and before each accurate crop, call `before_stage`. For `throttle`, publish state, sleep/backoff in the worker, optionally trigger safe memory cleanup, then re-evaluate. For `defer`, return an unfinished/deferred result without beginning the next stage. Never abort an in-flight call into Paddle.

- [ ] **Step 4: Re-run tests and commit.**

  Run the command from Step 1; expected PASS.  
  Commit: `feat: expose staged OCR pipeline progress`

## Task 5: Correct queue admission, activity lease and extension behavior

**Files:**
- Modify: `picorgftp_sql/services/ocr_queue.py`
- Modify: `picorgftp_sql/services/ocr_worker.py`
- Modify: `picorgftp_sql/sqlite_store.py`
- Modify: `tests/test_ocr_queue.py`

- [ ] **Step 1: Write failing scheduler/lease tests.**

  Use an injected clock to prove:

  - no job starts while last user activity is within the configured idle window;
  - `pause_cpu_percent` defers a pending job and preserves it in the queue;
  - `max_cpu_percent` does **not** reject a job at the scheduler level (the Job Object owns continuous CPU limiting);
  - a 60-minute base lease is measured from latest user activity, not submit time;
  - every completed OCR job adds 30 minutes of lease extension for subsequent work, so a ten-job backlog cannot time out merely because its enqueue timestamp is old;
  - failed/requeued jobs do not gain an extension; a user action resets/recomputes the lease deterministically.

  Run: `.venv-build\Scripts\python.exe -m pytest tests\test_ocr_queue.py -q`  
  Expected: FAIL against the old CPU-gating scheduler.

- [ ] **Step 2: Introduce explicit queue lease state.**

  Implement an `OcrQueueLease` (stored with queue metadata or deterministically reconstructed with durable completion timestamps) whose effective expiry is:

  ```text
  last_user_activity + 60 minutes + (successful_jobs_since_activity × 30 minutes)
  ```

  Ensure the state survives ordinary web-process restart when queue records do. Define the single source of activity events: meaningful authenticated/UI HTTP activity already tracked by middleware, excluding OCR event-polling so watching a long run cannot artificially prolong it.

- [ ] **Step 3: Change scheduler transitions.**

  The scheduler should claim only when idle, lease-valid and admission CPU is below `pause_cpu_percent`. A `defer` from the worker returns a claimed job to `pending` without an error. Cancellation is an explicit terminal/cancelled state. Preserve existing retries and avoid a tight requeue loop by setting retry timestamps/backoff.

- [ ] **Step 4: Re-run tests and commit.**

  Run the command from Step 1; expected PASS.  
  Commit: `feat: base OCR queue lease on user activity`

## Task 6: Wire worker, settings, resource policy and APIs into FastAPI

**Files:**
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/resource_monitor.py`
- Modify: `tests/test_pimcore_web.py`
- Modify: `tests/test_ocr_settings.py`

- [ ] **Step 1: Write failing API and lifecycle tests.**

  Test application startup starts exactly one fake/controlled OCR worker and shutdown stops it. Cover:

  - test upload creates a test `run_id`, submits the currently selected profiles, and returns immediately;
  - `GET /api/settings/ocr/runs/{run_id}?after_sequence=N` returns snapshot plus ordered incremental events;
  - `POST /api/settings/ocr/runs/{run_id}/cancel` requests safe-boundary cancellation;
  - test admission failure reports `paused`/reason and creates no `ocr_crop_jobs` row;
  - background job messages update the existing queue job and persist final numerical results;
  - settings changes are sent to the existing worker for subsequent boundaries and its CPU cap is refreshed;
  - a diagnostics response includes worker PID/capability and relevant host/worker telemetry but not filesystem-sensitive values.

  Run: `.venv-build\Scripts\python.exe -m pytest tests\test_pimcore_web.py tests\test_ocr_settings.py -q`  
  Expected: FAIL.

- [ ] **Step 2: Replace direct OCR calls with a central dispatch service.**

  Build an app-owned `OcrExecutionService` around `OcrWorkerProcess`, `OcrProgressRegistry`, `OcrResourcePolicy` and the resource monitor. It is the sole caller of the process and maps worker events to snapshots/database updates. Use it from the tester, initial image collection and queued crop processing, so all three honor the same profile list and controls.

  Maintain a synchronous adapter only where the calling path cannot yet be asynchronous; it must wait for the central dispatch result, never instantiate a recognizer in the web process.

- [ ] **Step 3: Implement API contracts and cancellation cleanup.**

  The test-start route returns `202` with `{run_id, state, events_url, cancel_url}`. The event route uses polling (initially 500–1000 ms) and `after_sequence` to avoid transferring duplicate events. Preserve old clients by keeping/temporarily adapting the former analysis route until `app.js` uses the new contract.

  On a worker crash, mark the test run failed with an actionable diagnostic and safely requeue any affected background job. On app shutdown, request worker stop and requeue uncompleted claimed jobs without leaving crop locks.

- [ ] **Step 4: Re-run tests and commit.**

  Run the command from Step 1; expected PASS.  
  Commit: `feat: serve live controlled OCR runs`

## Task 7: Build live tester visualization and resource-limit controls

**Files:**
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_web_ui_integrity.py`
- Modify: `tests/test_pimcore_web.py`

- [ ] **Step 1: Write UI-contract tests first.**

  Extend integrity tests to require the setting control IDs, unit-mode inputs, accessible values, test run polling/cancel hooks and renderer functions for candidate overlays and accurate-crop previews. Add backend HTML/API assertions for any initial data attributes the UI consumes.

  Run: `.venv-build\Scripts\python.exe -m pytest tests\test_web_ui_integrity.py tests\test_pimcore_web.py -q`  
  Expected: FAIL.

- [ ] **Step 2: Implement settings controls.**

  Add a CPU target slider, CPU admission-gate slider, RAM mode toggle (% / GB) with live conversion based on reported physical total RAM, RAM target slider/number control, and a disk-busy-percent slider. Clearly label these as *current usage* limits. Validate and serialize through the settings API; do not rely on browser-only validation.

- [ ] **Step 3: Implement incremental run rendering.**

  After upload, poll the new run endpoint until a terminal state. Render a chronological stage timeline and a source-image canvas with colors/legend by model:

  - fast detected sectors/candidates;
  - accurate result regions;
  - currently processed accurate crop, with crop number and source bbox.

  Display a compact crop preview strip using server-provided temporary crop/thumbnail URLs only when present. Show `throttled` and `paused` messages with resource, observed value, configured limit and next retry state. Add a visible safe cancel button. Disable/re-enable actions predictably and clean up polling timers when navigating away.

- [ ] **Step 4: Make the background queue inspectable.**

  Expand existing queue rendering with current run stage, last resource pause, retry/lease information and a cancellation control for pending/active jobs. Keep tester state separate from persistent queue state so a test never appears as a queued background job.

- [ ] **Step 5: Re-run tests and commit.**

  Run the command from Step 1; expected PASS.  
  Commit: `feat: show OCR work and resource throttling live`

## Task 8: Package, regression-test and document operational behavior

**Files:**
- Modify: `Generator exe/build_web_exe.ps1` (only if the smoke build proves a new hidden import/data collection is required)
- Modify: `README.md` or existing OCR settings documentation
- Modify: relevant tests from Tasks 1–7 as needed

- [ ] **Step 1: Add a packaged-runtime smoke check where feasible.**

  Verify the new worker module and `ctypes` Windows adapter are collected by the existing PyInstaller options. Do not add broad hidden-import flags without reproducing a missing import. If build scripting must change, add a narrow package/module inclusion and document why.

- [ ] **Step 2: Document the controls in user language.**

  Explain the difference between CPU target, CPU admission gate, RAM soft target, disk-busy soft target, and why a running inference completes its current stage before yielding. Document both-profile behavior and the 60-minutes-from-last-activity plus 30-minutes-per-successful-job queue lease rule.

- [ ] **Step 3: Run complete verification.**

  Run:

  ```powershell
  .venv-build\Scripts\python.exe -m pytest tests\test_image_dimensions.py tests\test_pimcore_web.py tests\test_ocr_cache.py tests\test_ocr_queue.py tests\test_ocr_settings.py tests\test_ocr_resource_policy.py tests\test_ocr_progress.py tests\test_ocr_worker_process.py tests\test_web_ui_integrity.py -q
  git diff --check
  ```

  If the test environment is Windows, additionally perform a short manual smoke test: start the server, select both profiles, upload the supplied dimension image, confirm fast candidate overlays followed by accurate crop events, and lower a resource limit to observe a between-stage throttle.

- [ ] **Step 4: Commit final integration and report build status accurately.**

  Commit: `feat: complete live OCR resource controls` (or only the remaining documentation/package delta if prior tasks were committed individually). Report test output and whether an EXE was actually built; do not infer a build artifact from installation logs alone.

## Plan review checklist

- [ ] Each approved requirement is covered: common profile pipeline, live sectors/crops, continuous CPU cap, RAM/disk soft limits, separate CPU gate, test no-queue behavior, and activity-based extensible queue lease.
- [ ] Every external boundary has a test double: Win32 adapter, worker IPC, resource telemetry, clock, and OCR recognizers.
- [ ] No plan step requires force-killing Paddle inference or uses disk capacity as a substitute for disk I/O utilization.
- [ ] Database changes are additive/migrated and do not rewrite existing OCR job data.
