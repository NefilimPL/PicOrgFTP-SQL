# Slot Open Overlay Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore all slot controls to their original preview-overlay positions while keeping the Open button persistently visible and stateful.

**Architecture:** Preserve `slotOpenState` and `updateSlotOpenButton`. Split the render containers so FIT and Usun use the restored preview overlay and Otworz uses that same overlay; do not append controls to metadata or change card sizing CSS.

**Tech Stack:** Vanilla JavaScript, CSS, Python unittest.

## Global Constraints

- FIT, Usun, and Otworz remain in their pre-existing preview overlay positions.
- Otworz stays in the DOM and becomes disabled or enabled in place.
- No slot card or preview dimension rule changes.

---

### Task 1: Restore overlay placement

**Files:**

- Modify: `tests/test_web_ui_integrity.py`
- Modify: `picorgftp_sql/web/static/app.js:3916-4034`
- Modify: `picorgftp_sql/web/static/app.css:2609-2621,3744-3747`

**Interfaces:**

- Consumes: `updateSlotOpenButton(button, prefix, photo, file)`.
- Produces: the original `.slot-preview-actions` overlay containing FIT, Usun, and Otworz.

- [ ] **Step 1: Write the failing test**

Replace the layout regression assertion with expectations that `controls.className` is `slot-preview-actions`, controls are appended to `preview`, the existing FIT and Usun position rules are present, and no `.slot-controls` or `.slot-meta { overflow: visible; }` rule remains.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_ui_integrity.py -k slot_open_button_stays_outside -v`

Expected: FAIL because the current code appends `.slot-controls` to metadata.

- [ ] **Step 3: Write minimal implementation**

Restore `slot-preview-actions` and append its controls to `preview`. Restore the original FIT, Usun, and Otworz overlay CSS and restore metadata overflow. Keep the unconditional Open append and `updateSlotOpenButton` call.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_web_ui_integrity.py -k slot_open_button_stays_outside -v`

Expected: PASS.

- [ ] **Step 5: Run focused regression checks**

Run: `python -m pytest tests/test_web_ui_integrity.py -v; node --check picorgftp_sql/web/static/app.js`

Expected: PASS and exit code 0.

- [ ] **Step 6: Commit**

Run: `git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py; git commit -m "fix: restore slot action overlay"`
