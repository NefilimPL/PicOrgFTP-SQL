# Task 3: Read and classify Entra Client Secret expiry through Graph

## Files

- Create `picorgftp_sql/entra_secret_expiry.py`.
- Create `tests/test_entra_secret_expiry.py`.
- Do not change `requirements-web.txt`: it already contains `msal>=1.37,<2`.

## Binding requirements

- Export `fetch_entra_secret_expiry(settings, *, now=None, opener=urllib.request.urlopen) -> dict[str, object]`.
- It consumes normalized Entra settings: Tenant ID, Client ID, Client Secret. It returns only safe result fields: `status`, `code`, `expires_at`, `remaining_seconds`, `remaining_days`, `application_name`, `credential_name`, `credential_key_id`, `source`, and `error_message`.
- It must acquire an application token through MSAL client credentials with the Graph `/.default` scope, then request only `appId,displayName,passwordCredentials` from Graph.
- Prefer `GET /v1.0/applications(appId='{client_id}')`; if Graph returns 400/404, use a filtered `/v1.0/applications` fallback.
- Parse `endDateTime` into canonical UTC milliseconds and calculate remaining seconds/days from injected `now`.
- Select exactly one active credential matching the Graph `hint` and the first three characters of Client Secret. If no hint match exists, select only a single active credential. If several candidates are possible, return `status=unavailable`, `code=credential_ambiguous`; never choose by latest expiry.
- Classify Graph 401/403 as `permission_required` with an instruction that names `Application.Read.All` and admin consent. Classify missing app, invalid payload, unavailable transport and malformed settings with stable codes/messages.
- Never return or include Client Secret, Graph access token, authorization headers, raw exception text or HTTP response body. Sanitize any caught error.
- Do not decode access-token expiry as the secret expiry.

## TDD requirements

1. Add failing tests using mocked MSAL and fake `opener` for unique hint match, single active fallback, ambiguity, Graph 403, app-not-found fallback, invalid Graph data, canonical time and no leaks.
2. Run `python -m pytest -q tests/test_entra_secret_expiry.py` and record RED.
3. Implement the smallest isolated module.
4. Run `python -m pytest -q tests/test_entra_secret_expiry.py tests/test_secret_persistence.py tests/test_email_delivery.py`.
5. Run `git diff --check`, self-review, commit only Task 3 files.

## Report

Write the full report to `.superpowers/sdd/task-3-report.md`, including exact RED/GREEN commands and output, implementation decisions, commit hash, and concerns. Return only `DONE`/`DONE_WITH_CONCERNS`/`BLOCKED`, hash, test summary, and one concern line.
