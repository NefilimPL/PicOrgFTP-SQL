# Task 4 report: compact resource monitor UI

## Status and commit

- Status: complete on branch `dev`.
- Commit subject: `feat: show backend resource status`.
- Task files: `picorgftp_sql/web/static/index.html`,
  `picorgftp_sql/web/static/app.js`, `picorgftp_sql/web/static/app.css`,
  `tests/test_web_ui_integrity.py`, and this report.

## Scope implemented

- Added a compact two-line system/backend CPU, RAM, and disk indicator directly
  beneath the existing backend-health control without expanding the top bar.
- Added an accessible resource detail disclosure controlled by hover, focus,
  click, outside click, and Escape. Detailed rows are created as DOM nodes and
  installed with `replaceChildren`; all server values use `textContent`.
- Rendered raw host/backend values, configured thresholds, sample and latch
  timestamps/state, job/client counts, and explicit unavailable reasons.
- Connected every successful `/api/health` poll to `payload.resources` while
  retaining an explicit unavailable state before the first sample.
- Added the Monitor settings tab with indicator visibility and CPU/RAM/I/O
  thresholds saved through the existing `/api/settings` action.
- Added safe simulation plus bounded CPU/RAM/disk real-test controls. Real-test
  controls stay disabled while pending, server messages render through
  `textContent`, and the normal health poll refreshes after each response.
- The browser calls only Task 3 endpoints and never creates an incident itself.
  No Task 2/resource-monitor backend internals were changed.

## TDD evidence

### RED

```powershell
$env:PYTHONHOME = 'C:\Users\k.bober\AppData\Local\Programs\Python\Python314'
& 'C:\Python314\python.exe' -m pytest tests/test_web_ui_integrity.py -k resource -v --basetemp '.tmp_test/task4-red-20260721-01'
```

Result: 2 failed for the expected missing `resourceStatus` markup and
`renderResourceStatus` function.

### GREEN and verification

- Focused resource UI tests: 2 passed, 58 deselected.
- Required UI/source integrity suites: 106 passed.
- Resource config/API/monitor regression selection: 65 passed, 39 deselected.
- Fresh full suite: 990 passed, 52 subtests passed, with 13 existing
  FastAPI/Starlette deprecation warnings.
- `C:\Program Files\nodejs\node.exe --check picorgftp_sql/web/static/app.js`:
  exit 0 with no syntax diagnostics.
- `git diff --check`: clean.

All pytest verification used the required Python 3.14 `PYTHONHOME`, interpreter,
and a unique Task 4 basetemp. A first nested backend basetemp attempt could not
recreate its removed parent directory; the same selection passed with a unique
top-level basetemp.

## Self-review

- Confirmed `show_status` changes only `resourceStatus.hidden` and refreshes
  immediately after settings load/save; backend health remains visible.
- Confirmed missing, null, non-finite, and `{available: false}` metrics never
  render as `NaN`, and provider reasons are preserved in the detail popover.
- Confirmed detector latches alone set the compact badge to critical.
- Confirmed the detail disclosure mirrors the existing health accessibility
  pattern and keeps `hidden` and `aria-expanded` synchronized.
- Confirmed the simulation flow disables all real-test controls, uses only the
  authenticated request helper, displays the server response safely, and polls
  health afterward.
- Confirmed no plan, ledger, backend, or resource-monitor internal files changed.

## Residual risks

- Visual behavior was reviewed through markup/CSS/source integrity rather than
  an automated browser screenshot suite; JavaScript parsing was verified by Node.
- The Task 5 FTP-cache invariant is conditional until Task 5 introduces
  `setFtpPreviewCache`; once the helper exists, the UI integrity test rejects any
  remaining direct `ftpPreviewCache.set(...)` call.

## Follow-up review fixes (2026-07-22)

### Scope

- Bumped both static bundle URLs to the shared cache key
  `20260722-resource-monitor-rerender1`, following the existing
  date-feature-revision deployment convention.
- Replaced test-run DOM-node capture with stable module-level
  `resourceMonitorTestState` and `updateResourceMonitorTestUi()`.
- The updater resolves the currently rendered result and all test buttons after
  every Monitor form render and at request start, success, error, and completion.
  A settings rerender during an in-flight request therefore preserves the
  pending message, keeps replacement buttons disabled, renders the server result
  into the visible node, and re-enables the current buttons in `finally`.
- Added deterministic source-integrity coverage for the shared asset key and
  rerender-safe pending/result flow. Removed stale cache-key assertions from
  unrelated Pimcore UI tests.

### TDD and verification evidence

- RED: 4 selected tests failed for the stale `health2` cache key, missing stable
  state/updater, and the old detached-node implementation.
- Focused GREEN: 4 passed, 104 deselected.
- UI/source integrity: 108 passed.
- Node syntax check: exit 0 with no diagnostics.
- Full suite: 992 passed, 52 subtests passed, with the same 13 existing
  FastAPI/Starlette deprecation warnings.
- The first full-suite attempt reached 64% without failures before the
  120-second command timeout; a fresh longer run completed successfully.
- `git diff --check`: clean.

### Follow-up self-review

- Confirmed neither `runResourceMonitorTest()` nor its asynchronous continuations
  retain result or button nodes across an `await`.
- Confirmed every newly rendered safe/CPU/RAM/disk button carries the common
  update selector and derives `disabled` from the stable pending state.
- Confirmed the visible result always derives from the stable message state and
  the current DOM is refreshed after both success and failure, then again after
  clearing pending state.
- Confirmed CSS and JavaScript cache keys are identical and no old Task 4 bundle
  key remains in HTML or tests.
- Confirmed no backend, plan, ledger, or Task 2 internals changed.

Follow-up commit subject: `fix: preserve resource test status across rerenders`.
