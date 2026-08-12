# Reliable Similar-file Lookup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make similar-file suggestions responsive, correct during rapid form changes, and visibly active while retaining strict LED/NO-LED matching.

**Architecture:** The discovery module will accept name/type/model with optional colour and extra, and cache digests by immutable file metadata. The web-data layer will coalesce identical lookups and log anonymized timings. The browser will own cancellable lookups and a slot-local scanning state independent of photo loading.

**Tech Stack:** Python, FastAPI/Starlette, threading, local file index, vanilla JavaScript, CSS, pytest/unittest, Node.js.

## Global Constraints

- Web panel only; desktop behavior remains unchanged.
- Candidates remain read-only until explicitly accepted; signed token and authorization rules remain unchanged.
- Name, type_name, and model are the minimum lookup identity.
- A supplied colour or extra is strict: LED and NO-LED must not cross-match.
- A current lookup must be able to supersede a prior one; photo loading must not schedule similar lookup.
- Search feedback applies only to free slots, respects `prefers-reduced-motion`, and preserves manual/accepted files.
- Logs contain only a SHA-256-derived query fingerprint, elapsed time, counters, and candidate count—never paths or product values.

---

### Task 1: Partial-identity discovery and digest reuse

**Files:**

- Modify: `picorgftp_sql/similar_product_files.py`
- Modify: `tests/test_similar_product_files.py`

**Interfaces:**

- Produces: `find_similar_file_candidates(base_dir, product, slot_defs, settings, *, file_index=None, occupied_prefixes=()) -> list[SimilarFileCandidate]` accepting an optional colour and extra.
- Adds: module-private `_DigestCache.get(path: str) -> tuple[int, str] | None`, keyed by canonical path, `st_size`, and `st_mtime_ns`.

- [ ] **Step 1: Write failing domain tests**

```python
def test_base_identity_finds_candidates_before_colour_and_extra_are_chosen(tmp_path):
    _write_product_file(tmp_path, "BLACK", "01", b"black")
    _write_product_file(tmp_path, "WHITE", "01", b"white")
    product = {**white_product(), "color1": "", "extra": ""}

    candidates = find_similar_file_candidates(
        str(tmp_path), product, slot_defs(), enabled_slots()
    )

    assert [item.source_color_segment for item in candidates] == ["BLACK", "WHITE"]


def test_explicit_extra_keeps_led_and_no_led_separate(tmp_path):
    _write_product_file(tmp_path, "BLACK", "01", b"led", extra="LED")
    _write_product_file(tmp_path, "WHITE", "01", b"no-led", extra="NO-LED")
    product = {**white_product(), "color1": "OAK", "extra": "LED"}

    candidates = find_similar_file_candidates(
        str(tmp_path), product, slot_defs(), enabled_slots()
    )

    assert [item.source_color_segment for item in candidates] == ["BLACK"]


def test_unchanged_candidate_uses_cached_digest(tmp_path, monkeypatch):
    _write_product_file(tmp_path, "BLACK", "01", b"black")
    calls = 0
    original = similar_product_files._read_digest

    def count_reads(path):
        nonlocal calls
        calls += 1
        return original(path)

    monkeypatch.setattr(similar_product_files, "_read_digest", count_reads)
    find_similar_file_candidates(str(tmp_path), white_product(), slot_defs(), enabled_slots())
    find_similar_file_candidates(str(tmp_path), white_product(), slot_defs(), enabled_slots())
    assert calls == 1
```

Extend `_write_product_file` with `extra="NO-LED"` and import the module for the digest spy. Keep the existing traversal, slot allocation, and same-colour tests.

- [ ] **Step 2: Verify that the tests fail**

Run: `pytest tests/test_similar_product_files.py -k "base_identity or explicit_extra or cached_digest" -v`

Expected: FAIL because a colour is required, blank extra becomes NO-LED, and each invocation rereads the digest.

- [ ] **Step 3: Implement only the tested behavior**

```python
class _DigestCache:
    def get(self, path: str) -> tuple[int, str] | None:
        canonical = os.path.realpath(os.path.abspath(path))
        stat = os.stat(canonical)
        key = (canonical, stat.st_size, stat.st_mtime_ns)
        # return cached digest for key; otherwise read and replace prior key for path


def find_similar_file_candidates(...):
    # require name/type/model, not a colour segment
    has_colour_filter = bool(any(colors))
    raw_extra = str(_product_value(product, "extra") or "").strip()
    selected_extra = normalize_extra_segment(raw_extra) if raw_extra else ""
    # exclude identical colour only when has_colour_filter
    # filter extras only when selected_extra is non-empty
    # use _DIGEST_CACHE.get(source_path)
```

Retain `_safe_child`, stable sorting, digest deduplication, and per-file `OSError` handling. Evict a prior digest cache record for a path if file size or mtime changes.

- [ ] **Step 4: Verify focused suite**

Run: `pytest tests/test_similar_product_files.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add picorgftp_sql/similar_product_files.py tests/test_similar_product_files.py
git commit -m "feat: speed partial similar file discovery"
```

### Task 2: Coalesced web lookup and anonymized timing

**Files:**

- Modify: `picorgftp_sql/web_data.py`
- Modify: `tests/test_web_app_files.py`

**Interfaces:**

- Produces: `find_web_similar_file_candidates(product_payload: dict[str, object]) -> list[SimilarFileCandidate]` using a normalized, occupied-slot-aware TTL cache and single-flight map.
- Adds: `reset_similar_file_lookup_cache() -> None` for test isolation only.

- [ ] **Step 1: Write failing cache tests**

```python
def test_web_similar_lookup_coalesces_identical_requests(monkeypatch):
    calls = 0

    def discover(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr(web_data, "find_similar_file_candidates", discover)
    web_data.reset_similar_file_lookup_cache()

    assert web_data.find_web_similar_file_candidates(_similar_product_payload()) == []
    assert web_data.find_web_similar_file_candidates(_similar_product_payload()) == []
    assert calls == 1


def test_web_similar_lookup_key_changes_with_extra_and_occupied_slots(monkeypatch):
    calls = []
    monkeypatch.setattr(
        web_data, "find_similar_file_candidates", lambda *_a, **kw: calls.append(kw) or []
    )
    web_data.reset_similar_file_lookup_cache()

    web_data.find_web_similar_file_candidates(_similar_product_payload())
    web_data.find_web_similar_file_candidates({**_similar_product_payload(), "extra": "LED"})
    web_data.find_web_similar_file_candidates(
        {**_similar_product_payload(), "occupied_prefixes": ["01"]}
    )

    assert len(calls) == 3
```

- [ ] **Step 2: Verify that the tests fail**

Run: `pytest tests/test_web_app_files.py -k "similar_lookup_coalesces or similar_lookup_key_changes" -v`

Expected: FAIL because each endpoint lookup currently calls discovery directly.

- [ ] **Step 3: Implement bounded cache, single-flight, and diagnostics**

```python
SIMILAR_LOOKUP_CACHE_TTL_SECONDS = 10.0
SIMILAR_LOOKUP_CACHE_MAX_ITEMS = 32

def _similar_lookup_key(normalized_payload, occupied_prefixes) -> tuple[str, ...]:
    return (
        normalized_text(normalized_payload.get("name")),
        normalized_text(normalized_payload.get("type_name")),
        normalized_text(normalized_payload.get("model")),
        normalized_text(normalized_payload.get("color1")),
        normalized_text(normalized_payload.get("color2")),
        normalized_text(normalized_payload.get("color3")),
        normalized_text(normalized_payload.get("extra")),
        *sorted(normalize_slot_prefix(prefix) for prefix in occupied_prefixes),
    )

def find_web_similar_file_candidates(product_payload):
    # normalize payload and derive key
    # under a lock: return fresh copy of nonexpired cached tuple, or wait on existing Event
    # owner scans without holding lock; cache tuple result; signal waiters in finally
    # log sha256(repr(key))[:12], elapsed milliseconds, and result count only
```

Expire entries at access, bound at 32 items, and remove the oldest when full. On an owner error, remove and signal its in-flight event, then re-raise. Do not change API response fields; existing `occupied_prefixes`, authorization, and token tests must remain valid.

- [ ] **Step 4: Verify web-data/API suite**

Run: `pytest tests/test_web_app_files.py -k "similar" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add picorgftp_sql/web_data.py tests/test_web_app_files.py
git commit -m "perf: coalesce similar file lookups"
```

### Task 3: Cancellable lookup lifecycle and slot feedback

**Files:**

- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_web_ui_integrity.py`

**Interfaces:**

- Adds state fields: `similarFileLookupController`, `similarFileLookupInFlight`, `similarFileLookupStartedAt`.
- Adds: `setSimilarFileLookupState(active, key = "")`, `cancelSimilarFileLookup()`, and `startSimilarFileLookup({ immediate = false } = {})`.
- Keeps: `lookupSimilarFiles()` as the only `/api/similar-files` request function.

- [ ] **Step 1: Write failing UI contracts and stale-response harness**

```python
def test_similar_lookup_uses_abort_signal_and_ignores_abort_error(self):
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("async function lookupSimilarFiles")
    end = source.index("function scheduleSimilarFileLookup", start)
    lookup = source[start:end]
    self.assertIn("new AbortController()", lookup)
    self.assertIn("signal: controller.signal", lookup)
    self.assertIn('error.name === "AbortError"', lookup)


def test_photo_load_does_not_schedule_similar_lookup(self):
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("async function loadPhotosForEntry")
    end = source.index("function fillForm", start)
    self.assertNotIn("scheduleSimilarFileLookup", source[start:end])


def test_empty_slot_has_search_feedback_and_reduced_motion_css(self):
    source = APP_JS.read_text(encoding="utf-8")
    css = APP_CSS.read_text(encoding="utf-8")
    self.assertIn("Automatyczne wyszukiwanie podobnych plikow", source)
    self.assertIn("similar-searching", source)
    self.assertIn(".slot-card.similar-searching .slot-preview", css)
    self.assertIn("@media (prefers-reduced-motion: reduce)", css)
```

Add a Node test harness with two deferred `requestJson` promises: start old lookup, start new lookup, resolve old last, then assert only new candidates are rendered and no error status was written.

- [ ] **Step 2: Verify expected UI failures**

Run: `pytest tests/test_web_ui_integrity.py -k "similar_lookup_uses_abort or photo_load_does_not_schedule or empty_slot_has_search or late_similar" -v`

Expected: FAIL because lookup has no abort controller, photo loading schedules lookup, and no search-state UI exists.

- [ ] **Step 3: Implement cancellable current-request ownership**

```javascript
function setSimilarFileLookupState(active, key = "") {
  state.similarFileLookupInFlight = active;
  state.similarFileLookupKey = active ? key : "";
  if (active) state.similarFileLookupStartedAt = performance.now();
  renderSlots();
}

async function lookupSimilarFiles() {
  const key = similarFileIdentityKey();
  if (!hasSimilarBaseIdentity()) return cancelSimilarFileLookup();
  state.similarFileLookupController?.abort();
  const controller = new AbortController();
  state.similarFileLookupController = controller;
  const requestId = ++state.similarFileLookupRequestId;
  setSimilarFileLookupState(true, key);
  try {
    const payload = await requestJson("/api/similar-files", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...fields, occupied_prefixes: similarOccupiedSlotPrefixes() }),
      signal: controller.signal,
      timeoutMs: 15000,
    });
    if (requestId !== state.similarFileLookupRequestId || similarFileIdentityKey() !== key) return;
    applySimilarCandidates(payload.candidates || []);
  } catch (error) {
    if (error.name !== "AbortError" && requestId === state.similarFileLookupRequestId) {
      showSimilarLookupError(error);
    }
  } finally {
    if (requestId === state.similarFileLookupRequestId) setSimilarFileLookupState(false);
  }
}
```

`hasSimilarBaseIdentity()` requires only name/type/model. Remove the `scheduleSimilarFileLookup()` call from `loadPhotosForEntry`. Make `fillForm`, the successful form-fill paths in `searchByEan` and `searchByProduct`, and the FIT action call `startSimilarFileLookup({ immediate: true })` after updating fields; retain 450 ms scheduling only on text input changes.

- [ ] **Step 4: Implement only-free-slot feedback**

```javascript
const searching = state.similarFileLookupInFlight && isFreeSimilarSlot(prefix);
card.classList.toggle("similar-searching", searching);
if (searching && !candidate && !selectedFile && !loadedPhoto) {
  empty.textContent = "Automatyczne wyszukiwanie podobnych plikow...";
  empty.setAttribute("role", "status");
  empty.setAttribute("aria-live", "polite");
} else {
  empty.removeAttribute("role");
  empty.removeAttribute("aria-live");
}
```

Apply in both `createSlotNode` and `updateSlotPreview` without altering candidate/PDF/upload rendering. Add animated RGB dashed border styling scoped to `.slot-card.similar-searching .slot-preview`; the reduced-motion media query keeps a static colour treatment. Manual, loaded, and accepted similar files must never get this class.

- [ ] **Step 5: Verify focused UI suite and parser**

Run: `pytest tests/test_web_ui_integrity.py -k "similar" -v`

Run: `& 'C:\\Program Files\\nodejs\\node.exe' --check picorgftp_sql/web/static/app.js`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py
git commit -m "feat: show similar file search progress"
```

### Task 4: Integrated regression verification

**Files:**

- Modify only a scoped defect revealed by verification in Tasks 1–3.

**Interfaces:**

- Verifies discovery, authenticated API, UI lifecycle, accessibility, and existing explicit-acceptance behavior together.

- [ ] **Step 1: Run all directly affected test suites**

Run: `pytest tests/test_similar_product_files.py tests/test_web_app_files.py tests/test_web_ui_integrity.py -v`

Expected: PASS.

- [ ] **Step 2: Run static verification**

Run: `python -m compileall -q picorgftp_sql`

Run: `& 'C:\\Program Files\\nodejs\\node.exe' --check picorgftp_sql/web/static/app.js`

Run: `git diff --check`

Expected: all commands exit 0.

- [ ] **Step 3: Confirm requirement coverage from test output**

Confirm: unchanged candidates do not reread digests, identical lookups share discovery work, explicit LED/NO-LED filtering holds, stale browser responses cannot render, photo loading does not start scan, and scan animation excludes manual/accepted slots.

- [ ] **Step 4: Commit a verification correction only when one was necessary**

If no test revealed a defect, make no additional commit. If a defect was found, add only the affected files from Tasks 1–3 and use: 

```bash
git commit -m "fix: complete similar file lookup reliability"
```
