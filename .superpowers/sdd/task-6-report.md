# Task 6 report: backend resource-monitor documentation

## Scope

- Added the `Zasoby backendu` operating guide to `docs/web-panel.md`.
- Distinguished whole-host CPU, RAM, and disk diagnostics from the backend
  process-tree CPU, RAM, and I/O metrics that drive alerts.
- Documented the five-second cadence, configurable threshold ranges, strict
  threshold comparison, two-high-sample latch, two-normal-sample release, and
  suppression of repeated alerts while latched.
- Documented unavailable disk counters, the allowlisted public snapshot, and the
  exclusion of temporary paths, secrets, and exception text.
- Documented administrator authorization, safe simulation, bounded real tests,
  result states, and automatic worker/directory cleanup.
- Added a source-integrity assertion that keeps the backend-only alert and test
  semantics present in the operator guide. No runtime behavior was changed.

## TDD evidence

- RED:
  `C:\Python314\python.exe -m pytest tests/test_source_integrity.py -k resource -v --basetemp tmp_test_task6_red_20260722_01`
  failed only the new documentation assertion at its first missing phrase;
  1 failed, 2 passed, 46 deselected.
- GREEN: the same selection with basetemp
  `tmp_test_task6_green_20260722_02` passed: 3 passed, 46 deselected.

Both runs set
`PYTHONHOME=C:\Users\k.bober\AppData\Local\Programs\Python\Python314` and used
the required `C:\Python314\python.exe` interpreter.

## Final verification

- Full suite:
  `C:\Python314\python.exe -m pytest -q --basetemp tmp_test_task6_full_20260722_03`
  passed: 1,008 passed, 52 subtests passed, 13 existing FastAPI/Starlette
  deprecation warnings, in 120.61 seconds.
- `C:\Python314\python.exe -m compileall -q picorgftp_sql`: exit 0.
- `C:\Program Files\nodejs\node.exe --check picorgftp_sql/web/static/app.js`:
  exit 0 with no syntax diagnostics.
- `git diff --check`: clean before commit.
- The Windows backend and live CPU, RAM, and disk resource tests were not
  started, as explicitly required for this task. The full suite exercises their
  bounded lifecycle and result contracts without creating live resource load.

## Self-review

- Confirmed the host line is described as diagnostic only and that all three
  alert thresholds apply solely to backend metrics.
- Confirmed the guide matches the detector: values must be greater than the
  threshold, two consecutive high samples latch, two normal samples release,
  and unavailable values reset pending counts without creating an alert.
- Confirmed a real test is not described as directly creating an incident: a
  positive result requires the ordinary sampler to cross and confirm the
  configured backend threshold.
- Confirmed the documented caps match the implementation: about 20 seconds,
  25% CPU, 256 MiB RAM, and 128 MiB disk data, with only one worker at a time and
  automatic cleanup on terminal paths.
- Confirmed only the operator guide, its source-integrity assertion, and this
  report are in Task 6 scope; no plan, ledger, release code, or runtime file was
  edited.

## Commit

This report is included in commit `docs: explain backend resource monitoring`.

## Residual risk

- Live Windows acceptance evidence for actual threshold crossings and temporary
  directory cleanup is intentionally absent because live resource load was
  prohibited. Those paths remain covered by deterministic unit and integration
  tests in the passing full suite.
