# Compact Observability and Entra Secret Expiry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render live logs and history in a compact, expandable form and automatically monitor Microsoft Entra Client Secret expiry with safe critical reminders.

**Architecture:** The browser receives normalized presentation fields instead of rendering provider dictionaries through a generic JSON formatter. A dedicated Entra expiry module obtains a Graph application token, reads `passwordCredentials`, and persists safe status plus reminder claims in the existing SQLite store. The notification worker invokes the monitor daily; due thresholds emit ordinary critical observability events, so the existing notification outbox, recipient rules, and primary/fallback delivery remain authoritative.

**Tech Stack:** Python 3.13, FastAPI, SQLite, MSAL, urllib, vanilla JavaScript, CSS, pytest/unittest.

## Global Constraints

- Use only the existing SQLite database resolved by `storage_settings.resolve_sqlite_path()`; do not add JSON sidecar state or another SQLite file.
- Never return, render, log, queue, or mail Client Secret values, Graph access tokens, Authorization headers, or full Graph error payloads.
- Client Secret expiry is distinct from access-token expiry. Graph metadata requires `Application.Read.All` with admin consent; `Mail.Send` alone is insufficient.
- Live defaults to a single dense row per event; details are user-expanded and remain keyboard accessible.
- History default view must not stringify raw `evidence` or `integrations` objects.
- Entra reminder thresholds are exactly `14, 7, 3, 2, 1` days. A threshold is emitted at most once for a tenant/client/credential/expiry combination.
- Expiry reminders are `critical` operational events and use existing `critical` notification rules and delivery fallback.
- Preserve existing browser test seams, source-integrity tests, and event/outbox transaction guarantees.

---

### Task 1: Normalize compact history evidence and render dense expandable UI

**Files:**
- Modify: `picorgftp_sql/web/static/app.js:4290-4640,4818-4870`
- Modify: `picorgftp_sql/web/static/app.css:2185-2290,2685-2875`
- Test: `tests/test_web_ui_integrity.py`
- Test: `tests/test_history_changes.py`

**Interfaces:**
- Consumes: existing history `change_set.files[*]`, `file.evidence.local|ftp|sql`, operational event fields, and existing `renderLogEvent(event)` call sites.
- Produces: `historyEvidenceBadges(evidence)`, `historyEvidenceDetails(evidence)`, `compactHistoryFileRow(file)`, and dense `<article class="log-event log-event-compact">` nodes.

- [ ] **Step 1: Write failing renderer/source tests**

```python
def test_history_renderer_uses_provider_badges_not_generic_json():
    source = _read("picorgftp_sql/web/static/app.js")
    start = source.index("function renderHistoryChanges")
    end = source.index("function renderHistoryDetails", start)
    renderer = source[start:end]
    assert "historyEvidenceBadges" in renderer
    assert "historyEvidenceDetails" in renderer
    assert 'historyChangeRow("Lokalnie", evidence.local)' not in renderer
    assert 'historyChangeRow("FTP", evidence.ftp)' not in renderer
    assert 'historyChangeRow("SQL", evidence.sql)' not in renderer


def test_live_renderer_uses_one_compact_summary_row():
    source = _read("picorgftp_sql/web/static/app.js")
    start = source.index("function renderLogEvent")
    end = source.index("function incidentValue", start)
    renderer = source[start:end]
    assert "log-event-compact" in renderer
    assert "log-event-summary-row" in renderer
    assert "details.append" in renderer
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_web_ui_integrity.py -k "history_renderer_uses_provider_badges or live_renderer_uses_one_compact_summary_row"`

Expected: FAIL because the compact helpers and CSS classes do not exist.

- [ ] **Step 3: Add presentation-only helpers and replace raw object rows**

```javascript
function historyEvidenceBadges(evidence = {}) {
  const output = document.createElement("span");
  output.className = "history-evidence-badges";
  for (const [provider, entries] of Object.entries(evidence)) {
    for (const entry of Array.isArray(entries) ? entries : [entries]) {
      if (!entry || typeof entry !== "object") continue;
      const badge = document.createElement("span");
      const status = entry.status || entry.upload_status || "unknown";
      badge.className = `history-evidence-badge status-${status}`;
      badge.textContent = `${provider.toUpperCase()} ${historyEvidenceLabel(status)}${entry.elapsed_ms !== undefined ? ` ${formatHistoryDuration(entry.elapsed_ms)}` : ""}`;
      output.appendChild(badge);
    }
  }
  return output;
}

function compactHistoryFileRow(file) {
  const details = document.createElement("details");
  details.className = "history-file-change";
  const summary = document.createElement("summary");
  summary.className = "history-file-summary";
  summary.append(historySlotLabel(file), historyNameDelta(file), historySizeDelta(file), historyEvidenceBadges(file.evidence));
  details.append(summary, historyEvidenceDetails(file.evidence));
  return details;
}
```

Render `changeSet.integrations` only in a final collapsed `details.history-technical-details` block. Reuse `historyChangeValue` inside that block only, never in a default history section for object values.

Rewrite `renderLogEvent` to append one flex/grid `log-event-summary-row` containing time, severity label, summary, compact context chips and a disclosure marker. Keep `details > pre.log-lines` as the sole expanded technical area.

- [ ] **Step 4: Add dense CSS with narrow-screen fallback**

```css
.logs-output-live { display: grid; gap: 0; }
.log-event-compact { padding: 0; border-width: 0 0 1px; border-radius: 0; }
.log-event-summary-row { display: grid; grid-template-columns: auto auto minmax(0, 1fr) auto; gap: 8px; min-height: 34px; align-items: center; padding: 5px 8px; }
.log-event-summary-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-file-summary { display: grid; grid-template-columns: auto minmax(170px, 1fr) minmax(130px, .45fr) auto; gap: 8px; align-items: center; cursor: pointer; }
.history-evidence-badges { display: inline-flex; flex-wrap: wrap; gap: 4px; }
@media (max-width: 760px) { .log-event-summary-row, .history-file-summary { grid-template-columns: 1fr auto; } }
```

Use small colored badges; do not add animation for info/success.

- [ ] **Step 5: Run focused UI and history tests**

Run: `python -m pytest -q tests/test_web_ui_integrity.py tests/test_history_changes.py`

Expected: PASS. Inspect the renderer source test to confirm no default raw-object history rows remain.

- [ ] **Step 6: Commit**

```powershell
git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py tests/test_history_changes.py
git commit -m "feat: compact live logs and change history"
```

### Task 2: Persist safe Entra expiry status and idempotent reminder claims in SQLite

**Files:**
- Modify: `picorgftp_sql/sqlite_store.py:25,526-825,2430`
- Test: `tests/test_sqlite_store.py`
- Test: `tests/test_notification_outbox.py`

**Interfaces:**
- Consumes: canonical UTC timestamps and the existing `SqliteStore.connection()` transaction boundary.
- Produces: `get_entra_secret_status(tenant_id, client_id) -> dict`, `upsert_entra_secret_status(status) -> dict`, `clear_entra_secret_status(tenant_id, client_id) -> int`, and `claim_entra_secret_reminder(..., threshold_days, claimed_at) -> bool`.

- [ ] **Step 1: Write failing storage tests**

```python
def test_entra_expiry_status_round_trip_and_secret_never_persists(tmp_path):
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.initialize()
    store.upsert_entra_secret_status({
        "tenant_id": "tenant", "client_id": "client", "status": "ok",
        "expires_at": "2026-08-01T10:00:00.000Z", "credential_name": "Primary",
        "credential_key_id": "internal-key", "secret": "must-not-persist",
    })
    result = store.get_entra_secret_status("tenant", "client")
    assert result["credential_name"] == "Primary"
    assert "secret" not in result
    assert "credential_key_id" not in result


def test_entra_expiry_reminder_claim_is_atomic_and_rotation_is_distinct(tmp_path):
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    assert store.claim_entra_secret_reminder("tenant", "client", "key-a", "2026-08-01T00:00:00.000Z", 7, "2026-07-25T00:00:00.000Z")
    assert not store.claim_entra_secret_reminder("tenant", "client", "key-a", "2026-08-01T00:00:00.000Z", 7, "2026-07-25T00:00:01.000Z")
    assert store.claim_entra_secret_reminder("tenant", "client", "key-b", "2026-09-01T00:00:00.000Z", 7, "2026-08-25T00:00:00.000Z")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_sqlite_store.py -k "entra_expiry"`

Expected: FAIL because the tables and methods do not exist.

- [ ] **Step 3: Add schema version 7 and narrow store methods**

Add tables inside `SqliteStore.initialize()`:

```sql
CREATE TABLE IF NOT EXISTS entra_secret_status (
    tenant_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    status TEXT NOT NULL,
    expires_at TEXT NOT NULL DEFAULT '',
    credential_name TEXT NOT NULL DEFAULT '',
    credential_key_id TEXT NOT NULL DEFAULT '',
    application_name TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    last_checked_at TEXT NOT NULL DEFAULT '',
    last_success_at TEXT NOT NULL DEFAULT '',
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (tenant_id, client_id)
);
CREATE TABLE IF NOT EXISTS entra_secret_reminders (
    tenant_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    credential_key_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    threshold_days INTEGER NOT NULL,
    claimed_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, client_id, credential_key_id, expires_at, threshold_days)
);
```

`get_entra_secret_status` returns a public projection and removes `credential_key_id`. `claim_entra_secret_reminder` uses `INSERT ... ON CONFLICT DO NOTHING` inside `BEGIN IMMEDIATE`; its boolean result is derived from `cursor.rowcount == 1`. Increment `SCHEMA_VERSION` to `7`, index `last_checked_at`, and include both tables in `clear_operational_data()` only if their data is defined as operational. Do **not** clear them for normal log clearing; expose count `0` only if unchanged.

- [ ] **Step 4: Run focused storage and notification tests**

Run: `python -m pytest -q tests/test_sqlite_store.py tests/test_notification_outbox.py`

Expected: PASS, including current schema-version and operational-clear assertions updated for version 7.

- [ ] **Step 5: Commit**

```powershell
git add picorgftp_sql/sqlite_store.py tests/test_sqlite_store.py tests/test_notification_outbox.py
git commit -m "feat: persist Entra secret expiry state"
```

### Task 3: Read and classify Entra Client Secret expiry through Graph

**Files:**
- Create: `picorgftp_sql/entra_secret_expiry.py`
- Test: `tests/test_entra_secret_expiry.py`
- Modify: `requirements-web.txt` only if the existing `msal` dependency is absent

**Interfaces:**
- Consumes: normalized `email_notifications.entra` settings with `tenant_id`, `client_id`, and `client_secret`.
- Produces: `fetch_entra_secret_expiry(settings, *, now=None, opener=urllib.request.urlopen) -> dict[str, object]`.
- Result contract: `{status, code, expires_at, remaining_seconds, remaining_days, application_name, credential_name, credential_key_id, source, error_message}`; only the store receives `credential_key_id`, and public API projections remove it.

- [ ] **Step 1: Write failing Graph client tests with fake responses**

```python
def test_fetch_selects_unique_hint_matching_active_secret(monkeypatch):
    result = fetch_entra_secret_expiry(
        {"tenant_id": "tenant", "client_id": "client", "client_secret": "abc-value"},
        opener=_graph_opener({"passwordCredentials": [
            {"hint": "abc", "displayName": "Current", "keyId": "key-1", "endDateTime": "2026-08-01T00:00:00Z"}
        ]}),
        now=_utc("2026-07-20T00:00:00Z"),
    )
    assert result["status"] == "ok"
    assert result["credential_name"] == "Current"
    assert result["remaining_days"] == 12


def test_fetch_maps_graph_forbidden_to_permission_required(monkeypatch):
    result = fetch_entra_secret_expiry(_settings(), opener=_http_error(403, "forbidden"))
    assert result["status"] == "unavailable"
    assert result["code"] == "permission_required"
    assert "Application.Read.All" in result["error_message"]


def test_fetch_refuses_ambiguous_credentials(monkeypatch):
    result = fetch_entra_secret_expiry(_settings("missing-hint"), opener=_graph_opener({"passwordCredentials": [_active("a"), _active("b")]}))
    assert result["status"] == "unavailable"
    assert result["code"] == "credential_ambiguous"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_entra_secret_expiry.py`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement an isolated Graph reader**

Use `msal.ConfidentialClientApplication(...).acquire_token_for_client(["https://graph.microsoft.com/.default"])` with a 20-second request timeout. Request only `appId,displayName,passwordCredentials`. Parse Graph times to canonical UTC. Select exactly one unique hint match; otherwise select exactly one active credential; otherwise return `credential_ambiguous`.

```python
def _safe_error(code: str) -> str:
    return {
        "permission_required": "Dodaj Microsoft Graph Application.Read.All i zatwierdź admin consent.",
        "application_not_found": "Nie znaleziono aplikacji Entra dla podanego Client ID.",
        "credential_ambiguous": "Nie można jednoznacznie dopasować aktywnego Client Secret.",
        "transport_unavailable": "Nie można teraz połączyć się z Microsoft Graph.",
        "invalid_response": "Microsoft Graph zwrócił nieprawidłowe dane aplikacji.",
    }[code]
```

Redact every caught exception through `sanitize_free_text`; do not include HTTP response bodies in the result. Do not use the decoded access token for expiry status.

- [ ] **Step 4: Run module and secret-redaction regression tests**

Run: `python -m pytest -q tests/test_entra_secret_expiry.py tests/test_secret_persistence.py tests/test_email_delivery.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add picorgftp_sql/entra_secret_expiry.py tests/test_entra_secret_expiry.py requirements-web.txt
git commit -m "feat: read Entra client secret expiry"
```

### Task 4: Monitor expiry, emit deduplicated critical events, and expose the admin API

**Files:**
- Create: `picorgftp_sql/entra_secret_monitor.py`
- Modify: `picorgftp_sql/notification_service.py:941-1000`
- Modify: `picorgftp_sql/web/app.py:4520-4620,5545-5650,6160-6190`
- Modify: `picorgftp_sql/web_data.py:2878-3055`
- Test: `tests/test_entra_secret_monitor.py`
- Test: `tests/test_observability_api.py`
- Test: `tests/test_notification_service.py`

**Interfaces:**
- Consumes: `fetch_entra_secret_expiry`, `SqliteStore` expiry methods, `emit_event`, and current email settings.
- Produces: `refresh_entra_secret_status(force=False) -> dict`, `process_due_entra_secret_reminders(now=None) -> int`, `GET /api/settings/email/entra-expiry`, and `POST /api/settings/email/entra-expiry/refresh`.

- [ ] **Step 1: Write failing monitor/API tests**

```python
def test_due_threshold_emits_once_and_uses_critical_event(monkeypatch, store):
    monkeypatch.setattr(monitor, "fetch_entra_secret_expiry", lambda *_args, **_kwargs: _expiry(days=3))
    emitted = []
    monkeypatch.setattr(monitor, "emit_event", lambda **event: emitted.append(event) or event)
    assert monitor.process_due_entra_secret_reminders(now=_utc("2026-07-20T00:00:00Z")) == 1
    assert emitted[0]["severity"] == "critical"
    assert emitted[0]["event_type"] == "entra.secret_expiry_due"
    assert monitor.process_due_entra_secret_reminders(now=_utc("2026-07-20T01:00:00Z")) == 0


def test_entra_expiry_refresh_is_admin_only_and_redacted(api_environment, monkeypatch):
    client, _store = api_environment
    monkeypatch.setattr(web_app, "refresh_entra_secret_status", lambda **_kwargs: {"status": "ok", "credential_name": "Primary", "expires_at": "2026-08-01T00:00:00.000Z"})
    assert client.get("/api/settings/email/entra-expiry").status_code == 403
    csrf = _login(client)
    response = client.post("/api/settings/email/entra-expiry/refresh", headers={"X-PicOrg-CSRF": csrf})
    assert response.status_code == 200
    assert "secret" not in response.text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_entra_secret_monitor.py tests/test_observability_api.py -k "entra_expiry"`

Expected: FAIL because monitor and endpoints do not exist.

- [ ] **Step 3: Implement monitor and daily worker hook**

```python
REMINDER_THRESHOLDS = (14, 7, 3, 2, 1)

def process_due_entra_secret_reminders(now: datetime | None = None) -> int:
    status = refresh_entra_secret_status(now=now)
    if status.get("status") != "ok":
        return 0
    threshold = _nearest_unsent_due_threshold(status, now=now)
    if threshold is None or not _store.claim_entra_secret_reminder(..., threshold, ...):
        return 0
    emit_event(
        severity="critical", event_type="entra.secret_expiry_due", module="entra",
        stage="secret-expiry", summary=f"Client Secret Entra wygasa za {threshold} dni.",
        recommended_action="Utwórz nowy Client Secret w Entra, zapisz go w ustawieniach i uruchom kontrolę.",
        details=_safe_expiry_details(status, threshold),
    )
    return 1
```

If `remaining_seconds <= 0`, emit a separately claimed `entra.secret_expired` event. Store `last_checked_at` for every attempt and preserve last success on unavailable Graph. `permission_required` emits one warning event per status change, with notification suppression to avoid repeated mail.

Add a once-per-24-hour monotonic guard in `notification_service._worker_loop` around `process_due_entra_secret_reminders`; catch errors so delivery processing continues. Trigger a refresh after email settings save only when Entra tenant/client/secret changes, and after a successful Entra test-mail attempt. The API endpoints require administrator and return `public_entra_secret_status` only.

- [ ] **Step 4: Run focused monitor, API, worker and outbox tests**

Run: `python -m pytest -q tests/test_entra_secret_monitor.py tests/test_observability_api.py tests/test_notification_service.py tests/test_notification_outbox.py`

Expected: PASS, with one event per threshold and no secret/token string in any payload.

- [ ] **Step 5: Commit**

```powershell
git add picorgftp_sql/entra_secret_monitor.py picorgftp_sql/notification_service.py picorgftp_sql/web/app.py picorgftp_sql/web_data.py tests/test_entra_secret_monitor.py tests/test_observability_api.py tests/test_notification_service.py
git commit -m "feat: alert on Entra client secret expiry"
```

### Task 5: Render Entra expiry state in mail settings and perform final regression

**Files:**
- Modify: `picorgftp_sql/web/static/app.js:10844-11070`
- Modify: `picorgftp_sql/web/static/app.css` near `.mail-channel-card`
- Test: `tests/test_web_ui_integrity.py`
- Test: `tests/test_web_smoke_ci.py`
- Test: `tests/test_source_integrity.py`

**Interfaces:**
- Consumes: safe response from `GET /api/settings/email/entra-expiry` and refresh response from `POST /api/settings/email/entra-expiry/refresh`.
- Produces: `renderEntraExpiryStatus(status)` and an Entra card with accessible live status and refresh control.

- [ ] **Step 1: Write failing UI source tests**

```python
def test_mail_settings_render_entra_expiry_status_and_refresh_button():
    source = _read("picorgftp_sql/web/static/app.js")
    assert "function renderEntraExpiryStatus" in source
    assert "/api/settings/email/entra-expiry" in source
    assert "Sprawdz teraz" in source
    assert "Application.Read.All" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_web_ui_integrity.py -k "entra_expiry_status"`

Expected: FAIL because no expiry status renderer exists.

- [ ] **Step 3: Add compact status panel and explicit refresh**

```javascript
function renderEntraExpiryStatus(status = {}) {
  const panel = document.createElement("div");
  panel.className = `entra-expiry-status entra-expiry-${status.status || "unknown"}`;
  panel.textContent = status.status === "ok"
    ? `Secret: ${status.credential_name || "bez nazwy"} · wygasa ${formatDateTime(status.expires_at)} · pozostało ${status.remaining_days} dni`
    : status.error_message || "Brak odczytanej daty wygaśnięcia Client Secret.";
  return panel;
}
```

Load the cached public status while rendering the mail tab. `Sprawdź teraz` calls the refresh endpoint, disables itself while pending, then replaces the same panel. For `permission_required`, render an inline instruction naming `Application.Read.All` and admin consent. Do not make a network request merely to render every settings tab refresh.

- [ ] **Step 4: Run UI and smoke regressions**

Run: `python -m pytest -q tests/test_web_ui_integrity.py tests/test_web_smoke_ci.py tests/test_source_integrity.py`

Expected: PASS.

- [ ] **Step 5: Run full verification and commit**

Run: `python -m pytest -q`

Expected: PASS with zero failures.

```powershell
git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py tests/test_web_smoke_ci.py tests/test_source_integrity.py
git commit -m "feat: show Entra secret expiry in mail settings"
```

## Plan Self-Review

- Spec coverage: Task 1 covers compact live/history and removal of default JSON; Task 2 covers one SQLite database and durable state; Task 3 covers Graph access, permission messaging and ambiguity; Task 4 covers daily refresh, critical thresholds, deduplication, outbox and cache; Task 5 covers the mail-settings UI and complete regression.
- Placeholder scan: no TODO/TBD or generic test instructions; each task identifies files, interfaces, failing tests, commands and commit scope.
- Type consistency: the status contract begins in Task 3, persistence in Task 2, monitor/API in Task 4 and UI projection in Task 5. Internal `credential_key_id` is intentionally stripped before Task 5.
