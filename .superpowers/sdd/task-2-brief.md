# Task 2: Persist safe Entra expiry state and idempotent reminder claims

## Files

- Modify `picorgftp_sql/sqlite_store.py`.
- Extend `tests/test_sqlite_store.py` and any schema-version expectation in `tests/test_notification_outbox.py`.

## Binding requirements

- The existing SQLite database is the only persistence target. Do not create a file-based cache, a second SQLite database, or a config secret copy.
- Bump `SCHEMA_VERSION` from 6 to 7 with idempotent initialization.
- Add one status record per `tenant_id`/`client_id`, containing only safe metadata: status, expiry timestamp, credential/application display names, internal credential key id, source, last attempt/success timestamps, stable error code and safe message.
- Add reminder claims keyed by `tenant_id`, `client_id`, `credential_key_id`, `expires_at`, and `threshold_days`.
- `get_entra_secret_status(tenant_id, client_id)` must return a public projection that removes `credential_key_id` and never includes secret/token/authentication fields even if a malformed payload was submitted.
- `upsert_entra_secret_status(status)` must validate/canonicalize timestamps and return a public projection.
- `clear_entra_secret_status(tenant_id, client_id)` removes one cache record and its matching reminder claims.
- `claim_entra_secret_reminder(tenant_id, client_id, credential_key_id, expires_at, threshold_days, claimed_at)` is atomic and returns True only for the first claim. A rotated credential or changed expiry creates an independent claim sequence.
- Normal log clearing must preserve both expiry status and reminder claims. Do not add either table to `clear_operational_data()`.
- Add appropriate indexes for status check time and reminder lookup.

## TDD requirements

1. Add failing tests for safe status roundtrip, secret/token stripping, claim idempotency, rotation/expiry distinction, and preservation during operational clear.
2. Run the new tests and observe failures before implementation.
3. Add minimal schema/methods using the existing `SqliteStore.connection()` and canonical timestamp helpers.
4. Run `python -m pytest -q tests/test_sqlite_store.py tests/test_notification_outbox.py`.
5. Run `git diff --check`, self-review, commit only Task 2 files.

## Report

Write the detailed report to `.superpowers/sdd/task-2-report.md`: changed files, exact RED/GREEN commands and outputs, commit hash, schema version, and concerns. Return only `DONE`/`DONE_WITH_CONCERNS`/`BLOCKED`, hash, test summary, and one concern line.
