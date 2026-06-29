# SQLite Maintenance and Backups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove unsafe default login/SQL values, document SQL placeholders, upgrade SQLite timestamps and file-index segmentation, and add SQLite repair, scheduled backups, backup history, restore, and diff.

**Architecture:** Keep the existing `SqliteStore` and active data-store layer, but add focused shared modules for SQLite maintenance and backups. Web APIs call those modules and the web settings UI renders the new controls. Legacy files remain import-only and are never deleted by repair or backup.

**Tech Stack:** Python stdlib `sqlite3`, `json`, `datetime`, `pathlib`, `shutil`, existing FastAPI web backend, existing static JS/CSS, pytest/unittest.

---

## File Structure

- Modify `picorgftp_sql/web/static/login.html`: remove the hard-coded username value.
- Modify `picorgftp_sql/web/static/login.js`: persist the last successful username in `localStorage`.
- Modify `picorgftp_sql/common.py`: make the default SQL query empty and keep placeholder metadata constants generic.
- Modify `picorgftp_sql/config.py`: preserve existing saved SQL queries but stop substituting hidden defaults for empty queries.
- Modify `picorgftp_sql/services/sql_service.py`: add placeholder metadata and explicit "query not configured" behavior.
- Modify `picorgftp_sql/sqlite_store.py`: schema v3, ISO history timestamps, segment cache rows, index creation, and public segment APIs.
- Modify `picorgftp_sql/file_index.py`: emit ISO `generated_at` and use segment cache APIs when available.
- Create `picorgftp_sql/sqlite_backup.py`: backup configuration, online copy, retention, history, restore, and masked diff.
- Create `picorgftp_sql/sqlite_maintenance.py`: repair flow, integrity check, migrations, timestamp conversion, segment rebuild, analyze/vacuum.
- Modify `picorgftp_sql/storage_settings.py`: load/save backup bootstrap settings and resolve `BACKUP` folder beside `local_settings.json`.
- Modify `picorgftp_sql/data_store.py`: expose file-index segment APIs through SQLite adapter.
- Modify `picorgftp_sql/web_data.py`: include backup settings/history in snapshots and update backup settings.
- Modify `picorgftp_sql/web/app.py`: add admin-only repair, backup, restore, diff, and schedule endpoints; start/stop backup scheduler.
- Modify `picorgftp_sql/web/static/index.html`: add backup history/diff modal containers.
- Modify `picorgftp_sql/web/static/app.js`: render placeholder help, repair/import actions, backup schedule grid, history, restore, and diff.
- Modify `picorgftp_sql/web/static/app.css`: style the schedule grid and backup history/diff modal.
- Modify `picorgftp_sql/app.py`: stop falling back to a production-looking SQL template in desktop settings and SQL paths.
- Add/modify tests under `tests/` as listed per task.

---

### Task 1: Login Last Successful Username

**Files:**
- Modify: `picorgftp_sql/web/static/login.html`
- Modify: `picorgftp_sql/web/static/login.js`
- Test: `tests/test_web_ui_integrity.py`

- [ ] **Step 1: Write failing UI integrity tests**

Append these assertions to `WebUiIntegrityTests.test_login_page_keeps_accessible_login_form` and add a new JS test:

```python
        login_source = LOGIN_HTML.read_text(encoding="utf-8")
        self.assertNotIn('value="admin"', login_source)

    def test_login_js_remembers_last_successful_username(self) -> None:
        source = (ROOT / "picorgftp_sql" / "web" / "static" / "login.js").read_text(encoding="utf-8")

        self.assertIn('LAST_LOGIN_USERNAME_KEY = "picorg-last-login-username"', source)
        self.assertIn("localStorage.getItem(LAST_LOGIN_USERNAME_KEY)", source)
        self.assertIn("localStorage.setItem(LAST_LOGIN_USERNAME_KEY, username)", source)
        self.assertLess(
            source.index("localStorage.setItem(LAST_LOGIN_USERNAME_KEY, username)"),
            source.index('window.location.href = "/"'),
        )
```

- [ ] **Step 2: Run the failing test**

Run: `python -m pytest tests/test_web_ui_integrity.py::WebUiIntegrityTests::test_login_page_keeps_accessible_login_form tests/test_web_ui_integrity.py::WebUiIntegrityTests::test_login_js_remembers_last_successful_username -q`

Expected: FAIL because `login.html` still contains `value="admin"` and `login.js` does not use localStorage.

- [ ] **Step 3: Implement login persistence**

In `login.html`, change:

```html
<input name="username" autocomplete="username" value="admin" required>
```

to:

```html
<input name="username" autocomplete="username" required>
```

In `login.js`, replace the current file with this behavior while keeping the same endpoint:

```javascript
const form = document.querySelector("#loginForm");
const message = document.querySelector("#loginMessage");
const usernameInput = form?.querySelector('[name="username"]');
const LAST_LOGIN_USERNAME_KEY = "picorg-last-login-username";

try {
  const previousUsername = localStorage.getItem(LAST_LOGIN_USERNAME_KEY) || "";
  if (usernameInput && previousUsername) {
    usernameInput.value = previousUsername;
  }
} catch (_error) {
  // Browsers can disable localStorage; login still works without it.
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "";
  const username = String(new FormData(form).get("username") || "").trim();
  const response = await fetch("/api/login", {
    method: "POST",
    headers: { "X-Requested-With": "XMLHttpRequest" },
    body: new FormData(form),
  });
  if (response.ok) {
    try {
      if (username) {
        localStorage.setItem(LAST_LOGIN_USERNAME_KEY, username);
      }
    } catch (_error) {}
    window.location.href = "/";
    return;
  }
  const payload = await response.json().catch(() => ({}));
  message.textContent = payload.detail || "Logowanie nie powiodlo sie.";
});
```

- [ ] **Step 4: Run the test**

Run: `python -m pytest tests/test_web_ui_integrity.py::WebUiIntegrityTests::test_login_page_keeps_accessible_login_form tests/test_web_ui_integrity.py::WebUiIntegrityTests::test_login_js_remembers_last_successful_username -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add picorgftp_sql/web/static/login.html picorgftp_sql/web/static/login.js tests/test_web_ui_integrity.py
git commit -m "feat: remember last web login username"
```

---

### Task 2: Empty SQL Defaults and Placeholder Metadata

**Files:**
- Modify: `picorgftp_sql/common.py`
- Modify: `picorgftp_sql/config.py`
- Modify: `picorgftp_sql/services/sql_service.py`
- Modify: `picorgftp_sql/app.py`
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/web/static/app.js`
- Test: `tests/test_config.py`
- Test: `tests/test_sql_service.py`
- Test: `tests/test_source_integrity.py`

- [ ] **Step 1: Write failing config and source tests**

Add to `tests/test_config.py`:

```python
from picorgftp_sql import common


class DefaultConfigSafetyTests(unittest.TestCase):
    def test_default_sql_query_is_empty_and_contains_no_production_url(self) -> None:
        self.assertEqual(common.DEFAULT_CONFIG["sql_query"], "")
        self.assertEqual(common.SQL_UPDATE_TEMPLATE, "")
        self.assertNotIn("xml.wipmebgroup.pl", repr(common.DEFAULT_CONFIG))
        self.assertNotIn("object_query_1", repr(common.DEFAULT_CONFIG))
```

Add to `tests/test_source_integrity.py`:

```python
    def test_web_sql_settings_show_placeholder_help(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "picorgftp_sql" / "web" / "static" / "app.js").read_text(encoding="utf-8")
        sql_start = source.index("function renderSettingsSql")
        slots_start = source.index("function renderSettingsSlots", sql_start)
        sql_body = source[sql_start:slots_start]

        self.assertIn("sqlPlaceholderHelp", source)
        self.assertIn("{ean}", sql_body)
        self.assertIn("{filename}", sql_body)
        self.assertIn("{col}", sql_body)
        self.assertIn("{column}", sql_body)
```

- [ ] **Step 2: Write failing SQL service tests**

Add to `tests/test_sql_service.py`:

```python
from picorgftp_sql.services.sql_service import sql_placeholder_metadata


    def test_empty_sql_query_is_not_configured_for_column_detection(self) -> None:
        result = detect_available_columns({"sql_query": "", "db_type": "mysql"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["columns"], [])
        self.assertEqual(result["table"], "")
        self.assertIn("nie skonfigurowano", result["message"].lower())

    def test_placeholder_metadata_lists_supported_tokens(self) -> None:
        placeholders = sql_placeholder_metadata()
        tokens = {item["token"] for item in placeholders}

        self.assertEqual(tokens, {"{ean}", "{filename}", "{col}", "{column}"})
```

- [ ] **Step 3: Run failing tests**

Run: `python -m pytest tests/test_config.py tests/test_sql_service.py::SqlServiceTests::test_empty_sql_query_is_not_configured_for_column_detection tests/test_sql_service.py::SqlServiceTests::test_placeholder_metadata_lists_supported_tokens tests/test_source_integrity.py::SourceIntegrityTests::test_web_sql_settings_show_placeholder_help -q`

Expected: FAIL because defaults and placeholder metadata still use the old behavior.

- [ ] **Step 4: Update defaults and config persistence**

In `picorgftp_sql/common.py`, change `SQL_UPDATE_TEMPLATE` to an empty string and keep `DEFAULT_CONFIG["sql_query"]` pointing to it:

```python
SQL_UPDATE_TEMPLATE = ""
```

In `picorgftp_sql/config.py`, update `save_config()` so it stores the provided query as-is:

```python
w: config.get(w, ""),
```

Audit `load_config()` and `_merge_raw_config()` to keep using persisted `raw_config.get(w, config_copy[w])`, which preserves saved queries without adding a hidden default.

- [ ] **Step 5: Update SQL service no-query behavior**

In `picorgftp_sql/services/sql_service.py`, add:

```python
def configured_sql_query(config_dict):
    return str(config_dict.get(w, "") or "").strip()


def sql_placeholder_metadata():
    return [
        {"token": "{ean}", "description": "Aktualny EAN produktu uzywany w WHERE."},
        {"token": "{filename}", "description": "Nazwa wygenerowanego pliku zdjecia."},
        {"token": "{col}", "description": "Kolumna SQL przypisana do slotu."},
        {"token": "{column}", "description": "Alias dla {col}."},
    ]
```

Change `detect_available_columns()`:

```python
template = configured_sql_query(config_dict)
if not template:
    return {
        "ok": False,
        "columns": [],
        "table": "",
        "preview": "",
        "message": "Nie skonfigurowano zapytania SQL.",
    }
```

Change `extract_presence_context()` to return `None` when `configured_sql_query(config_dict)` is empty instead of falling back to `SQL_UPDATE_TEMPLATE`.

- [ ] **Step 6: Update desktop and web fallback sites**

In `picorgftp_sql/app.py` and `picorgftp_sql/web/app.py`, replace `D.get(w, SQL_UPDATE_TEMPLATE)` / `config.CONFIG.get(w, SQL_UPDATE_TEMPLATE) or SQL_UPDATE_TEMPLATE` patterns with `D.get(w, "")` or `config.CONFIG.get(w, "")`. When a query is required and empty, skip the operation with the existing user-facing status/error pattern.

- [ ] **Step 7: Render placeholder help in web settings**

In `picorgftp_sql/web/static/app.js`, add:

```javascript
function sqlPlaceholderHelp() {
  const wrapper = document.createElement("div");
  wrapper.className = "settings-note sql-placeholder-help";
  const items = [
    ["{ean}", "EAN aktualnego produktu"],
    ["{filename}", "Nazwa wygenerowanego pliku"],
    ["{col}", "Kolumna SQL przypisana do slotu"],
    ["{column}", "Alias dla {col}"],
  ];
  wrapper.append("Dostepne placeholdery SQL: ");
  for (const [token, label] of items) {
    const code = document.createElement("code");
    code.textContent = token;
    wrapper.append(code, ` ${label}; `);
  }
  return wrapper;
}
```

In `renderSettingsSql()`, add `sqlPlaceholderHelp()` in the `"Tryb SQL"` group next to `inputField("query", ...)`.

- [ ] **Step 8: Run tests**

Run: `python -m pytest tests/test_config.py tests/test_sql_service.py tests/test_source_integrity.py -q`

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add picorgftp_sql/common.py picorgftp_sql/config.py picorgftp_sql/services/sql_service.py picorgftp_sql/app.py picorgftp_sql/web/app.py picorgftp_sql/web/static/app.js tests/test_config.py tests/test_sql_service.py tests/test_source_integrity.py
git commit -m "feat: remove default sql query and show placeholders"
```

---

### Task 3: SQLite ISO History Timestamps and Schema v3

**Files:**
- Modify: `picorgftp_sql/sqlite_store.py`
- Test: `tests/test_sqlite_store.py`

- [ ] **Step 1: Write failing migration and roundtrip tests**

Add to `tests/test_sqlite_store.py`:

```python
import json


def test_web_history_schema_uses_iso_created_at(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()
    store.save_history([
        {
            "id": "hist-1",
            "ts": 1782392554.3,
            "time": "2026-06-25 13:02:34",
            "user": "admin",
            "ean": "5901234567890",
        }
    ])

    with sqlite3.connect(tmp_path / "data.sqlite") as conn:
        columns = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(web_history)")}
        row = conn.execute("SELECT created_at, payload_json FROM web_history WHERE id = 'hist-1'").fetchone()

    assert columns["created_at"].upper() == "TEXT"
    assert isinstance(row[0], str)
    assert row[0].endswith("Z")
    assert "T" in row[0]
    payload = json.loads(row[1])
    assert payload["created_at"] == row[0]


def test_migration_converts_legacy_web_history_ts_real(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_version (version INTEGER NOT NULL, applied_at TEXT NOT NULL);
            INSERT INTO schema_version VALUES (2, '2026-06-25T12:00:00.000Z');
            CREATE TABLE web_history (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, ts REAL NOT NULL);
            INSERT INTO web_history VALUES (
                'hist-1',
                '{"id":"hist-1","ts":1782392554.3,"user":"admin","ean":"5901234567890"}',
                1782392554.3
            );
            """
        )

    store = SqliteStore(str(db_path))
    store.initialize()

    with sqlite3.connect(db_path) as conn:
        columns = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(web_history)")}
        row = conn.execute("SELECT created_at, payload_json FROM web_history WHERE id = 'hist-1'").fetchone()

    assert "created_at" in columns
    assert row[0].endswith("Z")
    payload = json.loads(row[1])
    assert payload["created_at"] == row[0]
    assert isinstance(payload["ts"], str)
    assert payload["ts"].endswith("Z")
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_sqlite_store.py::test_web_history_schema_uses_iso_created_at tests/test_sqlite_store.py::test_migration_converts_legacy_web_history_ts_real -q`

Expected: FAIL because `web_history` still uses `ts REAL`.

- [ ] **Step 3: Implement ISO helpers and schema v3**

In `sqlite_store.py`, set:

```python
SCHEMA_VERSION = 3
```

Add helpers:

```python
def _iso_from_timestamp(value: object) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z") and "T" in text:
            return text
        try:
            value = float(text)
        except (TypeError, ValueError):
            return _now_iso()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _now_iso()
    return datetime.fromtimestamp(number, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _history_created_at(payload: dict[str, object]) -> str:
    return _iso_from_timestamp(payload.get("created_at") or payload.get("ts") or payload.get("time"))
```

Change the create schema for `web_history`:

```sql
CREATE TABLE IF NOT EXISTS web_history (
    id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

- [ ] **Step 4: Add migration for legacy `ts REAL`**

In `initialize()`, after base `CREATE TABLE IF NOT EXISTS`, inspect `PRAGMA table_info(web_history)`. If `ts` exists and `created_at` does not:

```python
conn.execute("ALTER TABLE web_history RENAME TO web_history_legacy_ts")
conn.execute(
    """
    CREATE TABLE web_history (
        id TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """
)
for row in conn.execute("SELECT id, payload_json, ts FROM web_history_legacy_ts").fetchall():
    payload = _json_loads(row["payload_json"], {})
    if not isinstance(payload, dict):
        payload = {}
    created_at = _iso_from_timestamp(payload.get("created_at") or payload.get("ts") or row["ts"])
    payload["created_at"] = created_at
    payload["ts"] = created_at
    conn.execute(
        "INSERT INTO web_history (id, payload_json, created_at) VALUES (?, ?, ?)",
        (row["id"], _json_dumps(payload), created_at),
    )
conn.execute("DROP TABLE web_history_legacy_ts")
```

Add:

```sql
CREATE INDEX IF NOT EXISTS idx_web_history_created_at ON web_history(created_at);
CREATE INDEX IF NOT EXISTS idx_product_entries_ean ON product_entries(ean);
CREATE INDEX IF NOT EXISTS idx_product_entries_identity ON product_entries(name, type_name, model);
CREATE INDEX IF NOT EXISTS idx_app_config_values_updated_at ON app_config_values(updated_at);
```

- [ ] **Step 5: Update history load/save methods**

Change `load_history()` to order by `created_at, rowid`. Change `save_history()` and `append_history()` to calculate `created_at`, store it in the JSON payload, set `payload["ts"] = created_at`, and insert into the new column.

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_sqlite_store.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add picorgftp_sql/sqlite_store.py tests/test_sqlite_store.py
git commit -m "feat: store sqlite history timestamps as iso text"
```

---

### Task 4: Segmented SQLite File Index Cache

**Files:**
- Modify: `picorgftp_sql/sqlite_store.py`
- Modify: `picorgftp_sql/data_store.py`
- Modify: `picorgftp_sql/file_index.py`
- Test: `tests/test_sqlite_store.py`
- Test: `tests/test_file_index.py`

- [ ] **Step 1: Write failing tests for segment rows**

Add to `tests/test_sqlite_store.py`:

```python
def test_file_index_segments_are_saved_by_name_prefix(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()
    snapshot = {
        "version": 1,
        "root": "C:/photos",
        "generated_at": "2026-06-25T13:02:34.300Z",
        "names": ["LUNA", "MAGGIORE"],
        "types": {"LUNA": ["SZAFKA"], "MAGGIORE": ["KOMODA"]},
        "models": {},
        "colors": {},
        "extras": {},
        "files": {},
    }

    store.save_file_index_cache(snapshot)

    with sqlite3.connect(tmp_path / "data.sqlite") as conn:
        rows = conn.execute(
            """
            SELECT segment_key, section, lookup_key, payload_json
            FROM file_index_segments
            ORDER BY segment_key, section, lookup_key
            """
        ).fetchall()

    assert ("L", "names", "LUNA", '"LUNA"') in rows
    assert ("M", "names", "MAGGIORE", '"MAGGIORE"') in rows
```

Add to `tests/test_file_index.py`:

```python
    def test_sqlite_cache_store_writes_iso_generated_at_and_segments(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "_ZDJECIA PRZEROBIONE_"
            product_dir = root / "MAGGIORE" / "KOMODA" / "MA03" / "BIALY" / "NO-LED"
            product_dir.mkdir(parents=True)
            (product_dir / "5901234567890_01_MAIN.jpg").write_text("a", encoding="utf-8")
            sqlite_store = SqliteStore(str(base / "data.sqlite"))

            index = LocalFileIndex(str(root), str(base / "file_index.json"), cache_store=sqlite_store)
            self.assertTrue(index.refresh_sync())
            snapshot = sqlite_store.load_file_index_cache()

            self.assertIsInstance(snapshot["generated_at"], str)
            self.assertIn("T", snapshot["generated_at"])
            self.assertTrue(snapshot["generated_at"].endswith("Z"))
            self.assertEqual(sqlite_store.load_file_index_segment("M", "names", "MAGGIORE"), "MAGGIORE")
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_sqlite_store.py::test_file_index_segments_are_saved_by_name_prefix tests/test_file_index.py::LocalFileIndexTests::test_sqlite_cache_store_writes_iso_generated_at_and_segments -q`

Expected: FAIL because `file_index_segments` and segment APIs do not exist.

- [ ] **Step 3: Implement segment schema and APIs**

In `sqlite_store.initialize()`, add:

```sql
CREATE TABLE IF NOT EXISTS file_index_segments (
    segment_key TEXT NOT NULL,
    section TEXT NOT NULL,
    lookup_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (segment_key, section, lookup_key)
);
CREATE INDEX IF NOT EXISTS idx_file_index_segments_lookup
    ON file_index_segments(segment_key, section, lookup_key);
CREATE INDEX IF NOT EXISTS idx_file_index_segments_updated_at
    ON file_index_segments(updated_at);
```

Add helpers:

```python
def _segment_key(value: object) -> str:
    text = _upper(value)
    for ch in text:
        if ch.isalnum():
            return ch if ch.isascii() else "_"
    return "_"
```

Add methods:

```python
def save_file_index_segments(self, snapshot: dict[str, object]) -> int:
    self.initialize()
    generated_at = _iso_from_timestamp(snapshot.get("generated_at"))
    rows = []
    for name in snapshot.get("names", []) if isinstance(snapshot.get("names"), list) else []:
        rows.append((_segment_key(name), "names", _upper(name), name))
    for section in ("types", "models", "colors", "extras", "files"):
        section_payload = snapshot.get(section, {})
        if not isinstance(section_payload, dict):
            continue
        for lookup_key, value in section_payload.items():
            segment = _segment_key(str(lookup_key).split("\x1f", 1)[0])
            rows.append((segment, section, str(lookup_key), value))
    with self.connection() as conn:
        conn.execute("DELETE FROM file_index_segments")
        for segment, section, lookup_key, value in rows:
            conn.execute(
                """
                INSERT INTO file_index_segments
                    (segment_key, section, lookup_key, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (segment, section, lookup_key, _json_dumps(value), generated_at),
            )
    return len(rows)


def load_file_index_segment(self, segment_key: str, section: str, lookup_key: str):
    self.initialize()
    with self.connection() as conn:
        row = conn.execute(
            """
            SELECT payload_json FROM file_index_segments
            WHERE segment_key = ? AND section = ? AND lookup_key = ?
            """,
            (_text(segment_key) or "_", _text(section), _text(lookup_key)),
        ).fetchone()
    if not row:
        return None
    return _json_loads(row["payload_json"], None)
```

In `save_file_index_cache()`, normalize `generated_at` to ISO and call `save_file_index_segments()`.

- [ ] **Step 4: Wire active data store and file index**

In `data_store.SqliteDataStoreAdapter`, add methods `save_file_index_segments()` and `load_file_index_segment()`.

In `file_index._build_snapshot()`, replace numeric `time.time()` for `generated_at` with an injected ISO helper or:

```python
from datetime import datetime, timezone

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
```

Update `file_index_status()` in `web_data.py` later if needed to parse ISO strings; Task 8 covers the web-friendly label.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_sqlite_store.py tests/test_file_index.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add picorgftp_sql/sqlite_store.py picorgftp_sql/data_store.py picorgftp_sql/file_index.py tests/test_sqlite_store.py tests/test_file_index.py
git commit -m "feat: segment sqlite file index cache"
```

---

### Task 5: SQLite Backup Core

**Files:**
- Create: `picorgftp_sql/sqlite_backup.py`
- Modify: `picorgftp_sql/storage_settings.py`
- Test: `tests/test_sqlite_backup.py`

- [ ] **Step 1: Write failing backup tests**

Create `tests/test_sqlite_backup.py`:

```python
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from picorgftp_sql import sqlite_backup, storage_settings


def _create_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL, applied_at TEXT NOT NULL)")
        conn.execute("INSERT INTO schema_version VALUES (3, '2026-06-25T13:02:34.300Z')")
        conn.execute("CREATE TABLE app_config_values (path TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL)")
        conn.execute("INSERT INTO app_config_values VALUES ('database.query', '\"secret query\"', '2026-06-25T13:02:34.300Z')")


def test_backup_creates_sqlite_copy_and_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "data.sqlite"
    backup_dir = tmp_path / "BACKUP"
    _create_db(db_path)

    result = sqlite_backup.create_backup(str(db_path), str(backup_dir), reason="manual", now=datetime(2026, 6, 25, 13, 2, 34, tzinfo=timezone.utc))

    assert result["ok"] is True
    backup_path = Path(result["backup_path"])
    meta_path = backup_path.with_suffix(".json")
    assert backup_path.exists()
    assert meta_path.exists()
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    assert metadata["reason"] == "manual"
    assert metadata["schema_version"] == 3


def test_backup_retention_keeps_newest_manual_and_scheduled(tmp_path: Path) -> None:
    backup_dir = tmp_path / "BACKUP"
    backup_dir.mkdir()
    for index in range(4):
        db = backup_dir / f"picorgftp_sql-20260625-130{index}00-manual.sqlite"
        db.write_text("x", encoding="utf-8")
        db.with_suffix(".json").write_text(json.dumps({"created_at": f"2026-06-25T13:0{index}:00.000Z", "reason": "manual"}), encoding="utf-8")

    removed = sqlite_backup.enforce_retention(str(backup_dir), max_copies=2)

    assert removed["removed"] == 2
    remaining = sorted(path.name for path in backup_dir.glob("*.sqlite"))
    assert remaining == [
        "picorgftp_sql-20260625-130200-manual.sqlite",
        "picorgftp_sql-20260625-130300-manual.sqlite",
    ]


def test_backup_settings_roundtrip(tmp_path: Path) -> None:
    settings_path = tmp_path / "local_settings.json"
    with patch.object(storage_settings.settings, "BASE_DIR_SETTINGS_PATH", str(settings_path)):
        saved = storage_settings.save_backup_settings({"enabled": True, "days": ["mon"], "hours": [8, 13], "max_copies": 4})
        loaded = storage_settings.load_backup_settings()

    assert saved["enabled"] is True
    assert loaded["days"] == ["mon"]
    assert loaded["hours"] == [8, 13]
    assert loaded["max_copies"] == 4
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_sqlite_backup.py -q`

Expected: FAIL because `sqlite_backup.py` and backup settings helpers do not exist.

- [ ] **Step 3: Implement backup settings in `storage_settings.py`**

Add constants and functions:

```python
BACKUP_SETTINGS_KEY = "sqlite_backup"
BACKUP_DEFAULTS = {
    "enabled": False,
    "days": [],
    "hours": [],
    "max_copies": 10,
    "last_run_slots": [],
}


def _normalize_backup_settings(raw: object) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    days = [str(day).lower() for day in payload.get("days", []) if str(day).lower() in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}]
    hours = sorted({max(0, min(23, int(hour))) for hour in payload.get("hours", [])})
    try:
        max_copies = max(1, min(999, int(payload.get("max_copies", 10))))
    except (TypeError, ValueError):
        max_copies = 10
    return {
        "enabled": bool(payload.get("enabled", False)),
        "days": days,
        "hours": hours,
        "max_copies": max_copies,
        "last_run_slots": [str(item) for item in payload.get("last_run_slots", []) if str(item).strip()],
    }


def load_backup_settings() -> dict[str, Any]:
    data = load_bootstrap_settings()
    return _normalize_backup_settings(data.get(BACKUP_SETTINGS_KEY, BACKUP_DEFAULTS))


def save_backup_settings(updates: dict[str, object]) -> dict[str, Any]:
    settings_payload = _normalize_backup_settings(updates)
    save_bootstrap_settings({BACKUP_SETTINGS_KEY: settings_payload})
    return settings_payload


def resolve_backup_dir() -> str:
    return str(_settings_path().resolve().parent / "BACKUP")
```

- [ ] **Step 4: Implement `sqlite_backup.py`**

Create the module with:

```python
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _backup_name(now: datetime, reason: str) -> str:
    safe_reason = "".join(ch for ch in str(reason or "manual").lower() if ch.isalnum() or ch in {"-", "_"}) or "manual"
    return f"picorgftp_sql-{now.astimezone(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{safe_reason}.sqlite"


def _schema_version(path: str) -> int:
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()
        return int(row[0] or 0) if row else 0
    except Exception:
        return 0


def _integrity_check(path: str) -> str:
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0] if row else "")
    except Exception as exc:
        return str(exc)


def create_backup(source_path: str, backup_dir: str, *, reason: str = "manual", now: datetime | None = None) -> dict[str, Any]:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(str(source))
    timestamp = now or datetime.now(timezone.utc)
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / _backup_name(timestamp, reason)
    method = "sqlite_backup"
    try:
        with sqlite3.connect(str(source)) as src, sqlite3.connect(str(target)) as dst:
            src.backup(dst)
    except sqlite3.Error:
        method = "raw_copy"
        target.write_bytes(source.read_bytes())
    metadata = {
        "source_path": str(source),
        "backup_path": str(target),
        "created_at": now_iso(timestamp),
        "reason": reason,
        "size_bytes": target.stat().st_size,
        "schema_version": _schema_version(str(target)),
        "integrity_check": _integrity_check(str(target)),
        "method": method,
    }
    target.with_suffix(".json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, **metadata}


def list_backups(backup_dir: str) -> list[dict[str, Any]]:
    items = []
    for db_path in Path(backup_dir).glob("*.sqlite"):
        meta_path = db_path.with_suffix(".json")
        metadata: dict[str, Any] = {}
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                metadata = {}
        metadata.setdefault("backup_path", str(db_path))
        metadata.setdefault("created_at", "")
        metadata.setdefault("reason", "")
        metadata.setdefault("size_bytes", db_path.stat().st_size)
        items.append(metadata)
    return sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def enforce_retention(backup_dir: str, max_copies: int) -> dict[str, Any]:
    keep = max(1, int(max_copies or 1))
    candidates = [item for item in list_backups(backup_dir) if item.get("reason") in {"manual", "scheduled"}]
    remove = candidates[keep:]
    removed = 0
    for item in remove:
        db_path = Path(str(item["backup_path"]))
        for path in (db_path, db_path.with_suffix(".json")):
            try:
                path.unlink()
                removed += 1 if path.suffix == ".sqlite" else 0
            except FileNotFoundError:
                pass
    return {"removed": removed}
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_sqlite_backup.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add picorgftp_sql/sqlite_backup.py picorgftp_sql/storage_settings.py tests/test_sqlite_backup.py
git commit -m "feat: add sqlite backup core"
```

---

### Task 6: SQLite Repair Core

**Files:**
- Create: `picorgftp_sql/sqlite_maintenance.py`
- Modify: `picorgftp_sql/sqlite_store.py`
- Test: `tests/test_sqlite_maintenance.py`

- [ ] **Step 1: Write failing repair tests**

Create `tests/test_sqlite_maintenance.py`:

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from picorgftp_sql.sqlite_maintenance import repair_sqlite_database
from picorgftp_sql.sqlite_store import SqliteStore


def test_repair_creates_backup_and_migrates_legacy_history(tmp_path: Path) -> None:
    db_path = tmp_path / "data.sqlite"
    backup_dir = tmp_path / "BACKUP"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_version (version INTEGER NOT NULL, applied_at TEXT NOT NULL);
            INSERT INTO schema_version VALUES (2, '2026-06-25T12:00:00.000Z');
            CREATE TABLE web_history (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, ts REAL NOT NULL);
            INSERT INTO web_history VALUES ('hist-1', '{"id":"hist-1","ts":1782392554.3,"user":"admin"}', 1782392554.3);
            """
        )

    result = repair_sqlite_database(str(db_path), str(backup_dir))

    assert result["ok"] is True
    assert Path(result["backup"]["backup_path"]).exists()
    assert result["integrity_check"] == "ok"
    assert result["schema_version"] >= 3
    payload = SqliteStore(str(db_path)).load_history()[0]
    assert payload["created_at"].endswith("Z")


def test_repair_preserves_config_and_user_data(tmp_path: Path) -> None:
    db_path = tmp_path / "data.sqlite"
    store = SqliteStore(str(db_path))
    store.initialize()
    store.save_config({"sql_query": "UPDATE product SET img = {filename}", "db_type": "mysql"})
    store.save_users([{"username": "admin", "password_hash": "hash", "role": "admin"}])

    result = repair_sqlite_database(str(db_path), str(tmp_path / "BACKUP"))

    repaired = SqliteStore(str(db_path))
    assert result["ok"] is True
    assert repaired.load_config()["sql_query"] == "UPDATE product SET img = {filename}"
    assert repaired.load_users()[0]["username"] == "admin"
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_sqlite_maintenance.py -q`

Expected: FAIL because `sqlite_maintenance.py` does not exist.

- [ ] **Step 3: Implement maintenance module**

Create `picorgftp_sql/sqlite_maintenance.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .sqlite_backup import create_backup
from .sqlite_store import SCHEMA_VERSION, SqliteStore


def integrity_check(database_path: str) -> str:
    with sqlite3.connect(database_path) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0] if row else "")


def current_schema_version(database_path: str) -> int:
    try:
        with sqlite3.connect(database_path) as conn:
            row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()
        return int(row[0] or 0) if row else 0
    except sqlite3.Error:
        return 0


def rebuild_file_index_segments(store: SqliteStore) -> int:
    snapshot = store.load_file_index_cache()
    if not snapshot:
        return 0
    return store.save_file_index_segments(snapshot)


def repair_sqlite_database(database_path: str, backup_dir: str) -> dict[str, Any]:
    db_path = Path(database_path)
    if not db_path.exists():
        raise FileNotFoundError(str(db_path))
    backup = create_backup(str(db_path), backup_dir, reason="pre-repair")
    check = integrity_check(str(db_path))
    if check.lower() != "ok":
        return {"ok": False, "backup": backup, "integrity_check": check, "schema_version": current_schema_version(str(db_path)), "warnings": ["integrity_check_failed"]}
    before_version = current_schema_version(str(db_path))
    store = SqliteStore(str(db_path))
    store.initialize()
    segments = rebuild_file_index_segments(store)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("ANALYZE")
        conn.execute("VACUUM")
    return {
        "ok": True,
        "backup": backup,
        "integrity_check": "ok",
        "schema_version": current_schema_version(str(db_path)),
        "previous_schema_version": before_version,
        "target_schema_version": SCHEMA_VERSION,
        "segments_rebuilt": segments,
        "warnings": [],
    }
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_sqlite_maintenance.py tests/test_sqlite_store.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add picorgftp_sql/sqlite_maintenance.py picorgftp_sql/sqlite_store.py tests/test_sqlite_maintenance.py
git commit -m "feat: add sqlite repair workflow"
```

---

### Task 7: Backup Schedule Logic

**Files:**
- Modify: `picorgftp_sql/sqlite_backup.py`
- Modify: `picorgftp_sql/storage_settings.py`
- Test: `tests/test_sqlite_backup.py`

- [ ] **Step 1: Write failing schedule tests**

Add to `tests/test_sqlite_backup.py`:

```python
def test_due_schedule_slots_respects_day_hour_and_last_run() -> None:
    now = datetime(2026, 6, 22, 8, 15, tzinfo=timezone.utc)  # Monday
    settings_payload = {
        "enabled": True,
        "days": ["mon", "tue"],
        "hours": [8, 13],
        "max_copies": 5,
        "last_run_slots": [],
    }

    due = sqlite_backup.due_schedule_slots(settings_payload, now)

    assert due == ["2026-06-22T08"]

    settings_payload["last_run_slots"] = ["2026-06-22T08"]
    assert sqlite_backup.due_schedule_slots(settings_payload, now) == []


def test_mark_schedule_slots_run_keeps_recent_slots() -> None:
    updated = sqlite_backup.mark_schedule_slots_run(
        {"last_run_slots": ["2026-06-21T08"]},
        ["2026-06-22T08"],
    )

    assert updated["last_run_slots"] == ["2026-06-21T08", "2026-06-22T08"]
```

- [ ] **Step 2: Run failing schedule tests**

Run: `python -m pytest tests/test_sqlite_backup.py::test_due_schedule_slots_respects_day_hour_and_last_run tests/test_sqlite_backup.py::test_mark_schedule_slots_run_keeps_recent_slots -q`

Expected: FAIL because schedule helpers do not exist.

- [ ] **Step 3: Implement schedule helpers**

In `sqlite_backup.py`, add:

```python
WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def schedule_slot(now: datetime) -> str:
    value = now.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H")


def due_schedule_slots(settings_payload: dict[str, Any], now: datetime | None = None) -> list[str]:
    value = now or datetime.now(timezone.utc)
    if not settings_payload.get("enabled"):
        return []
    day = WEEKDAY_KEYS[value.weekday()]
    hour = value.hour
    if day not in set(settings_payload.get("days") or []):
        return []
    if hour not in {int(item) for item in settings_payload.get("hours") or []}:
        return []
    slot = schedule_slot(value)
    if slot in set(settings_payload.get("last_run_slots") or []):
        return []
    return [slot]


def mark_schedule_slots_run(settings_payload: dict[str, Any], slots: list[str]) -> dict[str, Any]:
    updated = dict(settings_payload or {})
    existing = [str(item) for item in updated.get("last_run_slots", [])]
    merged = existing + [slot for slot in slots if slot not in existing]
    updated["last_run_slots"] = merged[-500:]
    return updated
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_sqlite_backup.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add picorgftp_sql/sqlite_backup.py tests/test_sqlite_backup.py
git commit -m "feat: add sqlite backup schedule logic"
```

---

### Task 8: Backup Restore and Masked Diff

**Files:**
- Modify: `picorgftp_sql/sqlite_backup.py`
- Test: `tests/test_sqlite_backup.py`

- [ ] **Step 1: Write failing restore and diff tests**

Add to `tests/test_sqlite_backup.py`:

```python
def test_restore_backup_creates_pre_restore_backup_and_replaces_database(tmp_path: Path) -> None:
    active = tmp_path / "active.sqlite"
    backup = tmp_path / "BACKUP" / "picorgftp_sql-20260625-130234-manual.sqlite"
    backup.parent.mkdir()
    _create_db(active)
    _create_db(backup)
    with sqlite3.connect(backup) as conn:
        conn.execute("UPDATE app_config_values SET value_json = '\"restored\"' WHERE path = 'database.query'")

    result = sqlite_backup.restore_backup(str(active), str(backup), str(backup.parent))

    assert result["ok"] is True
    assert Path(result["pre_restore_backup"]["backup_path"]).exists()
    with sqlite3.connect(active) as conn:
        value = conn.execute("SELECT value_json FROM app_config_values WHERE path = 'database.query'").fetchone()[0]
    assert value == '"restored"'


def test_diff_databases_masks_secret_values(tmp_path: Path) -> None:
    left = tmp_path / "left.sqlite"
    right = tmp_path / "right.sqlite"
    _create_db(left)
    _create_db(right)
    with sqlite3.connect(right) as conn:
        conn.execute("INSERT INTO app_config_values VALUES ('ftp.password', '\"secret\"', '2026-06-25T13:02:34.300Z')")

    diff = sqlite_backup.diff_databases(str(left), str(right))

    assert diff["tables"]["app_config_values"]["added"] >= 1
    assert "secret" not in json.dumps(diff)
    assert "ftp.password" in json.dumps(diff)
    assert "present" in json.dumps(diff)
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_sqlite_backup.py::test_restore_backup_creates_pre_restore_backup_and_replaces_database tests/test_sqlite_backup.py::test_diff_databases_masks_secret_values -q`

Expected: FAIL because restore and diff helpers do not exist.

- [ ] **Step 3: Implement restore**

In `sqlite_backup.py`, add:

```python
import tempfile


def restore_backup(active_path: str, backup_path: str, backup_dir: str) -> dict[str, Any]:
    pre_restore = create_backup(active_path, backup_dir, reason="pre-restore")
    active = Path(active_path)
    source = Path(backup_path)
    fd, temp_path = tempfile.mkstemp(prefix="restore_", suffix=".sqlite.tmp", dir=str(active.parent))
    os.close(fd)
    temp = Path(temp_path)
    try:
        temp.write_bytes(source.read_bytes())
        os.replace(str(temp), str(active))
    finally:
        if temp.exists():
            temp.unlink()
    return {"ok": True, "pre_restore_backup": pre_restore, "restored_from": str(source), "active_path": str(active)}
```

- [ ] **Step 4: Implement masked diff**

Add:

```python
SECRET_KEYWORDS = ("password", "pass", "secret", "token", "hash", "api_key")


def _mask_value(key: str, value: object) -> object:
    lowered = str(key or "").lower()
    if any(keyword in lowered for keyword in SECRET_KEYWORDS):
        return "present" if str(value or "") else "empty"
    return value


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
    except sqlite3.Error:
        return 0


def _config_rows(conn: sqlite3.Connection) -> dict[str, object]:
    try:
        rows = conn.execute("SELECT path, value_json FROM app_config_values ORDER BY path").fetchall()
    except sqlite3.Error:
        return {}
    return {str(path): _mask_value(str(path), value) for path, value in rows}


def diff_databases(active_path: str, backup_path: str) -> dict[str, Any]:
    tables = ["app_config_values", "list_values", "slot_definitions", "sql_column_map", "sql_available_columns", "web_users", "product_entries", "file_index_segments", "web_history"]
    with sqlite3.connect(active_path) as active, sqlite3.connect(backup_path) as backup:
        active_counts = {table: _table_count(active, table) for table in tables}
        backup_counts = {table: _table_count(backup, table) for table in tables}
        active_config = _config_rows(active)
        backup_config = _config_rows(backup)
    config_added = sorted(set(backup_config) - set(active_config))
    config_removed = sorted(set(active_config) - set(backup_config))
    config_changed = sorted(key for key in set(active_config) & set(backup_config) if active_config[key] != backup_config[key])
    return {
        "tables": {
            table: {
                "active": active_counts[table],
                "backup": backup_counts[table],
                "added": max(0, backup_counts[table] - active_counts[table]),
                "removed": max(0, active_counts[table] - backup_counts[table]),
            }
            for table in tables
        },
        "config": {
            "added": [{"key": key, "value": backup_config[key]} for key in config_added],
            "removed": [{"key": key, "value": active_config[key]} for key in config_removed],
            "changed": [{"key": key, "active": active_config[key], "backup": backup_config[key]} for key in config_changed],
        },
    }
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_sqlite_backup.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add picorgftp_sql/sqlite_backup.py tests/test_sqlite_backup.py
git commit -m "feat: add sqlite backup restore and diff"
```

---

### Task 9: Web API Endpoints and Settings Snapshot

**Files:**
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/app.py`
- Test: `tests/test_web_smoke_ci.py`
- Test: `tests/test_web_data_users.py`

- [ ] **Step 1: Write failing API route tests**

In `tests/test_web_smoke_ci.py`, extend `test_critical_backend_routes_remain_registered` expected paths with:

```python
            "/api/settings/sqlite/repair",
            "/api/settings/sqlite/backup",
            "/api/settings/sqlite/backups",
            "/api/settings/sqlite/backup-diff",
            "/api/settings/sqlite/restore",
```

Add:

```python
    def test_sqlite_repair_endpoint_returns_summary(self) -> None:
        client = TestClient(web_app.app)
        with (
            patch.object(web_app.storage_settings, "resolve_sqlite_path", return_value="C:/Data/app.sqlite"),
            patch.object(web_app.storage_settings, "resolve_backup_dir", return_value="C:/Data/BACKUP"),
            patch.object(web_app, "repair_sqlite_database", return_value={"ok": True, "integrity_check": "ok"}),
            patch.object(web_app, "settings_snapshot", return_value={"data_mode": "sqlite"}),
        ):
            response = client.post("/api/settings/sqlite/repair")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_sqlite_backup_history_endpoint_lists_backups(self) -> None:
        client = TestClient(web_app.app)
        with patch.object(web_app.storage_settings, "resolve_backup_dir", return_value="C:/Data/BACKUP"), patch.object(web_app.sqlite_backup, "list_backups", return_value=[{"backup_path": "copy.sqlite"}]):
            response = client.get("/api/settings/sqlite/backups")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["backup_path"], "copy.sqlite")
```

- [ ] **Step 2: Write failing snapshot tests**

Add to `tests/test_web_data_users.py`:

```python
    def test_settings_snapshot_exposes_backup_settings(self) -> None:
        temp_dir = _workspace_temp("web_data_backup_settings")
        with (
            patch.object(web_data.settings, "AC", str(temp_dir)),
            patch.object(web_data.storage_settings, "load_backup_settings", return_value={"enabled": True, "days": ["mon"], "hours": [8], "max_copies": 3, "last_run_slots": []}),
            patch.object(web_data.storage_settings, "resolve_backup_dir", return_value=str(temp_dir / "BACKUP")),
        ):
            snapshot = web_data.settings_snapshot()

        self.assertEqual(snapshot["sqlite_backup"]["days"], ["mon"])
        self.assertEqual(snapshot["sqlite_backup_dir"], str(temp_dir / "BACKUP"))
```

- [ ] **Step 3: Run failing tests**

Run: `python -m pytest tests/test_web_smoke_ci.py::WebSmokeCiTests::test_critical_backend_routes_remain_registered tests/test_web_smoke_ci.py::WebSmokeCiTests::test_sqlite_repair_endpoint_returns_summary tests/test_web_smoke_ci.py::WebSmokeCiTests::test_sqlite_backup_history_endpoint_lists_backups tests/test_web_data_users.py::WebDataUserTests::test_settings_snapshot_exposes_backup_settings -q`

Expected: FAIL because endpoints and snapshot fields do not exist.

- [ ] **Step 4: Update `web_data.settings_snapshot()` and `update_settings()`**

Import/use `storage_settings.load_backup_settings()` and `storage_settings.resolve_backup_dir()`:

```python
"sqlite_backup": storage_settings.load_backup_settings(),
"sqlite_backup_dir": storage_settings.resolve_backup_dir(),
```

In `update_settings()`, read `backup_payload = payload.get("sqlite_backup") if isinstance(payload.get("sqlite_backup"), dict) else {}` and call `storage_settings.save_backup_settings(backup_payload)` when present.

- [ ] **Step 5: Add web app imports**

In `picorgftp_sql/web/app.py`, import:

```python
from .. import sqlite_backup
from ..sqlite_maintenance import repair_sqlite_database
```

- [ ] **Step 6: Add admin-only endpoints**

Add near other settings endpoints:

```python
    @app.post("/api/settings/sqlite/repair")
    async def settings_sqlite_repair(request: Request) -> JSONResponse:
        _require_admin(request)
        database_path = storage_settings.resolve_sqlite_path()
        backup_dir = storage_settings.resolve_backup_dir()
        result = await run_in_threadpool(repair_sqlite_database, database_path, backup_dir)
        data_store.reset_active_store_cache()
        config.initialize_config(interactive=False)
        result["settings"] = settings_snapshot()
        return JSONResponse(result)

    @app.post("/api/settings/sqlite/backup")
    async def settings_sqlite_backup(request: Request) -> JSONResponse:
        _require_admin(request)
        result = await run_in_threadpool(
            sqlite_backup.create_backup,
            storage_settings.resolve_sqlite_path(),
            storage_settings.resolve_backup_dir(),
            reason="manual",
        )
        sqlite_backup.enforce_retention(storage_settings.resolve_backup_dir(), storage_settings.load_backup_settings().get("max_copies", 10))
        return JSONResponse(result)

    @app.get("/api/settings/sqlite/backups")
    def settings_sqlite_backups(request: Request) -> Dict[str, Any]:
        _require_admin(request)
        return {"items": sqlite_backup.list_backups(storage_settings.resolve_backup_dir())}

    @app.post("/api/settings/sqlite/backup-diff")
    async def settings_sqlite_backup_diff(request: Request) -> JSONResponse:
        _require_admin(request)
        payload = await request.json()
        backup_path = str(payload.get("backup_path") if isinstance(payload, dict) else "")
        result = await run_in_threadpool(sqlite_backup.diff_databases, storage_settings.resolve_sqlite_path(), backup_path)
        return JSONResponse(result)

    @app.post("/api/settings/sqlite/restore")
    async def settings_sqlite_restore(request: Request) -> JSONResponse:
        _require_admin(request)
        payload = await request.json()
        backup_path = str(payload.get("backup_path") if isinstance(payload, dict) else "")
        result = await run_in_threadpool(
            sqlite_backup.restore_backup,
            storage_settings.resolve_sqlite_path(),
            backup_path,
            storage_settings.resolve_backup_dir(),
        )
        data_store.reset_active_store_cache()
        config.initialize_config(interactive=False)
        result["settings"] = settings_snapshot()
        return JSONResponse(result)
```

If the test client exposes an error because `reason` is keyword-only, wrap `create_backup` with `lambda` or use `functools.partial`.

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/test_web_smoke_ci.py tests/test_web_data_users.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_web_smoke_ci.py tests/test_web_data_users.py
git commit -m "feat: expose sqlite maintenance web apis"
```

---

### Task 10: Web Settings UI for Repair, Backup Schedule, History, Restore, Diff

**Files:**
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Test: `tests/test_web_ui_integrity.py`
- Test: `tests/test_source_integrity.py`

- [ ] **Step 1: Write failing static UI tests**

Add to `tests/test_web_ui_integrity.py`:

```python
    def test_backup_history_and_diff_modals_exist(self) -> None:
        html = _parse(INDEX_HTML)

        self.assertIn("backupHistoryModal", html.ids)
        self.assertIn("backupHistoryOutput", html.ids)
        self.assertIn("backupDiffModal", html.ids)
        self.assertIn("backupDiffOutput", html.ids)
```

Add to `tests/test_source_integrity.py`:

```python
    def test_web_settings_include_sqlite_repair_and_backup_controls(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "picorgftp_sql" / "web" / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn("repairSqliteDatabaseButton", source)
        self.assertIn("manualSqliteBackupButton", source)
        self.assertIn("backupHistoryButton", source)
        self.assertIn("sqliteBackupScheduleGrid", source)
        self.assertIn("/api/settings/sqlite/repair", source)
        self.assertIn("/api/settings/sqlite/backup", source)
        self.assertIn("/api/settings/sqlite/backups", source)
        self.assertIn("/api/settings/sqlite/restore", source)
        self.assertIn("/api/settings/sqlite/backup-diff", source)
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_web_ui_integrity.py::WebUiIntegrityTests::test_backup_history_and_diff_modals_exist tests/test_source_integrity.py::SourceIntegrityTests::test_web_settings_include_sqlite_repair_and_backup_controls -q`

Expected: FAIL because UI controls do not exist.

- [ ] **Step 3: Add modal containers**

In `index.html`, add two modal blocks near existing modal views:

```html
<div id="backupHistoryModal" class="modal-view">
  <section class="manager-panel">
    <header class="modal-header">
      <h1>Historia wersji bazy</h1>
      <button type="button" class="ghost-button modal-close" data-close-backup-history>Zamknij</button>
    </header>
    <div id="backupHistoryOutput" class="backup-history-output empty-state">Brak kopii.</div>
  </section>
</div>

<div id="backupDiffModal" class="modal-view">
  <section class="manager-panel">
    <header class="modal-header">
      <h1>Roznice kopii bazy</h1>
      <button type="button" class="ghost-button modal-close" data-close-backup-diff>Zamknij</button>
    </header>
    <div id="backupDiffOutput" class="backup-diff-output empty-state">Brak danych.</div>
  </section>
</div>
```

- [ ] **Step 4: Add JS controls**

In `app.js`, add DOM refs for the new outputs and close buttons. Add these functions with concrete request and render behavior:

```javascript
const backupHistoryOutput = document.querySelector("#backupHistoryOutput");
const backupDiffOutput = document.querySelector("#backupDiffOutput");
const SQLITE_BACKUP_DAYS = [
  ["mon", "Pon"],
  ["tue", "Wt"],
  ["wed", "Sr"],
  ["thu", "Czw"],
  ["fri", "Pt"],
  ["sat", "Sob"],
  ["sun", "Nd"],
];

function repairSqliteDatabaseButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Napraw plik bazy danych";
  button.addEventListener("click", async () => {
    button.disabled = true;
    settingsStatus.textContent = "Naprawianie bazy SQLite...";
    try {
      const payload = await requestJson("/api/settings/sqlite/repair", { method: "POST", timeoutMs: 120000 });
      if (payload.settings) state.settings = payload.settings;
      settingsStatus.textContent = payload.ok ? "Naprawa bazy zakonczona." : payload.integrity_check || "Naprawa nie powiodla sie.";
      renderSettings();
    } catch (error) {
      settingsStatus.textContent = error.message || "Nie udalo sie naprawic bazy.";
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function manualSqliteBackupButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Utworz kopie teraz";
  button.addEventListener("click", async () => {
    button.disabled = true;
    settingsStatus.textContent = "Tworzenie kopii SQLite...";
    try {
      const payload = await requestJson("/api/settings/sqlite/backup", { method: "POST", timeoutMs: 120000 });
      settingsStatus.textContent = payload.backup_path ? `Utworzono kopie: ${payload.backup_path}` : "Utworzono kopie SQLite.";
    } catch (error) {
      settingsStatus.textContent = error.message || "Nie udalo sie utworzyc kopii.";
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function backupHistoryButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Historia wersji";
  button.addEventListener("click", async () => {
    settingsStatus.textContent = "Wczytywanie historii kopii...";
    const payload = await requestJson("/api/settings/sqlite/backups");
    renderBackupHistory(payload.items || []);
    document.querySelector("#backupHistoryModal")?.classList.add("active");
  });
  return button;
}

function sqliteBackupScheduleGrid(settings = {}) {
  const wrapper = document.createElement("div");
  wrapper.className = "sqlite-backup-grid";
  wrapper.append(document.createElement("span"));
  for (let hour = 0; hour < 24; hour += 1) {
    const header = document.createElement("strong");
    header.textContent = String(hour).padStart(2, "0");
    wrapper.append(header);
  }
  const selectedDays = new Set(settings.days || []);
  const selectedHours = new Set((settings.hours || []).map((hour) => Number(hour)));
  for (const [dayKey, dayLabel] of SQLITE_BACKUP_DAYS) {
    const day = document.createElement("strong");
    day.textContent = dayLabel;
    wrapper.append(day);
    for (let hour = 0; hour < 24; hour += 1) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = "sqlite_backup_slot";
      input.value = `${dayKey}:${hour}`;
      input.checked = selectedDays.has(dayKey) && selectedHours.has(hour);
      label.append(input, String(hour).padStart(2, "0"));
      wrapper.append(label);
    }
  }
  return wrapper;
}

function collectSqliteBackupSchedule(form) {
  const slots = [...form.querySelectorAll('[name="sqlite_backup_slot"]:checked')].map((input) => input.value);
  const days = [...new Set(slots.map((slot) => slot.split(":")[0]).filter(Boolean))];
  const hours = [...new Set(slots.map((slot) => Number(slot.split(":")[1])).filter((hour) => Number.isFinite(hour)))].sort((a, b) => a - b);
  return {
    enabled: days.length > 0 && hours.length > 0,
    days,
    hours,
    max_copies: form.querySelector('[name="sqlite_backup_max_copies"]')?.value || 10,
  };
}

function renderBackupHistory(items = []) {
  backupHistoryOutput.textContent = "";
  if (!items.length) {
    backupHistoryOutput.className = "backup-history-output empty-state";
    backupHistoryOutput.textContent = "Brak kopii zapasowych.";
    return;
  }
  backupHistoryOutput.className = "backup-history-output";
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "backup-history-row";
    const summary = document.createElement("div");
    const actions = document.createElement("div");
    const restore = document.createElement("button");
    const diff = document.createElement("button");
    summary.textContent = `${item.created_at || "bez daty"} | ${item.reason || "kopia"} | ${item.size_bytes || 0} B`;
    restore.type = "button";
    restore.className = "secondary-button";
    restore.textContent = "Przywroc";
    restore.addEventListener("click", () => restoreSqliteBackup(item.backup_path));
    diff.type = "button";
    diff.className = "secondary-button";
    diff.textContent = "Pokaz roznice";
    diff.addEventListener("click", () => showSqliteBackupDiff(item.backup_path));
    actions.append(restore, diff);
    row.append(summary, actions);
    backupHistoryOutput.appendChild(row);
  }
}

async function restoreSqliteBackup(backupPath) {
  if (!backupPath || !window.confirm("Przywrocic wybrana kopie bazy SQLite?")) return;
  const payload = await requestJson("/api/settings/sqlite/restore", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ backup_path: backupPath }),
    timeoutMs: 120000,
  });
  if (payload.settings) state.settings = payload.settings;
  settingsStatus.textContent = "Przywrocono kopie. Odswiez panel, jesli widzisz stare dane.";
  renderSettings();
}

async function showSqliteBackupDiff(backupPath) {
  const payload = await requestJson("/api/settings/sqlite/backup-diff", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ backup_path: backupPath }),
    timeoutMs: 120000,
  });
  backupDiffOutput.className = "backup-diff-output";
  backupDiffOutput.textContent = JSON.stringify(payload, null, 2);
  document.querySelector("#backupDiffModal")?.classList.add("active");
}
```

In `renderSettingsApp()`, change the runtime group action row to:

```javascript
actionRow(importLegacyDataButton(), repairSqliteDatabaseButton(), manualSqliteBackupButton(), backupHistoryButton())
```

Add a new field group:

```javascript
settingsFieldGroup("Kopie zapasowe SQLite",
  sqliteBackupScheduleGrid(s.sqlite_backup || {}),
  inputField("sqlite_backup_max_copies", "Maksymalna liczba kopii", s.sqlite_backup?.max_copies || 10, { type: "number", min: 1, max: 999 })
)
```

Update the settings payload builder to include:

```javascript
sqlite_backup: collectSqliteBackupSchedule(form)
```

- [ ] **Step 5: Add CSS**

In `app.css`, add:

```css
.sqlite-backup-grid {
  display: grid;
  grid-template-columns: 72px repeat(24, minmax(28px, 1fr));
  gap: 4px;
  overflow-x: auto;
  grid-column: 1 / -1;
}

.sqlite-backup-grid label {
  display: grid;
  place-items: center;
  min-height: 28px;
}

.backup-history-row,
.backup-diff-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-color);
}
```

Use existing CSS variables if names differ; keep classes scoped to backup UI.

- [ ] **Step 6: Run UI tests**

Run: `python -m pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py tests/test_source_integrity.py
git commit -m "feat: add sqlite maintenance controls to web settings"
```

---

### Task 11: Web Runtime Backup Poller and ISO File Index Status

**Files:**
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/web_data.py`
- Test: `tests/test_web_smoke_ci.py`
- Test: `tests/test_web_data_users.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_web_data_users.py`:

```python
    def test_file_index_status_accepts_iso_generated_at(self) -> None:
        class Index:
            def get_status(self):
                return {
                    "state": "ready",
                    "cache_loaded": True,
                    "has_snapshot": True,
                    "dirs_scanned": 1,
                    "products_scanned": 1,
                    "name_count": 1,
                    "generated_at": "2026-06-25T13:02:34.300Z",
                    "error": "",
                }

        with patch.object(web_data, "_file_index_enabled", return_value=True), patch.object(web_data, "_get_file_index", return_value=Index()):
            status = web_data.file_index_status()

        self.assertEqual(status["generated_at"], "2026-06-25T13:02:34.300Z")
        self.assertIn("2026-06-25", status["label"])
```

Add to `tests/test_web_smoke_ci.py`:

```python
    def test_backup_scheduler_runs_due_slots(self) -> None:
        with (
            patch.object(web_app.storage_settings, "load_backup_settings", return_value={"enabled": True, "days": ["mon"], "hours": [8], "max_copies": 2, "last_run_slots": []}),
            patch.object(web_app.sqlite_backup, "due_schedule_slots", return_value=["2026-06-22T08"]),
            patch.object(web_app.sqlite_backup, "create_backup", return_value={"ok": True}),
            patch.object(web_app.storage_settings, "resolve_sqlite_path", return_value="C:/Data/app.sqlite"),
            patch.object(web_app.storage_settings, "resolve_backup_dir", return_value="C:/Data/BACKUP"),
            patch.object(web_app.sqlite_backup, "mark_schedule_slots_run", return_value={"enabled": True, "days": ["mon"], "hours": [8], "max_copies": 2, "last_run_slots": ["2026-06-22T08"]}),
            patch.object(web_app.storage_settings, "save_backup_settings") as save_backup_settings,
        ):
            result = web_app._run_due_sqlite_backups_once()

        self.assertEqual(result["created"], 1)
        save_backup_settings.assert_called_once()
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_web_data_users.py::WebDataUserTests::test_file_index_status_accepts_iso_generated_at tests/test_web_smoke_ci.py::WebSmokeCiTests::test_backup_scheduler_runs_due_slots -q`

Expected: FAIL because ISO parsing and scheduler function do not exist.

- [ ] **Step 3: Update file index status**

In `web_data.py`, add:

```python
from datetime import datetime, timezone


def _parse_generated_at(value: object) -> tuple[str, float | None]:
    text = _text(value)
    if text.endswith("Z") and "T" in text:
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return text, dt.timestamp()
        except ValueError:
            return text, None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return text, None
    iso = datetime.fromtimestamp(number, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return iso, number
```

Use this in `file_index_status()` for `age_seconds` and label formatting.

- [ ] **Step 4: Add scheduler helper**

In `web/app.py`, add module globals:

```python
_BACKUP_SCHEDULER_STOP = threading.Event()
_BACKUP_SCHEDULER_THREAD: threading.Thread | None = None
```

Add:

```python
def _run_due_sqlite_backups_once() -> Dict[str, Any]:
    settings_payload = storage_settings.load_backup_settings()
    slots = sqlite_backup.due_schedule_slots(settings_payload)
    if not slots:
        return {"created": 0, "slots": []}
    result = sqlite_backup.create_backup(
        storage_settings.resolve_sqlite_path(),
        storage_settings.resolve_backup_dir(),
        reason="scheduled",
    )
    sqlite_backup.enforce_retention(storage_settings.resolve_backup_dir(), settings_payload.get("max_copies", 10))
    updated = sqlite_backup.mark_schedule_slots_run(settings_payload, slots)
    storage_settings.save_backup_settings(updated)
    return {"created": 1, "slots": slots, "backup": result}
```

In startup event, start a daemon thread that calls `_run_due_sqlite_backups_once()` every 60 seconds until shutdown. In shutdown event, set the stop event and join briefly.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_web_smoke_ci.py tests/test_web_data_users.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add picorgftp_sql/web/app.py picorgftp_sql/web_data.py tests/test_web_smoke_ci.py tests/test_web_data_users.py
git commit -m "feat: schedule sqlite backups in web runtime"
```

---

### Task 12: Full Verification

**Files:**
- Modify files only to fix discovered failures.

- [ ] **Step 1: Run targeted tests**

Run:

```powershell
python -m pytest tests/test_config.py tests/test_sql_service.py tests/test_sqlite_store.py tests/test_file_index.py tests/test_sqlite_backup.py tests/test_sqlite_maintenance.py tests/test_web_data_users.py tests/test_web_smoke_ci.py tests/test_web_ui_integrity.py tests/test_source_integrity.py -q
```

Expected: PASS.

- [ ] **Step 2: Run broader suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 3: Static syntax checks**

Run:

```powershell
python -m compileall -q PicOrgFTP-SQL.pyw PicOrgFTP-SQL-WEB.pyw PicOrgFTP-SQL-QtSlots.pyw picorgftp_sql tests tools
node --check picorgftp_sql/web/static/app.js
```

Expected: no output and exit code 0.

- [ ] **Step 4: Manual smoke when practical**

Run the web server, open settings, and verify:

- Login username is empty on first browser use and remembers the last successful login.
- SQL tab shows placeholder help.
- New config starts with an empty SQL query.
- "Napraw plik bazy danych" creates a pre-repair backup and reports success.
- "Kopie zapasowe SQLite" schedule can be saved.
- Manual backup appears in "Historia wersji".
- Diff opens and masks secret values.
- Restore creates a pre-restore backup before replacing the database.

---

## Self-Review

- Spec coverage: login behavior is Task 1; SQL defaults and placeholders are Task 2; SQLite ISO timestamps are Task 3; index segmentation is Task 4; repair is Task 6; backup core/schedule/history/restore/diff are Tasks 5, 7, 8, 9, 10, and 11; verification is Task 12.
- Placeholder scan: plan intentionally uses the word "placeholder" only for SQL placeholder help. It contains no open implementation placeholders.
- Type consistency: backup settings use `sqlite_backup`, `days`, `hours`, `max_copies`, and `last_run_slots` consistently across storage, API, and UI tasks. History timestamps use `created_at` as ISO UTC text and preserve JSON display fields.
