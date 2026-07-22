# Task 6 report: backend resource-monitor documentation

## Scope

- Added the `Zasoby backendu` operating guide to `docs/web-panel.md`.
- Distinguished whole-host CPU, RAM, and disk-activity diagnostics from the
  backend current-PID CPU, RAM, and I/O metrics that drive alerts. During a
  bounded real test, the registered helper PID is included as well; arbitrary
  child-process trees are not included.
- Documented the five-second cadence, configurable threshold ranges, strict
  threshold comparison, two-high-sample latch, two-normal-sample release, and
  suppression of repeated alerts while latched.
- Documented unavailable disk counters, the allowlisted public snapshot, and the
  exclusion of temporary paths, secrets, and exception text.
- Documented administrator authorization, safe simulation, bounded real tests,
  result states, successful cleanup, and the retained reservation/blocking
  semantics of `cleanup_failed`.
- Added a source-integrity assertion that keeps the backend-only alert and test
  semantics present in the operator guide. No runtime behavior was changed.

## TDD evidence

- RED:
  `C:\Python314\python.exe -m pytest tests/test_source_integrity.py -k resource -v --basetemp tmp_test_task6_red_20260722_01`
  failed only the new documentation assertion at its first missing phrase;
  1 failed, 2 passed, 46 deselected.
- GREEN: the same selection with basetemp
  `tmp_test_task6_green_20260722_02` passed: 3 passed, 46 deselected.
- Review RED: the contextual replacement assertion failed on the old
  `drzewa procesów backendu` wording because the required current backend PID
  scope was absent: 1 failed, 48 deselected.
- Review GREEN: after correcting all four reviewed contracts, the contextual
  selection passed: 1 passed, 48 deselected, using basetemp
  `tmp_test_task6_review_green_20260722_05`.

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

## Live Windows acceptance

The acceptance harness started the real FastAPI/uvicorn application on an
ephemeral `127.0.0.1` port with an isolated temporary runtime. It logged in as
the isolated default administrator, used the returned CSRF token and the normal
settings and resource-test HTTP endpoints, and ran one test at a time. The
baseline contained no `picorg_resource_test_*` directory.

- CPU: configured CPU/RAM/I/O thresholds `10/90/256`; HTTP 200 in 13.898 s,
  `ok=true`, `status=detected`, `timed_out=false`. Exactly one new ordinary
  `backend.resource_high` event, `evt-ead7c1a1c167419f94d25595b0304367`, had
  trigger metric `cpu_percent`.
- RAM: configured thresholds `90/1/256`; HTTP 200 in 9.400 s,
  `ok=true`, `status=detected`, `timed_out=false`. Exactly one new ordinary
  resource event had trigger metric `memory_percent`. Host RAM was
  16,934,494,208 bytes, so the 256 MiB cap represented 1.5851% and the normal
  1% threshold was safely reachable. The matching event was
  `evt-f770e8a09b924745b01844560453fdea`.
- Disk: configured thresholds `90/90/1`; HTTP 200 in 14.375 s,
  `ok=true`, `status=detected`, `timed_out=false`. Exactly one new ordinary
  resource event, `evt-22b69b89b82841afb942cf0478839cff`, had trigger metric
  `disk_io_bytes_per_second`.
- After every response, `test_worker_registered=false` and there were no new
  resource-test directories. Final evidence also showed no new directory, the
  backend thread stopped, and the isolated runtime was removed.

The first startup-only attempt reached the backend but login returned HTTP 403
because the harness omitted the browser's required `X-Requested-With` marker.
No resource test ran in that attempt; its backend stopped and both its isolated
runtime and temp-directory check were clean. The corrected run used that normal
request marker and completed the evidence above.

## Review follow-up verification

- Focused resource documentation/source selection:
  `C:\Python314\python.exe -m pytest tests/test_source_integrity.py -k resource -v --basetemp tmp_test_task6_review_final_focused_20260722_08`:
  3 passed, 46 deselected.
- Fresh full suite:
  `C:\Python314\python.exe -m pytest -q --basetemp tmp_test_task6_review_final_full_20260722_09`:
  1,008 passed, 52 subtests passed, 13 existing FastAPI/Starlette deprecation
  warnings, in 126.75 seconds.
- `C:\Python314\python.exe -m compileall -q picorgftp_sql`: exit 0.
- `C:\Program Files\nodejs\node.exe --check picorgftp_sql/web/static/app.js`:
  exit 0 with no syntax diagnostics.
- `git diff --check`: clean before the follow-up commit.

## Self-review

- Confirmed the host disk line is activity/busy time rather than storage
  occupancy, and that all three alert thresholds apply solely to backend
  metrics.
- Confirmed backend metrics include only the current server PID plus a registered
  bounded helper PID, rather than an arbitrary descendant process tree.
- Confirmed the guide matches the detector: values must be greater than the
  threshold, two consecutive high samples latch, two normal samples release,
  and unavailable values reset pending counts without creating an alert.
- Confirmed a real test is not described as directly creating an incident: a
  positive result requires the ordinary sampler to cross and confirm the
  configured backend threshold.
- Confirmed the documented caps match the implementation: about 20 seconds,
  25% CPU, 256 MiB RAM, and 128 MiB disk data, with only one worker at a time.
  Cleanup success releases registration; `cleanup_failed` retains it and blocks
  another real test until a later stop or cleanup retry succeeds.
- Confirmed only the operator guide, its source-integrity assertion, and this
  report are in Task 6 scope; no plan, ledger, release code, or runtime file was
  edited.

## Commit

The initial report is in commit `docs: explain backend resource monitoring`.
Review corrections and live evidence are included in follow-up commit
`docs: correct resource monitor operations guide`.

## Residual risk

- Live acceptance is host-dependent, so deterministic unit and integration tests
  remain the portable regression coverage for failure and `cleanup_failed`
  branches that cannot be induced safely in the operational acceptance run.
