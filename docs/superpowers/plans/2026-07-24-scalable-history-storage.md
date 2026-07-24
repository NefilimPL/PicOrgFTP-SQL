# Scalable History Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make history list and EAN details bounded SQLite queries so history browsing never decodes or renders the entire history per request.

**Architecture:** Add a redacted `web_history_index` next to full `web_history.payload_json` rows. SQLite summary queries group and page index rows; detail queries select one indexed payload page. Legacy JSON keeps a compatible fallback.

**Tech Stack:** Python 3.14, SQLite, FastAPI, vanilla JavaScript, unittest/pytest.

## Global Constraints

- Work directly on `dev`; do not create, switch, merge, or delete branches.
- Preserve authentication, redaction, existing user/search semantics and 2000-record retention.
- Preserve automatic `openModal("history")` loading and abort stale browser requests.
- SQLite summary pages decode zero full payloads; detail pages decode at most 25 payloads.
- Detail pages default to 25; summary pages remain capped at 50 groups.

### Task 1: Add indexed SQLite summary and detail reads

**Files:**

- Modify: `picorgftp_sql/sqlite_store.py:30`, `:591-941`, `:3319-3387`.
- Test: `tests/test_observability_store.py`.

**Interfaces:**

- `history_summary_snapshot(*, user="", query="", page=1, page_size=50) -> dict[str, Any]`.
- `history_group_snapshot(*, ean, user="", query="", page=1, page_size=25) -> dict[str, Any] | None`.

- [ ] Write failing tests for bounded reads.

```python
def test_history_summary_snapshot_uses_index_without_payload_decode(tmp_path, monkeypatch):
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.save_history([_history_record(index) for index in range(60)])
    store.initialize()  # one-time index backfill before measuring hot reads
    monkeypatch.setattr(sqlite_store, "_json_loads", lambda *_: (_ for _ in ()).throw(AssertionError("payload decode")))
    payload = store.history_summary_snapshot(page=2, page_size=50)
    assert payload["page"] == 2
    assert len(payload["groups"]) == 10

def test_history_group_snapshot_decodes_only_requested_page(tmp_path, monkeypatch):
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    store.save_history([_history_record(index, ean="5901") for index in range(60)])
    store.initialize()  # one-time index backfill before measuring hot reads
    calls = 0
    original = sqlite_store._json_loads
    def counted(value, fallback):
        nonlocal calls
        calls += 1
        return original(value, fallback)
    monkeypatch.setattr(sqlite_store, "_json_loads", counted)
    payload = store.history_group_snapshot(ean="5901", page=2, page_size=25)
    assert len(payload["items"]) == calls == 25
    assert payload["total_items"] == 60
    assert payload["total_pages"] == 3
```

- [ ] Verify RED with `uv run --with pytest --with httpx --with-requirements requirements-web.txt pytest tests/test_observability_store.py -k "history_summary_snapshot or history_group_snapshot" -v`.
- [ ] Increase `SCHEMA_VERSION`; create `web_history_index(id, ean, username, product_id, action, summary, entry_json, search_text, created_at)`, plus `(ean, created_at DESC, id DESC)` and `(username, created_at DESC, id DESC)` indexes.
- [ ] Project already-redacted payloads into the index. Its lowercased `search_text` contains EAN, product ID, summary, action, username and scalar `details.entry` values.
- [ ] During `initialize()`, rebuild the index in the open transaction only when its count differs from `web_history`.
- [ ] Make the existing `save_history()` and `append_history()` upsert the matching index row in their current transactions, so a same-count replacement cannot leave stale groups; retention pruning remains Task 2.
- [ ] Use `casefold()` for both projected `search_text` and the query filter, matching the legacy `web_data` search behavior.
- [ ] Query summaries from the index with filters, `GROUP BY ean`, `MAX(created_at)`, latest `entry_json`, `LIMIT ? OFFSET ?`. Query detail-page IDs from the index, join `web_history`, then decode only those payloads.
- [ ] Verify GREEN with the previous pytest command, then commit: `git add picorgftp_sql/sqlite_store.py tests/test_observability_store.py` and `git commit -m "feat: index SQLite history summaries"`.

### Task 2: Keep payloads and indexes atomically synchronized

**Files:**

- Modify: `picorgftp_sql/sqlite_store.py:3336-3387`.
- Modify: `picorgftp_sql/web_data.py:497-540`.
- Test: `tests/test_observability_store.py`, `tests/test_web_data_users.py`.

- [ ] Write failing tests.

```python
def test_append_history_keeps_payload_and_index_at_retention_limit(tmp_path):
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    for index in range(2001):
        store.append_history(_history_record(index, ean=f"590{index:010d}"))
    with store.connection() as conn:
        payload_count = conn.execute("SELECT COUNT(*) FROM web_history").fetchone()[0]
        index_count = conn.execute("SELECT COUNT(*) FROM web_history_index").fetchone()[0]
    assert payload_count == index_count == 2000

def test_record_history_appends_to_sqlite_without_full_history_load():
    store = Mock()
    with patch.object(web_data, "_active_sqlite_store", return_value=store), patch.object(web_data, "_load_history_records", side_effect=AssertionError("full load")):
        web_data.record_history(username="alice", action="save", ean="5901")
    store.append_history.assert_called_once()
```

- [ ] Verify RED with `uv run --with pytest --with httpx --with-requirements requirements-web.txt pytest tests/test_observability_store.py tests/test_web_data_users.py -k "retention_limit or appends_to_sqlite" -v`.
- [ ] Add the 2000-record prune to the already atomic payload/index writes: delete index rows outside newest IDs, then delete matching payload rows.
- [ ] Make `record_history()` return after `sqlite_store.append_history(record)` when SQLite is active.
- [ ] Verify GREEN with the previous command, then commit: `git add picorgftp_sql/sqlite_store.py picorgftp_sql/web_data.py tests/test_observability_store.py tests/test_web_data_users.py` and `git commit -m "fix: append indexed SQLite history directly"`.

### Task 3: Page the detail contract through data and HTTP

**Files:**

- Modify: `picorgftp_sql/web_data.py:623-692`.
- Modify: `picorgftp_sql/web/app.py:5104-5118`.
- Test: `tests/test_web_data_users.py`, `tests/test_observability_api.py`.

- [ ] Write failing contracts.

```python
def test_history_group_snapshot_pages_legacy_records():
    records = [_record(index, ean="5901") for index in range(60)]
    with patch.object(web_data, "_load_history_records", return_value=records):
        payload = web_data.history_group_snapshot(ean="5901", page=2, page_size=25)
    assert len(payload["items"]) == 25
    assert (payload["page"], payload["total_items"], payload["total_pages"]) == (2, 60, 3)

def test_history_details_api_pages_one_ean(api_environment):
    client, _store = api_environment
    _login(client)
    for _ in range(30):
        web_data.record_history(username="alice", action="save", ean="5901")
    response = client.get("/api/history/details?ean=5901&page=2&page_size=25")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 5
    assert response.json()["total_pages"] == 2
```

- [ ] Verify RED with `uv run --with pytest --with httpx --with-requirements requirements-web.txt pytest tests/test_web_data_users.py tests/test_observability_api.py -k "pages_legacy_records or pages_one_ean" -v`.
- [ ] Delegate SQLite snapshots to the new store APIs. In JSON fallback, keep filters/sort, clamp detail pages to 25, slice after filtering and return `total_items`, `page`, `page_size`, `total_pages`.
- [ ] Add `page` and `page_size` to `history_details_api` and pass both to the data layer.
- [ ] Verify GREEN with the previous command, then commit: `git add picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_web_data_users.py tests/test_observability_api.py` and `git commit -m "feat: page history detail responses"`.

### Task 4: Page and bound detail rendering in the browser

**Files:**

- Modify: `picorgftp_sql/web/static/index.html:313-321`.
- Modify: `picorgftp_sql/web/static/app.js:22-28`, `:4880-5055`.
- Test: `tests/test_web_ui_integrity.py` and `tests/test_source_integrity.py` if the static key changes.

- [ ] Write a failing UI test.

```python
def test_history_detail_ui_pages_and_aborts_stale_requests(self):
    source = APP_JS.read_text(encoding="utf-8")
    html = INDEX_HTML.read_text(encoding="utf-8")
    self.assertIn('id="historyDetailPrevButton"', html)
    self.assertIn('id="historyDetailNextButton"', html)
    self.assertIn('page: String(page)', source)
    self.assertIn('page_size: String(state.historyDetailPageSize)', source)
    self.assertIn('historyDetailPrevButton.disabled = page <= 1', source)
    self.assertIn('historyDetailNextButton.disabled = page >= totalPages', source)
```

- [ ] Verify RED with `& 'C:\Users\k.bober\AppData\Local\uv\cache\builds-v0\.tmpsIPEAe\Scripts\python.exe' -m unittest discover -s tests -p test_web_ui_integrity.py -k history_detail_ui_pages -v`.
- [ ] Add previous/next controls and page label below detail output. Store `historyDetailPageSize = 25`; button listeners request the current summary group at adjacent pages.
- [ ] Make `loadHistoryDetails(group, { page = 1 } = {})` send `page` and `page_size`, keep controller race guards, and use a single `DocumentFragment` in `renderHistoryDetails()`.
- [ ] Render page label from `total_items` and `total_pages`; disable boundary buttons.
- [ ] Verify GREEN, then run `node --check picorgftp_sql/web/static/app.js`, the full web/history pytest suite, and `git diff --check`.
- [ ] Run a synthetic 2000-large-payload SQLite probe that prints only timing, response bytes and decode counts. Assert a 50-group summary decodes zero full payloads and a 25-item detail page decodes 25.
- [ ] Commit: `git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js tests/test_web_ui_integrity.py tests/test_source_integrity.py` and `git commit -m "feat: page history details in web UI"`.

## Plan self-review

- Covers index creation/recovery, direct writes, data fallback, API contract, UI and performance proof.
- Every task starts with RED and ends with GREEN verification.
- No task introduces a branch or unrelated refactor.
