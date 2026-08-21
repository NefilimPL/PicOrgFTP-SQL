# OCR Value Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Persist locally recognized numeric values from selected image slots and use them to validate Pimcore values without blocking users.

**Architecture:** Pure normalization and a SQLite repository form the core. A two-stage PaddleOCR adapter and an idle-aware worker fill the repository; web APIs and UI only consume state. Dimension-specific template sources migrate to a boolean ocr_validation mapping property.

**Tech Stack:** Python 3.11–3.14, FastAPI, SQLite/WAL, PaddleOCR 3.x, PaddlePaddle 3.x, OpenCV, vanilla JavaScript/CSS, PyInstaller, pytest and Node test runner.

**Spec:** docs/superpowers/specs/2026-08-21-ocr-value-collection-design.md

## Global Constraints

- OCR stays local; APIs accept only existing signed upload/cache tokens and never client filesystem paths.
- Normalize , to . for entered values, ignore fractional portions, and map every special character to one ? only for comparison.
- No selected OCR slots means no scan is scheduled.
- Interactive OCR yields to user activity; unfinished crop tasks persist and run only when idle/CPU limits permit.
- Web without OCR omits OCR UI, endpoints and vision dependencies; OCR web includes models offline.
- Preserve all non-OCR template and upload behavior.

---

## Planned file structure

| File | Responsibility |
| --- | --- |
| picorgftp_sql/services/ocr_values.py | Pure numeric extraction, canonical comparison and immutable records. |
| picorgftp_sql/services/ocr_scanning.py | Two-stage Paddle/OpenCV adapter. |
| picorgftp_sql/services/ocr_queue.py | Idle- and CPU-limited persisted job worker. |
| picorgftp_sql/sqlite_store.py | Schema v16 plus OCR scans, jobs and approvals. |
| picorgftp_sql/ocr_settings.py | OCR setting defaults and normalization. |
| picorgftp_sql/pimcore_config.py | ocr_validation persistence; legacy image_dimension removal. |
| picorgftp_sql/web/app.py | Feature-gated OCR APIs. |
| picorgftp_sql/web_manager.py | Slot lifecycle, validation and cancellation hand-off. |
| picorgftp_sql/web/static/* | Admin controls, overlays, mismatch controls and queue. |
| Generator exe/* and .github/workflows/build-exe.yml | Four BAT entry points and three CI targets. |

### Task 1: Canonical OCR value comparison

**Files:**
- Create: picorgftp_sql/services/ocr_values.py
- Create: tests/test_ocr_values.py

**Interfaces:**
- Produces OcrValue(text, comparison, confidence, bbox).
- Produces normalize_entered_ocr_value(value), comparison_key(value), and ocr_values_match(left, right).

- [ ] **Step 1: Write the failing tests.**

~~~
from picorgftp_sql.services.ocr_values import comparison_key, normalize_entered_ocr_value, ocr_values_match

def test_comparison_ignores_decimals_and_special_character_kind():
    assert normalize_entered_ocr_value("120,9/140.1") == "120.9/140.1"
    assert comparison_key("120,9/140.1") == "120?140"
    assert comparison_key("120-140") == "120?140"
    assert ocr_values_match("120,9/140.1", "120-140")

def test_comparison_preserves_special_character_count():
    assert comparison_key("120--140") == "120??140"
    assert not ocr_values_match("120--140", "120-140")
~~~

- [ ] **Step 2: Verify red.**

Run: pytest tests/test_ocr_values.py -v

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Write minimal production code.**

~~~
@dataclass(frozen=True)
class OcrValue:
    text: str
    comparison: str
    confidence: float
    bbox: tuple[int, int, int, int]

def normalize_entered_ocr_value(value: object) -> str:
    return str(value or "").strip().replace(",", ".")

def comparison_key(value: object) -> str:
    text = normalize_entered_ocr_value(value)
    result: list[str] = []
    index = 0
    while index < len(text):
        if text[index].isdigit():
            start = index
            while index < len(text) and text[index].isdigit():
                index += 1
            result.append(text[start:index])
            if index < len(text) and text[index] == ".":
                index += 1
                while index < len(text) and text[index].isdigit():
                    index += 1
            continue
        if not text[index].isalpha() and not text[index].isspace():
            result.append("?")
        index += 1
    return "".join(result) if any(char.isdigit() for char in result) else ""
~~~

Whitespace is ignored before parsing; letter runs are discarded; return an empty key when no digits remain.

- [ ] **Step 4: Add no-digit, OCR-letter and multiple-integer cases.**

~~~
def test_ocr_letters_are_removed_but_structure_is_retained():
    assert comparison_key("W 120/140 mm") == "120?140"
    assert comparison_key("brak") == ""
~~~

- [ ] **Step 5: Verify green and commit.**

Run: pytest tests/test_ocr_values.py -v
Expected: PASS.

~~~
git add picorgftp_sql/services/ocr_values.py tests/test_ocr_values.py
git commit -m "feat: add OCR value normalization"
~~~

### Task 2: Settings and Pimcore migration

**Files:**
- Create: picorgftp_sql/ocr_settings.py
- Modify: picorgftp_sql/config.py
- Modify: picorgftp_sql/pimcore_config.py:71-152, 306-390
- Test: tests/test_settings.py
- Test: tests/test_pimcore_config.py

**Interfaces:**
- Produces DEFAULT_OCR_SETTINGS and normalize_ocr_settings(value).
- normalize_field_mapping() produces ocr_validation: bool and never emits image_dimension.

- [ ] **Step 1: Write failing settings and migration tests.**

~~~
def test_ocr_settings_bound_idle_and_cpu_limits():
    assert normalize_ocr_settings({"idle_seconds": -1, "max_cpu_percent": 101}) == {
        "enabled_slots": [], "background_enabled": False,
        "idle_seconds": 0, "max_cpu_percent": 100, "pause_cpu_percent": 100,
    }

def test_mapping_discards_legacy_dimension_property():
    mapping = normalize_field_mapping({
        "source": "WIDTH",
        "image_dimension": {"slot": "15", "dimension": "width"},
    })
    assert mapping["ocr_validation"] is False
    assert "image_dimension" not in mapping
~~~

- [ ] **Step 2: Verify red.**

Run: pytest tests/test_settings.py tests/test_pimcore_config.py -k "ocr or dimension" -v
Expected: FAIL because OCR settings and ocr_validation are missing.

- [ ] **Step 3: Implement normalization and migration.**

~~~
DEFAULT_OCR_SETTINGS = {
    "enabled_slots": [], "background_enabled": False,
    "idle_seconds": 5, "max_cpu_percent": 35, "pause_cpu_percent": 85,
}
def normalize_ocr_settings(value: object) -> dict[str, object]:
    raw = value if isinstance(value, dict) else {}
    slots = list(dict.fromkeys(
        str(item).strip() for item in raw.get("enabled_slots", [])
        if str(item).strip()
    )) if isinstance(raw.get("enabled_slots"), list) else []
    idle = max(0, min(3600, int(raw.get("idle_seconds", 5))))
    maximum = max(0, min(100, int(raw.get("max_cpu_percent", 35))))
    pause = max(maximum, min(100, int(raw.get("pause_cpu_percent", 85))))
    return {"enabled_slots": slots, "background_enabled": bool(raw.get("background_enabled")),
            "idle_seconds": idle, "max_cpu_percent": maximum, "pause_cpu_percent": pause}
~~~

Wire the function into config load/save. Read old image_dimension safely but discard it in normalized saves.

- [ ] **Step 4: Cover duplicate slots, invalid values and unchanged ordinary mappings.**

Run: pytest tests/test_settings.py tests/test_pimcore_config.py -v
Expected: PASS.

- [ ] **Step 5: Commit.**

~~~
git add picorgftp_sql/ocr_settings.py picorgftp_sql/config.py picorgftp_sql/pimcore_config.py tests/test_settings.py tests/test_pimcore_config.py
git commit -m "feat: configure OCR validation settings"
~~~

### Task 3: Persistent cache, crop jobs and approvals

**Files:**
- Modify: picorgftp_sql/sqlite_store.py:46, 1229-1755
- Create: tests/test_ocr_store.py
- Modify: tests/test_sqlite_store.py

**Interfaces:**
- Bumps SCHEMA_VERSION from 15 to 16.
- Produces upsert_ocr_scan, get_ocr_scan, enqueue_ocr_crop_job, claim_ocr_crop_job, complete_ocr_crop_job, list_ocr_crop_jobs, record_ocr_approval and has_ocr_approval on SQLiteStore.

- [ ] **Step 1: Write failing repository tests.**

~~~
def test_ocr_scan_survives_store_reopen(tmp_path):
    path = tmp_path / "store.sqlite"
    store = SQLiteStore(str(path)); store.initialize()
    store.upsert_ocr_scan("a" * 64, [{
        "text": "120/140", "comparison": "120?140",
        "confidence": .91, "bbox": [1, 2, 3, 4],
    }], "partial")
    reopened = SQLiteStore(str(path)); reopened.initialize()
    assert reopened.get_ocr_scan("a" * 64)["values"][0]["comparison"] == "120?140"

def test_approval_requires_same_image_hash_set(tmp_path):
    store = initialized_store(tmp_path)
    store.record_ocr_approval("WIDTH", "120", ["hash-a"])
    assert store.has_ocr_approval("WIDTH", "120", ["hash-a"])
    assert not store.has_ocr_approval("WIDTH", "120", ["hash-b"])
~~~

- [ ] **Step 2: Verify red.**

Run: pytest tests/test_ocr_store.py -v
Expected: FAIL because SQLiteStore has no OCR methods.

- [ ] **Step 3: Add schema and transactional methods.**

Create ocr_image_scans, ocr_detected_values, ocr_crop_jobs and ocr_validation_approvals. Use unique (image_hash, ordinal), index pending jobs by (status, created_at), and store sorted image hashes as canonical JSON. Claim one job atomically inside the existing transaction pattern.

- [ ] **Step 4: Cover partial update, failed job, single concurrent claim and value-change invalidation.**

Run: pytest tests/test_ocr_store.py tests/test_sqlite_store.py -v
Expected: PASS.

- [ ] **Step 5: Commit.**

~~~
git add picorgftp_sql/sqlite_store.py tests/test_ocr_store.py tests/test_sqlite_store.py
git commit -m "feat: persist OCR scan cache and jobs"
~~~

### Task 4: Two-stage local OCR scanning

**Files:**
- Create: picorgftp_sql/services/ocr_scanning.py
- Modify: picorgftp_sql/services/image_dimensions.py
- Create: tests/test_ocr_scanning.py
- Modify: tests/test_image_dimensions.py

**Interfaces:**
- Produces scan_image(path, discoverer, refiner, cancel_requested) -> ScanResult.
- ScanResult exposes fast_values, refined_values and deferred_bboxes.
- Existing settings diagnostics become generic values/bboxes/confidence and report mobile and server models.

- [ ] **Step 1: Write failing injected-adapter tests.**

~~~
def test_scan_persists_fast_values_and_defers_cancelled_crops(tmp_path):
    result = scan_image(
        str(tmp_path / "image.png"),
        discoverer=FakeDiscovery([value("120/140")]),
        refiner=FakeRefiner(),
        cancel_requested=lambda: True,
    )
    assert [item.comparison for item in result.fast_values] == ["120?140"]
    assert result.deferred_bboxes == [(1, 2, 30, 20)]
~~~

- [ ] **Step 2: Verify red.**

Run: pytest tests/test_ocr_scanning.py -v
Expected: FAIL because the scanner module is absent.

- [ ] **Step 3: Implement two adapters.**

Use PP-OCRv5 mobile discovery on the original image. Clamp padded bbox coordinates, rotate tall crops where necessary, upscale with cv2.INTER_CUBIC, apply grayscale plus unsharp mask, then run PP-OCRv5 Server recognition. Keep only values with digits and retain original text, confidence and source bbox. Do not download models in tests.

- [ ] **Step 4: Cover crop bounds, failed refiner, decimal restoration and diagnostic boxes.**

Run: pytest tests/test_ocr_scanning.py tests/test_image_dimensions.py -v
Expected: PASS.

- [ ] **Step 5: Commit.**

~~~
git add picorgftp_sql/services/ocr_scanning.py picorgftp_sql/services/image_dimensions.py tests/test_ocr_scanning.py tests/test_image_dimensions.py
git commit -m "feat: add two-stage local OCR scanning"
~~~

### Task 5: Idle- and CPU-aware queue worker

**Files:**
- Create: picorgftp_sql/services/ocr_queue.py
- Modify: picorgftp_sql/web/active_clients.py
- Create: tests/test_ocr_queue.py

**Interfaces:**
- Produces OcrQueueScheduler(store, scanner, cpu_percent, now).run_once().
- run_once returns disabled, busy, idle_wait, cpu_pause, empty or processed.
- mark_user_activity(at=None) exposes the latest user activity time.

- [ ] **Step 1: Write failing scheduling tests.**

~~~
def test_scheduler_waits_for_idle_period():
    scheduler = scheduler_with(
        settings={"background_enabled": True, "idle_seconds": 5,
                  "max_cpu_percent": 50, "pause_cpu_percent": 85},
        now=lambda: 104, cpu=lambda: 10, last_activity=100,
    )
    assert scheduler.run_once() == "idle_wait"

def test_scheduler_pauses_above_hard_cpu_limit():
    scheduler = scheduler_with(
        settings={"background_enabled": True, "idle_seconds": 0,
                  "max_cpu_percent": 50, "pause_cpu_percent": 85},
        cpu=lambda: 90,
    )
    assert scheduler.run_once() == "cpu_pause"
~~~

- [ ] **Step 2: Verify red.**

Run: pytest tests/test_ocr_queue.py -v
Expected: FAIL because the scheduler does not exist.

- [ ] **Step 3: Implement cooperative one-job scheduling.**

Check queue enabled, active requests, idle seconds and hard CPU limit before claim. Run one crop; if user activity appears, return the job to pending unchanged. Between jobs throttle when CPU exceeds max_cpu_percent. Save exception state without discarding the job payload.

- [ ] **Step 4: Cover disabled queue, active request, success, exception and resume.**

Run: pytest tests/test_ocr_queue.py tests/test_ocr_store.py -v
Expected: PASS.

- [ ] **Step 5: Commit.**

~~~
git add picorgftp_sql/services/ocr_queue.py picorgftp_sql/web/active_clients.py tests/test_ocr_queue.py
git commit -m "feat: schedule OCR crops during idle time"
~~~

### Task 6: Feature-gated APIs and slot lifecycle

**Files:**
- Modify: picorgftp_sql/web/app.py:1080-1207, 5224-5250, 5982-6025, 6477-6528
- Modify: picorgftp_sql/web_manager.py
- Modify: picorgftp_sql/web/upload_staging.py
- Create: tests/test_web_ocr_api.py
- Modify: tests/test_web_runtime_api.py
- Modify: tests/test_upload_staging.py

**Interfaces:**
- Adds GET /api/ocr/slots, GET /api/ocr/jobs, POST /api/ocr/validate and POST /api/ocr/approval.
- Existing POST /api/settings/ocr/analyze returns generic values, bboxes and confidence only.
- Build flag controls route registration.

- [ ] **Step 1: Write failing secure endpoint tests.**

~~~
def test_validation_uses_signed_slot_tokens_not_client_paths(client, signed_slot_token):
    response = client.post("/api/ocr/validate", json={
        "field_id": "WIDTH", "value": "120,8", "slot_tokens": [signed_slot_token],
    })
    assert response.status_code == 200
    assert response.json()["comparison"] == "120"

def test_plain_web_has_no_ocr_route(client_without_ocr):
    assert client_without_ocr.get("/api/ocr/slots").status_code == 404
~~~

- [ ] **Step 2: Verify red.**

Run: pytest tests/test_web_ocr_api.py -v
Expected: FAIL because the APIs and feature flag do not exist.

- [ ] **Step 3: Implement secure integration.**

Resolve each token only with existing _path_from_file_token, hash content in chunks, look up SQLite, and schedule scans only for selected slots. Refresh/clear cancels interactive work, writes found values and enqueues remaining bboxes. Return pending/empty neutrally; return mismatch only after completed non-empty results.

- [ ] **Step 4: Cover cache hit, changed hash, rejected non-admin settings, approval invalidation and background hand-off.**

Run: pytest tests/test_web_ocr_api.py tests/test_web_runtime_api.py tests/test_upload_staging.py -v
Expected: PASS.

- [ ] **Step 5: Commit.**

~~~
git add picorgftp_sql/web/app.py picorgftp_sql/web_manager.py picorgftp_sql/web/upload_staging.py tests/test_web_ocr_api.py tests/test_web_runtime_api.py tests/test_upload_staging.py
git commit -m "feat: expose cached OCR slot validation"
~~~

### Task 7: Web UI: admin, overlays and validation actions

**Files:**
- Modify: picorgftp_sql/web/static/index.html:135-154, 456-584, 771-786
- Modify: picorgftp_sql/web/static/app.js
- Modify: picorgftp_sql/web/static/app.css:2371-2927, 3320-3550
- Create: tests/js/ocr-values.test.js
- Modify: tests/test_web_ui_integrity.py
- Modify: tests/test_pimcore_templates.py

**Interfaces:**
- Browser state adds ocrBySlot and ocrJobs.
- Pure browser helpers: normalizeOcrInput, renderOcrOverlay and applyOcrValidation.
- Template editor sends ocr_validation next to translation controls.

- [ ] **Step 1: Write failing browser and template tests.**

~~~
test("normalizes comma before OCR validation", () => {
  expect(normalizeOcrInput("120,5")).toBe("120.5");
});

test("mismatch has both decisions", () => {
  const node = applyOcrValidation(field(), {status: "mismatch", values: ["120/140"]});
  expect(node.classList.contains("ocr-mismatch")).toBe(true);
  expect(node.querySelector('[data-ocr-action="accept"]')).not.toBeNull();
  expect(node.querySelector('[data-ocr-action="reject"]')).not.toBeNull();
});
~~~

~~~
def test_mapping_keeps_ocr_validation_without_dimension_source():
    mapping = normalize_field_mapping({"source": "WIDTH", "ocr_validation": True})
    assert mapping["ocr_validation"] is True
    assert "image_dimension" not in mapping
~~~

- [ ] **Step 2: Verify red.**

Run: node --test tests/js/ocr-values.test.js
Expected: FAIL because helpers and controls do not exist.

Run: pytest tests/test_pimcore_templates.py tests/test_web_ui_integrity.py -k "ocr or dimension" -v
Expected: FAIL because new controls are absent.

- [ ] **Step 3: Implement visual states.**

Render RGB animated ocr-collecting border and status on selected pending slots. In open-image view overlay native-coordinate rectangles with value/confidence labels. Replace dimension controls with one ocr_validation checkbox near translation controls. Render admin slot checkboxes, generic diagnostics, CPU/idle controls and crop-job miniature queue. On mismatch show red field, tooltip list and ✓/✕; accept posts approval and reject restores previous value or clears it. Hide the full OCR tab and all OCR states when feature flag is false.

- [ ] **Step 4: Add coordinate, neutral pending/empty, accepted-exception and admin-only queue cases.**

Run: node --test tests/js/ocr-values.test.js
Expected: PASS.

Run: pytest tests/test_pimcore_config.py tests/test_pimcore_templates.py tests/test_web_ui_integrity.py -v
Expected: PASS.

- [ ] **Step 5: Commit.**

~~~
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/js/ocr-values.test.js tests/test_pimcore_templates.py tests/test_web_ui_integrity.py
git commit -m "feat: show OCR values and validation controls"
~~~

### Task 8: Deterministic EXE and Actions variants

**Files:**
- Modify: Generator exe/BUILD_ALL_EXE.bat
- Modify: Generator exe/BUILD_LOCAL_EXE.bat
- Modify: Generator exe/BUILD_WEB_EXE.bat
- Modify: Generator exe/BUILD_WEB_EXE_OCR.bat
- Delete: Generator exe/BUILD_LOCAL_EXE_OCR.bat
- Modify: Generator exe/build_all_exe.ps1
- Modify: Generator exe/build_web_exe.ps1
- Modify: .github/workflows/build-exe.yml
- Modify: tests/test_build_exe_workflow.py
- Modify: tests/test_web_smoke_ci.py

**Interfaces:**
- build_web_exe.ps1 -IncludeVision -IncludeVisionModels is the offline OCR command.
- CI target IDs are local, web and web-ocr-offline.

- [ ] **Step 1: Write failing package contract tests.**

~~~
def test_bats_are_exactly_the_four_supported_entry_points():
    assert build_bat_names() == {
        "BUILD_ALL_EXE.bat", "BUILD_LOCAL_EXE.bat",
        "BUILD_WEB_EXE.bat", "BUILD_WEB_EXE_OCR.bat",
    }

def test_workflow_has_three_explicit_targets():
    assert workflow_matrix_targets() == {"local", "web", "web-ocr-offline"}
~~~

- [ ] **Step 2: Verify red.**

Run: pytest tests/test_build_exe_workflow.py -v
Expected: FAIL because local OCR BAT and a two-target CI matrix exist.

- [ ] **Step 3: Make build paths explicit.**

BUILD_WEB_EXE_OCR.bat directly invokes build_web_exe.ps1 with both flags; remove its D/M menu. BUILD_ALL_EXE.bat runs local plain, web plain, then web offline OCR. Delete local OCR BAT. Plain web must neither install requirements-vision.txt nor register OCR API/UI; offline web bundles mobile plus server model cache.

- [ ] **Step 4: Cover no choice /c DM, plain-web no vision dependencies and OCR model collection only in web-ocr-offline.**

Run: pytest tests/test_build_exe_workflow.py tests/test_web_smoke_ci.py -v
Expected: PASS.

- [ ] **Step 5: Commit.**

~~~
git add "Generator exe" .github/workflows/build-exe.yml tests/test_build_exe_workflow.py tests/test_web_smoke_ci.py
git commit -m "build: ship three deterministic EXE variants"
~~~

### Task 9: Documentation, localization and full verification

**Files:**
- Modify: docs/web-panel.md
- Modify: docs/building-exe.md
- Modify: docs/pimcore.md
- Modify: picorgftp_sql/Localization/pl.json
- Modify: picorgftp_sql/Localization/eng.json
- Modify: picorgftp_sql/Localization/ua.json
- Modify: tests/test_source_integrity.py

- [ ] **Step 1: Write failing source/documentation checks.**

~~~
def test_ocr_docs_do_not_advertise_dimension_thresholds():
    assert "minimalna pewnosc" not in read("docs/web-panel.md").casefold()
    assert "BUILD_LOCAL_EXE_OCR.bat" not in read("docs/building-exe.md")
~~~

- [ ] **Step 2: Verify red.**

Run: pytest tests/test_source_integrity.py -k "ocr or build" -v
Expected: FAIL until documentation is updated.

- [ ] **Step 3: Update user-facing content.**

Document selected slots, persistent hashes, idle queue limits, comparison, accept/reject behavior, image overlays, four BAT files and three CI artifacts. Add every new visible OCR key in Polish, English and Ukrainian.

- [ ] **Step 4: Run full verification.**

Run: pytest -q
Expected: PASS.

Run: node --test tests/js/*.test.js
Expected: PASS.

Run: git diff --check
Expected: no output.

- [ ] **Step 5: Commit and report fresh evidence.**

~~~
git add docs picorgftp_sql/Localization tests/test_source_integrity.py
git commit -m "docs: explain persistent OCR value validation"
~~~

## Requirement coverage review

- Universal capture, two-stage OCR, persistent cache and background continuation: Tasks 1, 3, 4, 5.
- Selected slots, CPU/idle limits and administrator queue: Tasks 2, 5, 6, 7.
- Pimcore checkbox plus mismatch approval/revert: Tasks 2, 6, 7.
- Rectangles, values, confidence and diagnostics: Tasks 4, 6, 7.
- Removal of dimensions and minimum confidence: Tasks 2, 4, 7.
- Four BAT files and three Actions variants: Task 8.
- Localization, documentation and full verification: Task 9.
