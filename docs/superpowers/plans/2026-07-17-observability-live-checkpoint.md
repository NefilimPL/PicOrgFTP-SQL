# Observability Live Checkpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an atomic live snapshot/checkpoint and fix paused refresh, navigation cache, unread ordering, and paused status races.

**Architecture:** SQLite owns the atomic snapshot boundary and returns an opaque ledger event ID. The API exposes it only in explicit live-seed mode, and the browser uses it to start the existing durable SSE feed after applying the snapshot.

**Tech Stack:** Python 3.13, sqlite3, FastAPI, vanilla JavaScript, unittest/pytest.

## Global Constraints

- Keep ordinary `/api/observability/events` pagination at default 20 and maximum 100.
- Never expose the internal stream sequence.
- Preserve admin authorization and password-protected clear behavior.
- Make all production behavior changes test-first.
- Commit all follow-up files once in one focused fix commit.

---

### Task 1: Atomic store snapshot

**Files:**
- Modify: `tests/test_observability_store.py`
- Modify: `picorgftp_sql/sqlite_store.py`

**Interfaces:**
- Produces: `snapshot_operational_event_stream(*, since: str, limit: int = 2000) -> dict[str, Any]` with `items` and `stream_after_id`.

- [ ] Add failing tests for an empty marker, latest surviving window rows, a pruned/tombstone marker, no sequence leakage, and polling more than 100 events inserted after the checkpoint.
- [ ] Run the focused store tests and confirm failures are caused by the missing snapshot method.
- [ ] Implement the single-connection read transaction, bounded 2,000-row query, and chronological output.
- [ ] Run the focused store tests to GREEN.

### Task 2: Explicit API live-seed mode

**Files:**
- Modify: `tests/test_observability_api.py`
- Modify: `picorgftp_sql/web/app.py`

**Interfaces:**
- Consumes: `snapshot_operational_event_stream(since=..., limit=2000)`.
- Produces: `GET /api/observability/events?live_seed=1` response with `items`, `stream_after_id`, `unread`, and `server_time`.

- [ ] Add failing API tests for admin-only live seed, opaque marker/no sequence, and unchanged ordinary limit/cursor behavior.
- [ ] Run the focused API tests and confirm expected failures.
- [ ] Branch the endpoint on `live_seed`, keeping ordinary query validation unchanged.
- [ ] Run focused store/API tests to GREEN.

### Task 3: Browser checkpoint, pause, navigation, and unread races

**Files:**
- Modify: `tests/test_source_integrity.py`
- Modify: `tests/test_web_ui_integrity.py`
- Modify: `picorgftp_sql/web/static/app.js`

**Interfaces:**
- Consumes: live-seed `stream_after_id`.
- Produces: seed-before-stream lifecycle, pause-buffer-only refresh, isolated incident discovery/cache fill, and dispatch-ordered unread updates.

- [ ] Add failing source/UI assertions for `live_seed=1`, `stream_after_id` EventSource URL, removal of stream-first seeding, pause-only buffering/rendering, paused `onopen`, dispatch-time unread generations, and two-phase exact incident navigation.
- [ ] Run the focused source/UI tests and confirm expected failures.
- [ ] Replace paged REST seeding with the atomic seed response and open one stream after the latest generation applies it.
- [ ] Route paused seed/SSE items exclusively through a deduplicated bounded pause buffer and retain paused status text.
- [ ] Allocate unread generations at request dispatch without response-time authoritative increments.
- [ ] Discover incidents in temporary pages, then populate only the actual severity cache with a severity-filtered walk; keep jobs cache/cursor correct.
- [ ] Run focused source/UI tests to GREEN.

### Task 4: Verification and handoff

**Files:**
- Modify: `.superpowers/sdd/task-7-report.md`

- [ ] Run `python -m pytest tests/test_observability_store.py tests/test_observability_api.py tests/test_source_integrity.py tests/test_web_ui_integrity.py -q`.
- [ ] Run `git diff --check` and inspect the complete diff for scope and race regressions.
- [ ] Append RED/GREEN evidence, files, self-review, test results, and remaining concerns to the Task 7 report.
- [ ] Commit all changed files with one focused fix subject and report the full SHA.
