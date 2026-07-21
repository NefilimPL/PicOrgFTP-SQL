# Task 4 report — Entra secret expiry monitor

## Scope delivered

- Added `picorgftp_sql/entra_secret_monitor.py` with safe status refresh and due-reminder processing.
- Added persisted-status cache fallback, permission-required change-only warning, exact reminder thresholds, atomic claims, and separate expired-secret events.
- Added the daily notification-worker hook with exception isolation.
- Added admin-only status and refresh API endpoints, with the normal mutating-request CSRF middleware protecting POST.
- Invalidated and refreshed status after Entra tenant/client/secret changes; a successful test mail delivered by Entra also refreshes status.

## TDD evidence

RED command:

```text
python -m pytest -q tests/test_entra_secret_monitor.py tests/test_observability_api.py tests/test_notification_service.py tests/test_notification_outbox.py
```

Initial result: `3 failed, 77 passed, 5 warnings, 12 errors`.  The expected failures were missing `picorgftp_sql.entra_secret_monitor`, the missing worker hook, and the missing API integration.

GREEN command:

```text
python -m pytest -q tests/test_entra_secret_monitor.py tests/test_observability_api.py tests/test_notification_service.py tests/test_notification_outbox.py
```

Final result: `92 passed, 5 warnings in 88.12s`.

Additional focused monitor check: `12 passed in 4.09s`.

`git diff --check` completed with exit code 0.

## Threshold and dedup evidence

- Tests cover exactly 14, 7, 3, 2, and 1 day thresholds.
- At a multi-threshold state, the nearest threshold is claimed first; an existing claim prevents a second event and does not back-fill a less-urgent historical threshold.
- SQLite `claim_entra_secret_reminder` is called before `emit_event`; repeated passes emit no duplicate due event.
- Expiry uses the distinct threshold-0 claim and `entra.secret_expired` event type.

## Changed files

- `picorgftp_sql/entra_secret_monitor.py`
- `picorgftp_sql/notification_service.py`
- `picorgftp_sql/web/app.py`
- `picorgftp_sql/web_data.py`
- `tests/test_entra_secret_monitor.py`
- `tests/test_observability_api.py`
- `tests/test_notification_service.py`

## Commit

`67c3207 feat: monitor Entra secret expiry`

## Concerns

The required suite is green; it reports five existing FastAPI/TestClient deprecation warnings.

## Review-fix addendum

- Added a monitor-only SQLite accessor for `credential_key_id`; public status
  projections and API responses still omit it. Cache fallback now preserves this
  internal identifier, and reminder claims use it directly rather than a hash of
  client ID and expiry.
- The Graph reader now returns a uniquely hint-matched expired credential (or a
  sole expired fallback) with negative remaining time. Ambiguous expired
  credentials remain unavailable.
- Added coverage for key rotation with identical expiry, reader-to-monitor
  expired event flow, Entra-settings invalidation/refresh without secret logs,
  and successful versus failed Entra test mail refresh behavior.

Review RED: the new regression suite initially exposed missing internal status
access, incorrect expired-credential selection, and duplicate prevention based
on the hash rather than Graph key ID. One unrelated login-rate-limit failure was
isolated in the API test fixture state.

Review GREEN command:

```text
python -m pytest -q tests/test_entra_secret_expiry.py tests/test_entra_secret_monitor.py tests/test_sqlite_store.py tests/test_observability_api.py tests/test_notification_service.py tests/test_notification_outbox.py tests/test_email_settings.py tests/test_web_data_users.py
```

Result: `218 passed, 5 warnings in 101.76s`; `git diff --check` passed.

Review-fix commit: `aa2f6ee fix: preserve Entra expiry reminder identity`.
