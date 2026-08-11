# Slot Source Overlay Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline execution selected by the user). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put source-aware slot actions on the preview and provide a selectable SQL text/copy view.

**Architecture:** Source badges become selectors over the existing `state.slotSources` map. Slot rendering adds an SQL text state and a reusable preview-overlay container; `openSlotFile` resolves the current source before opening. Modal decision controls receive permanent filled colors.

**Tech Stack:** Vanilla JavaScript, static HTML/CSS, Python unittest with Node.js contracts.

## Global Constraints

- LOCAL, FTP, SQL and POD select a visible source state.
- SQL is text/copy only unless its value is an HTTP(S) URL.
- Similar candidates remain unsubmitted until explicit acceptance.

---

### Task 1: Source selection, overlays, SQL card and decision button contrast

**Files:**

- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**

- Consumes: `state.slotSources`, `thumbnailUrl`, `openSlotFile`, `renderSlotBadges`.
- Produces: `isHttpUrl`, an SQL preview renderer, and `.slot-preview-actions` overlay controls.

- [ ] **Step 1: Write failing behavior tests**

```python
def test_sql_badge_selects_text_copy_preview_and_only_opens_http_urls(self) -> None:
    # Seed a SQL value; assert the badge selects `sql`, the preview exposes
    # the exact text and copy control, and opening a non-URL is blocked.

def test_slot_actions_are_preview_overlays_not_meta_controls(self) -> None:
    css = APP_CSS.read_text(encoding='utf-8')
    self.assertIn('.slot-preview-actions', css)
    self.assertIn('top: 8px', css)
    self.assertIn('bottom: 8px', css)
```

- [ ] **Step 2: Run RED**

Run: `./.venv-build/Scripts/python.exe -m pytest tests/test_web_ui_integrity.py -k "sql_badge_selects or slot_actions_are_preview_overlays" -v`

Expected: FAIL because SQL copies directly and actions live in `.slot-controls`.

- [ ] **Step 3: Implement the minimal renderer and source-aware opener**

```javascript
function isHttpUrl(value) {
  try { const url = new URL(String(value || '').trim()); return ['http:', 'https:'].includes(url.protocol); }
  catch (_error) { return false; }
}
```

Have every available source badge write `state.slotSources.set(prefix, key)` and call `updateSlotPreview`. For SQL render the literal value plus a copy button. Put FIT, Usun and Otworz into preview overlay corners; open only the selected source.

- [ ] **Step 4: Run GREEN**

Run the Step 2 command and `node --check picorgftp_sql/web/static/app.js`.

- [ ] **Step 5: Commit**

```powershell
git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py
git commit -m "feat: move slot controls onto source previews"
```

### Task 2: Focused regression verification

**Files:**

- Test: `tests/test_similar_product_files.py`
- Test: `tests/test_web_app_files.py`
- Test: `tests/test_web_ui_integrity.py`

- [ ] **Step 1: Run focused web suites**

Run: `./.venv-build/Scripts/python.exe -m pytest tests/test_similar_product_files.py tests/test_web_app_files.py tests/test_web_ui_integrity.py -q`

Expected: all selected tests pass.

- [ ] **Step 2: Check final diff**

Run: `node --check picorgftp_sql/web/static/app.js; ./.venv-build/Scripts/python.exe -m compileall -q picorgftp_sql/web; git diff --check; git status --short`

Expected: all checks exit 0 and no uncommitted tracked changes remain.
