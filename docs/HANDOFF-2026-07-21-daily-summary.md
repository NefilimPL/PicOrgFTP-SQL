# Handoff — daily change summary, mail help, and notification safety

## Start here

Repository: `C:\_GitHub_\PicOrgFTP-SQL`  
Branch: `dev`  
Base currently checked out: `2ae7687` (`origin/dev` is the same commit).  

Do **not** reset, checkout, discard, or overwrite the current worktree. It has
uncommitted user-authorized work that must be reviewed and committed only after
full verification.

Run first:

```powershell
git status --short
git diff --check
git diff --stat
```

At handoff time the intended uncommitted files are:

- `picorgftp_sql/notification_service.py`
- `picorgftp_sql/sqlite_store.py`
- `picorgftp_sql/web/static/app.css`
- `picorgftp_sql/web/static/app.js`
- `tests/test_notification_outbox.py`
- `tests/test_notification_service.py`
- `tests/test_source_integrity.py`
- `tests/test_sqlite_store.py`

`git diff --check` was clean at handoff.

## User-approved requirements

### 1. Stop e-mail spam from informational events

Root cause was confirmed: every `info` operational event created an individual
notification outbox intent. One successful PIMcore update can emit many
technical `info` events (process stages, SQL profiles, FTP/SQL success), which
caused about 43 separate e-mails.

Required behavior:

- `info` events stay in live logs and history.
- `info` events must **not** create immediate e-mail intents or deliveries.
- Existing pending legacy `info` intents must complete without sending.
- Warning, error and critical notifications remain incident-based; do not
  weaken them.

The initial suppression was committed in `2ae7687` and must stay intact.

### 2. One compact daily summary e-mail

The daily report is for regular users, not administrators.

- Mail settings contain configurable `daily_summary_time`, normalized as
  strict `HH:MM`; default is `16:00`.
- Timezone is fixed to `Europe/Warsaw`.
- Reporting window is continuous: from the previous successful report to the
  current scheduled run. Example: 20.07 16:00 → 21.07 16:00. Changes after
  16:00 therefore appear in the following report and are never lost.
- Send one e-mail only if product changes occurred.
- No maximum number of EANs. Each EAN must be one compact line.
- Only user-facing content:
  - `utworzono nowy wpis`,
  - `zaktualizowano dane PIMcore: <nazwy pól>`,
  - `zaktualizowano zdjęcia: sloty <numery>`.
- Exclude SQL, FTP, durations, operational stages, raw JSON, stack traces and
  internal diagnostics.
- Recipients are the enabled `info` rule recipients. Do not invent an actor.
- Use configured primary mail channel and fallback.
- If there are no recipients, do not mark the report sent; it should run when
  configuration becomes valid.

### 3. Durability and concurrency constraints

These were found in review and are non-negotiable:

- A failed report waits 5 minutes before retry; it must not be retried every
  2-second worker iteration.
- A pending or sending older window blocks creation of a later overlapping
  window (FIFO); failed changes cannot be silently abandoned.
- Claims must be atomic in SQLite. Exactly one worker may own a report.
- A worker claim has a token/lease. `finalize` must compare the current token;
  a stale worker cannot finalize a report reclaimed by another worker.
- Recovery only releases `sending` claims older than 10 minutes. It must use a
  compare-and-swap predicate on the old claim data/token.
- Handle DST safely. Current approved approach rejects `02:xx` as an unsafe
  `Europe/Warsaw` local schedule and normalizes it back to `16:00`; preserve
  this policy unless the user explicitly changes it.
- Schema is now intended to be version **10**, including migrations from the
  earlier v8/v9 daily-report table layouts.

The backend agent reported RED/GREEN evidence for this final token fix:

```text
158 focused tests passed
git diff --check passed
python -m compileall -q picorgftp_sql passed
```

Do not trust this alone: inspect diff and run tests yourself.

### 4. Settings UI

Uncommitted UI work adds:

- a `time` input for `daily_summary_time`, default `16:00`, labelled
  `Europe/Warsaw`;
- reusable clickable `?` help popovers;
- keyboard accessibility: button semantics, `aria-expanded`, `aria-controls`,
  `role="tooltip"`, Escape closes and restores focus, outside click closes;
- help for each severity and relevant mail options;
- explicit Entra guidance:
  - Tenant ID = **Identyfikator katalogu (dzierżawy)**,
  - Client ID = **Identyfikator aplikacji (klienta)**,
  - Client Secret = **Certyfikaty i wpisy tajne → Wpisy tajne klienta →
    Wartość**,
  - never use **Identyfikator wpisu tajnego** or **Identyfikator obiektu**,
  - explain address `Od` and SMTP fields clearly.

The UI agent reported:

```text
python -m pytest -q tests/test_source_integrity.py -> 45 passed
python -m pytest -q tests/test_email_settings.py tests/test_source_integrity.py -> 88 passed
```

`node --check` was unavailable locally; do not claim JS syntax verification by
Node unless Node is available.

## Work already committed before this handoff

- `86cd266` — Entra expiry observability hardening
- `353ef71`, `4773dcc` — CodeQL regex remediation
- `f6846ed`, `3ed4c14` — test every notification severity
- `3fb654f` — daily-summary design and plan
- `2ae7687` — initial daily-summary backend work (review it; it is on remote)

Specifications and plans:

- `docs/superpowers/specs/2026-07-20-daily-change-summary-and-mail-help-design.md`
- `docs/superpowers/plans/2026-07-20-daily-change-summary-and-mail-help.md`

## Important remaining scope: realistic mail tests and exception attachments

The user additionally requested the next feature after daily-summary work:

- Test e-mails must visually and structurally resemble final real alerts, not
  generic text such as “Symulacja krytycznej awarii”.
- Generate believable, harmless test scenarios (Pimcore rejection, FTP failure,
  unavailable photo location, backend exception, Entra Secret expiring in 7
  days). Clearly mark them `[TEST][SYMULACJA]`.
- Error and critical messages attach a redacted, bounded `.txt` file **only
  when an actual/simulated exception or traceback exists**.
- Do not attach a `.txt` for validation errors, forbidden file/slot errors,
  bad user data, or other normal non-exception failures.
- Attachment text must redact password/token/client secret/key ID and be
  size-bounded. Do not put a huge traceback in mail HTML/text body.
- This feature has **not** been implemented yet. Design it and add tests first.

Inspect `picorgftp_sql/email_delivery.py` and `MailMessage` before design: the
current transport/message model may need an explicit attachment interface.

## Required next steps

1. Inspect all uncommitted diffs line-by-line.
2. Re-review the token/lease backend changes. Fix every Critical/Important
   finding before proceeding.
3. Run focused backend and UI tests:

```powershell
python -m pytest tests/test_email_settings.py tests/test_notification_outbox.py tests/test_notification_service.py tests/test_observability.py tests/test_sqlite_store.py tests/test_source_integrity.py -q
```

4. Run the full suite:

```powershell
python -m pytest -q
git diff --check
```

5. Only after all tests and review are clean, commit the current daily-summary
   backend/UI changes deliberately. Suggested message:

```text
feat: add daily change summary emails
```

6. Then design and implement the still-pending realistic test templates and
   exception attachments as a separate TDD-tested change.
7. Do not push, merge or reset without the user's explicit instruction.
