# Similar File Decision Modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline execution selected by the user). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require an explicit accept/reject decision for every similar-product file suggestion before a product update can be sent, while making pending slots prominent and previewable.

**Architecture:** Existing `state.similarCandidates` remains the single source of pending decisions. A modal renders the map and delegates choice to the existing acceptance/dismissal paths; the submit handler gates before creating a request. Slot rendering consumes the same pending-state helper for default previews and strong visual status.

**Tech Stack:** Vanilla JavaScript, static HTML/CSS, Python `unittest` with Node.js behavior harnesses.

## Global Constraints

- Similar candidates remain unsubmitted until explicit acceptance.
- Closing the modal does not submit and leaves updates blocked.
- `Zapisz i kontynuuj` is enabled only after every pending candidate has a decision.
- Do not change matching rules, storage, lookup APIs, or manual-upload behavior.

---

### Task 1: Add the accessible decision modal and pending visual state

**Files:**

- Modify: `picorgftp_sql/web/static/index.html: before script tags`
- Modify: `picorgftp_sql/web/static/app.css: slot-card and modal styles`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**

- Produces `#similarDecisionModal`, `#similarDecisionList`, `#similarDecisionRejectAllButton`, `#similarDecisionContinueButton`.
- Produces CSS state `.slot-card.slot-similar-pending` and `.slot-similar-decision`.

- [ ] **Step 1: Write the failing test**

```python
def test_similar_decision_modal_exposes_preview_list_and_blocking_actions(self) -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    css = APP_CSS.read_text(encoding="utf-8")
    for identifier in (
        'id="similarDecisionModal"', 'id="similarDecisionList"',
        'id="similarDecisionRejectAllButton"', 'id="similarDecisionContinueButton"',
    ):
        self.assertIn(identifier, html)
    self.assertIn(".slot-card.slot-similar-pending", css)
    self.assertIn("@keyframes slot-similar-pending-pulse", css)
```

- [ ] **Step 2: Run RED**

Run: `./.venv-build/Scripts/python.exe -m pytest tests/test_web_ui_integrity.py::WebUiIntegrityTests::test_similar_decision_modal_exposes_preview_list_and_blocking_actions -v`

Expected: FAIL because the modal and visual state do not exist.

- [ ] **Step 3: Add minimal production markup and styles**

Add a `role="dialog"`, `aria-modal="true"` modal with close, all-reject and disabled continue actions. Style pending cards with a blue border and restrained pulse, an always-visible `Wymaga decyzji · z podobnego` label, and permanent green/red action colors.

- [ ] **Step 4: Run GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py
git commit -m "feat: add similar file decision modal shell"
```

### Task 2: Render pending decisions and default candidate previews

**Files:**

- Modify: `picorgftp_sql/web/static/app.js: similar-candidate helpers and slot renderers`
- Modify: `picorgftp_sql/web/static/app.css: decision-row preview layout`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**

- Consumes `state.similarCandidates`, `acceptSimilarCandidate(prefix)`, `dismissSimilarCandidate(prefix)`, and `renderSlot(prefix)`.
- Produces `pendingSimilarCandidatePrefixes()`, `renderSimilarDecisionModal()`, `openSimilarDecisionModal()`, `closeSimilarDecisionModal()`, and `focusFirstPendingSimilarCandidate()`.

- [ ] **Step 1: Write failing behavior tests**

```python
def test_pending_similar_candidate_renders_without_selecting_pod_source(self) -> None:
    # Seed an unselected candidate and empty slot in the Node DOM harness.
    # Assert candidate.thumb_url is rendered as the visible image source.

def test_decision_modal_accept_and_reject_resolve_only_the_chosen_slots(self) -> None:
    # Seed candidates for 01 and 02.
    # Accept 01 and reject 02; assert only 01 enters state.files and
    # no unresolved candidates remain.
```

- [ ] **Step 2: Run RED**

Run: `./.venv-build/Scripts/python.exe -m pytest tests/test_web_ui_integrity.py -k "pending_similar_candidate_renders_without_selecting_pod_source or decision_modal_accept_and_reject" -v`

Expected: FAIL because candidates only preview after selecting `POD`, and no modal renderer exists.

- [ ] **Step 3: Implement the smallest rendering helpers**

```javascript
function pendingSimilarCandidatePrefixes() {
  return (state.slots || []).map((slot) => slot.prefix)
    .filter((prefix) => similarCandidateForSlot(prefix));
}

function focusFirstPendingSimilarCandidate() {
  const prefix = pendingSimilarCandidatePrefixes()[0];
  slotGrid.querySelector(`[data-slot-prefix="${prefix}"]`)
    ?.scrollIntoView({ behavior: "smooth", block: "center" });
}
```

Render each modal row with slot name, source color, candidate image/PDF preview, and decisions. Reuse the existing accept/dismiss functions, then render the changed card and modal. In `updateSlotPreview`, prefer a pending candidate whenever there is no selected file, even if `POD` was not clicked. Add or remove the card status class in both initial and incremental renders.

- [ ] **Step 4: Run GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py
git commit -m "feat: highlight pending similar file decisions"
```

### Task 3: Gate updates and continue only after all choices

**Files:**

- Modify: `picorgftp_sql/web/static/app.js: form submit listener and modal event wiring`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**

- Consumes `pendingSimilarCandidatePrefixes()` and `openSimilarDecisionModal()`.
- Produces `submitProductForm()`, which contains the existing request creation/submission body.

- [ ] **Step 1: Write failing gate tests**

```python
def test_pending_similar_candidates_block_submit_until_all_are_decided(self) -> None:
    # With a pending candidate, assert no requestJson call and the modal opens.
    # After every accept/reject decision, assert continuation creates one request.

def test_reject_all_enables_continue_without_serializing_a_similar_token(self) -> None:
    # Reject all candidates, continue, and assert no candidate token is submitted.
```

- [ ] **Step 2: Run RED**

Run: `./.venv-build/Scripts/python.exe -m pytest tests/test_web_ui_integrity.py -k "pending_similar_candidates_block_submit or reject_all_enables_continue" -v`

Expected: FAIL because submit currently proceeds directly to `ensureSlotUploadsReady()`.

- [ ] **Step 3: Extract and gate the submit path**

```javascript
productForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (pendingSimilarCandidatePrefixes().length) {
    openSimilarDecisionModal();
    return;
  }
  submitProductForm().catch(handleSubmitError);
});
```

Move the existing asynchronous submit body into `submitProductForm` without changing its data serialization. Closing the modal focuses and scrolls to the first unresolved card. `Odrzuć wszystkie` dismisses a snapshot of pending prefixes. Continue stays disabled until no prefixes remain, then closes the modal and calls `submitProductForm`.

- [ ] **Step 4: Run GREEN**

Run: `./.venv-build/Scripts/python.exe -m pytest tests/test_web_ui_integrity.py -k "similar_candidate or similar_decision or pending_similar" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add picorgftp_sql/web/static/app.js tests/test_web_ui_integrity.py
git commit -m "feat: require similar file decisions before update"
```

### Task 4: Verify the web UI and package-ready assets

**Files:**

- Modify: `tests/test_web_ui_integrity.py` only if verification reveals a missing behavioral contract.

- [ ] **Step 1: Run relevant suites**

Run: `./.venv-build/Scripts/python.exe -m pytest tests/test_similar_product_files.py tests/test_web_app_files.py tests/test_web_ui_integrity.py -q`

Expected: every selected test passes.

- [ ] **Step 2: Run static checks**

Run: `node --check picorgftp_sql/web/static/app.js; ./.venv-build/Scripts/python.exe -m compileall picorgftp_sql; git diff --check`

Expected: all commands exit 0.

- [ ] **Step 3: Inspect and commit any final test-only adjustment**

```powershell
git status --short
git diff --check
git add tests/test_web_ui_integrity.py
git commit -m "test: cover similar file decision flow"
```

Create this commit only if Task 4 changes a tracked test file.

