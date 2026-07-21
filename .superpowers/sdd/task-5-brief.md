# Task 5: Render Entra Client Secret expiry in mail settings

## Files

- Modify `picorgftp_sql/web/static/app.js` in mail settings helpers and `renderSettingsMail`.
- Modify `picorgftp_sql/web/static/app.css` beside existing mail-channel styles.
- Extend `tests/test_web_ui_integrity.py`, `tests/test_web_smoke_ci.py`, and `tests/test_source_integrity.py` only if needed.

## Binding requirements

- The Microsoft Entra card displays the safe cached status from `GET /api/settings/email/entra-expiry` without automatically performing a Graph refresh every time the settings tab is rendered.
- Display concise status: application name, credential display name, expiry date/time, remaining days, last successful/check time, and whether value is cached. Use local presentation time; retain canonical UTC in an accessible title/tooltip.
- Status `ok` is visually calm when far from expiry; use warning/critical visual treatment when remaining days reach the existing thresholds or expiry has passed. Do not animate success/info states.
- Display `permission_required` with explicit `Application.Read.All` and admin-consent instruction, distinct from generic transport/unavailable errors.
- Add `Sprawdz teraz` button. It POSTs `/api/settings/email/entra-expiry/refresh`, disables while pending, replaces the same status panel with the safe response, and handles request failure without clearing the last rendered status.
- Never interpolate/render `credential_key_id`, secret, token, headers, raw Graph details or error response body. Use `textContent`, not `innerHTML`, for backend values.
- Keep both Entra and SMTP cards responsive; expiry panel uses a compact grid/inline metadata rather than a full-height card.
- Preserve existing settings save and test-mail behavior.

## TDD requirements

1. Add source-integrity tests for `renderEntraExpiryStatus`, safe endpoints, refresh text, `Application.Read.All`, and absence of `innerHTML` in the renderer slice.
2. Add/extend UI smoke test if practical to validate no backend-sensitive key is queried/rendered.
3. Run focused tests RED before implementation.
4. Implement minimal JS/CSS.
5. Run `python -m pytest -q tests/test_web_ui_integrity.py tests/test_web_smoke_ci.py tests/test_source_integrity.py`.
6. Run `git diff --check`, self-review, commit only Task 5 files.

## Report

Write full report to `.superpowers/sdd/task-5-report.md` with RED/GREEN evidence, changed files, commit hash and concerns. Return only `DONE`/`DONE_WITH_CONCERNS`/`BLOCKED`, hash, tests, concern.
