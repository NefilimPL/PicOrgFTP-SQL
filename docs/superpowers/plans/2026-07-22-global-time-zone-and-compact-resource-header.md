# Global Time Zone and Compact Resource Header Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an administrator-controlled IANA display-time-zone setting for the whole web panel, then compact the header and clarify the resource terminology.

**Architecture:** A new normalized `web_display` configuration section stores the selected IANA name. The backend supplies a server-validated IANA catalog; JavaScript uses a central formatter and raw epoch/UTC values. The header layout stays a frontend responsibility.

**Tech Stack:** Python 3.14, FastAPI, `zoneinfo`, JavaScript `Intl.DateTimeFormat`, vanilla HTML/CSS, pytest.

## Global Constraints

- `web_display.time_zone` is global, durable, admin-editable, and defaults to exactly `UTC`.
- Valid values are exactly `UTC` plus the sorted server `zoneinfo.available_timezones()` catalog; invalid input normalizes to `UTC`.
- Browser formatting uses IANA names and date-correct CET/CEST for `Europe/Warsaw`; never persist `CET` or `CEST`.
- Save through the existing authenticated, CSRF-protected settings route.
- Visible timestamps use the central formatter or an explicit duration formatter; do not infer a zone from backend-local display strings.
- Preserve resource-disclosure keyboard/pointer behavior and unavailable-data handling.
- Run pytest with `PYTHONHOME=C:\Users\k.bober\AppData\Local\Programs\Python\Python314`, `C:\Python314\python.exe`, and unique `tmp_test` basetemps.
- Validate JavaScript with `C:\Program Files\nodejs\node.exe --check picorgftp_sql\web\static\app.js`.

---

### Task 1: Persist and expose the IANA display setting

**Files:**
- Modify: `picorgftp_sql/common.py`
- Modify: `picorgftp_sql/config.py`
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/app.py`
- Test: `tests/test_config.py`
- Test: `tests/test_web_data_users.py`
- Test: `tests/test_observability_api.py`

**Interfaces:**
- Produces `WEB_DISPLAY_SETTINGS_KEY = "web_display"`.
- Produces `normalize_web_display_settings(value: object) -> dict[str, str]`.
- Produces `available_display_time_zones() -> list[str]`, returning `UTC` first.
- Produces admin `GET /api/settings/time-zones` with `{"time_zones": ["UTC", ...]}`.
- Produces `settings_snapshot()["web_display"]` and accepts partial `update_settings({"web_display": {"time_zone": value}})`.

- [ ] **Step 1: Write failing tests**

```python
def test_normalize_web_display_settings_accepts_iana_and_falls_back(monkeypatch):
    monkeypatch.setattr(config, "available_display_time_zones", lambda: ["UTC", "Europe/Warsaw"])
    assert config.normalize_web_display_settings({"time_zone": "Europe/Warsaw"}) == {"time_zone": "Europe/Warsaw"}
    assert config.normalize_web_display_settings({"time_zone": "CEST"}) == {"time_zone": "UTC"}

def test_time_zone_catalog_requires_admin(client, admin_headers):
    assert client.get("/api/settings/time-zones").status_code == 401
    payload = client.get("/api/settings/time-zones", headers=admin_headers).json()
    assert payload["time_zones"][0] == "UTC"
    assert "Europe/Warsaw" in payload["time_zones"]
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
$env:PYTHONHOME = 'C:\Users\k.bober\AppData\Local\Programs\Python\Python314'
& 'C:\Python314\python.exe' -m pytest tests/test_config.py tests/test_web_data_users.py tests/test_observability_api.py -k 'web_display or time_zone' -q --basetemp 'tmp_test/time-zone-task1-red'
```

Expected: FAIL for absent key, normalizer, snapshot section, or endpoint.

- [ ] **Step 3: Implement the minimal configuration contract**

```python
WEB_DISPLAY_SETTINGS_KEY = "web_display"

def normalize_web_display_settings(value: object) -> dict[str, str]:
    candidate = value.get("time_zone") if isinstance(value, dict) else None
    name = str(candidate or "UTC").strip()
    return {"time_zone": name if name in available_display_time_zones() else "UTC"}
```

Apply it at every existing config default, SQLite merge, file-load, save, update,
and snapshot boundary. Build the catalog from `zoneinfo.available_timezones()`;
do not expose configuration secrets from the endpoint.

- [ ] **Step 4: Verify GREEN and commit**

Run:

```powershell
$env:PYTHONHOME = 'C:\Users\k.bober\AppData\Local\Programs\Python\Python314'
& 'C:\Python314\python.exe' -m pytest tests/test_config.py tests/test_web_data_users.py tests/test_observability_api.py -q --basetemp 'tmp_test/time-zone-task1-green'
```

Expected: PASS.

```powershell
git add picorgftp_sql/common.py picorgftp_sql/config.py picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_config.py tests/test_web_data_users.py tests/test_observability_api.py
git commit -m "feat: add global display time zone setting"
```

### Task 2: Centralize timestamp formatting and migrate time payloads

**Files:**
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/app.py`
- Test: `tests/test_web_ui_integrity.py`
- Test: `tests/test_source_integrity.py`
- Test: `tests/test_web_data_users.py`

**Interfaces:**
- Consumes `state.settings.web_display.time_zone` and Task 1 catalog endpoint.
- Produces `formatPanelTimestamp(value, { date = true, time = true } = {}) -> string`.
- Produces UTC fallback if the IANA name is invalid in the browser.
- Consumes raw `ts`, epoch, or ISO UTC values; rendering never depends on server-local display strings.

- [ ] **Step 1: Write failing formatter and raw-timestamp tests**

```python
def test_web_ui_uses_the_central_panel_timestamp_formatter() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    assert "function formatPanelTimestamp" in source
    assert "timeZone: selectedPanelTimeZone()" in source
    assert "new Date(eventTime).toLocaleTimeString()" not in source

def test_user_snapshot_keeps_raw_epoch_for_auth_times():
    snapshot = web_data.user_snapshot("admin")
    assert isinstance(snapshot["extension_token_last_used_ts"], (int, float))
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
$env:PYTHONHOME = 'C:\Users\k.bober\AppData\Local\Programs\Python\Python314'
& 'C:\Python314\python.exe' -m pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py tests/test_web_data_users.py -k 'timestamp or time_zone or raw_epoch' -q --basetemp 'tmp_test/time-zone-task2-red'
```

Expected: FAIL for absent formatter and display-only values.

- [ ] **Step 3: Implement formatter, raw values, and catalog-backed settings field**

```javascript
function selectedPanelTimeZone() {
  return String(state.settings?.web_display?.time_zone || "UTC");
}

function formatPanelTimestamp(value, options = {}) {
  const date = coercePanelDate(value);
  if (!date) return "Brak danych";
  const formatterOptions = {
    dateStyle: options.date === false ? undefined : "medium",
    timeStyle: options.time === false ? undefined : "medium",
    timeZone: selectedPanelTimeZone(),
    timeZoneName: "short",
  };
  try { return new Intl.DateTimeFormat("pl-PL", formatterOptions).format(date); }
  catch { return new Intl.DateTimeFormat("pl-PL", { ...formatterOptions, timeZone: "UTC" }).format(date); }
}
```

Use it for health time, resource sample/last-trigger, live logs, PIMcore history,
Entra expiry/auth times, backup history, and user metadata. Preserve elapsed
durations as durations. Add raw epoch/ISO companions before removing a renderer's
dependency on any preformatted local string. Render a searchable full IANA list,
submit only `web_display: { time_zone }`, and rerender timestamp views after save.

- [ ] **Step 4: Verify GREEN and commit**

Run:

```powershell
$env:PYTHONHOME = 'C:\Users\k.bober\AppData\Local\Programs\Python\Python314'
& 'C:\Python314\python.exe' -m pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py tests/test_web_data_users.py tests/test_observability_api.py -q --basetemp 'tmp_test/time-zone-task2-green'
& 'C:\Program Files\nodejs\node.exe' --check picorgftp_sql\web\static\app.js
```

Expected: pytest PASS and Node exit code 0.

```powershell
git add picorgftp_sql/web/static/app.js picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_web_ui_integrity.py tests/test_source_integrity.py tests/test_web_data_users.py tests/test_observability_api.py
git commit -m "feat: format panel timestamps in global time zone"
```

### Task 3: Compact the header and clarify resource details

**Files:**
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `picorgftp_sql/web/static/app.js`
- Test: `tests/test_web_ui_integrity.py`
- Test: `tests/test_source_integrity.py`

**Interfaces:**
- Consumes `formatPanelTimestamp` from Task 2.
- Produces a header with version/location above the title and health/resources in one right-side group.
- Produces labels `Aktywni w ostatnich 3 min`, `Alarm oczekujacy (1. probka)`, and `Alarm aktywny (2 probki)`.

- [ ] **Step 1: Write failing markup and terminology tests**

```python
def test_compact_header_keeps_health_and_resource_indicators_in_one_right_group() -> None:
    markup = INDEX_HTML.read_text(encoding="utf-8")
    assert 'class="header-meta"' in markup
    assert 'class="header-observability"' in markup
    assert markup.index('id="backendHealthStatus"') < markup.index('id="resourceStatus"')

def test_resource_detail_copy_explains_clients_and_latch_stages() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    assert "Aktywni w ostatnich 3 min" in source
    assert "Alarm oczekujacy (1. probka)" in source
    assert "Alarm aktywny (2 probki)" in source
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
$env:PYTHONHOME = 'C:\Users\k.bober\AppData\Local\Programs\Python\Python314'
& 'C:\Python314\python.exe' -m pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py -k 'header or resource or time_zone' -q --basetemp 'tmp_test/time-zone-task3-red'
```

Expected: FAIL for absent groups and labels.

- [ ] **Step 3: Implement compact responsive layout**

```html
<div class="header-meta">
  <span id="versionInfo"></span>
  <span id="serverInfo"></span>
</div>
<div class="header-observability">
  <!-- existing backend-health and resource-status controls -->
</div>
```

Use CSS grid/flex to keep controls in one right-side desktop row and wrap them
below the title on narrow screens. Preserve existing ids, button roles, focus,
Escape, hover, and `hidden` behavior. Render resource dates with the Task 2
formatter and replace only ambiguous labels, not detector data.

- [ ] **Step 4: Bump cache keys, verify GREEN, and commit**

Use one new matching cache query key for `app.css` and `app.js` in `index.html`.

Run:

```powershell
$env:PYTHONHOME = 'C:\Users\k.bober\AppData\Local\Programs\Python\Python314'
& 'C:\Python314\python.exe' -m pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py tests/test_observability_api.py -q --basetemp 'tmp_test/time-zone-task3-green'
& 'C:\Program Files\nodejs\node.exe' --check picorgftp_sql\web\static\app.js
```

Expected: pytest PASS and Node exit code 0.

```powershell
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.css picorgftp_sql/web/static/app.js tests/test_web_ui_integrity.py tests/test_source_integrity.py
git commit -m "feat: compact resource header and labels"
```

### Task 4: Document and verify the complete behavior

**Files:**
- Modify: `docs/web-panel.md`
- Modify: `tests/test_source_integrity.py`

**Interfaces:**
- Consumes Task 1 global setting and Task 2 formatter contract.
- Produces operator documentation for the global IANA/DST behavior.

- [ ] **Step 1: Write the failing documentation assertion**

```python
def test_web_panel_documents_global_iana_time_zone_and_warsaw_dst() -> None:
    guide = WEB_PANEL_DOC.read_text(encoding="utf-8")
    assert "globalna strefa czasu" in guide
    assert "IANA" in guide
    assert "Europe/Warsaw" in guide
    assert "CET/CEST" in guide
```

- [ ] **Step 2: Verify RED, document, then verify release GREEN**

Document that the administrator selects one installation-wide IANA zone, `UTC`
is the safe default, `Europe/Warsaw` follows CET/CEST automatically, and changing
display does not modify stored UTC timestamps, thresholds, or event ordering.
Document the recent-HTTP meaning of `Aktywni w ostatnich 3 min` and the two-sample
alarm stages.

Run:

```powershell
$env:PYTHONHOME = 'C:\Users\k.bober\AppData\Local\Programs\Python\Python314'
& 'C:\Python314\python.exe' -m pytest tests/test_source_integrity.py -k 'time_zone or warsaw' -q --basetemp 'tmp_test/time-zone-task4-red'
& 'C:\Python314\python.exe' -m pytest -q --basetemp 'tmp_test/time-zone-release'
& 'C:\Python314\python.exe' -m compileall -q picorgftp_sql tests PicOrgFTP-SQL-WEB.pyw
& 'C:\Program Files\nodejs\node.exe' --check picorgftp_sql\web\static\app.js
git diff --check
```

Expected: first command fails before documentation, then focused/full pytest,
compileall, Node, and diff check pass after the implementation.

- [ ] **Step 3: Commit documentation and verification**

```powershell
git add docs/web-panel.md tests/test_source_integrity.py
git commit -m "docs: explain global panel time zone"
```

## Plan Self-Review

- Spec coverage: Task 1 covers global persistence/catalog/validation; Task 2 covers all timestamp contracts and formatting; Task 3 covers the compact header and resource terminology; Task 4 covers documentation and release verification.
- Placeholder scan: no open placeholders or unspecified validation actions remain.
- Type consistency: Task 1 defines `web_display.time_zone`, `available_display_time_zones`, and the catalog endpoint consumed by Task 2; Task 2 defines `formatPanelTimestamp` consumed by Task 3.
