# Observability and Detailed History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace text-log-driven UI with structured SQLite events, incidents and durable job timelines, enrich product/Pimcore/file history with exact diffs, and add the live logs tabs plus backend health indicator.

**Architecture:** Add structured operational tables to the existing `picorgftp_sql.sqlite`, expose them through a focused observability service, and keep the existing text files as a best-effort mirror. Processing, Pimcore and exception boundaries emit correlated events; history stores a separate user-facing change set; the web UI consumes cursor APIs and an SSE stream.

**Tech Stack:** Python 3.11+, SQLite, FastAPI/Starlette, browser JavaScript, CSS, pytest/unittest.

## Global Constraints

- Use only the existing `picorgftp_sql.sqlite`; do not create a second database.
- Treat legacy files only as import sources. New observability data is SQLite-only.
- Store timestamps as UTC ISO 8601 and render them in browser-local time.
- Redact secrets before persistence, not only before presentation.
- Keep text logs as a compatibility mirror; do not parse them for the new UI.
- Retain live `info` events for 24 hours. Keep warning/error/critical events and job summaries until an administrator clears operational logs.
- Load alert/job lists in cursor batches of 20; do not add numbered pagination.
- Coalesce identical incidents for 15 minutes.
- Preserve all existing history records and routes during migration.
- Follow test-first red/green/refactor for every behavior change.

---

### Task 1: SQLite Operational Schema and Repository

**Files:**
- Modify: `picorgftp_sql/sqlite_store.py`
- Modify: `picorgftp_sql/sqlite_maintenance.py`
- Modify: `picorgftp_sql/data_store.py`
- Test: `tests/test_sqlite_store.py`
- Test: `tests/test_sqlite_maintenance.py`
- Create: `tests/test_observability_store.py`

**Interfaces:**
- Produces: `SqliteStore.append_operational_event(event: dict[str, object]) -> dict[str, Any]`
- Produces: `SqliteStore.query_operational_events(*, severities=(), username="", ean="", job_id="", module="", query="", after_id="", cursor="", limit=20, since="") -> dict[str, Any]`
- Produces: `SqliteStore.upsert_job_run(job: dict[str, object]) -> dict[str, Any]`
- Produces: `SqliteStore.query_job_runs(*, cursor="", limit=20) -> dict[str, Any]`
- Produces: `SqliteStore.upsert_incident(incident: dict[str, object]) -> dict[str, Any]`
- Produces: `SqliteStore.find_open_incident(fingerprint: str) -> dict[str, Any] | None`
- Produces: `SqliteStore.query_incidents(*, severity="", cursor="", limit=20) -> dict[str, Any]`
- Produces: `SqliteStore.mark_alerts_read(username: str, severity: str, event_id: str, created_at: str) -> None`
- Produces: `SqliteStore.unread_alert_summary(username: str) -> dict[str, object]`
- Produces: `SqliteStore.prune_info_events(before: str) -> int`
- Produces: `SqliteStore.clear_operational_data() -> dict[str, int]`

- [ ] **Step 1: Write failing schema and repository tests**

Add tests that initialize a fresh database and assert schema version `5`, the new tables, cursor ordering, filtering, unread markers and 24-hour pruning:

```python
def test_operational_schema_and_cursor_queries(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.initialize()
    first = store.append_operational_event({
        "id": "evt-1", "created_at": "2026-07-16T10:00:00.000Z",
        "severity": "info", "event_type": "job.started", "module": "process",
        "stage": "prepare", "username": "alice", "ean": "5900000000001",
        "job_id": "job-1", "summary": "Start", "details": {"step": 1},
    })
    store.append_operational_event({
        **first, "id": "evt-2", "created_at": "2026-07-16T10:01:00.000Z",
        "severity": "error", "summary": "FTP failed",
    })

    page = store.query_operational_events(severities=("error",), limit=20)
    assert [item["id"] for item in page["items"]] == ["evt-2"]
    assert page["next_cursor"] == ""
```

Also assert `clear_operational_data()` leaves `web_history` untouched and `normalize_timestamp_columns()` recognizes all new timestamp columns.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_observability_store.py tests/test_sqlite_store.py tests/test_sqlite_maintenance.py -q
```

Expected: FAIL because schema version 5 and repository methods do not exist.

- [ ] **Step 3: Add schema version 5 and tables**

Set `SCHEMA_VERSION = 5` and add these tables and indexes to `SqliteStore.initialize()`:

```sql
CREATE TABLE IF NOT EXISTS operational_events (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    severity TEXT NOT NULL,
    event_type TEXT NOT NULL,
    module TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT '',
    username TEXT NOT NULL DEFAULT '',
    ean TEXT NOT NULL DEFAULT '',
    product_id TEXT NOT NULL DEFAULT '',
    slot TEXT NOT NULL DEFAULT '',
    job_id TEXT NOT NULL DEFAULT '',
    correlation_id TEXT NOT NULL DEFAULT '',
    incident_id TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL,
    recommended_action TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}',
    exception_type TEXT NOT NULL DEFAULT '',
    traceback_text TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS job_runs (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL DEFAULT '',
    ean TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT '',
    stages_json TEXT NOT NULL DEFAULT '[]',
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    severity TEXT NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    first_event_id TEXT NOT NULL,
    latest_event_id TEXT NOT NULL,
    job_id TEXT NOT NULL DEFAULT '',
    correlation_id TEXT NOT NULL DEFAULT '',
    notification_window_at TEXT NOT NULL DEFAULT '',
    context_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS alert_reads (
    username TEXT NOT NULL,
    severity TEXT NOT NULL,
    event_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (username, severity)
);
```

Add indexes for `(created_at, id)`, `(severity, created_at)`, `job_id`,
`correlation_id`, `incidents(fingerprint, last_seen_at)`, and
`job_runs(started_at, id)`.

- [ ] **Step 4: Implement repository methods**

Use parameterized SQL, `_json_dumps`, `_json_loads`, and descending cursor
ordering by `(created_at, id)`. Encode cursors as URL-safe base64 JSON:

```python
def _page_cursor(created_at: object, identity: object) -> str:
    raw = _json_dumps([_text(created_at), _text(identity)]).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

def _decode_page_cursor(value: object) -> tuple[str, str]:
    text = _text(value)
    if not text:
        return "", ""
    padded = text + "=" * (-len(text) % 4)
    payload = _json_loads(base64.urlsafe_b64decode(padded).decode("utf-8"), [])
    if not isinstance(payload, list) or len(payload) != 2:
        return "", ""
    return _text(payload[0]), _text(payload[1])
```

Return event dictionaries with `details`, not `details_json`. Clamp `limit` to
`1..100`. Build dynamic `WHERE` clauses only from fixed column names and bind
all values. Add matching delegators to `SqliteDataStoreAdapter`.

- [ ] **Step 5: Extend maintenance timestamp coverage**

Add the new timestamp columns to `TIMESTAMP_COLUMNS`, including
`operational_events.created_at`, both job timestamps, all incident timestamps,
and `alert_reads.created_at`. Ensure repair initializes version 5 before
`ANALYZE` and `VACUUM`.

- [ ] **Step 6: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add picorgftp_sql/sqlite_store.py picorgftp_sql/sqlite_maintenance.py picorgftp_sql/data_store.py tests/test_observability_store.py tests/test_sqlite_store.py tests/test_sqlite_maintenance.py
git commit -m "feat: add structured observability storage"
```

### Task 2: Event Domain, Redaction and Incident Correlation

**Files:**
- Create: `picorgftp_sql/observability.py`
- Create: `tests/test_observability.py`

**Interfaces:**
- Consumes: Task 1 repository methods.
- Produces: `emit_event(*, severity, event_type, summary, module="", stage="", username="", ean="", product_id="", slot="", job_id="", correlation_id="", recommended_action="", details=None, exception=None) -> dict[str, object]`
- Produces: `record_job(job: dict[str, object]) -> dict[str, object]`
- Produces: `coalesce_incident(event: dict[str, object], now: datetime | None = None) -> dict[str, object] | None`
- Produces: `incident_context(incident: dict[str, object], *, before_limit=5, after_limit=5) -> dict[str, list[dict[str, object]]]`
- Produces: `redact_value(value: object) -> object`
- Produces: `prune_live_events(now: datetime | None = None) -> int`
- Produces: `observability_store() -> SqliteStore`

- [ ] **Step 1: Write failing domain tests**

Cover normalization, redaction at any nesting level, stable fingerprints,
15-minute coalescing, correlation-based before/problem/after context and the
rule that `info` never creates an incident:

```python
def test_emit_event_redacts_before_storage(monkeypatch) -> None:
    fake = FakeStore()
    monkeypatch.setattr(observability, "observability_store", lambda: fake)
    event = observability.emit_event(
        severity="error", event_type="pimcore.update_failed", summary="Failure",
        details={"client_secret": "secret", "nested": {"token": "abc", "safe": 2}},
    )
    assert event["details"] == {
        "client_secret": "[REDACTED]",
        "nested": {"token": "[REDACTED]", "safe": 2},
    }
    assert fake.events[0] == event
```

For incident tests use fixed UTC datetimes at `10:00`, `10:14` and `10:16`;
assert the first two share an incident with `notification_due=False` on the
second occurrence, and the third returns `notification_due=True` while
retaining the same incident identity and incremented count.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_observability.py -q
```

Expected: FAIL because `picorgftp_sql.observability` does not exist.

- [ ] **Step 3: Implement event normalization and redaction**

Create severity constants and redact keys matching
`password|pass|secret|token|authorization|api_key|cookie` case-insensitively.
Cap traceback text at 32 KiB and individual scalar strings at 8 KiB.

```python
SEVERITIES = ("info", "warning", "error", "critical")
SECRET_KEY_RE = re.compile(
    r"password|pass|secret|token|authorization|api[_-]?key|cookie",
    re.IGNORECASE,
)

def redact_value(value: object, key: str = "") -> object:
    if key and SECRET_KEY_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return value[:8192]
    return value
```

`observability_store()` must always resolve
`storage_settings.resolve_sqlite_path()`, initialize that one database, and not
change `data_mode`.

- [ ] **Step 4: Implement incident fingerprinting and coalescing**

Build the fingerprint from event type, module, stage, exception type and
normalized stable context (`ean`, `slot`), never from timestamps or full
messages. Hash with SHA-256. `info` returns `None`.

When a matching open incident exists, update `last_seen_at`, `latest_event_id`,
count and context. A new incident sets `notification_window_at` to now and
returns transient `notification_due=True`. Later occurrences return true only
when at least 15 minutes passed since `notification_window_at`, and then advance
that field. Persist the assigned `incident_id` back on the event; do not store
the transient `notification_due` flag in `operational_events`.

`incident_context()` queries only the incident's `job_id` or `correlation_id`,
orders events chronologically, locates `first_event_id`/`latest_event_id`, and
returns at most five events before, the problem events, and five events after.
It must never pull unrelated events merely because their timestamps are close.

- [ ] **Step 5: Add fallback text logging without recursion**

Allow registration of one best-effort mirror callback. If SQLite persistence
fails, call the mirror with the original event and re-raise only when the
caller explicitly uses `strict=True`; default event emission must not hide the
business exception.

- [ ] **Step 6: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add picorgftp_sql/observability.py tests/test_observability.py
git commit -m "feat: add structured event and incident service"
```

### Task 3: Persist Process Jobs and Capture Backend/Frontend Failures

**Files:**
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/web/static/app.js`
- Test: `tests/test_web_app_files.py`
- Test: `tests/test_web_smoke_ci.py`
- Test: `tests/test_source_integrity.py`

**Interfaces:**
- Consumes: `emit_event`, `record_job` from Task 2.
- Changes: `_process_upload_snapshot(..., job_id: str = "")`.
- Produces route: `POST /api/observability/client-errors` (authenticated).

- [ ] **Step 1: Write failing process correlation tests**

Patch `emit_event` and `record_job`, queue a job, invoke `_run_process_job`, and
assert every emitted stage/result uses the same generated `job_id`. Add route
tests that submit a browser error and verify `critical` emission with redacted
details.

```python
def test_process_job_persists_correlated_result(self) -> None:
    with (
        patch.object(web_app, "_process_upload_snapshot", return_value={
            "timing": {"stages": []}, "ftp": {}, "sql": {},
            "local_delete": {}, "skipped_slots": [],
        }),
        patch.object(web_app, "record_job") as record_job,
    ):
        queued = web_app._queue_process_job(username="alice", cache_scope="x", form=fake_form())
        web_app._run_process_job(queued["job_id"])
    assert record_job.call_args.args[0]["id"] == queued["job_id"]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_web_app_files.py tests/test_web_smoke_ci.py tests/test_source_integrity.py -q
```

Expected: FAIL because jobs are memory-only and the client-error route/listeners
do not exist.

- [ ] **Step 3: Thread `job_id` through processing**

Pass `job_id` from `_run_process_job` to `_process_upload_snapshot`. Emit an
`info` event whenever `mark()` starts a stage. On completion choose severity:

```python
def _result_severity(payload: dict[str, object]) -> str:
    blocking = [
        payload.get("ftp", {}).get("error"),
        payload.get("sql", {}).get("error"),
        *(payload.get("local_delete", {}).get("errors") or []),
    ]
    if any(blocking):
        return "error"
    if payload.get("skipped_slots"):
        return "warning"
    return "info"
```

Validation rejection stays `warning`; inability to complete a required
integration is `error`; unexpected exceptions are `critical`. Persist queued,
running, completed and failed job states with timing stages.

- [ ] **Step 4: Add backend exception capture**

Register an application exception handler for otherwise unhandled exceptions.
Generate a correlation ID, emit `critical`, mirror to `error_log.txt`, and
return status 500 with only the correlation ID and safe message. Do not convert
handled `HTTPException` validation responses into critical events.

- [ ] **Step 5: Add frontend exception capture**

Register `error` and `unhandledrejection` listeners in `app.js`. Send one
authenticated, CSRF-protected payload per unique fingerprint per minute:

```javascript
window.addEventListener("error", (event) => {
  reportClientFailure({
    kind: "error",
    message: event.message || "Frontend error",
    source: event.filename || "",
    line: Number(event.lineno || 0),
    column: Number(event.colno || 0),
    stack: event.error?.stack || "",
  }).catch(() => {});
});
```

The backend redacts and truncates all fields before emitting
`frontend.unhandled_error` as `critical`.

- [ ] **Step 6: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add picorgftp_sql/web/app.py picorgftp_sql/web/static/app.js tests/test_web_app_files.py tests/test_web_smoke_ci.py tests/test_source_integrity.py
git commit -m "feat: correlate jobs and capture application failures"
```

### Task 4: Product, File and Pimcore Change Sets

**Files:**
- Create: `picorgftp_sql/history_changes.py`
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/services/pimcore_service.py`
- Modify: `picorgftp_sql/web/static/app.js`
- Test: `tests/test_history_changes.py`
- Test: `tests/test_pimcore_service.py`
- Test: `tests/test_pimcore_web.py`
- Test: `tests/test_web_app_files.py`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Produces: `field_changes(before: Mapping[str, object] | None, after: Mapping[str, object], labels: Mapping[str, str] | None = None) -> list[dict[str, object]]`
- Produces: `file_changes(existing_photos, saved_files, delete_requests, migrated_prefixes) -> list[dict[str, object]]`
- Produces: `history_change_set(*, existing_entry, saved_entry, existing_photos, saved_files, delete_requests, migrated_prefixes, integrations, pimcore=None) -> dict[str, object]`
- Changes: Pimcore create/update results include a `change_set`.
- Changes: Pimcore template rendering returns per-profile SQL integration results that are forwarded into the create/update audit context.

- [ ] **Step 1: Write failing pure diff tests**

Cover created/updated/unchanged fields and added/replaced/deleted/migrated slots:

```python
def test_file_changes_describe_replacement_with_sizes_and_time() -> None:
    result = file_changes(
        existing_photos=[{"prefix": "03", "filename": "old.png", "path": "old.png", "size_bytes": 900}],
        saved_files=[{
            "prefix": "03", "source_name": "upload.jpg", "filename": "new.png",
            "source_size_bytes": 1200, "size_bytes": 800, "elapsed_ms": 42,
            "operation": "process_image", "content_fit": True,
        }],
        delete_requests=[], migrated_prefixes=[],
    )
    assert result == [{
        "slot": "03", "operation": "replaced", "before_name": "old.png",
        "after_name": "new.png", "source_name": "upload.jpg",
        "before_size_bytes": 900, "source_size_bytes": 1200,
        "after_size_bytes": 800, "elapsed_ms": 42,
        "processing_operation": "process_image", "content_fit": True,
    }]
```

Use `None` for unknown size/name; never invent `0 B`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_history_changes.py tests/test_pimcore_service.py tests/test_pimcore_web.py tests/test_web_app_files.py tests/test_web_ui_integrity.py -q
```

Expected: FAIL because change-set helpers and Pimcore diffs do not exist.

- [ ] **Step 3: Implement pure change-set helpers**

Normalize only for equality checks; preserve display values. Return:

```python
{
    "kind": "created" | "updated" | "synchronized",
    "fields": [{"key": key, "label": label, "before": old, "after": new}],
    "files": [...],
    "integrations": integrations,
    "pimcore": pimcore or {},
}
```

Determine previous file sizes with `os.path.getsize` before processing when a
local path exists. Preserve FTP filename even when local metadata is absent.

- [ ] **Step 4: Capture product/file state before mutation**

In `_process_upload_snapshot`, retain `existing_entry` and `existing_photos`
before saving/deleting. After `save_web_entry`, build `change_set` from those
snapshots plus `_result_payload(result)`, deletion requests, migration prefixes
and integration results. Store it under `details["change_set"]` in the existing
history record and include `job_id` in details.

Do not change the behavior of old history records.

- [ ] **Step 5: Add Pimcore create/update diffs**

In `create_product`, return initial mapped values:

```python
"change_set": {
    "kind": "created",
    "fields": [
        {"key": key, "label": key, "before": None, "after": value}
        for key, value in sorted(values.items())
    ],
}
```

In `update_product`, capture `_configured_values(config, current_data)` before
the PUT and compare it with verified values after the PUT. Return only changed
fields with before/after values. Persist this under both
`details.pimcore_operation` and top-level `details.change_set.pimcore`, so the
operation remains visible in the common EAN history.

- [ ] **Step 6: Preserve additional SQL-profile results used by Pimcore**

Measure every `execute_sql_value_query` call in `_render_templates` and return a
safe `integrations.sql_profiles` list containing `profile_id`, `source`,
`status`, `elapsed_ms`, warning codes and a redacted error. Keep existing
`warnings` unchanged for backward compatibility.

Store the latest render integration context in the Pimcore create/edit form
state and include it in the subsequent create/update request as
`integration_results`. The backend accepts only the expected safe keys,
attaches them to the Pimcore operation report/change set, and does not trust or
persist arbitrary browser objects.

- [ ] **Step 7: Emit integration events from the same results**

Emit one event per completed integration with `job_id`, elapsed time and counts.
Use `error` when the integration was required and returned an error; otherwise
use `info`. Emit one event per additional SQL-profile result from Step 6. Do not
log successful Pimcore lookup checks as warning/error.

- [ ] **Step 8: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add picorgftp_sql/history_changes.py picorgftp_sql/web/app.py picorgftp_sql/web_data.py picorgftp_sql/services/pimcore_service.py picorgftp_sql/web/static/app.js tests/test_history_changes.py tests/test_pimcore_service.py tests/test_pimcore_web.py tests/test_web_app_files.py tests/test_web_ui_integrity.py
git commit -m "feat: record detailed product and Pimcore changes"
```

### Task 5: Observability APIs, SSE and Health Readiness

**Files:**
- Modify: `picorgftp_sql/web/app.py`
- Test: `tests/test_observability_api.py`
- Test: `tests/test_web_smoke_ci.py`

**Interfaces:**
- Produces: `GET /api/observability/events`
- Produces: `GET /api/observability/incidents`
- Produces: `GET /api/observability/jobs`
- Produces: `GET /api/observability/stream?after_id=...`
- Produces: `POST /api/observability/read`
- Changes: `GET /api/health` returns local readiness and last-known integrations.
- Changes: `POST /api/logs/clear` also clears structured operational data but not `web_history`.

- [ ] **Step 1: Write failing authenticated API tests**

Use the existing test client/login helpers. Verify admin-only access, cursor
batch size 20, severity filters, SSE event framing, per-user unread state, clear
semantics and health payload:

```python
def test_health_reports_local_components_and_not_external_failures(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload["components"]) >= {"backend", "sqlite", "job_processor"}
    assert payload["components"]["backend"]["status"] == "online"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_observability_api.py tests/test_web_smoke_ci.py -q
```

Expected: FAIL because observability routes and readiness details do not exist.

- [ ] **Step 3: Implement cursor query endpoints**

Require admin for events/incidents/all jobs. Clamp `limit` to 20 by default and
100 maximum. Return:

```python
{"items": items, "next_cursor": next_cursor, "unread": summary, "server_time": now_iso()}
```

Validate severity against the four known values. Reject malformed cursor input
with HTTP 400 rather than interpolating it into SQL. Enrich each incident with
`incident_context()` so the response contains `before`, `problem` and `after`
arrays from the same job/correlation only.

- [ ] **Step 4: Implement SSE stream**

Use `StreamingResponse(media_type="text/event-stream")`. Poll SQLite for events
after the last ID, emit `id:` and JSON `data:` frames, send a comment heartbeat
every 15 seconds, and stop on `request.is_disconnected()`.

```python
async def stream_events(request: Request, after_id: str = "") -> StreamingResponse:
    _require_admin(request)
    async def generate():
        cursor = after_id
        while not await request.is_disconnected():
            page = observability_store().query_operational_events(after_id=cursor, limit=100)
            for item in reversed(page["items"]):
                cursor = str(item["id"])
                yield f"id: {cursor}\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(generate(), media_type="text/event-stream")
```

- [ ] **Step 5: Extend health readiness**

Check SQLite with `SELECT 1`; check that the process executor is not shut down;
return the last-known FTP/SQL/profile/Pimcore result from recent structured
events without contacting external services on every request. Keep the route
unauthenticated and free of paths, credentials and exception details.

- [ ] **Step 6: Update operational clearing and retention startup**

On startup call `prune_live_events()`. Schedule pruning at most hourly using the
existing scheduler lifecycle pattern. Clearing logs deletes operational events,
incidents, alert reads and job runs plus the existing text files, but never
deletes `web_history` or Pimcore submissions.

- [ ] **Step 7: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add picorgftp_sql/web/app.py tests/test_observability_api.py tests/test_web_smoke_ci.py
git commit -m "feat: expose observability stream and readiness API"
```

### Task 6: Detailed History Changes Modal

**Files:**
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_source_integrity.py`
- Modify: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Consumes: `details.change_set` from Task 4.
- Produces UI: `#historyChangesModal`, `#historyChangesTitle`, `#historyChangesOutput`.

- [ ] **Step 1: Write failing UI integrity tests**

Assert the modal exists, every history item has a `Zmiany` button, old records
show the compatibility message, and file rows render before/after names, sizes
and elapsed time.

```python
def test_history_exposes_detailed_changes_modal(self) -> None:
    assert 'id="historyChangesModal"' in self.html_source
    assert 'changesButton.textContent = "Zmiany"' in self.js_source
    assert "renderHistoryChanges(item)" in self.js_source
    assert "Szczegolowy zapis zmian nie byl jeszcze dostepny" in self.js_source
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_source_integrity.py tests/test_web_ui_integrity.py -q
```

Expected: FAIL because the modal and renderer do not exist.

- [ ] **Step 3: Add semantic modal markup**

Place a nested modal next to `historyTimingModal`. Include a heading, close
button and output container. Reuse existing modal accessibility/focus behavior.

- [ ] **Step 4: Implement safe DOM renderers**

Build nodes with `textContent`; never use raw `innerHTML` for logged values.
Render sections only when data exists:

```javascript
function historyChangeValue(value) {
  if (value === null || value === undefined || value === "") return "Brak danych";
  return String(value);
}

function formatBytes(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "Brak danych";
  const bytes = Math.max(0, Number(value));
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}
```

Show product fields, Pimcore fields, per-slot file cards, integrations and
`job_id`. Disable `Zmiany` only when neither `change_set` nor legacy details
exist.

- [ ] **Step 5: Add styles consistent with history**

Use existing variables and `history-item` spacing. Add a two-column before/after
grid that collapses to one column below 700 px. Highlight additions with
accent, deletions with danger and replacements with warning without animation.

- [ ] **Step 6: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_source_integrity.py tests/test_web_ui_integrity.py
git commit -m "feat: show detailed changes in product history"
```

### Task 7: Logs Tabs, Live Console and Durable Alert Lists

**Files:**
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_source_integrity.py`
- Modify: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Consumes: Task 5 observability endpoints and SSE stream.
- Produces tabs: `live`, `critical`, `error`, `warning`, `jobs`.

- [ ] **Step 1: Write failing logs UI tests**

Assert tab controls, per-severity badges, live controls, `EventSource`, cursor
`Wczytaj więcej`, read markers and absence of the old per-file category loop.

```python
def test_logs_use_tabs_live_stream_and_cursor_loading(self) -> None:
    assert 'data-log-tab="live"' in self.html_source
    assert 'data-log-tab="critical"' in self.html_source
    assert 'new EventSource("/api/observability/stream' in self.js_source
    assert 'logsLoadMoreButton.textContent = "Wczytaj wiecej"' in self.js_source
    assert "for (const log of logs)" not in self.js_source
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_source_integrity.py tests/test_web_ui_integrity.py -q
```

Expected: FAIL because the old renderer groups by source file.

- [ ] **Step 3: Replace logs markup with tabs and controls**

Add filters for text, severity/module/user/EAN/job; live pause/resume and
autoscroll toggles; an alert count badge per tab; output and load-more
containers. Keep refresh and password-protected clear actions.

- [ ] **Step 4: Implement tab state and cursor loading**

Store per-tab `{items, nextCursor, unread}` in `state.observability`. Switching
tabs renders cached items and fetches only when empty. `Wczytaj więcej` appends
and hides when `next_cursor` is empty. Mark a severity read only after its tab
is opened and the first page rendered.

- [ ] **Step 5: Implement live stream lifecycle**

Open `EventSource` only while the logs modal is open and the user is an admin.
On first open, seed the console from `/api/observability/events` with
`since=<UTC now minus 24 hours>`, then continue from the newest event ID through
SSE. Keep at most the last 2,000 DOM-visible live events while SQLite remains
the source for the full 24 hours. Pause stops DOM appends but buffers incoming
items; resume flushes the buffer. Persist autoscroll preference in
`localStorage`.

- [ ] **Step 6: Render incident and job context safely**

Use `textContent`. Cards show summary, recommended action, user/EAN/job,
occurrence count and expandable `before / problem / after` sections. Job cards
render stages and link to the incident or history EAN when identifiers exist.

- [ ] **Step 7: Update alert animation priority**

`critical > error > warning`; `info` never animates. Add a distinct error class
between warning and critical. Use per-user server unread counts, replacing the
old localStorage latest-ID marker.

- [ ] **Step 8: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_source_integrity.py tests/test_web_ui_integrity.py
git commit -m "feat: add live logs and alert tabs"
```

### Task 8: Header Online/Latency Indicator and Final Verification

**Files:**
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_source_integrity.py`
- Modify: `tests/test_web_ui_integrity.py`
- Modify: `docs/web-panel.md`

**Interfaces:**
- Consumes: enhanced `GET /api/health` from Task 5.
- Produces UI: `#backendHealthStatus` next to the application name.

- [ ] **Step 1: Write failing health indicator tests**

Assert header placement, five-sample smoothing, exact thresholds and three
failed polls before offline:

```python
def test_header_contains_smoothed_backend_health_indicator(self) -> None:
    assert 'id="backendHealthStatus"' in self.html_source
    assert "HEALTH_SLOW_MS = 300" in self.js_source
    assert "HEALTH_CRITICAL_MS = 1000" in self.js_source
    assert "HEALTH_OFFLINE_FAILURES = 3" in self.js_source
    assert "healthSamples.slice(-5)" in self.js_source
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_source_integrity.py tests/test_web_ui_integrity.py -q
```

Expected: FAIL because the indicator is absent.

- [ ] **Step 3: Add header markup and accessible tooltip**

Place the indicator beside `PicOrgFTP-SQL Web`. Use a status dot plus text and
an expandable/hover detail panel listing backend, SQLite, job processor and
last-known external components. Include `aria-live="polite"` and do not rely on
color alone.

- [ ] **Step 4: Implement measurement and smoothing**

Measure `performance.now()` around `/api/health`, poll every five seconds, use
the median of the last five successful samples, and classify:

```javascript
function healthLevel(ms, components = {}) {
  if (components.backend?.status !== "online" || components.sqlite?.status === "critical") {
    return "critical";
  }
  if (ms > HEALTH_CRITICAL_MS) return "critical";
  if (ms >= HEALTH_SLOW_MS || Object.values(components).some((item) => item.status === "degraded")) {
    return "slow";
  }
  return "online";
}
```

Set `offline` only after three consecutive fetch failures; reset failure count
on any successful response. Pause polling while the document is hidden and
immediately refresh on visibility return.

- [ ] **Step 5: Document admin behavior**

Update `docs/web-panel.md` with history `Zmiany`, log tabs, 24-hour live
retention, incident grouping, unread priority and health meanings.

- [ ] **Step 6: Run focused and full verification**

Run:

```powershell
python -m pytest tests/test_observability_store.py tests/test_observability.py tests/test_history_changes.py tests/test_observability_api.py tests/test_web_app_files.py tests/test_pimcore_service.py tests/test_pimcore_web.py tests/test_source_integrity.py tests/test_web_ui_integrity.py tests/test_web_smoke_ci.py tests/test_sqlite_store.py tests/test_sqlite_maintenance.py -q
python -m pytest -q
```

Expected: all tests PASS with no warnings introduced by this feature.

- [ ] **Step 7: Inspect final scope and secrets**

Run:

```powershell
git diff --check
rg -n "client_secret|password|authorization|api_key" picorgftp_sql/observability.py picorgftp_sql/web/app.py tests/test_observability.py
git status --short
```

Expected: no whitespace errors; every persisted secret-like test value is
redacted; changes are limited to files listed in this plan.

- [ ] **Step 8: Commit**

```powershell
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_source_integrity.py tests/test_web_ui_integrity.py docs/web-panel.md
git commit -m "feat: show backend health in web header"
```
