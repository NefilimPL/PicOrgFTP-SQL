# Similar Product Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let web-panel users preview and explicitly accept local files proposed from color variants of the same product.

**Architecture:** A pure Python module will normalize settings, discover sibling color directories, deduplicate files by SHA-256 and allocate candidates to selected slots. FastAPI will return only signed preview metadata, and the browser will keep candidates separate from submitted files until the operator accepts one.

**Tech Stack:** Python, FastAPI/Starlette, local file index, vanilla JavaScript, CSS, pytest/unittest.

## Global Constraints

- Web panel only; do not change desktop behavior.
- Match equal name, type, model and extra with a different normalized color combination.
- Search only local product folders; never use FTP, SQL or Pimcore as candidate sources.
- Default configuration is disabled with an empty permitted-slot list.
- Never expose local paths; reuse signed `/api/file` and `/api/thumbnail` endpoints.
- A candidate is not submitted or persisted until `Wczytaj z podobnego` is clicked.
- Prefer the source slot; overflow distinct candidates into the next free permitted slot.
- Manual upload or clearing a slot dismisses that candidate for the current draft.

---

### Task 1: Settings and pure discovery service

**Files:**

- Create: `picorgftp_sql/similar_product_files.py`
- Modify: `picorgftp_sql/common.py`
- Modify: `picorgftp_sql/config.py`
- Test: `tests/test_similar_product_files.py`

**Interfaces:**

- `SIMILAR_FILE_DETECTION_KEY = "similar_file_detection"`
- `normalize_similar_file_settings(raw_settings, slot_defs) -> dict[str, object]`
- `find_similar_file_candidates(base_dir, product, slot_defs, settings, *, file_index=None, occupied_prefixes=()) -> list[SimilarFileCandidate]`

- [ ] **Step 1: Write a failing configuration test**

```python
from picorgftp_sql.similar_product_files import normalize_similar_file_settings


def test_normalize_similar_settings_defaults_disabled_and_removes_unknown_slots():
    slots = [{"prefix": "01", "label": "Instrukcja"}, {"prefix": "02", "label": "Detal"}]
    assert normalize_similar_file_settings(
        {"enabled": True, "slot_prefixes": ["1", "99", "02", "02"]}, slots
    ) == {"enabled": True, "slot_prefixes": ["01", "02"]}
    assert normalize_similar_file_settings(None, slots) == {"enabled": False, "slot_prefixes": []}
```

- [ ] **Step 2: Confirm the test fails**

Run: `pytest tests/test_similar_product_files.py::test_normalize_similar_settings_defaults_disabled_and_removes_unknown_slots -v`

Expected: FAIL because the module is absent.

- [ ] **Step 3: Implement the disabled default and normalizer**

```python
# common.py
SIMILAR_FILE_DETECTION_KEY = "similar_file_detection"
DEFAULT_CONFIG.setdefault(SIMILAR_FILE_DETECTION_KEY, {"enabled": False, "slot_prefixes": []})

# similar_product_files.py
def normalize_similar_file_settings(raw_settings, slot_defs) -> dict[str, object]:
    raw_settings = raw_settings if isinstance(raw_settings, dict) else {}
    known = {slot["prefix"] for slot in slot_defs}
    prefixes = []
    for value in raw_settings.get("slot_prefixes", []):
        prefix = normalize_slot_prefix(value)
        if prefix in known and prefix not in prefixes:
            prefixes.append(prefix)
    return {"enabled": bool(raw_settings.get("enabled")), "slot_prefixes": prefixes}
```

Invoke the normalizer after slot definitions are normalized in the existing config-load path. Existing files must get the disabled default and lose deleted slot IDs.

- [ ] **Step 4: Confirm the normalizer passes**

Run: `pytest tests/test_similar_product_files.py::test_normalize_similar_settings_defaults_disabled_and_removes_unknown_slots -v`

Expected: PASS.

- [ ] **Step 5: Write failing discovery, digest and placement tests**

```python
def test_other_color_candidate_stays_in_its_source_slot(tmp_path):
    candidates = find_similar_file_candidates(str(tmp_path), white_product(), slot_defs(), enabled_slots())
    assert [(item.source_prefix, item.target_prefix) for item in candidates] == [("01", "01")]


def test_distinct_same_slot_files_overflow_and_duplicate_digest_is_skipped(tmp_path):
    # BLACK/01 and OAK/01 have different bytes; GREY/01 repeats BLACK bytes.
    candidates = find_similar_file_candidates(str(tmp_path), white_product(), slot_defs(), enabled_slots())
    assert [(item.source_color_segment, item.target_prefix) for item in candidates] == [
        ("BLACK", "01"), ("OAK", "02")
    ]


def test_occupied_or_non_permitted_slots_are_not_used(tmp_path):
    candidates = find_similar_file_candidates(
        str(tmp_path), white_product(), slot_defs(), enabled_slots(), occupied_prefixes={"01", "02"}
    )
    assert [item.target_prefix for item in candidates] == ["03"]
```

- [ ] **Step 6: Confirm discovery tests fail**

Run: `pytest tests/test_similar_product_files.py -k "source_slot or duplicate_digest or non_permitted" -v`

Expected: FAIL because discovery is absent.

- [ ] **Step 7: Implement bounded discovery, digest and allocation**

```python
@dataclass(frozen=True)
class SimilarFileCandidate:
    candidate_id: str
    source_prefix: str
    target_prefix: str
    source_path: str
    filename: str
    source_color_segment: str
    size_bytes: int
    sha256: str
    is_pdf: bool


def find_similar_file_candidates(base_dir, product, slot_defs, settings, *, file_index=None, occupied_prefixes=()):
    if not settings["enabled"] or not settings["slot_prefixes"]:
        return []
    # Enumerate only sibling color directories for the normalized name/type/model/extra.
    # Parse selected slots, hash readable files, drop repeated digests, sort by folder/name,
    # allocate source prefix first and then the next free selected prefix.
```

Use `file_index.get_colors`, `get_extras` and `get_product_files` when available, then merge direct `scandir` results so the index cannot hide newer files. Hash in chunks; catch `OSError` per file; never walk outside `base_dir`; never query a remote service.

- [ ] **Step 8: Confirm all domain tests pass**

Run: `pytest tests/test_similar_product_files.py -v`

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

Run: `git add picorgftp_sql/common.py picorgftp_sql/config.py picorgftp_sql/similar_product_files.py tests/test_similar_product_files.py`

Run: `git commit -m "feat: discover similar local product files"`

### Task 2: Settings persistence and authenticated API

**Files:**

- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/app.py`
- Test: `tests/test_web_app_files.py`

**Interfaces:**

- `settings_snapshot()` returns `similar_file_detection`.
- `update_settings(payload)` validates and persists `similar_file_detection` after slot definitions.
- `POST /api/similar-files` returns candidate fields: `id`, `source_prefix`, `target_prefix`, `filename`, `source_color`, `size_bytes`, `is_pdf`, `token`, `url`, `thumb_url`.

- [ ] **Step 1: Write failing persistence and API tests**

```python
def test_similar_settings_round_trip_removes_unknown_slots(monkeypatch):
    monkeypatch.setitem(config.CONFIG, SLOT_DEFS_KEY, [{"prefix": "01", "label": "Instrukcja"}])
    update_settings({"similar_file_detection": {"enabled": True, "slot_prefixes": ["01", "99"]}})
    assert settings_snapshot()["similar_file_detection"] == {"enabled": True, "slot_prefixes": ["01"]}


def test_similar_files_endpoint_requires_login_and_hides_source_path():
    with TestClient(web_app.app) as client:
        assert client.post("/api/similar-files", json=valid_product()).status_code == 401
    with patched_similar_candidate("C:/photos/BLACK/NO-LED/1_01.pdf"):
        response = authenticated_client().post("/api/similar-files", json=valid_product())
    item = response.json()["candidates"][0]
    assert item["url"].startswith("/api/file?token=")
    assert "path" not in item and "C:/" not in json.dumps(item)
```

- [ ] **Step 2: Confirm these tests fail**

Run: `pytest tests/test_web_app_files.py -k "similar_settings or similar_files_endpoint" -v`

Expected: FAIL because the setting and endpoint are absent.

- [ ] **Step 3: Implement persistence and index-aware lookup wrapper**

```python
# web_data.py, after slot definitions are normalized
similar_payload = payload.get(SIMILAR_FILE_DETECTION_KEY)
if isinstance(similar_payload, dict):
    cfg[SIMILAR_FILE_DETECTION_KEY] = normalize_similar_file_settings(
        similar_payload, cfg[SLOT_DEFS_KEY]
    )

# settings_snapshot() return payload
SIMILAR_FILE_DETECTION_KEY: normalize_similar_file_settings(
    cfg.get(SIMILAR_FILE_DETECTION_KEY), slot_defs
),
```

Add `find_web_similar_file_candidates(product_payload)`: apply existing product-field normalization, return no candidates for incomplete identity values, obtain `_get_file_index(start=True)` and invoke Task 1 with `settings.l`.

- [ ] **Step 4: Implement the read-only endpoint**

```python
@app.post("/api/similar-files")
async def similar_files_api(request: Request) -> JSONResponse:
    _require_user(request)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Niepoprawne dane produktu.")
    candidates = await run_in_threadpool(find_web_similar_file_candidates, payload)
    return JSONResponse({"candidates": [_public_similar_candidate(item) for item in candidates]})
```

`_public_similar_candidate` must pass the local path through `_enrich_photo_payload`, then return only declared fields. This endpoint does not create files, history events, cache entries, FTP requests or SQL requests.

- [ ] **Step 5: Confirm API tests pass**

Run: `pytest tests/test_web_app_files.py -k "similar_settings or similar_files_endpoint" -v`

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

Run: `git add picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_web_app_files.py`

Run: `git commit -m "feat: expose similar product file suggestions"`

### Task 3: Browser controls, candidate state and source preview

**Files:**

- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `picorgftp_sql/web/static/index.html` only if a stable PDF element is required
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**

- `state.similarCandidates`, `state.dismissedSimilarSlots`, `scheduleSimilarFileLookup()` and `acceptSimilarCandidate(prefix)`.
- Source key `similar`, represented by the `PODOBNE` button after `SQL`.

- [ ] **Step 1: Write failing browser-contract tests**

```python
def test_slot_settings_collect_similar_file_detection_configuration():
    source = APP_JS.read_text(encoding="utf-8")
    assert '"similar_file_detection"' in source
    assert '"Wykrywaj pliki z podobnych produktow"' in source
    assert "similar_file_slot_prefixes" in source


def test_similar_candidate_requires_explicit_acceptance_and_has_source_button():
    source = APP_JS.read_text(encoding="utf-8")
    assert "function acceptSimilarCandidate(prefix)" in source
    assert "Wczytaj z podobnego" in source
    assert '["similar", "PODOBNE"' in source
    assert 'source === "similar"' in source
```

- [ ] **Step 2: Confirm contracts fail**

Run: `pytest tests/test_web_ui_integrity.py -k "similar_candidate or similar_file_detection" -v`

Expected: FAIL because the controls and source are absent.

- [ ] **Step 3: Add settings controls in the Slots tab**

After the slot list in `renderSettingsSlots`, add the `similar_files_enabled` checkbox and a `similar_file_slot_prefixes` checkbox for every current slot. Disable per-slot controls while the global checkbox is off. Extend the existing save payload:

```javascript
similar_file_detection: {
  enabled: data.has("similar_files_enabled"),
  slot_prefixes: [...form.querySelectorAll('[name="similar_file_slot_prefixes"]:checked')]
    .map((input) => input.value),
},
```

- [ ] **Step 4: Add draft-only lookup and explicit acceptance**

```javascript
function acceptSimilarCandidate(prefix) {
  const candidate = state.similarCandidates.get(prefix);
  if (!candidate || state.dismissedSimilarSlots.has(prefix)) return;
  markSlotDeletion(prefix, state.loadedPhotos.get(prefix));
  state.files.set(prefix, {
    file: null, name: candidate.filename, size: candidate.size_bytes,
    type: candidate.is_pdf ? "application/pdf" : "", token: candidate.token,
    url: candidate.url, thumb_url: candidate.thumb_url, preprocessed: true,
    uploading: false, error: "", similar_candidate_id: candidate.id,
  });
  state.slotSources.set(prefix, "similar");
  renderSlot(prefix);
}
```

Lookup uses a 450 ms debounce after name/type/model/color/extra changes. Apply a response only when the monotonically increasing request ID and normalized identity key both still match. Before acceptance, candidates live only in `state.similarCandidates`; never in `state.files` or `state.loadedPhotos`. Manual upload or clear removes the candidate and records the prefix in `state.dismissedSimilarSlots`; reset both collections for a new draft.

- [ ] **Step 5: Add `PODOBNE`, 60% image preview and PDF preview**

Extend `renderSlotBadges`, `selectedSlotSource`, `thumbnailUrl`, `loadedFileUrl`, `openSlotFile`, `createSlotNode` and `updateSlotPreview` for source `similar`. Render `PODOBNE` only for a non-dismissed candidate and after `SQL`; clicking it switches the inline preview. Add `Wczytaj z podobnego` only for an unaccepted candidate. Candidate images use 60% opacity. A candidate PDF renders in the preview area as same-origin `<object type="application/pdf">` with filename fallback, and the object must be removed when switching sources. `Otworz` opens the current `similar` URL in a new tab.

- [ ] **Step 6: Add isolated CSS**

```css
.slot-card[data-active-source="similar"] .slot-preview.has-similar-candidate img { opacity: 0.6; }
.slot-similar-preview { width: 100%; height: 100%; border: 0; }
.slot-similar-accept { width: 100%; margin-top: 0.35rem; }
```

Use existing design tokens and button styles. Do not affect LOCAL, FTP, SQL or manually selected previews.

- [ ] **Step 7: Verify browser contracts and syntax**

Run: `pytest tests/test_web_ui_integrity.py -k "similar_candidate or similar_file_detection" -v`

Expected: PASS.

Run: `python -m compileall picorgftp_sql`

Expected: exit code 0.

If `C:\Program Files\nodejs\node.exe` exists, run `& 'C:\Program Files\nodejs\node.exe' --check picorgftp_sql\web\static\app.js`; otherwise record the existing Node-only check as skipped.

- [ ] **Step 8: Commit Task 3**

Run: `git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css picorgftp_sql/web/static/index.html tests/test_web_ui_integrity.py`

Run: `git commit -m "feat: review similar files in web slots"`

### Task 4: End-to-end regression and documentation

**Files:**

- Modify: `docs/web-panel.md`
- Modify: `tests/test_web_app_files.py`
- Test: `tests/test_similar_product_files.py`
- Test: `tests/test_web_ui_integrity.py`

- [ ] **Step 1: Write an end-to-end read-only lookup test**

```python
def test_similar_lookup_returns_submit_ready_token_but_does_not_schedule_a_slot(tmp_path, monkeypatch):
    source = tmp_path / "photos" / "BLACK" / "NO-LED" / "5901234567890_01.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(web_app, "find_web_similar_file_candidates", lambda _payload: [candidate_at(source)])
    response = authenticated_client().post("/api/similar-files", json=valid_product())
    item = response.json()["candidates"][0]
    assert web_app._path_from_file_token(item["token"]) == str(source)
    assert "existing_slot_01" not in response.request.content.decode("utf-8")
```

- [ ] **Step 2: Confirm the API contract passes**

Run: `pytest tests/test_web_app_files.py::test_similar_lookup_returns_submit_ready_token_but_does_not_schedule_a_slot -v`

Expected: PASS. The endpoint returns a valid signed token but does not create the browser form key `existing_slot_01`; only Task 3 acceptance creates that key.

- [ ] **Step 3: Document and verify acceptance-only submission**

Add `Pliki z podobnych produktów` to `docs/web-panel.md`: administrators enable the feature and choose slots; only local color variants are searched; candidates are not saved by default; `PODOBNE` switches the slot preview; `Otwórz` opens the active source; `Wczytaj z podobnego` accepts one file. Confirm the process serializer already turns accepted token-backed `state.files` entries into `existing_slot_<prefix>` and never reads `state.similarCandidates`; make only the smallest correction if it assumes every item has a browser `File` object.

- [ ] **Step 4: Run focused and full regression suites**

Run: `pytest tests/test_similar_product_files.py tests/test_web_app_files.py tests/test_web_ui_integrity.py -v`

Expected: PASS.

Run: `pytest -q`

Expected: PASS; Node-only coverage may be skipped only if `C:\Program Files\nodejs\node.exe` is missing.

- [ ] **Step 5: Review and commit only feature files**

Run: `git status --short`

Expected: only planned feature files plus pre-existing user changes.

Run: `git add docs/web-panel.md tests/test_web_app_files.py tests/test_similar_product_files.py tests/test_web_ui_integrity.py`

Run: `git commit -m "docs: document similar product file suggestions"`
