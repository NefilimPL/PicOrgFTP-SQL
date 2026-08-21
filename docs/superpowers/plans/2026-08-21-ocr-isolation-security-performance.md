# OCR Isolation, Security and Search Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep OCR from blocking the web panel, expose local fast/accurate profiles, fix the selected UI, and close the five CodeQL alerts.

**Architecture:** A Windows-capped child process performs OCR while the parent remains responsible for scheduling and SQLite. OCR profile definitions are pure data shared by status, settings and worker code. Resource sampling and similar-file discovery remain responsive and all filesystem/DOM sinks receive explicit validation.

**Tech Stack:** Python 3.11+, FastAPI, multiprocessing/ctypes Windows Job Objects, PaddleOCR 3.x, SQLite, vanilla JS/CSS, pytest, Node, CodeQL.

**Spec:** `docs/superpowers/specs/2026-08-21-ocr-isolation-security-performance-design.md`

## Global Constraints

- Run only locally bundled/cached OCR models; no runtime download.
- Work on the existing branch and checkout.
- `fast` is PP-OCRv5 Mobile and `accurate` is PP-OCRv5 Server; both run serially and merge deterministically.
- OCR fails closed when CPU data is unavailable or stale.
- The Windows CPU cap applies to the OCR process, never to the web backend.
- Existing signed-file-token authorization remains mandatory.

---

### Task 1: OCR profile registry and settings contract

**Files:**
- Create: `picorgftp_sql/services/ocr_profiles.py`
- Modify: `picorgftp_sql/ocr_settings.py`
- Modify: `picorgftp_sql/services/image_dimensions.py`
- Test: `tests/test_ocr_settings.py`, `tests/test_image_dimensions.py`

**Interfaces:**
- Produces `OcrProfile(id, label, detector_model, recognizer_model, cache_names)` and `available_ocr_profiles()`.
- Produces `normalize_ocr_settings(value)` with ordered `model_profiles: list[str]`.
- Consumes a profile id in `PaddleImageDimensionRecognizer(profile_id="fast")`.

- [ ] **Step 1: Write the failing tests**

```python
def test_ocr_settings_keep_available_profiles_in_order():
    assert normalize_ocr_settings({"model_profiles": ["accurate", "fast", "bad"]})["model_profiles"] == ["accurate", "fast"]

def test_profile_registry_has_local_fast_and_accurate_variants():
    profiles = {profile.id: profile for profile in available_ocr_profiles()}
    assert profiles["fast"].recognizer_model == "PP-OCRv5_mobile_rec"
    assert profiles["accurate"].recognizer_model == "PP-OCRv5_server_rec"
```

- [ ] **Step 2: Run red**

Run: `pytest tests/test_ocr_settings.py tests/test_image_dimensions.py -q`

Expected: FAIL because profiles and `model_profiles` do not exist.

- [ ] **Step 3: Implement the minimal registry**

Create immutable `fast` and `accurate` entries. Normalize only known ordered IDs, defaulting to `["fast"]`. Construct PaddleOCR with each profile's explicit detector and recognizer names, preserving disabled orientation and `enable_mkldnn=False`. Inspect cache only; never download a model.

- [ ] **Step 4: Run green**

Run: `pytest tests/test_ocr_settings.py tests/test_image_dimensions.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add picorgftp_sql/services/ocr_profiles.py picorgftp_sql/ocr_settings.py picorgftp_sql/services/image_dimensions.py tests/test_ocr_settings.py tests/test_image_dimensions.py
git commit -m "feat: add local OCR speed profiles"
```

### Task 2: Package both offline OCR profiles

**Files:**
- Modify: `Generator exe/build_web_exe.ps1`
- Modify: `Generator exe/BUILD_WEB_EXE_OCR.bat`
- Modify: `tests/test_build_exe_workflow.py`

**Interfaces:** The `web-ocr-offline` artifact contains local caches for every `available_ocr_profiles()` entry and never needs Internet access at runtime.

- [ ] **Step 1: Write the failing packaging test**

```python
def test_offline_ocr_build_collects_fast_and_accurate_profiles():
    source = BUILD_WEB_EXE.read_text(encoding="utf-8")
    assert "PP-OCRv5_mobile_rec" in source
    assert "PP-OCRv5_server_rec" in source
```

- [ ] **Step 2: Run red**

Run: `pytest tests/test_build_exe_workflow.py -q`

Expected: FAIL because the Server model is not collected.

- [ ] **Step 3: Implement deterministic model collection**

Extend the OCR build path to instantiate/cache both profile model pairs at build time under the bundled OCR cache directory. Fail the build with a clear message if either cache is missing; runtime only reads that directory.

- [ ] **Step 4: Run green**

Run: `pytest tests/test_build_exe_workflow.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add "Generator exe/build_web_exe.ps1" "Generator exe/BUILD_WEB_EXE_OCR.bat" tests/test_build_exe_workflow.py
git commit -m "build: bundle fast and accurate OCR profiles"
```

### Task 3: Isolated, CPU-capped OCR execution

**Files:**
- Create: `picorgftp_sql/services/ocr_process.py`
- Modify: `picorgftp_sql/services/ocr_queue.py`
- Modify: `picorgftp_sql/web/app.py`
- Test: `tests/test_ocr_process.py`, `tests/test_ocr_queue.py`, `tests/test_web_app_files.py`

**Interfaces:**
- Produces `OcrProcessRunner(cpu_cap_percent, processor).process(job, profiles) -> OcrProcessResult`.
- Produces `apply_windows_cpu_cap(process_handle, percent)` and `set_background_priority(process_handle)`.
- Scheduler consumes `cpu_percent: Callable[[], float | None]`; `None` returns `"cpu_stale"` without claiming a job.

- [ ] **Step 1: Write failing tests**

```python
def test_runner_caps_only_child_process(monkeypatch):
    calls = []
    runner = OcrProcessRunner(35, processor=lambda job, profiles: {"values": []}, capper=lambda handle, cap: calls.append((handle, cap)))
    assert runner.process({"id": "job-1"}, ["fast"]).ok is True
    assert calls == [("child", 35)]

def test_scheduler_refuses_missing_cpu_measurement():
    assert scheduler(cpu_percent=lambda: None).run_once() == "cpu_stale"
```

- [ ] **Step 2: Run red**

Run: `pytest tests/test_ocr_process.py tests/test_ocr_queue.py -q`

Expected: FAIL because the runner and `cpu_stale` do not exist.

- [ ] **Step 3: Implement runner and parent integration**

Use one long-lived `multiprocessing.Process` plus request/response queues. On Windows configure `JOB_OBJECT_CPU_RATE_CONTROL_INFORMATION` with enable, hard-cap and `cpu_rate = max(1, min(100, percent)) * 100`; lower only child priority. Parent-side `_process_ocr_crop_job` sends the already-owned crop and profile IDs, persists returned values, and requeues on process failure, timeout or user activity.

- [ ] **Step 4: Run green**

Run: `pytest tests/test_ocr_process.py tests/test_ocr_queue.py tests/test_web_app_files.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add picorgftp_sql/services/ocr_process.py picorgftp_sql/services/ocr_queue.py picorgftp_sql/web/app.py tests/test_ocr_process.py tests/test_ocr_queue.py tests/test_web_app_files.py
git commit -m "feat: isolate and cap background OCR"
```

### Task 4: Fresh CPU status and nonblocking resource persistence

**Files:**
- Modify: `picorgftp_sql/resource_monitor.py`
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/web/static/app.js`
- Test: `tests/test_resource_monitor.py`, `tests/test_web_ui_integrity.py`

**Interfaces:** `ResourceMonitor.latest_host_cpu(max_age_seconds) -> float | None`; public snapshots include `sample_age_seconds` and `stale`.

- [ ] **Step 1: Write failing tests**

```python
def test_stale_host_cpu_is_not_usable_for_ocr():
    monitor._latest["observed_monotonic"] = 10
    assert monitor.latest_host_cpu(max_age_seconds=5, now=20) is None

def test_slow_event_writer_does_not_delay_next_sample():
    monitor = monitor_with_blocking_emitter()
    monitor.sample_once(); monitor.sample_once()
    assert monitor.reader_calls == 2
```

- [ ] **Step 2: Run red**

Run: `pytest tests/test_resource_monitor.py tests/test_web_ui_integrity.py -q`

Expected: FAIL for absent freshness fields and synchronous alert persistence.

- [ ] **Step 3: Implement freshness and bounded event dispatch**

Record monotonic observation time with the public UTC time. Keep sampling under `_sampling_lock`, but submit normal notification persistence to one bounded worker so slow SQLite/outbox cannot delay sampling. Preserve strict persistence for explicit real-resource tests. Render age and stale warning in the resource/OCR UI.

- [ ] **Step 4: Run green**

Run: `pytest tests/test_resource_monitor.py tests/test_web_ui_integrity.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add picorgftp_sql/resource_monitor.py picorgftp_sql/web/app.py picorgftp_sql/web/static/app.js tests/test_resource_monitor.py tests/test_web_ui_integrity.py
git commit -m "fix: use fresh CPU data for OCR scheduling"
```

### Task 5: OCR settings UI, profile merging and layout A

**Files:**
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Test: `tests/test_web_app_files.py`, `tests/test_web_ui_integrity.py`

**Interfaces:** `GET /api/settings/ocr/status` returns `profiles: [{id,label,available,description}]`. `merge_ocr_profile_candidates(results)` retains largest confidence and `profile_ids`.

- [ ] **Step 1: Write failing API/UI tests**

```python
def test_ocr_status_exposes_offline_profile_availability(client):
    assert {item["id"] for item in client.get("/api/settings/ocr/status").json()["profiles"]} == {"fast", "accurate"}

def test_ocr_settings_use_full_width_slot_grid():
    assert ".ocr-settings-slots" in APP_CSS.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run red**

Run: `pytest tests/test_web_app_files.py tests/test_web_ui_integrity.py -q`

Expected: FAIL because profile payload and selected layout are absent.

- [ ] **Step 3: Implement layout and model result merge**

Return profile metadata without constructing models. In `renderSettingsOcr`, render controls, multi-select profile cards, then `.ocr-settings-slots` with selected counter; disable unavailable cards. Run selected profiles serially, merge candidates by normalized value plus overlapping box, retain highest confidence and all `profile_ids`. Add one-column mobile CSS.

- [ ] **Step 4: Run green**

Run: `pytest tests/test_web_app_files.py tests/test_web_ui_integrity.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add picorgftp_sql/web/app.py picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_app_files.py tests/test_web_ui_integrity.py
git commit -m "feat: configure OCR profiles in settings"
```

### Task 6: Similar-file cancellation and bounded discovery

**Files:**
- Modify: `picorgftp_sql/similar_product_files.py`
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/static/app.js`
- Test: `tests/test_similar_product_files.py`, `tests/test_web_ui_integrity.py`

**Interfaces:** `find_similar_file_candidates(..., should_continue: Callable[[], bool] | None = None)` stops before each directory/hash operation.

- [ ] **Step 1: Write failing cancellation test**

```python
def test_similar_discovery_stops_before_hashing_when_cancelled(tmp_path, monkeypatch):
    monkeypatch.setattr(similar_product_files, "_read_digest", lambda _: pytest.fail("hash should not run"))
    assert find_similar_file_candidates(str(tmp_path), product(), slots(), settings(), should_continue=lambda: False) == []
```

- [ ] **Step 2: Run red**

Run: `pytest tests/test_similar_product_files.py tests/test_web_ui_integrity.py -q`

Expected: FAIL because discovery has no cancellation contract.

- [ ] **Step 3: Implement bounded discovery**

Check `should_continue` before `scandir`, digest reads and after every candidate; stop once target slots are full. Associate server work with a current request generation, so reset/new form invalidates old work. Retain browser AbortController, clear debounce on reset and never render obsolete results/errors.

- [ ] **Step 4: Run green**

Run: `pytest tests/test_similar_product_files.py tests/test_web_ui_integrity.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add picorgftp_sql/similar_product_files.py picorgftp_sql/web_data.py picorgftp_sql/web/static/app.js tests/test_similar_product_files.py tests/test_web_ui_integrity.py
git commit -m "fix: cancel obsolete similar file discovery"
```

### Task 7: Close CodeQL path and DOM alerts

**Files:**
- Modify: `picorgftp_sql/path_security.py`
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/web/static/app.js`
- Test: `tests/test_path_security.py`, `tests/test_web_app_files.py`, `tests/test_web_ui_integrity.py`

**Interfaces:** `resolve_path_within_roots` returns only canonical contained paths; `trusted_ocr_image_url(value) -> str` permits only same-origin `/api/file` URLs.

- [ ] **Step 1: Write failing traversal/XSS tests**

```python
def test_resolver_rejects_other_volume_and_symlink_escape(tmp_path):
    with pytest.raises(PathSecurityError):
        resolve_path_within_roots("C:/outside/file.jpg", [tmp_path])

def test_ocr_image_url_rejects_html_and_external_origin():
    assert trusted_ocr_image_url("javascript:alert(1)") == ""
```

- [ ] **Step 2: Run red**

Run: `pytest tests/test_path_security.py tests/test_web_app_files.py tests/test_web_ui_integrity.py -q`

Expected: FAIL for sink-local containment and the URL allowlist.

- [ ] **Step 3: Implement explicit validation**

Canonicalize candidates using `Path.resolve(strict=False)`, compare against resolved trusted root before existence/type checks, and perform this explicit check at signed-token file sinks. Replace the loading overlay `innerHTML` and OCR URL assignment with constructed nodes and a parsed same-origin URL allowlist. Preserve normal image/token rendering.

- [ ] **Step 4: Run green and CodeQL**

Run: `pytest tests/test_path_security.py tests/test_web_app_files.py tests/test_web_ui_integrity.py -q`

Expected: PASS.

Run after push and analysis: `gh api 'repos/NefilimPL/PicOrgFTP-SQL/code-scanning/alerts?state=open&ref=refs/pull/221/head&per_page=100'`

Expected: no `py/path-injection` or `js/xss-through-dom` instances.

- [ ] **Step 5: Commit**

```bash
git add picorgftp_sql/path_security.py picorgftp_sql/web/app.py picorgftp_sql/web/static/app.js tests/test_path_security.py tests/test_web_app_files.py tests/test_web_ui_integrity.py
git commit -m "fix: secure file paths and OCR DOM rendering"
```

### Task 8: Regression and delivery verification

**Files:**
- Modify: `docs/web-panel.md`
- Modify: `docs/building-exe.md`

- [ ] **Step 1: Document profiles and no-download behavior**

Describe fast, accurate and dual-profile behavior, the Windows hard cap, stale CPU pause, and requirement that models already exist in the OCR bundle/cache.

- [ ] **Step 2: Run complete relevant suite**

Run: `pytest tests/test_ocr_settings.py tests/test_image_dimensions.py tests/test_ocr_process.py tests/test_ocr_queue.py tests/test_resource_monitor.py tests/test_similar_product_files.py tests/test_path_security.py tests/test_web_app_files.py tests/test_web_ui_integrity.py -q`

Expected: PASS.

- [ ] **Step 3: Inspect delivery**

Run: `git diff --check HEAD~6..HEAD` and `git status --short`

Expected: no whitespace errors and no unintended files.

- [ ] **Step 4: Commit documentation**

```bash
git add docs/web-panel.md docs/building-exe.md
git commit -m "docs: explain OCR resource profiles"
```
