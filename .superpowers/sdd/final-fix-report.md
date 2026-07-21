# Final fix wave report

## Scope

Implemented the binding final-review findings A–G on `dev` without unrelated refactoring.

## Delivered fixes

- **A — durable threshold delivery:** Due reminder persistence now happens after strict critical-event publication. The reminder event uses a stable SHA-256-derived ID and stable timestamp, so a failure before the reminder claim retries the same operational event and notification outbox intent. A claimed-reminder lookup prevents later re-publication.
- **B — safe expiry content:** Critical due/expired events include redacted application and credential names, canonical UTC expiry, numeric remaining days, and a human-readable remaining-time string. Credential key IDs, client secrets, tokens, headers, and raw Graph data remain excluded.
- **C — dense Live rows:** Live output overrides inherited grid spacing with `gap: 0`; summaries truncate with ellipsis, retain their full `title`, and are repeated in native `<details>` content.
- **D — safe default history:** Default field and overview rows turn arrays/objects into concise typed scalar descriptions. Pretty JSON remains only in collapsed `Dane techniczne` sections.
- **E — bounded token acquisition:** MSAL receives a session-backed HTTP adapter that forces the existing 20-second request timeout for `get` and `post` token calls.
- **F — worker restart guard:** A newly started notification worker clears `_WORKER_LAST_ENTRA_MONITOR_AT`, preserving the steady-state 24-hour guard while allowing startup monitoring after a same-process restart.
- **G — schema v7 checks:** Legacy user-version assertions use `sqlite_store.SCHEMA_VERSION`, retaining their v5/v6 migration scenarios without lowering schema version.

## Regression coverage

- Claim-side failure retry persists exactly one operational event and one notification intent.
- Critical expiry events assert safe application/credential names, canonical expiry, and remaining-time context.
- MSAL test seam asserts timeout adapter delivery.
- Fresh-worker test asserts monitor guard reset.
- UI/source integrity tests assert dense gap, ellipsis, summary title/full-details rendering, and technical-only object JSON.

## Verification

Focused A–G regressions:

```text
python -m pytest -q tests/test_entra_secret_monitor.py tests/test_entra_secret_expiry.py tests/test_notification_service.py tests/test_web_ui_integrity.py tests/test_observability_store.py
186 passed in 61.10s
```

Required full command:

```text
python -m pytest -q tests/test_entra_secret_expiry.py tests/test_entra_secret_monitor.py tests/test_notification_service.py tests/test_notification_outbox.py tests/test_observability_api.py tests/test_observability_store.py tests/test_sqlite_store.py tests/test_web_ui_integrity.py tests/test_history_changes.py tests/test_source_integrity.py tests/test_web_smoke_ci.py
336 passed, 9 warnings, 3 subtests passed in 475.73s
```

The warnings are FastAPI/Starlette deprecation warnings from existing startup/shutdown event usage; no test failures occurred. `git diff --check` also completed with exit code 0.
