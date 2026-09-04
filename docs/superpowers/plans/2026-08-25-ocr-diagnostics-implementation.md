# OCR Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Present paired fast/accurate OCR results, diagnostic timings and non-overlapping annotations while preserving decimal precision and making accurate-crop selection configurable.

**Architecture:** Keep the current list-returning run_ocr_pipeline API for current consumers, and add a structured report API that owns region IDs, crop decisions, translated accurate boxes and timings. The worker serializes that report through the existing progress snapshots; a small browser module renders the same report live and after completion.

**Tech Stack:** Python 3, Pillow, PaddleOCR adapters, FastAPI worker protocol, vanilla browser JavaScript/CSS, pytest, Node built-in test runner.

**Spec:** docs/superpowers/specs/2026-08-25-ocr-diagnostics-design.md

## Global Constraints

- Show raw OCR text unchanged; comparison treats comma and dot as equivalent but never removes decimal digits.
- Accurate OCR is eligible only when fast confidence is less than or equal to the configured 0-100 threshold; default is 99 and 100 includes 100% boxes.
- Crop padding is 25% of the longer region side, rounded to pixels and bounded to 8-64 px, before clipping to image bounds.
- Live and final views use the same report, colors (fast blue, accurate amber), pairing and label-placement rules.
- A skipped, unavailable, cancelled or empty accurate scan displays its explicit cause; it never becomes an empty right cell.

---

### Task 1: Preserve decimals and store the accurate-scan threshold

**Files:**
- Modify: picorgftp_sql/services/ocr_values.py:20-56
- Modify: picorgftp_sql/ocr_settings.py:11-78
- Modify: tests/test_ocr_values.py:1-22
- Modify: tests/test_ocr_settings.py:5-67

**Interfaces:**
- Produces comparison_key(value: object) -> str, preserving digits after a decimal separator while canonicalizing comma to dot.
- Produces normalized OCR setting accurate_confidence_threshold: int in 0..100, default 99.

- [ ] **Step 1: Write failing decimal and threshold tests**

~~~python
def test_comparison_key_preserves_decimal_digits_but_unifies_separator():
    assert comparison_key("23,4") == "23.4"
    assert comparison_key("23.4") == "23.4"
    assert not ocr_values_match("23,4", "23")

def test_normalize_ocr_settings_bounds_accurate_confidence_threshold():
    assert normalize_ocr_settings({})["accurate_confidence_threshold"] == 99
    assert normalize_ocr_settings({"accurate_confidence_threshold": -1})[
        "accurate_confidence_threshold"
    ] == 0
    assert normalize_ocr_settings({"accurate_confidence_threshold": 101})[
        "accurate_confidence_threshold"
    ] == 100
~~~

- [ ] **Step 2: Run the focused tests to verify the current behavior fails**

Run: pytest tests/test_ocr_values.py tests/test_ocr_settings.py -q

Expected: FAIL because comparison_key discards decimals and the setting is absent.

- [ ] **Step 3: Implement the smallest compatible behavior**

~~~python
# ocr_values.py
def comparison_key(value: object) -> str:
    text = normalize_entered_ocr_value(value)
    # Preserve complete numeric tokens including their decimal separator.

# ocr_settings.py
DEFAULT_OCR_SETTINGS["accurate_confidence_threshold"] = 99
threshold = _bounded_int(raw.get("accurate_confidence_threshold"), 99, 0, 100)
~~~

Return threshold from normalize_ocr_settings and update the existing full-dictionary expectation.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: pytest tests/test_ocr_values.py tests/test_ocr_settings.py -q

Expected: PASS.

- [ ] **Step 5: Commit the completed task**

~~~powershell
git add picorgftp_sql/services/ocr_values.py picorgftp_sql/ocr_settings.py tests/test_ocr_values.py tests/test_ocr_settings.py
git commit -m "feat: preserve decimal OCR values"
~~~

### Task 2: Create a region-aware OCR pipeline report

**Files:**
- Modify: picorgftp_sql/services/ocr_pipeline.py:1-147
- Modify: tests/test_ocr_pipeline.py:1-119

**Interfaces:**
- Produces immutable OcrPipelineRegion with region_id, fast_box, source_bbox, crop_bbox, accurate_boxes, status, reason, fast_elapsed_ms, crop_elapsed_ms and accurate_elapsed_ms.
- Produces OcrPipelineReport with regions, all_boxes and total_elapsed_ms.
- Produces run_ocr_pipeline_report(path, profile_ids, accurate_confidence_threshold=99, recognizer_factory=None, on_event=None, before_stage=None, sleeper=time.sleep, clock=time.perf_counter) -> OcrPipelineReport.
- Retains run_ocr_pipeline(path: str, *, profile_ids: Iterable[object], recognizer_factory=None, on_event=None, before_stage=None, sleeper=time.sleep) -> list[OcrTextBox] as a wrapper that returns report.all_boxes.
- Emits candidate_regions, crop_started, crop_finished and crop_skipped with region_id, boxes, reason and elapsed times.

- [ ] **Step 1: Write failing report, threshold, padding and timing tests**

~~~python
def test_report_pairs_accurate_boxes_with_fast_region(tmp_path):
    report = run_ocr_pipeline_report(
        str(image_path), profile_ids=["fast", "accurate"],
        accurate_confidence_threshold=100, recognizer_factory=_Recognizer,
    )
    region = report.regions[0]
    assert region.region_id == "region-1"
    assert region.accurate_boxes == (OcrTextBox("20kg", 0.95, (11, 14, 21, 19)),)

def test_report_skips_high_confidence_region_with_reason(tmp_path):
    report = run_ocr_pipeline_report(
        str(image_path), profile_ids=["fast", "accurate"],
        accurate_confidence_threshold=50, recognizer_factory=_HighConfidenceRecognizer,
    )
    assert report.regions[0].status == "skipped_threshold"
    assert "100% > 50%" in report.regions[0].reason

def test_crop_padding_is_symmetric_then_clipped_at_image_edge(tmp_path):
    image_path = tmp_path / "edge.png"
    Image.new("RGB", (30, 20), "white").save(image_path)
    report = run_ocr_pipeline_report(
        str(image_path), profile_ids=["fast", "accurate"],
        accurate_confidence_threshold=100, recognizer_factory=_EdgeRecognizer,
    )
    assert report.regions[0].source_bbox == (2, 2, 22, 12)
    assert report.regions[0].crop_bbox == (0, 0, 30, 20)
~~~

Use a deterministic clock iterator and assert non-negative elapsed milliseconds without sleeping.

- [ ] **Step 2: Run the pipeline tests to verify they fail**

Run: pytest tests/test_ocr_pipeline.py -q

Expected: FAIL because report types, crop padding and crop-skipped events do not exist.

- [ ] **Step 3: Implement the report without breaking the legacy list**

~~~python
@dataclass(frozen=True)
class OcrPipelineRegion:
    region_id: str
    fast_box: OcrTextBox
    source_bbox: tuple[int, int, int, int]
    crop_bbox: tuple[int, int, int, int] | None
    accurate_boxes: tuple[OcrTextBox, ...]
    status: str
    reason: str
    fast_elapsed_ms: int
    crop_elapsed_ms: int
    accurate_elapsed_ms: int

def run_ocr_pipeline(path, *, profile_ids, recognizer_factory=None, on_event=None,
                     before_stage=None, sleeper=time.sleep):
    return run_ocr_pipeline_report(
        path, profile_ids=profile_ids, recognizer_factory=recognizer_factory,
        on_event=on_event, before_stage=before_stage, sleeper=sleeper,
    ).all_boxes
~~~

Add _expanded_bbox() using the fixed 25%, 8-64 px rule. Create one region per fast box, skip only boxes whose confidence is greater than the threshold, and detect accurate text solely in each qualifying expanded crop. Translate accurate coordinates, retain a flattened duplicate-merged all_boxes view, and record/emit each timing.

- [ ] **Step 4: Run the pipeline tests to verify they pass**

Run: pytest tests/test_ocr_pipeline.py -q

Expected: PASS, including the existing legacy-list tests.

- [ ] **Step 5: Commit the completed task**

~~~powershell
git add picorgftp_sql/services/ocr_pipeline.py tests/test_ocr_pipeline.py
git commit -m "feat: report paired OCR crop diagnostics"
~~~

### Task 3: Serialize the report through the OCR worker

**Files:**
- Modify: picorgftp_sql/services/ocr_worker_process.py:51-129
- Modify: picorgftp_sql/web/app.py:1416-1450
- Modify: tests/test_ocr_worker_process.py:77-96
- Modify: tests/test_ocr_execution_service.py:45-79

**Interfaces:**
- Consumes run_ocr_pipeline_report and normalized accurate_confidence_threshold from worker resource settings.
- Produces diagnostics["regions"] JSON entries with region_id, fast, source_bbox, crop_bbox, accurate, status, reason and timings_ms.
- Retains diagnostics["candidates"] for background value collection and older API clients.

- [ ] **Step 1: Write a failing worker serialization test**

~~~python
def test_worker_result_keeps_region_pairing_and_timings(monkeypatch):
    result = next(event for event in events if event["kind"] == "result")
    region = result["diagnostics"]["regions"][0]
    assert region["region_id"] == "region-1"
    assert region["fast"]["text"] == "20 kg"
    assert region["accurate"][0]["text"] == "20kg"
    assert region["timings_ms"]["accurate"] >= 0
~~~

Add an execution-service fixture containing crop_skipped and crop_finished and assert their region IDs and payloads survive the snapshot.

- [ ] **Step 2: Run worker tests to verify they fail**

Run: pytest tests/test_ocr_worker_process.py tests/test_ocr_execution_service.py -q

Expected: FAIL because results contain flattened candidates only.

- [ ] **Step 3: Serialize report regions while retaining flattened diagnostics**

~~~python
report = run_ocr_pipeline_report(
    path, profile_ids=profiles,
    accurate_confidence_threshold=int(settings.get("accurate_confidence_threshold", 99)),
    before_stage=before_stage,
    on_event=emit_progress,
)
diagnostics = diagnostics_for_boxes(report.all_boxes)
payload["regions"] = [serialize_region(region) for region in report.regions]
payload["timings_ms"] = {"total": report.total_elapsed_ms}
~~~

Implement serialize_region() locally with JSON primitives only. Preserve regions and timings while adapting worker results in web/app.py; do not alter the background collector's flattened candidate contract.

- [ ] **Step 4: Run worker tests to verify they pass**

Run: pytest tests/test_ocr_worker_process.py tests/test_ocr_execution_service.py -q

Expected: PASS.

- [ ] **Step 5: Commit the completed task**

~~~powershell
git add picorgftp_sql/services/ocr_worker_process.py picorgftp_sql/web/app.py tests/test_ocr_worker_process.py tests/test_ocr_execution_service.py
git commit -m "feat: expose OCR region diagnostics"
~~~

### Task 4: Add browser-side diagnostic utilities and unit tests

**Files:**
- Create: picorgftp_sql/web/static/ocr-diagnostics.js
- Create: tests/js/ocr-diagnostics.test.js
- Modify: picorgftp_sql/web/static/index.html:770-774

**Interfaces:**
- Produces window.PicOrg.OcrDiagnostics.normalizeReport(payload), applyProgressEvent(report, event), formatDuration(ms) and placeLabels(labels, stageBounds).
- normalizeReport returns rows with fast and accurate lists, an explicit status/reason and timings_ms.
- placeLabels returns collision-free label rectangles selected from above, below, right, left, then rail.

- [ ] **Step 1: Write failing Node tests for live updates and collisions**

~~~javascript
test("live row keeps fast text while crop progress updates accurate state", () => {
  let report = api.normalizeReport({ regions: [] });
  report = api.applyProgressEvent(report, {
    kind: "candidate_regions",
    payload: { regions: [{ region_id: "region-1", text: "32,8", confidence: 0.93, bbox: [10, 10, 40, 25] }] },
  });
  report = api.applyProgressEvent(report, { kind: "crop_started", payload: { region_id: "region-1" } });
  assert.equal(report.rows[0].fast[0].text, "32,8");
  assert.equal(report.rows[0].status, "scanning");
});

test("placement moves overlapping labels to distinct positions", () => {
  const labels = api.placeLabels(twoOverlappingLabels, { width: 320, height: 200 });
  assert.notDeepEqual(labels[0].rect, labels[1].rect);
  assert.equal(new Set(labels.map((item) => item.position)).size, 2);
});
~~~

- [ ] **Step 2: Run the browser test to verify it fails**

Run: node --test tests/js/ocr-diagnostics.test.js

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the dependency-free browser module**

~~~javascript
window.PicOrg = window.PicOrg || {};
window.PicOrg.OcrDiagnostics = {
  normalizeReport(payload) {
    return { rows: (payload.regions || []).map(normalizeRegion), timings_ms: payload.timings_ms || {} };
  },
  applyProgressEvent(report, event) {
    return updateRegionRow(report, event.kind, event.payload || {});
  },
  formatDuration(milliseconds) {
    return milliseconds < 1000 ? `${Math.round(milliseconds)} ms` : `${(milliseconds / 1000).toFixed(2)} s`;
  },
  placeLabels(labels, stageBounds) {
    return labels.map((label, index) => firstFreePlacement(label, labels.slice(0, index), stageBounds));
  },
};
~~~

Normalize flattened and unavailable results to one visible fallback row with a reason. Load this file before app.js.

- [ ] **Step 4: Run the browser test to verify it passes**

Run: node --test tests/js/ocr-diagnostics.test.js

Expected: PASS.

- [ ] **Step 5: Commit the completed task**

~~~powershell
git add picorgftp_sql/web/static/ocr-diagnostics.js picorgftp_sql/web/static/index.html tests/js/ocr-diagnostics.test.js
git commit -m "feat: add OCR diagnostic view helpers"
~~~

### Task 5: Render paired diagnostics live and after completion

**Files:**
- Modify: picorgftp_sql/web/static/app.js:13644-13796,13897-14080
- Modify: picorgftp_sql/web/static/app.css:1449-1580
- Modify: tests/test_web_ui_integrity.py:65-115

**Interfaces:**
- Consumes window.PicOrg.OcrDiagnostics and worker regions/progress events.
- Produces renderOcrDiagnosticTable(report, focusRegionId) and renderOcrOverlay(stage, report, focusRegionId).
- Produces synchronized range and number inputs named ocr_accurate_confidence_threshold; settings save sends accurate_confidence_threshold inside ocr.

- [ ] **Step 1: Write failing UI integrity checks**

~~~python
def test_ocr_diagnostics_has_paired_live_columns_and_threshold_control(self):
    self.assertIn("renderOcrDiagnosticTable", source)
    self.assertIn("Szybki", source)
    self.assertIn("Dokladny", source)
    self.assertIn("ocr_accurate_confidence_threshold", source)
    self.assertIn("ocr-diagnostic-rail", css)
    self.assertIn("OcrDiagnostics.applyProgressEvent", source)
~~~

Also assert that the settings payload contains accurate_confidence_threshold: data.get("ocr_accurate_confidence_threshold").

- [ ] **Step 2: Run the UI integrity test to verify it fails**

Run: pytest tests/test_web_ui_integrity.py -q

Expected: FAIL because neither the paired table nor the threshold controls exist.

- [ ] **Step 3: Replace flattened candidate rendering with the shared report renderer**

~~~javascript
function renderOcrDiagnosticTable(report, focusRegionId = null) {
  // Create Szybki and Dokladny columns and one row per stable region.
  // Render an explicit status/reason instead of a blank accurate cell.
}

function renderOcrOverlay(stage, report, focusRegionId = null) {
  // Use OcrDiagnostics.placeLabels() and an ocr-diagnostic-rail fallback.
}
~~~

Make renderOcrLivePreview retain a normalized report and re-render table/overlay after each event. Make renderOcrDiagnostics consume result.regions using the same functions. Hover/focus must show raw text, comparison value, confidence, source/crop/output boxes, threshold decision and all timing values. Replace canvas text drawing with DOM annotation elements.

Add grid/table styles, fast/accurate colors, the diagnostic panel, focus styling and rail. In renderSettingsOcr create one labelled range input plus one number input (0-100), synchronize input events and save the number value.

- [ ] **Step 4: Run the browser and UI tests to verify they pass**

Run: node --test tests/js/ocr-diagnostics.test.js; pytest tests/test_web_ui_integrity.py -q

Expected: PASS.

- [ ] **Step 5: Commit the completed task**

~~~powershell
git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py
git commit -m "feat: show paired OCR diagnostics live"
~~~

### Task 6: Document and regression-test the feature

**Files:**
- Modify: docs/web-panel.md
- Modify: tests/test_web_app_files.py

**Interfaces:**
- Documents the <= threshold semantics, default 99, decimal comparison, crop margin, pairing and diagnostic status states.

- [ ] **Step 1: Add a static-file assertion for the new module**

~~~python
def test_web_static_files_include_ocr_diagnostics_module():
    assert (STATIC_DIR / "ocr-diagnostics.js").is_file()
~~~

- [ ] **Step 2: Document user-visible OCR behavior**

~~~markdown
### Tester OCR

Ustawienie "Skanuj dokladnym, gdy pewnosc szybkiego <= [%]" ma domyslnie 99.
Wartosc 100 skanuje wszystkie wycinki. Wynik pokazuje surowy odczyt obu modeli
w sparowanych kolumnach; 23,4 i 23.4 sa porownywane jako ta sama wartosc.
~~~

Also document the 25% / 8-64 px crop margin, hover details and statuses for skipped/empty accurate scans.

- [ ] **Step 3: Run the full relevant regression suite**

Run: pytest tests/test_ocr_values.py tests/test_ocr_settings.py tests/test_ocr_pipeline.py tests/test_ocr_worker_process.py tests/test_ocr_execution_service.py tests/test_web_ui_integrity.py tests/test_web_app_files.py -q; node --test tests/js/*.test.js

Expected: PASS.

- [ ] **Step 4: Inspect the final diff and commit the documentation task**

~~~powershell
git diff --check
git status --short
git add docs/web-panel.md tests/test_web_app_files.py
git commit -m "docs: explain OCR diagnostic controls"
~~~

## Plan Self-Review

- Spec coverage: Tasks 1-3 cover exact values, threshold settings, padding, paired reports, timings and explicit failure states. Tasks 4-5 cover the shared live/final two-column view, hover details and collision-free annotations. Task 6 covers documentation and regression verification.
- Placeholder scan: crop formula, threshold inequality/default, interfaces and fallback states are explicit.
- Type consistency: Task 2 defines the Python report consumed by Task 3. Task 3 serializes regions, Task 4 normalizes them, and Task 5 renders them. The accurate_confidence_threshold setting is defined in Task 1 and kept under exactly that name throughout.
