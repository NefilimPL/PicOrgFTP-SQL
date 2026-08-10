# Similar Product UI Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compact the similar-file settings and controls, and make candidate preview/open behavior reliable.

**Architecture:** Keep the existing settings payload and candidate model. The browser renders the selected prefixes inside their slot rows, refreshes lookup placement after a manual assignment, and uses candidate URLs directly. The backend canonicalizes signed-path roots before its existing containment check.

**Tech Stack:** FastAPI/Python, vanilla JavaScript/CSS, pytest, Node.js syntax checks.

## Global Constraints

- Work on the current `dev` branch.
- Preserve explicit acceptance: a suggestion is never submitted until `✓` is clicked.
- Keep lookup local and read-only.
- Keep the signed token and allowed-root boundary for all file/thumbnail routes.

---

### Task 1: Canonical preview-path validation

**Files:**
- Modify: `picorgftp_sql/web/app.py:_path_from_file_token`
- Modify: `tests/test_web_app_files.py`

**Interfaces:**
- Produces: `_path_from_file_token(token)` accepts a signed file under a resolved equivalent of `settings.l`.

- [ ] **Step 1: Write the failing test**

```python
def test_file_token_accepts_the_resolved_photos_root(tmp_path, monkeypatch):
    photos = tmp_path / "photos"
    source = photos / "BLACK" / "NO-LED" / "1_01.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"image")
    monkeypatch.setattr(web_app.settings, "l", str(photos))
    monkeypatch.setattr(web_app.os.path, "realpath", lambda path: str(source.parent.parent.parent) if path == str(photos) else os.path.realpath(path))
    assert web_app._path_from_file_token(web_app._file_token(str(source))) == str(source)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\\.venv-build\\Scripts\\python.exe -m pytest tests/test_web_app_files.py::test_file_token_accepts_the_resolved_photos_root -v`

Expected: FAIL because the validator compares unresolved absolute paths.

- [ ] **Step 3: Write minimal implementation**

```python
abs_path = os.path.realpath(os.path.abspath(path))
roots = [os.path.realpath(os.path.abspath(root)) for root in configured_roots]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\\.venv-build\\Scripts\\python.exe -m pytest tests/test_web_app_files.py::test_file_token_accepts_the_resolved_photos_root -v`

Expected: PASS.

### Task 2: Compact settings and suggestion controls

**Files:**
- Modify: `picorgftp_sql/web/static/app.js:renderSettingsSlots`, `createSlotNode`, `setSlotFile`, `renderSimilarCandidatePreview`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Consumes: `similar_file_detection.enabled`, `similar_file_detection.slot_prefixes`, and `state.similarCandidates`.
- Produces: per-row settings checkbox, `POD` badge, compact acceptance/rejection buttons, direct candidate thumbnail preview, and a reallocation lookup after manual assignment.

- [ ] **Step 1: Write failing browser contracts**

```python
def test_similar_settings_live_in_slot_rows_and_serialize_selected_prefixes(self): ...
def test_manual_slot_assignment_requests_candidate_reallocation(self): ...
def test_candidate_preview_uses_its_signed_thumbnail_directly(self): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\\.venv-build\\Scripts\\python.exe -m pytest tests/test_web_ui_integrity.py -k "similar" -v`

Expected: FAIL because the old detached checkbox list and full-width button remain.

- [ ] **Step 3: Implement minimal UI changes**

```javascript
// Each .slot-settings-row receives checkbox name=similar_file_slot_prefixes.
// Manual assignment calls scheduleSimilarFileLookup().
// Candidate preview uses candidate.thumb_url || candidate.url.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\\.venv-build\\Scripts\\python.exe -m pytest tests/test_web_ui_integrity.py -k "similar" -v`

Expected: PASS.

### Task 3: Focused verification and commit

**Files:**
- Modify: only files changed by Tasks 1–2.

- [ ] **Step 1: Run focused regression suite**

Run: `.\\.venv-build\\Scripts\\python.exe -m pytest tests/test_similar_product_files.py tests/test_web_app_files.py tests/test_web_ui_integrity.py -v`

Expected: PASS.

- [ ] **Step 2: Verify artifacts**

Run: `node --check picorgftp_sql/web/static/app.js`, `.\\.venv-build\\Scripts\\python.exe -m compileall -q picorgftp_sql`, and `git diff --check`.

Expected: all commands exit 0.

- [ ] **Step 3: Commit**

```powershell
git add docs/superpowers/specs/2026-08-10-similar-product-ui-refinement-design.md docs/superpowers/plans/2026-08-10-similar-product-ui-refinement.md picorgftp_sql/web/app.py picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_app_files.py tests/test_web_ui_integrity.py
git commit -m "fix: refine similar file controls and preview"
```
