# Task 1 report: compact live and history evidence UI

## Changed files

- `picorgftp_sql/web/static/app.js`
  - Replaced expanded history file cards with native `details` rows containing compact slot, operation, before/after filename and size, and Local/FTP/SQL evidence badges.
  - Added expanded per-operation Local/FTP/SQL evidence rendering, including repeated operations for one slot.
  - Kept legacy history and top-level integrations in collapsed `Dane techniczne` sections.
  - Rendered Live log events as one compact native `details` summary row with time, severity, summary, context, and disclosure control.
- `picorgftp_sql/web/static/app.css`
  - Added compact history, technical-details, evidence badge, compact Live log, severity accent, and narrow-screen grid styles.
- `tests/test_web_ui_integrity.py`
  - Added source-integrity coverage for compact history helpers and the compact Live renderer.
- `tests/test_history_changes.py`
  - Added coverage that every same-slot Local/FTP/SQL operation remains in the unchanged history payload.

## TDD evidence

Initial RED command:

```text
python -m pytest -q tests/test_web_ui_integrity.py tests/test_history_changes.py
```

Result: `2 failed, 66 passed in 0.90s`.

The expected failures established that `renderHistoryChanges` still rendered raw Local/FTP/SQL rows and `renderLogEvent` lacked `log-event-compact`.

Final GREEN command:

```text
python -m pytest -q tests/test_web_ui_integrity.py tests/test_history_changes.py
```

Result: `68 passed in 0.52s`.

Additional verification:

```text
git diff --check
```

Result: passed with no whitespace errors.

## Commit

`f8112e98e71a366ec049638c7c10143cfafffd4b` — `feat: compact live and history evidence UI`

## Concerns

Node.js is not installed in this workspace, so `node --check picorgftp_sql/web/static/app.js` could not run; the targeted Python integrity and history suites pass.
