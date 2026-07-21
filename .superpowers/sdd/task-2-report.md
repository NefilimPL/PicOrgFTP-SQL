# Task 2 Report: Entra expiry SQLite persistence

## Changed files

- `picorgftp_sql/sqlite_store.py`
  - Bumped `SCHEMA_VERSION` from 6 to 7.
  - Added idempotent `entra_secret_status` and `entra_secret_reminders` tables.
  - Added indexes for `last_checked_at` and reminder identity lookup.
  - Added safe status get/upsert/clear methods and atomic reminder claiming.
  - Kept both new tables out of `clear_operational_data()`.
- `tests/test_sqlite_store.py`
  - Added safe round-trip, timestamp validation, claim idempotency/identity,
    operational-clear preservation, and explicit-clear regression tests.
  - Updated the schema expectation to version 7 and both new tables.
- `tests/test_notification_outbox.py`
  - Updated the idempotent schema-version expectation to version 7.

## TDD evidence

### RED

Command:

```powershell
python -m pytest -q tests/test_sqlite_store.py -k "entra_expiry"
```

Output: `4 failed, 17 deselected in 2.97s`.

All four failures were expected `AttributeError`s for the absent
`upsert_entra_secret_status` and `claim_entra_secret_reminder` methods.

Additional RED for explicit status clearing:

```powershell
python -m pytest -q tests/test_sqlite_store.py -k "clear_entra_expiry_status"
```

Output: `1 failed, 21 deselected in 1.81s`.

The failure was the expected absent `clear_entra_secret_status` method.

### GREEN

Focused status tests:

```powershell
python -m pytest -q tests/test_sqlite_store.py -k "entra_expiry"
```

Output: `5 passed, 17 deselected in 2.41s`.

Required suite and whitespace check:

```powershell
python -m pytest -q tests/test_sqlite_store.py tests/test_notification_outbox.py
git diff --check
```

Output: `39 passed in 11.56s`; `git diff --check` exited 0 (only existing
line-ending conversion warnings were printed).

## Schema version

`SCHEMA_VERSION = 7`.

## Commit

Not created. Git staging/commit was blocked because the sandbox denied
creation of `.git/index.lock`; the escalation review was then rejected by an
external usage-limit response.

## Concerns

No functional concern found in the Task 2 scope. The only outstanding concern
is that a local commit still needs to be created once Git index-lock access is
available.

## Follow-up: public-field hardening

Reviewer finding: `_text()` coerced arbitrary objects with `str(value)`, so a
malformed status payload could persist and return dictionary/list text through
the public `tenant_id`, `client_id`, or `status` fields.

Resolution:

- Tenant/client IDs and related persisted status text now require scalar text,
  are redacted, and are bounded before storage.
- Status is restricted to `ok`, `unavailable`, or `unknown`; non-string and
  unsupported values normalize to `unknown`.
- Public status projection sanitizes stored values again, including error text,
  to protect existing malformed rows.
- Removed `idx_entra_secret_reminders_lookup`: it duplicated the exact
  composite primary-key lookup and does not serve a distinct query.

Follow-up RED:

```powershell
python -m pytest -q tests/test_sqlite_store.py -k "malformed_public_fields"
```

Output: `1 failed, 22 deselected in 1.64s` with the expected `DID NOT RAISE
ValueError` failure for a dictionary tenant ID.

Follow-up GREEN:

```powershell
python -m pytest -q tests/test_sqlite_store.py -k "malformed_public_fields"
python -m pytest -q tests/test_sqlite_store.py tests/test_notification_outbox.py
git diff --check
```

Output: `1 passed, 22 deselected in 1.56s`; then `40 passed in 11.13s`.
`git diff --check` exited 0 (only line-ending conversion warnings printed).
