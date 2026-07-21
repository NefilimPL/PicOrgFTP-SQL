# Email Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one mail configuration with Microsoft Entra/Graph and generic SMTP channels, configurable primary/fallback delivery, per-severity recipient rules, user email addresses, durable background delivery and test messages.

**Architecture:** Extend the existing SQLite/config layers with a durable delivery queue and normalized encrypted mail settings. Isolate Graph and SMTP behind one transport interface, resolve recipients from severity rules plus the correlated actor, and run delivery in a restart-safe background worker that records every primary/fallback attempt as observability data.

**Tech Stack:** Python 3.11+, SQLite, FastAPI/Starlette, `msal` 1.37.x/1.x, standard-library `smtplib`/`email`, browser JavaScript, CSS, pytest/unittest.

## Global Constraints

- This plan starts after `2026-07-16-observability-history.md` is complete.
- Use the existing `picorgftp_sql.sqlite`; do not create another database.
- Store Client Secret and SMTP password encrypted through the existing config encryption path.
- Never return new mail secrets from settings, secret-reveal or diagnostics APIs.
- Keep both channels in one configuration; select one primary and optionally use the other as fallback.
- A primary send failure causes at most one immediate fallback attempt.
- Use one logical `Message-ID` for primary and fallback attempts.
- Define independent rules for info, warning, error and critical; default all rules to disabled.
- Merge comma-separated fixed recipients with the correlated actor's optional user email, validate and deduplicate addresses.
- Coalesce repeated incident emails for 15 minutes.
- Test messages do not create incidents or recursively trigger notification errors.
- Mail delivery must never block or change the product-processing result.
- Follow test-first red/green/refactor for every behavior change.

---

### Task 1: Mail Settings Model, Encryption and Delivery Schema

**Files:**
- Create: `picorgftp_sql/email_settings.py`
- Modify: `picorgftp_sql/common.py`
- Modify: `picorgftp_sql/config.py`
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/sqlite_store.py`
- Modify: `picorgftp_sql/sqlite_maintenance.py`
- Modify: `picorgftp_sql/data_store.py`
- Test: `tests/test_email_settings.py`
- Test: `tests/test_config.py`
- Test: `tests/test_observability_store.py`
- Test: `tests/test_sqlite_maintenance.py`

**Interfaces:**
- Produces constants: `EMAIL_SETTINGS_KEY = "email_notifications"`, `EMAIL_CLIENT_SECRET = "client_secret"`, `EMAIL_SMTP_PASSWORD = "password"`.
- Produces: `default_email_settings() -> dict[str, object]`
- Produces: `normalize_email_settings(raw: object) -> dict[str, object]`
- Produces: `public_email_settings(raw: object) -> dict[str, object]`
- Produces: `SqliteStore.enqueue_notification_delivery(record) -> dict[str, Any]`
- Produces: `SqliteStore.pending_notification_deliveries(limit=20) -> list[dict[str, Any]]`
- Produces: `SqliteStore.update_notification_delivery(delivery_id, *, status, used_channel="", attempts=None, updated_at, next_attempt_at="") -> dict[str, Any]`
- Produces: `SqliteStore.query_notification_deliveries(*, incident_id="", cursor="", limit=20) -> dict[str, Any]`
- Changes: `SqliteStore.clear_operational_data()` also deletes notification deliveries while preserving product history.

- [ ] **Step 1: Write failing settings and schema tests**

Test normalization bounds ports, validates channel/security enum values, parses
recipient strings and keeps four complete rule blocks:

```python
def test_normalize_email_settings_builds_both_channels_and_rules() -> None:
    result = normalize_email_settings({
        "primary_channel": "smtp",
        "fallback_enabled": True,
        "smtp": {"host": "smtp.example", "port": "587", "security": "starttls"},
        "rules": {"error": {"enabled": True, "recipients": "a@example.com, b@example.com", "include_actor": True}},
    })
    assert result["primary_channel"] == "smtp"
    assert result["smtp"]["port"] == 587
    assert result["rules"]["error"]["recipients"] == ["a@example.com", "b@example.com"]
    assert set(result["rules"]) == {"info", "warning", "error", "critical"}
```

Assert `config.save_config()` encrypts both new secrets and a blank submitted
secret preserves the raw encrypted value. Initialize a database and assert
schema version `6` plus the delivery table.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_email_settings.py tests/test_config.py tests/test_observability_store.py tests/test_sqlite_maintenance.py -q
```

Expected: FAIL because mail settings and schema version 6 do not exist.

- [ ] **Step 3: Implement normalized settings**

Create this default shape:

```python
def default_email_settings() -> dict[str, object]:
    return {
        "primary_channel": "entra",
        "fallback_enabled": False,
        "entra": {
            "tenant_id": "", "client_id": "", "client_secret": "", "from_address": "",
        },
        "smtp": {
            "host": "", "port": 587, "security": "starttls", "username": "",
            "password": "", "from_address": "", "from_name": "",
        },
        "rules": {
            severity: {"enabled": False, "recipients": [], "include_actor": False}
            for severity in ("info", "warning", "error", "critical")
        },
    }
```

Normalize primary to `entra|smtp`, security to `starttls|tls|none`, port to
`1..65535`, recipient inputs from string/list, and booleans. Preserve values but
do not validate connectivity here.

`public_email_settings()` removes both secrets and adds
`client_secret_set`/`password_set` booleans.

- [ ] **Step 4: Integrate settings with config encryption**

Add the defaults in `common.py`. In `config.py`, decrypt both secrets on load,
then build the saved payload using the existing `_pick_secret` helper:

```python
email_settings = normalize_email_settings(config.get(EMAIL_SETTINGS_KEY))
email_payload = copy.deepcopy(email_settings)
email_payload["entra"][EMAIL_CLIENT_SECRET] = _pick_secret(
    EMAIL_SETTINGS_KEY, "entra.client_secret", email_settings["entra"][EMAIL_CLIENT_SECRET]
)
email_payload["smtp"][EMAIL_SMTP_PASSWORD] = _pick_secret(
    EMAIL_SETTINGS_KEY, "smtp.password", email_settings["smtp"][EMAIL_SMTP_PASSWORD]
)
payload[EMAIL_SETTINGS_KEY] = email_payload
```

Because existing `preserve_secrets` is section/key based, extend `_pick_secret`
with a small dotted-path reader for these two keys; do not flatten or expose the
secret. Update `_preserve_unsubmitted_config_secrets`, `update_settings()` and
`settings_snapshot()` in `web_data.py`. Do not add mail secrets to
`settings_secret_values()`.

- [ ] **Step 5: Add schema version 6 and delivery repository**

Create:

```sql
CREATE TABLE IF NOT EXISTS notification_deliveries (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL DEFAULT '',
    event_id TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    primary_channel TEXT NOT NULL,
    used_channel TEXT NOT NULL DEFAULT '',
    recipients_json TEXT NOT NULL DEFAULT '[]',
    message_json TEXT NOT NULL,
    attempts_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    next_attempt_at TEXT NOT NULL DEFAULT ''
);
```

Add indexes on `(status, next_attempt_at, created_at)` and
`(incident_id, created_at)`. Add timestamp maintenance entries and adapter
delegators. Repository methods return decoded `recipients`, `message` and
`attempts` fields. Extend `clear_operational_data()` and its tests to remove
delivery rows without touching `web_history` or `pimcore_submissions`.

- [ ] **Step 6: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add picorgftp_sql/email_settings.py picorgftp_sql/common.py picorgftp_sql/config.py picorgftp_sql/web_data.py picorgftp_sql/sqlite_store.py picorgftp_sql/sqlite_maintenance.py picorgftp_sql/data_store.py tests/test_email_settings.py tests/test_config.py tests/test_observability_store.py tests/test_sqlite_maintenance.py
git commit -m "feat: add encrypted mail settings and delivery queue"
```

### Task 2: Optional Email Address on Web Users

**Files:**
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Test: `tests/test_web_data_users.py`
- Test: `tests/test_web_smoke_ci.py`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Changes: `add_user(username, password, role="user", email="")`.
- Changes: `update_user(..., email: str | None = None, ...)`.
- Public user payload includes `email`.

- [ ] **Step 1: Write failing user email tests**

Add tests for normalization, persistence, clearing and invalid address rejection:

```python
def test_update_user_persists_normalized_email() -> None:
    with patch.object(web_data, "load_user_records", return_value=[web_data._default_admin()]), \
         patch.object(web_data, "save_users", side_effect=lambda users: [web_data._public_user(item) for item in users]):
        users = web_data.update_user("admin", email=" Admin@Example.COM ")
    assert users[0]["email"] == "Admin@example.com"
```

Route/UI tests assert add and edit forms send the email field.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_web_data_users.py tests/test_web_smoke_ci.py tests/test_web_ui_integrity.py -q
```

Expected: FAIL because users do not include email.

- [ ] **Step 3: Add reusable address validation**

In `email_settings.py`, use `email.headerregistry.Address` or
`email.utils.parseaddr` plus a conservative single-address check:

```python
def normalize_email_address(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    display, address = parseaddr(text)
    if display or address != text or address.count("@") != 1:
        raise ValueError("Niepoprawny adres e-mail.")
    local, domain = address.rsplit("@", 1)
    if not local or "." not in domain or any(ch.isspace() for ch in address):
        raise ValueError("Niepoprawny adres e-mail.")
    return f"{local}@{domain.lower()}"
```

- [ ] **Step 4: Persist and expose user email**

Add `email` to `_default_admin`, `_normalized_user_record`, `_public_user`,
`add_user` and `update_user`. Since `web_users` stores JSON payloads, no column
migration is required. Existing users normalize to an empty string.

Forward email in POST/PATCH user routes. Empty PATCH email clears it.

- [ ] **Step 5: Update users settings UI**

Add an optional e-mail input to the new-user form and each existing user row.
Use `type="email"`, `autocomplete="email"`, and send the value on save. Keep the
current responsive user row behavior.

- [ ] **Step 6: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add picorgftp_sql/web_data.py picorgftp_sql/web/app.py picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_data_users.py tests/test_web_smoke_ci.py tests/test_web_ui_integrity.py
git commit -m "feat: store notification email on web users"
```

### Task 3: Microsoft Graph and Generic SMTP Transports

**Files:**
- Create: `picorgftp_sql/email_delivery.py`
- Modify: `requirements-web.txt`
- Modify: `requirements-build.txt`
- Modify: `PicOrgFTP-SQL-WEB.spec`
- Create: `tests/test_email_delivery.py`
- Modify: `tests/test_build_exe_workflow.py`

**Interfaces:**
- Produces dataclass: `MailMessage(message_id, subject, text_body, html_body, sender_address, sender_name, recipients)`.
- Produces protocol: `MailTransport.send(message: MailMessage) -> dict[str, object]`.
- Produces: `GraphMailTransport(settings: Mapping[str, object])`.
- Produces: `SmtpMailTransport(settings: Mapping[str, object])`.
- Produces: `build_transport(channel: str, settings: Mapping[str, object]) -> MailTransport`.

- [ ] **Step 1: Write failing transport contract tests**

Test Graph token request and sendMail payload with a fake MSAL client and fake
HTTP opener. Test SMTP TLS modes with fake `SMTP`/`SMTP_SSL` classes:

```python
def test_smtp_transport_uses_starttls_login_and_message_id(monkeypatch) -> None:
    smtp = FakeSmtp()
    monkeypatch.setattr(email_delivery.smtplib, "SMTP", lambda host, port, timeout: smtp)
    transport = SmtpMailTransport({
        "host": "smtp.example", "port": 587, "security": "starttls",
        "username": "sender", "password": "secret",
    })
    result = transport.send(sample_message())
    assert smtp.calls[:2] == ["ehlo", "starttls"]
    assert smtp.login_args == ("sender", "secret")
    assert "Message-ID: <incident-1@picorgftp-sql>" in smtp.message
    assert result["channel"] == "smtp"
```

Also assert exceptions and returned diagnostics never include passwords,
secrets or access tokens.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_email_delivery.py tests/test_build_exe_workflow.py -q
```

Expected: FAIL because transports and MSAL dependency do not exist.

- [ ] **Step 3: Add MSAL dependency and build inclusion**

Add `msal>=1.37,<2` to web and build requirements. Ensure the web PyInstaller
spec collects MSAL package data/hidden imports only if the existing analysis
does not discover them automatically. Update workflow integrity assertions.

- [ ] **Step 4: Implement Graph transport**

Use `msal.ConfidentialClientApplication` with authority
`https://login.microsoftonline.com/{tenant_id}` and
`acquire_token_for_client(["https://graph.microsoft.com/.default"])`.
POST JSON to:

```python
endpoint = (
    "https://graph.microsoft.com/v1.0/users/"
    + urllib.parse.quote(sender, safe="")
    + "/sendMail"
)
payload = {
    "message": {
        "subject": message.subject,
        "body": {"contentType": "HTML", "content": message.html_body},
        "toRecipients": [
            {"emailAddress": {"address": address}} for address in message.recipients
        ],
        "internetMessageHeaders": [
            {"name": "x-picorg-message-id", "value": message.message_id}
        ],
    },
    "saveToSentItems": True,
}
```

Use a 20-second timeout and accept HTTP 202 only. Return channel, status code
and elapsed time; redact MSAL/HTTP error details.

- [ ] **Step 5: Implement SMTP transport**

Use `EmailMessage`, set `From`, `To`, `Subject`, `Message-ID`, plain text and
HTML alternatives. Build a verified SSL context using `certifi.where()` when
available. Use `SMTP_SSL` for `tls`, `SMTP.starttls` for `starttls`, and plain
`SMTP` only for `none`. Login only when username is non-empty. Always call
`quit()`/close in `finally`.

- [ ] **Step 6: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add picorgftp_sql/email_delivery.py requirements-web.txt requirements-build.txt PicOrgFTP-SQL-WEB.spec tests/test_email_delivery.py tests/test_build_exe_workflow.py
git commit -m "feat: add Graph and SMTP mail transports"
```

### Task 4: Recipient Rules, Durable Worker and Fallback

**Files:**
- Create: `picorgftp_sql/notification_service.py`
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/observability.py`
- Create: `tests/test_notification_service.py`
- Modify: `tests/test_observability.py`
- Modify: `tests/test_web_app_files.py`

**Interfaces:**
- Consumes: Task 1 delivery repository, Task 2 user email, Task 3 transports, and phase-1 incident `notification_due`.
- Produces: `resolve_recipients(event, settings, user_lookup) -> list[str]`.
- Produces: `queue_incident_notification(event, incident) -> dict[str, object] | None`.
- Produces: `process_delivery(delivery_id: str) -> dict[str, object]`.
- Produces: `start_notification_worker() -> None`, `stop_notification_worker() -> None`.
- Produces: `send_test_message(*, channel, recipient, use_fallback=False) -> dict[str, object]`.

- [ ] **Step 1: Write failing rules and fallback tests**

Cover disabled rules, fixed recipients, actor inclusion, deduplication,
15-minute notification suppression, primary success, primary failure plus
fallback success, both failures, restart recovery and recursion prevention:

```python
def test_process_delivery_falls_back_once_with_same_message_id() -> None:
    primary = FakeTransport(error=RuntimeError("primary down"))
    fallback = FakeTransport(result={"channel": "smtp", "status": "sent"})
    service = NotificationService(
        store=FakeStore.with_pending_delivery(),
        transport_factory=lambda channel, _settings: {
            "entra": primary, "smtp": fallback,
        }[channel],
        settings_loader=mail_settings,
    )
    result = service.process_delivery("delivery-1")
    assert len(primary.messages) == 1
    assert len(fallback.messages) == 1
    assert primary.messages[0].message_id == fallback.messages[0].message_id
    assert result["status"] == "fallback"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_notification_service.py tests/test_observability.py tests/test_web_app_files.py -q
```

Expected: FAIL because notification service and worker do not exist.

- [ ] **Step 3: Implement recipient resolution and safe message builder**

Read the exact severity rule. Return `[]` when disabled. Normalize fixed
addresses and, when `include_actor`, add `find_user(event["username"])["email"]`
if present. Deduplicate case-insensitively while retaining display order.

Build a Polish subject and both text/HTML body from redacted event/incident
fields. Escape every HTML value with `html.escape`. Do not include raw config,
cookies, authorization headers or an unrestricted traceback.

- [ ] **Step 4: Enqueue only notification-due incidents**

Phase-1 `coalesce_incident()` returns transient `notification_due=True` on the
first occurrence and after a 15-minute notification window, otherwise false.
After successful event persistence call `queue_incident_notification` only when
that flag is true and recipients are non-empty. Record disabled/no-recipient
cases as `skipped` deliveries only for warning/error/critical, not for routine
info events.

- [ ] **Step 5: Implement primary/fallback delivery**

For one claimed delivery:

1. mark it `sending`;
2. try the configured primary once;
3. on failure and enabled fallback, try the other channel once;
4. store redacted attempt results;
5. finish as `sent`, `fallback` or `error`.

Emit `notification.sent` as `info` and `notification.failed` as an operational
`error` with `details={"suppress_notifications": True}`. The incident hook must
honor that flag to prevent recursive e-mails.

- [ ] **Step 6: Implement restart-safe background worker**

Use a daemon thread plus `threading.Event`, following the backup scheduler
lifecycle. Poll pending rows every two seconds, claim deterministically and
process a bounded batch. On startup convert stale `sending` rows older than five
minutes back to `pending`. Start in FastAPI startup and stop/join in shutdown.

- [ ] **Step 7: Implement direct test sending**

Validate one recipient, build a clearly marked test message, and call the
selected channel. If `use_fallback=True`, use the configured primary/fallback
path. Return redacted attempts without creating an incident or queue row.

- [ ] **Step 8: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add picorgftp_sql/notification_service.py picorgftp_sql/web/app.py picorgftp_sql/observability.py tests/test_notification_service.py tests/test_observability.py tests/test_web_app_files.py
git commit -m "feat: deliver incident mail with fallback"
```

### Task 5: Mail Settings and Test UI

**Files:**
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_web_smoke_ci.py`
- Modify: `tests/test_source_integrity.py`
- Modify: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Produces settings tab: `mail`.
- Produces: `POST /api/settings/email/test` (admin-only).
- Consumes existing `GET/PUT /api/settings` public mail snapshot.

- [ ] **Step 1: Write failing route and UI tests**

Assert the mail tab, both channel field groups, primary/fallback controls, four
severity rule blocks, test recipient/channel controls and secret placeholder
behavior. Route tests verify secrets are never returned and test errors are
redacted.

```python
def test_mail_settings_tab_has_both_channels_and_rules(self) -> None:
    assert 'data-settings-tab="mail"' in self.html_source
    assert "renderSettingsMail()" in self.js_source
    for severity in ("info", "warning", "error", "critical"):
        assert f'email_rule_{severity}_enabled' in self.js_source
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_web_smoke_ci.py tests/test_source_integrity.py tests/test_web_ui_integrity.py -q
```

Expected: FAIL because the mail settings tab and test route are absent.

- [ ] **Step 3: Add admin test route**

Accept:

```json
{"recipient":"admin@example.com","channel":"entra|smtp|primary","use_fallback":true}
```

Require admin and CSRF, call `send_test_message` in `run_in_threadpool`, and
return `{ok, status, used_channel, attempts, elapsed_ms}`. Convert validation to
HTTP 400 and transport failure to HTTP 502 without secret-bearing details.

- [ ] **Step 4: Add Mail settings tab and forms**

Add a `Poczta` settings tab after Pimcore. Render:

- primary channel select and fallback checkbox;
- Entra Tenant ID, Client ID, Client Secret and `Od`;
- SMTP host, port, security, login, password, address/name `Od`;
- four severity cards with enabled, comma-separated recipients and
  `Wyślij także do powiązanego użytkownika`;
- test recipient, channel and fallback controls.

Secret inputs are password fields whose placeholder uses `*_set`; empty submit
preserves the saved secret. For SMTP `none`, display an inline danger warning.

- [ ] **Step 5: Implement save and test behavior**

Serialize recipient text to arrays after splitting commas/trimming. Disable
test buttons while running, show which channel succeeded, and render both
redacted attempts if fallback occurred. Never place a returned secret into an
input or DOM data attribute.

- [ ] **Step 6: Add responsive styles**

Follow existing `settings-form`, `settings-grid`, `check-row` and status colors.
Use two columns for the channel cards on wide screens and one column below
920 px. Do not use animation for successful test messages.

- [ ] **Step 7: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add picorgftp_sql/web/app.py picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_smoke_ci.py tests/test_source_integrity.py tests/test_web_ui_integrity.py
git commit -m "feat: add mail settings and test messages"
```

### Task 6: Incident Delivery Status, Documentation and Final Verification

**Files:**
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_observability_api.py`
- Modify: `tests/test_web_ui_integrity.py`
- Modify: `docs/web-panel.md`
- Modify: `docs/building-exe.md`

**Interfaces:**
- Changes incident API/cards to include `deliveries` with status and redacted attempts.

- [ ] **Step 1: Write failing delivery status tests**

Assert incident detail responses include matching delivery records and UI maps
statuses to Polish labels `Oczekuje`, `Wysłano`, `Fallback`, `Pominięto`, `Błąd`.
Verify non-admin routes cannot inspect recipients or attempts.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_observability_api.py tests/test_web_ui_integrity.py -q
```

Expected: FAIL because incident responses do not include delivery status.

- [ ] **Step 3: Attach redacted delivery status to incidents**

For incident detail/list items query recent matching deliveries and return only:

```python
{
    "id": delivery["id"],
    "status": delivery["status"],
    "used_channel": delivery["used_channel"],
    "recipient_count": len(delivery["recipients"]),
    "created_at": delivery["created_at"],
    "updated_at": delivery["updated_at"],
    "attempts": redact_value(delivery["attempts"]),
}
```

Do not expose recipient addresses in general incident list payloads.

- [ ] **Step 4: Render delivery state on alert cards**

Show the latest status and channel as a compact badge. Expanded details show
redacted attempt times/errors and recipient count. A failed e-mail must not
change the incident severity or hide the original operational error.

- [ ] **Step 5: Document configuration and provider prerequisites**

Update `docs/web-panel.md` with both channels, primary/fallback, four rule
blocks, 15-minute coalescing, actor e-mail and test messages. Update
`docs/building-exe.md` with MSAL dependency/build notes. Document that Graph
requires application `Mail.Send` admin consent and SMTP providers may require
an application password.

- [ ] **Step 6: Run focused and full verification**

Run:

```powershell
python -m pytest tests/test_email_settings.py tests/test_email_delivery.py tests/test_notification_service.py tests/test_observability.py tests/test_observability_store.py tests/test_observability_api.py tests/test_web_data_users.py tests/test_web_smoke_ci.py tests/test_source_integrity.py tests/test_web_ui_integrity.py tests/test_config.py tests/test_build_exe_workflow.py tests/test_sqlite_maintenance.py -q
python -m pytest -q
```

Expected: all tests PASS with no new warnings.

- [ ] **Step 7: Run secret and scope audit**

Run:

```powershell
git diff --check
rg -n "client_secret|smtp.*password|access_token|Authorization" picorgftp_sql tests
git status --short
```

Expected: persisted/API values are encrypted, omitted or `[REDACTED]`; only
configuration plumbing and explicit fake test values contain secret key names;
changes are limited to plan files.

- [ ] **Step 8: Commit**

```powershell
git add picorgftp_sql/web/app.py picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_observability_api.py tests/test_web_ui_integrity.py docs/web-panel.md docs/building-exe.md
git commit -m "feat: show notification delivery status"
```
