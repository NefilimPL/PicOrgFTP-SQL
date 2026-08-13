# Slot Open Button Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep an unobscured `Otwórz` button visible for every slot and update its disabled state when the active LOCAL, FTP, or SQL source becomes ready.

**Architecture:** Add a source-readiness helper that returns whether opening is possible and why it is unavailable. Render the button once in the card metadata area, then use the helper from first rendering and incremental updates. FTP remains disabled while only its remote filename is known and becomes enabled when the preview cache supplies a token or URL.

**Tech Stack:** Vanilla browser JavaScript, CSS, Python `unittest`, and Node.js for browser-independent helper behavior.

## Global Constraints

- The full Polish label must remain `Otwórz`; no truncation or ellipsis is permitted.
- The button must sit outside `.slot-preview` and must not obscure the image.
- LOCAL requires a local token; FTP requires a cached token or URL; SQL requires a valid HTTP/HTTPS URL.
- A source that is loading or permanently unavailable leaves the button visible and disabled with an explanatory title.
- Switching sources and FTP preview completion must update the existing button without a new EAN search.

---

### Task 1: Source-readiness contract

**Files:**

- Modify: `picorgftp_sql/web/static/app.js:2578-2584`
- Modify: `tests/test_web_ui_integrity.py`

**Interfaces:**

- Consumes: `selectedSlotSource(prefix, photo)`, `filePreviewUrl(prefix, file)`, `isHttpUrl(value)`.
- Produces: `slotOpenState(prefix, photo, file) -> { enabled: boolean, title: string }`.
- Preserves: `selectedSlotSourceCanOpen(prefix, photo, file) -> boolean` as a wrapper over `slotOpenState(...).enabled`.

- [ ] **Step 1: Write the failing test**

Add a Node-backed test that evaluates `slotOpenState` with hand-written fixtures. It must assert that FTP with only `ftp_filename` yields `{ enabled: false, title: "Pobieranie pliku FTP..." }`; FTP with `ftp_url: "/api/file?token=abc"` yields `{ enabled: true, title: "Otwórz aktywne źródło FTP" }`; an HTTPS SQL value is enabled; and plain SQL text is disabled.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_ui_integrity.py -k slot_open_state_tracks_ready -v`

Expected: FAIL because `slotOpenState` is not defined in `app.js`.

- [ ] **Step 3: Write minimal implementation**

Add `slotOpenState`, returning an explicit loading or unavailable title for every source. Make `selectedSlotSourceCanOpen` return `slotOpenState(prefix, photo, file).enabled`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_ui_integrity.py -k slot_open_state_tracks_ready -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add tests/test_web_ui_integrity.py picorgftp_sql/web/static/app.js; git commit -m "fix: model slot open readiness"`

### Task 2: Persistent control and unobscured layout

**Files:**

- Modify: `picorgftp_sql/web/static/app.js:3703-3753,3884-4003`
- Modify: `picorgftp_sql/web/static/app.css:2596-2636`
- Modify: `tests/test_web_ui_integrity.py`

**Interfaces:**

- Consumes: `slotOpenState(prefix, photo, file)` from Task 1.
- Produces: `updateSlotOpenButton(button, prefix, photo, file)`, which sets `disabled`, `title`, and `aria-disabled` without removing the button.
- Preserves: `openSlotFile(prefix)` as the click handler.

- [ ] **Step 1: Write the failing test**

Add a test that executes `updateSlotOpenButton` against one minimal button object, changing its fixture from FTP-loading to FTP-ready. Assert the same object first has `disabled: true` and then `disabled: false`. Assert the renderer appends controls to metadata, never appends them to the preview, and CSS has no absolute `.slot-preview-actions .slot-open-button` rule.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_ui_integrity.py -k slot_open_button_updates_existing -v`

Expected: FAIL because the helper and persistent metadata control do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create the button for every card and append controls to the metadata/control region. Replace conditional append/hide logic with `updateSlotOpenButton`; it must leave the element visible and change only state, title, and ARIA attributes. Change CSS to normal layout flow with `white-space: nowrap` and enough width for the full label.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_ui_integrity.py -k "slot_open_state_tracks_ready or slot_open_button_updates_existing" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add tests/test_web_ui_integrity.py picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css; git commit -m "fix: keep slot open button visible"`

### Task 3: Regression verification

**Files:**

- Verify: `tests/test_web_ui_integrity.py`
- Verify: `picorgftp_sql/web/static/app.js`
- Verify: `picorgftp_sql/web/static/app.css`

**Interfaces:**

- Consumes: completed Tasks 1 and 2.
- Produces: verified initial loading, source switching, and FTP readiness behavior.

- [ ] **Step 1: Run focused UI tests**

Run: `python -m pytest tests/test_web_ui_integrity.py -v`

Expected: PASS with no failures.

- [ ] **Step 2: Run syntax validation**

Run: `node --check picorgftp_sql/web/static/app.js`

Expected: exit code 0.

- [ ] **Step 3: Inspect the final patch**

Run: `git diff --check HEAD^..HEAD; git status --short`

Expected: no whitespace errors and no unintended files.
