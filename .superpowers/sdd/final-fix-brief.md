# Final fix wave: compact observability and Entra expiry

Apply all items below in one coherent change. Use TDD: add/adjust regression tests first, capture failures where practical, then run the listed focused suites and `git diff --check`. Commit the complete wave and write `.superpowers/sdd/final-fix-report.md`.

## A. Durable threshold delivery

`picorgftp_sql/entra_secret_monitor.py` currently claims a reminder before a later, separate `emit_event()` transaction. If event/incident/outbox persistence fails after claim, the threshold is lost forever. Make the reminder claim and critical event/incident/outbox persistence atomic or durable/retryable. Reuse the existing SQLite transaction/outbox primitives rather than creating a second delivery channel. Add crash/failure regression proving retry eventually publishes one due event/delivery and never duplicates it.

## B. Complete safe expiry event content

Critical due/expired events must include safe `application_name`, `credential_name`, canonical expiry, and human-readable remaining time/days in their details/body context. Continue excluding credential key ID, secret/token/header/raw Graph data. Add assertions.

## C. Dense Live row requirements

In `app.js`/`app.css`, Live rows must have zero inherited inter-row grid gap, long summaries must ellipsize in the default row, expose their full string in `title`, and include the full summary inside the expanded details. Preserve keyboard-native `details`. Add source/UI integrity tests for gap, truncation class/style, title and expanded full summary.

## D. No generic raw object JSON in default history

Default history field/overview rows must use typed safe scalar summaries. Generic object serialization is allowed only in collapsed `Dane techniczne` sections. Ensure arbitrary object values cannot appear as multi-line `JSON.stringify` in a default section. Add source/renderer regression.

## E. Bound Graph token acquisition

`fetch_entra_secret_expiry` must bound MSAL token acquisition as well as Graph metadata requests. Supply a timeout-configured HTTP client/session supported by MSAL or equivalent bounded mechanism; a hung token request must not block the daily worker without a timeout. Add a test/seam proving configured timeout reaches token client or bounded acquisition path. Preserve token secrecy.

## F. Worker restart monitor guard

Reset `_WORKER_LAST_ENTRA_MONITOR_AT` when a truly fresh worker starts, so a stop/start in the same process runs its startup monitor instead of waiting up to 24h. Preserve no-overlap and 24-hour steady-state behavior. Add focused test.

## G. Schema v7 expectations

Update the three full-suite test assertions in `tests/test_observability_store.py` that still expect `PRAGMA user_version == 6` to use schema v7/current `SCHEMA_VERSION`, preserving their v5/v6 migration semantics. Do not lower schema version.

## Required verification

Run at least:

```powershell
python -m pytest -q tests/test_entra_secret_expiry.py tests/test_entra_secret_monitor.py tests/test_notification_service.py tests/test_notification_outbox.py tests/test_observability_api.py tests/test_observability_store.py tests/test_sqlite_store.py tests/test_web_ui_integrity.py tests/test_history_changes.py tests/test_source_integrity.py tests/test_web_smoke_ci.py
git diff --check
```

Then report commit hash, test count/output and concerns. Do not modify unrelated behavior.
