# Task 1: Normalize compact history evidence and render dense expandable UI

## Files

- Modify `picorgftp_sql/web/static/app.js` in history renderers and `renderLogEvent`.
- Modify `picorgftp_sql/web/static/app.css` in history and log styles.
- Extend `tests/test_web_ui_integrity.py` and `tests/test_history_changes.py`.

## Binding requirements

- The Live tab defaults to exactly one dense row per event: time, severity, summary, compact user/EAN/job context, disclosure control.
- The default live row has small color accents only; never animate info/success.
- Full recommended action, exception, traceback and structured details remain in an accessible expanded `details` section.
- History's default view must never use generic formatting/JSON for `file.evidence.local`, `file.evidence.ftp`, `file.evidence.sql`, or top-level integrations.
- A changed slot is one collapsed row containing slot, operation, before-to-after filename, before-to-after size, and compact Local/FTP/SQL badges with statuses and elapsed time.
- When expanded, preserve source filename/size, image processing settings/timing, and each individual local/FTP/SQL operation. A same-slot save and delete must both remain visible.
- Top-level integrations are only allowed in a final collapsed `Dane techniczne` section, never repeated underneath every slot.
- Older history records without `change_set` retain a compatibility message; legacy raw data is technical/collapsed only.
- Use semantic native `details`/`summary`; keyboard behavior must remain accessible.
- On narrow screens, summary grids can use two rows but must not create page-wide horizontal scroll.

## TDD requirements

1. Add source-integrity tests proving `renderHistoryChanges` calls compact helpers and no longer calls `historyChangeRow` with raw Local/FTP/SQL evidence.
2. Add source-integrity tests proving `renderLogEvent` emits `log-event-compact`, `log-event-summary-row`, and a `details` section.
3. Run the new tests and capture the failing result before implementation.
4. Add helpers such as `historyEvidenceBadges`, `historyEvidenceDetails`, and compact history file-row construction. Do not change server payload contracts.
5. Add compact CSS and responsive fallback.
6. Run `python -m pytest -q tests/test_web_ui_integrity.py tests/test_history_changes.py`.
7. Run `git diff --check`, self-review, commit only task files.

## Report

Write the detailed report to `.superpowers/sdd/task-1-report.md`: changed files, exact test commands/results, commit hash, and concerns. Return only `DONE`/`DONE_WITH_CONCERNS`/`BLOCKED`, hash, test summary, and one concern line.
