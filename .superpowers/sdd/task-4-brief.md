# Task 4: Monitor expiry, emit critical events, and expose admin API

## Files

- Create `picorgftp_sql/entra_secret_monitor.py`.
- Modify `picorgftp_sql/notification_service.py` only for daily worker hook.
- Modify `picorgftp_sql/web/app.py` for safe admin endpoints and trigger points.
- Modify `picorgftp_sql/web_data.py` only if required to safely detect/save changed Entra configuration.
- Create `tests/test_entra_secret_monitor.py`.
- Extend `tests/test_observability_api.py` and `tests/test_notification_service.py`.

## Binding requirements

- Export `refresh_entra_secret_status(*, force=False, now=None) -> dict` and `process_due_entra_secret_reminders(*, now=None) -> int` from the monitor.
- The monitor reads normalized email settings, calls Task 3's Graph reader, persists Task 2's safe status, and never passes raw secret/token data to events or status endpoints.
- Preserve the last successful expiry result if Graph is temporarily unavailable, record the latest failed attempt, and mark the source as cached/saved appropriately.
- A Graph `permission_required` outcome emits a notification-suppressed warning only when status/code changes; it must not create repeating e-mails.
- Due thresholds are exactly `14, 7, 3, 2, 1`. When multiple past thresholds are due, choose only the nearest/most urgent unsent one. Claim it atomically before emitting an event.
- A valid due threshold emits `severity=critical`, `event_type=entra.secret_expiry_due`; an expired secret emits a separately deduplicated critical `entra.secret_expired` event.
- Critical events use ordinary `emit_event`, so existing critical recipient rules, transactional outbox, SMTP/Entra primary and fallback remain in control. There is no actor for these system events.
- Hook one monitor pass into the existing notification worker no more often than once per 24 hours. Any monitor exception must not stop delivery processing. Tests must reset the guard.
- Add `GET /api/settings/email/entra-expiry` and `POST /api/settings/email/entra-expiry/refresh`; both require admin, POST requires normal CSRF. Responses use Task 2's public projection only.
- Changing Entra tenant/client/secret settings invalidates the cached status and schedules/attempts a fresh control without logging secrets. A successful direct Entra test-mail also refreshes status; failed mail must not hide existing status.

## TDD requirements

1. Add failing monitor tests for safe persistence, cache fallback, status-change-only permission warning, exact thresholds, one-most-urgent selection, atomic duplicate prevention, expired secret, and safe critical event details.
2. Add failing worker/API tests for 24-hour guard, error isolation, admin/CSRF behavior, and redacted GET/POST response.
3. Run focused tests and capture RED.
4. Implement the monitor, then worker/API integration.
5. Run `python -m pytest -q tests/test_entra_secret_monitor.py tests/test_observability_api.py tests/test_notification_service.py tests/test_notification_outbox.py`.
6. Run `git diff --check`, self-review, commit only Task 4 files.

## Report

Write detailed report to `.superpowers/sdd/task-4-report.md`: RED/GREEN commands, threshold/dedup evidence, changed files, commit hash and concerns. Return only `DONE`/`DONE_WITH_CONCERNS`/`BLOCKED`, hash, test summary, concern line.
