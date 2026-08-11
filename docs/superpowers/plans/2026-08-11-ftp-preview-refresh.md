# FTP Preview Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent active FTP previews from opening stale local-cache tokens and tighten slot action overlays.

**Architecture:** Keep the passive FTP browser cache unchanged. Add a `forceRefresh` option to the existing `loadFtpPreview` request path; explicit FTP selection and opening use it, replacing stale token URLs with the response from `/api/ftp-preview`. CSS alone positions overlay buttons at a 3px inset.

**Tech Stack:** Vanilla JavaScript, FastAPI FTP-preview API, CSS, pytest UI integrity tests.

## Global Constraints

- SQL remains a value/presence indicator and no remote SQL URL availability check is added.
- Only explicit FTP selection and opening bypass the browser FTP preview cache.
- A failed FTP refresh must not open the previous cached `/api/file` URL.
- FIT, Usuń, and Otwórz use a 3px preview-frame inset.

---

### Task 1: Force refresh active FTP sources

**Files:**
- Modify: `picorgftp_sql/web/static/app.js:2569-2588,2645-2704,3151-3245`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Consumes: `loadFtpPreview(photo, prefix, requestId, options)` and `/api/ftp-preview` response `{ token, url, thumb_url, file_version }`.
- Produces: `options.forceRefresh` bypassing `state.ftpPreviewCache`; `openSlotFile(prefix)` awaits refresh before calling `window.open` for an FTP source.

- [ ] **Step 1: Write the failing test**

```python
def test_active_ftp_source_refreshes_before_opening_stale_cache_token():
    source = APP_JS.read_text(encoding="utf-8")
    loader = source[source.index("async function loadFtpPreview"):source.index("function nextBackgroundFtpPreviewCandidate")]
    opener = source[source.index("async function openSlotFile"):source.index("function markSlotDeletion")]
    assert "options.forceRefresh" in loader
    assert "await loadFtpPreview(photo, prefix, state.photoLoadRequestId, { forceRefresh: true })" in opener
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv-build/Scripts/python.exe -m pytest tests/test_web_ui_integrity.py -q`

Expected: FAIL because `forceRefresh` does not exist and the opener only loads FTP when `ftp_token` is missing.

- [ ] **Step 3: Write minimal implementation**

```javascript
const forceRefresh = Boolean(options.forceRefresh);
const cached = forceRefresh ? null : cacheKey ? state.ftpPreviewCache.get(cacheKey) : null;
```

Call `loadFtpPreview(photo, prefix, state.photoLoadRequestId, { forceRefresh: true })` for an FTP badge and before opening an FTP source. Refresh errors propagate, so `window.open` is not reached.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv-build/Scripts/python.exe -m pytest tests/test_web_ui_integrity.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add picorgftp_sql/web/static/app.js tests/test_web_ui_integrity.py
git commit -m "fix: refresh FTP previews before opening"
```

### Task 2: Tighten preview action overlays

**Files:**
- Modify: `picorgftp_sql/web/static/app.css:2597-2610`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Consumes: `.slot-preview-actions` and its FIT, clear, and open button class names.
- Produces: all three overlay controls positioned with `3px` from their assigned preview corners.

- [ ] **Step 1: Write the failing test**

```python
def test_slot_preview_action_overlays_use_a_three_pixel_corner_inset():
    css = APP_CSS.read_text(encoding="utf-8")
    assert ".slot-preview-actions .slot-fit-button {\n  top: 3px;\n  left: 3px;" in css
    assert ".slot-preview-actions .slot-clear-button {\n  top: 3px;\n  right: 3px;" in css
    assert ".slot-preview-actions .slot-open-button {\n  bottom: 3px;\n  left: 3px;" in css
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv-build/Scripts/python.exe -m pytest tests/test_web_ui_integrity.py -q`

Expected: FAIL because the CSS currently uses `8px`.

- [ ] **Step 3: Write minimal implementation**

```css
.slot-preview-actions .slot-fit-button { top: 3px; left: 3px; }
.slot-preview-actions .slot-clear-button { top: 3px; right: 3px; }
.slot-preview-actions .slot-open-button { bottom: 3px; left: 3px; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv-build/Scripts/python.exe -m pytest tests/test_web_ui_integrity.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py
git commit -m "style: tighten slot preview actions"
```
