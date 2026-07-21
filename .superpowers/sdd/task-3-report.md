# Task 3 Report: Entra Client Secret expiry Graph reader

## Changed files

- `picorgftp_sql/entra_secret_expiry.py`
  - Added isolated `fetch_entra_secret_expiry(settings, *, now=None, opener=...)`.
  - Uses MSAL client credentials with the Graph `/.default` scope.
  - Requests only `appId`, `displayName`, and `passwordCredentials`, with a
    direct `applications(appId=...)` request and a filtered fallback for
    Graph 400/404.
  - Produces a fixed safe result shape; classifies malformed settings,
    authentication, permission, application, credential, transport, and
    invalid-payload outcomes with stable Polish messages.
  - Parses `endDateTime` to canonical UTC milliseconds, calculates injected
    remaining time, selects a unique active hint match (or only active
    fallback), and never uses access-token expiry.
  - Does not propagate exception text or HTTP bodies, and redacts configured
    client-secret and acquired access-token values even if Graph metadata
    maliciously echoes them.
- `tests/test_entra_secret_expiry.py`
  - Added mocked MSAL/fake-opener coverage for unique hint selection, sole
    active fallback, ambiguity, Graph permission denial, Graph fallback,
    absent app, malformed Graph payloads, canonical time calculations,
    client-ID mismatch, and secret/token/error-text non-leakage.

## TDD evidence

### RED

Initial task-required command:

```powershell
python -m pytest -q tests/test_entra_secret_expiry.py
```

Output: `1 error in 0.27s`, the expected collection failure:
`ModuleNotFoundError: No module named 'picorgftp_sql.entra_secret_expiry'`.

Review-driven fallback classification regression:

```powershell
python -m pytest -q tests/test_entra_secret_expiry.py -k filtered_fallback_is_empty
```

Output: `1 failed, 8 deselected in 0.24s`; the uncorrected code returned
`invalid_response` instead of `application_not_found`.

No-leak regression:

```powershell
python -m pytest -q tests/test_entra_secret_expiry.py -k echoed_by_graph_metadata
```

Output: `1 failed, 9 deselected in 0.29s`; the uncorrected reader returned a
Graph metadata value equal to the access-token sentinel.

Primary-response identity validation regression:

```powershell
python -m pytest -q tests/test_entra_secret_expiry.py -k primary_application_id
```

Output: `1 failed, 10 deselected in 0.25s`; the uncorrected reader accepted a
primary response whose `appId` differed from the configured Client ID.

### GREEN

Initial focused GREEN:

```powershell
python -m pytest -q tests/test_entra_secret_expiry.py
```

Output: `8 passed in 0.25s`.

Final task-required suite:

```powershell
python -m pytest -q tests/test_entra_secret_expiry.py tests/test_secret_persistence.py tests/test_email_delivery.py
```

Output: `43 passed, 4 warnings in 3.09s`. The four warnings are existing
FastAPI `on_event` deprecation warnings from `picorgftp_sql/web/app.py`.

Whitespace validation:

```powershell
git diff --check
```

Output: exit code 0.

## Implementation decisions

- Every return uses the exact ten-field safe contract. No setting, access
  token, request header, exception string, or response body is returned.
- A 401/403 maps to `permission_required` and names both
  `Application.Read.All` and admin consent. A direct Graph 400/404 attempts
  the filtered fallback before final classification.
- Credentials are active only when their parsed expiry is later than the
  injected UTC time. Multiple hint matches or multiple unmatched active
  credentials are intentionally ambiguous; expiry order is never used as a
  tiebreaker.
- Graph names and key IDs are sanitized and additionally scrubbed for the
  actual client-secret and acquired access-token strings.

## Commit

`137b71bd0b45ee236ae84368ef5d43ab82ba8300` — `feat: read Entra client secret expiry`

## Concerns

No functional concerns in Task 3 scope. The required suite reports four
pre-existing FastAPI deprecation warnings outside this task.

## Review fix: overlength metadata redaction

### Root cause

`_safe_graph_text` first called `sanitize_free_text(..., limit=512)` and only
then replaced the complete known Client Secret and access-token values. When
untrusted Graph metadata contained a known sensitive value longer than the
limit, the truncation preserved a prefix but removed the full value needed by
the later replacement.

### TDD evidence

RED:

```powershell
python -m pytest -q tests/test_entra_secret_expiry.py -k partial_overlength
```

Output: `1 failed, 11 deselected in 0.30s`. The failure correctly identified
`application_name` as retaining a 64-character prefix of the configured Client
Secret.

GREEN:

```powershell
python -m pytest -q tests/test_entra_secret_expiry.py -k partial_overlength
python -m pytest -q tests/test_entra_secret_expiry.py tests/test_secret_persistence.py tests/test_email_delivery.py
git diff --check
```

Output: `1 passed, 11 deselected in 0.15s`; then `44 passed, 4 warnings in
4.16s`; `git diff --check` exited 0. The warnings are the same pre-existing
FastAPI `on_event` deprecations.

### Resolution

Known Client Secret and access-token values are now replaced in raw untrusted
Graph metadata before the existing generic sanitization and 512-byte bound.
The regression uses metadata containing overlength Client Secret and access
token values and verifies that neither full values nor partial prefixes appear
in any returned public field.

Review-fix commit: `5309f39ee82ab1d0f36ddc8979630caeb2d6bb9b` —
`fix: redact overlength Graph metadata`.
