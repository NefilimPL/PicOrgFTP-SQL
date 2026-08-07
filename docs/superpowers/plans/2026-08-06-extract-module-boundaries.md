# Extract Module Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the web, desktop FTP preview, and frontend responsibilities into independently testable modules without changing application behavior.

**Architecture:** `web/app.py` remains the composition root and passes typed dependency containers to routers. The desktop root delegates asynchronous FTP preview coordination to a Tk-free controller. Browser modules expose APIs through the existing `window.PicOrg` namespace; `app.js` only composes their dependencies.

**Tech Stack:** Python 3.11+, FastAPI/APIRouter, dataclasses, pytest, Node.js built-in test runner, PyInstaller build configuration.

## Global Constraints

- Preserve every existing route path, status code, response shape, middleware exclusion, and auth callback.
- New services and controllers must not import `picorgftp_sql.web.app` or `picorgftp_sql.app`.
- Keep Tk access on the UI thread; controller workers never access widgets.
- Do not introduce browser globals outside `window.PicOrg`.
- Include every new static asset in template order and the PyInstaller asset mechanism.
- Remove an old shim only after an exact call-site search identifies no production consumer.
- Full post-change benchmark median may differ by at most 5% from the recorded baseline.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `web/process_models.py` | process-only snapshots and request/response models |
| `web/process_api.py` | process router and injected dependencies |
| `web/runtime_api.py` | runtime, file-index, and presence router |
| `desktop_ftp_preview.py` | thread-safe latest-request FTP preview controller |
| `static/autocomplete.js` | autocomplete lifecycle and DOM adapter |
| `static/process-jobs.js` | process-job refresh deduplication and runtime reaction |
| `static/app.js` | browser composition root |
| `tests/test_module_boundaries.py` | route snapshots and import boundaries |
| `tests/js/*.test.js` | browser-module contracts |

### Task 1: Establish characterization guards and a benchmark baseline

**Files:**
- Create: `tests/test_module_boundaries.py`
- Modify: `tests/test_web_app_files.py`, `tests/test_app_performance_helpers.py`

- [ ] **Step 1: Add route and import characterization tests**

```python
def test_services_do_not_import_composition_roots():
    for path in SERVICE_MODULES:
        assert "picorgftp_sql.web.app" not in path.read_text(encoding="utf-8")
        assert "picorgftp_sql.app" not in path.read_text(encoding="utf-8")

def test_route_contract_snapshot_is_stable():
    assert route_snapshot(create_app()) == EXPECTED_ROUTES
```

- [ ] **Step 2: Record five import/start samples and their median**

Run: `python -m pytest tests/test_module_boundaries.py tests/test_web_app_files.py tests/test_app_performance_helpers.py -q`.

Expected: a committed baseline fixture reports the median in milliseconds and all existing contracts pass.

### Task 2: Extract the process API router

**Files:**
- Create: `picorgftp_sql/web/process_models.py`, `picorgftp_sql/web/process_api.py`, `tests/test_web_process_api.py`
- Modify: `picorgftp_sql/web/app.py:6757-6835`, `tests/test_web_app_files.py`, `tests/test_module_boundaries.py`

**Interfaces:**
- Produces: `ProcessApiDependencies` and `build_process_router(dependencies) -> APIRouter`.

- [ ] **Step 1: Add isolated router coverage**

```python
dependencies = ProcessApiDependencies(queue=queue, stage_form=stage_form,
    current_user=lambda _: "alice", cache_scope=lambda _r, _u: "scope-a", job_store=job_store)
app = FastAPI(); app.include_router(build_process_router(dependencies))
assert TestClient(app).post("/api/process/background", files=FILES, data=FORM).status_code == 200
queue.reserve.assert_called_once_with("scope-a")
```

- [ ] **Step 2: Run the isolated test before extraction**

Run: `python -m pytest tests/test_web_process_api.py -v`.

- [ ] **Step 3: Move process-only models and routes**

Put `_ProcessFormSnapshot` equivalents in `process_models.py`. The dependency dataclass receives queue, staging callback, user callback, cache scope callback, and job store. Include the returned router once in `web/app.py`; delete only the old decorated endpoints.

- [ ] **Step 4: Verify contracts**

Run: `python -m pytest tests/test_web_process_api.py tests/test_module_boundaries.py tests/test_web_app_files.py -k "process or route_contract or services_do_not_import" -q`.

### Task 3: Extract runtime and presence API router

**Files:**
- Create: `picorgftp_sql/web/runtime_api.py`, `tests/test_web_runtime_api.py`
- Modify: `picorgftp_sql/web/app.py:5009-5500`, `tests/test_runtime_status.py`, `tests/test_active_clients_registry.py`, `tests/test_module_boundaries.py`

**Interfaces:**
- Produces: `RuntimeApiDependencies` and `build_runtime_router(dependencies) -> APIRouter`.

- [ ] **Step 1: Add router delegation tests**

```python
app = FastAPI(); app.include_router(build_runtime_router(dependencies))
client = TestClient(app)
assert client.get("/api/runtime-status").json() == runtime_payload()
assert client.get("/api/server/presence").status_code == 200
```

- [ ] **Step 2: Move endpoint-only code and retain middleware**

The router owns runtime status, file-index status/refresh, presence GET/leave, and existing lightweight summary endpoints. `web/app.py` retains session parsing and the one `active_clients.record` middleware call.

- [ ] **Step 3: Verify presence exclusions and route snapshot**

Run: `python -m pytest tests/test_web_runtime_api.py tests/test_runtime_status.py tests/test_active_clients_registry.py tests/test_module_boundaries.py tests/test_web_app_files.py -k "runtime or presence or file_index or route_contract" -q`.

### Task 4: Extract the desktop FTP preview controller

**Files:**
- Create: `picorgftp_sql/desktop_ftp_preview.py`, `tests/test_desktop_ftp_preview.py`
- Modify: `picorgftp_sql/app.py:620,6282-6305`, `tests/test_app_performance_helpers.py`, `tests/test_module_boundaries.py`

**Interfaces:**
- Produces: `DesktopFtpPreviewController.request(ean, on_success, on_error) -> int`, `cancel_current()`, and `close()`.

- [ ] **Step 1: Add stale-result and shutdown tests**

```python
first = controller.request("5901", on_success=results.append, on_error=errors.append)
second = controller.request("5902", on_success=results.append, on_error=errors.append)
downloader.finish(first, preview_result("5901")); downloader.finish(second, preview_result("5902"))
for callback in scheduled: callback()
assert [item.ean for item in results] == ["5902"]
```

- [ ] **Step 2: Implement the controller without Tk imports**

Store request id and cancellation event under a lock. The injected downloader works off-thread; the injected scheduler returns to UI code and checks the current request id again. `close()` cancels the outstanding request and closes the temp manager once.

- [ ] **Step 3: Switch `App` and verify**

Run: `python -m pytest tests/test_desktop_ftp_preview.py tests/test_app_performance_helpers.py tests/test_ftp_service.py tests/test_module_boundaries.py -q`.

### Task 5: Extract autocomplete frontend module

**Files:**
- Create: `picorgftp_sql/web/static/autocomplete.js`, `tests/js/helpers.js`, `tests/js/autocomplete.test.js`
- Modify: `picorgftp_sql/web/static/app.js`, `picorgftp_sql/web/static/index.html`, `tests/test_module_boundaries.py`

**Interfaces:**
- Produces: `window.PicOrg.AutocompleteController` and `window.PicOrg.setupAutocomplete(dependencies)`.

- [ ] **Step 1: Add latest-request controller test**

```javascript
const controller = new window.PicOrg.AutocompleteController({
  fieldName: "name", localSuggestions: () => ["LOCAL"], remoteSuggestions: () => remote.promise,
  render: values => rendered.push(values), delayMs: 0, setTimer: callback => (callback(), 1), clearTimer: () => {},
});
controller.refresh(); remote.resolve(["REMOTE"]); await controller.pendingForTest();
assert.deepEqual(rendered.at(-1), ["LOCAL", "REMOTE"]);
```

- [ ] **Step 2: Move debounce, cancellation, merge, ARIA, and keyboard lifecycle**

Keep DOM specifics behind callbacks or `setupAutocomplete`; module load itself must have no side effects. `app.js` builds one dependency object and calls setup once.

- [ ] **Step 3: Add asset order and run Node checks**

Insert scripts in this order: `latest-request.js`, `autocomplete.js`, `runtime-status.js`, `process-jobs.js`, `app.js`.

Run: `node --test tests/js/latest-request.test.js tests/js/autocomplete.test.js`; `node --check picorgftp_sql/web/static/autocomplete.js`; `node --check picorgftp_sql/web/static/app.js`.

### Task 6: Extract process-jobs frontend module

**Files:**
- Create: `picorgftp_sql/web/static/process-jobs.js`, `tests/js/process-jobs.test.js`
- Modify: `picorgftp_sql/web/static/app.js`, `picorgftp_sql/web/static/index.html`, `tests/test_module_boundaries.py`

**Interfaces:**
- Produces: `window.PicOrg.ProcessJobsController({ fetchJobs, render, timerApi })` with `refresh()` returning the shared in-flight promise.

- [ ] **Step 1: Add refresh-deduplication test**

```javascript
const first = controller.refresh(); const second = controller.refresh();
assert.equal(requests, 1);
pending.resolve({ jobs: [] }); await Promise.all([first, second]);
```

- [ ] **Step 2: Move queue fetch/state/render orchestration**

Keep a single in-flight refresh, runtime version, and active job. Do not add a permanent poller; the runtime poller invokes a version-change callback or callers invoke `refresh()`.

- [ ] **Step 3: Verify module and runtime-poller interaction**

Run: `node --test tests/js/process-jobs.test.js tests/js/runtime-status.test.js`; `node --check picorgftp_sql/web/static/process-jobs.js`; `node --check picorgftp_sql/web/static/app.js`.

### Task 7: Remove proven-dead shims, package assets, and commit

**Files:**
- Modify: `picorgftp_sql/web/app.py`, `picorgftp_sql/app.py`, `picorgftp_sql/web/static/app.js`, `Generator exe/build_common.ps1`, `tests/test_build_exe_workflow.py`, `docs/superpowers/STATUS.md`

- [ ] **Step 1: Search every old shim before deleting it**

Run: `rg -n "def (_save_upload|_queue_process_job|_flush_active_clients_locked)|function (setupAutocomplete|scheduleProcessJobPoll)" picorgftp_sql tests`.

Expected: each candidate is either a single canonical definition or an identified test reference. Delete only the old duplicate after its calls are migrated.

- [ ] **Step 2: Add all four static assets to the build test and configuration**

Assert that `latest-request.js`, `autocomplete.js`, `runtime-status.js`, and `process-jobs.js` occur in the generated PyInstaller configuration alongside `app.js`.

- [ ] **Step 3: Run characterization, Node, build, and full regression**

Run: `python -m pytest tests/test_module_boundaries.py tests/test_web_process_api.py tests/test_web_runtime_api.py tests/test_desktop_ftp_preview.py tests/test_build_exe_workflow.py tests/test_web_app_files.py tests/test_app_performance_helpers.py -q`; `node --test tests/js/latest-request.test.js tests/js/autocomplete.test.js tests/js/runtime-status.test.js tests/js/process-jobs.test.js`; `python -m pytest -q`; `python -m compileall -q picorgftp_sql tests`; `node --check picorgftp_sql/web/static/app.js`; `git diff --check`.

- [ ] **Step 4: Compare benchmark medians and update status**

Run the five-sample import/start benchmark from Task 1. Compute `abs(after - before) / before`; investigate any median difference above `0.05`. Record module-boundary completion, commit, commands, and measurements in `docs/superpowers/STATUS.md`.

- [ ] **Step 5: Commit the second stage**

```bash
git add picorgftp_sql tests docs/superpowers "Generator exe/build_common.ps1"
git commit -m "refactor: extract performance module boundaries"
```
