# SQLite Data Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add selectable legacy/SQLite data storage for desktop and web, migrate legacy files into one SQLite database, and restore SQL column detection in web slot settings.

**Architecture:** Add a shared storage layer that keeps current payload shapes while routing reads and writes to legacy files or SQLite. Keep `local_settings.json` as bootstrap state for data mode, image location, and SQLite database location. Move SQL column detection into a shared service and expose it through both desktop and web.

**Tech Stack:** Python stdlib `sqlite3`, existing FastAPI web backend, existing Tkinter desktop UI, existing `openpyxl` legacy helpers, `unittest`/`pytest`.

---

### Task 1: Bootstrap Storage Settings

**Files:**
- Create: `picorgftp_sql/storage_settings.py`
- Modify: `picorgftp_sql/settings.py`
- Test: `tests/test_storage_settings.py`

- [ ] **Step 1: Write failing tests for SQLite path resolution**

```python
from pathlib import Path
from unittest.mock import patch

from picorgftp_sql import storage_settings


def test_sqlite_path_in_image_dir(tmp_path):
    image_dir = tmp_path / "photos"
    image_dir.mkdir()
    with patch.object(storage_settings.settings, "AC", str(image_dir)):
        resolved = storage_settings.resolve_sqlite_path(
            {"database_location_mode": "image_dir"}
        )
    assert resolved == str(image_dir / "picorgftp_sql.sqlite")


def test_sqlite_path_in_custom_location(tmp_path):
    target = tmp_path / "custom" / "data.sqlite"
    resolved = storage_settings.resolve_sqlite_path(
        {"database_location_mode": "custom", "database_path": str(target)}
    )
    assert resolved == str(target.resolve())


def test_sqlite_path_in_exe_dir(tmp_path):
    settings_file = tmp_path / "local_settings.json"
    with patch.object(storage_settings.settings, "BASE_DIR_SETTINGS_PATH", str(settings_file)):
        resolved = storage_settings.resolve_sqlite_path(
            {"database_location_mode": "exe_dir"}
        )
    assert resolved == str(tmp_path / "picorgftp_sql.sqlite")
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest tests/test_storage_settings.py -q`
Expected: FAIL because `picorgftp_sql.storage_settings` does not exist.

- [ ] **Step 3: Implement storage settings helpers**

Create constants `DATA_MODE_KEY`, `DATA_MODE_LEGACY`, `DATA_MODE_SQLITE`,
`DATABASE_LOCATION_MODE_KEY`, `DATABASE_PATH_KEY`, default filename
`picorgftp_sql.sqlite`, and functions:

```python
def normalize_data_mode(value: object) -> str:
    text = str(value or "").strip().lower()
    return DATA_MODE_SQLITE if text == DATA_MODE_SQLITE else DATA_MODE_LEGACY


def normalize_database_location_mode(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {DATABASE_LOCATION_IMAGE_DIR, DATABASE_LOCATION_CUSTOM, DATABASE_LOCATION_EXE_DIR}:
        return text
    return DATABASE_LOCATION_IMAGE_DIR


def load_bootstrap_settings() -> dict[str, object]:
    data = dict(common.BASE_DIR_SETTINGS_TEMPLATE)
    path = Path(settings.BASE_DIR_SETTINGS_PATH)
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data.update(loaded)
    data[DATA_MODE_KEY] = normalize_data_mode(data.get(DATA_MODE_KEY))
    data[DATABASE_LOCATION_MODE_KEY] = normalize_database_location_mode(
        data.get(DATABASE_LOCATION_MODE_KEY)
    )
    return data


def save_bootstrap_settings(updates: dict[str, object]) -> dict[str, object]:
    data = load_bootstrap_settings()
    data.update(updates or {})
    data[DATA_MODE_KEY] = normalize_data_mode(data.get(DATA_MODE_KEY))
    data[DATABASE_LOCATION_MODE_KEY] = normalize_database_location_mode(
        data.get(DATABASE_LOCATION_MODE_KEY)
    )
    path = Path(settings.BASE_DIR_SETTINGS_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    return data


def resolve_sqlite_path(payload: dict[str, object] | None = None) -> str:
    data = payload or load_bootstrap_settings()
    mode = normalize_database_location_mode(data.get(DATABASE_LOCATION_MODE_KEY))
    if mode == DATABASE_LOCATION_CUSTOM:
        return str(Path(str(data.get(DATABASE_PATH_KEY) or "")).expanduser().resolve())
    if mode == DATABASE_LOCATION_EXE_DIR:
        return str(Path(settings.BASE_DIR_SETTINGS_PATH).resolve().parent / DEFAULT_SQLITE_FILENAME)
    return str(Path(settings.AC).resolve() / DEFAULT_SQLITE_FILENAME)


def storage_summary() -> dict[str, object]:
    data = load_bootstrap_settings()
    return {
        "data_mode": normalize_data_mode(data.get(DATA_MODE_KEY)),
        "database_location_mode": normalize_database_location_mode(
            data.get(DATABASE_LOCATION_MODE_KEY)
        ),
        "database_path": resolve_sqlite_path(data),
        "image_dir": settings.AC,
    }
```

`load_bootstrap_settings()` must merge existing `local_settings.json` with
`BASE_DIR_SETTINGS_TEMPLATE` and default missing data mode to `legacy`.

- [ ] **Step 4: Run tests and verify they pass**

Run: `python -m pytest tests/test_storage_settings.py -q`
Expected: PASS.

---

### Task 2: SQLite Schema and Low-Level Store

**Files:**
- Create: `picorgftp_sql/sqlite_store.py`
- Test: `tests/test_sqlite_store.py`

- [ ] **Step 1: Write failing schema tests**

```python
import sqlite3

from picorgftp_sql.sqlite_store import SqliteStore


def test_schema_creates_expected_tables(tmp_path):
    db_path = tmp_path / "data.sqlite"
    store = SqliteStore(str(db_path))
    store.initialize()
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {
        "schema_version",
        "app_settings",
        "slot_definitions",
        "sql_column_map",
        "sql_available_columns",
        "list_values",
        "product_entries",
        "web_users",
        "web_history",
        "file_index_cache",
    } <= tables


def test_config_roundtrip_preserves_payload(tmp_path):
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()
    store.save_config({"db_type": "mysql", "enable_sql_update": True})
    assert store.load_config()["db_type"] == "mysql"
    assert store.load_config()["enable_sql_update"] is True
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest tests/test_sqlite_store.py -q`
Expected: FAIL because `SqliteStore` does not exist.

- [ ] **Step 3: Implement schema and config methods**

Implement `SqliteStore.initialize()`, `connect()`, `load_config()`,
`save_config()`, `load_slots()`, `save_slots()`, `load_sql_columns()`, and
`save_sql_columns()`. Store large config blocks as JSON in `app_settings` while
keeping slots and SQL mappings relational.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_sqlite_store.py -q`
Expected: PASS.

---

### Task 3: List and Product Entry SQLite API

**Files:**
- Modify: `picorgftp_sql/sqlite_store.py`
- Test: `tests/test_sqlite_store.py`

- [ ] **Step 1: Add failing tests for Excel-equivalent data**

```python
from picorgftp_sql.excel_utils import ENTRY_RECORDS_KEY


def test_lists_roundtrip_uses_excel_payload_shape(tmp_path):
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()
    store.save_lists(
        {
            "NAZWY": ["MAGGIORE"],
            "TYPY": ["KOMODA"],
            "MODELE": ["MA03"],
            "KOLORY": ["BIALY"],
            "DODATKI": ["NO-LED"],
            ENTRY_RECORDS_KEY: [
                {
                    "EAN": "5901234567890",
                    "NAZWA": "MAGGIORE",
                    "TYP": "KOMODA",
                    "MODEL": "MA03",
                    "KOLOR1": "BIALY",
                    "KOLOR2": "",
                    "KOLOR3": "",
                    "DODATKI": "NO-LED",
                    "PRODUCT_ID": "PRD-1",
                }
            ],
        }
    )
    payload = store.load_lists()
    assert payload["NAZWY"] == ["MAGGIORE"]
    assert payload[ENTRY_RECORDS_KEY][0]["PRODUCT_ID"] == "PRD-1"
```

- [ ] **Step 2: Run test and verify it fails**

Run: `python -m pytest tests/test_sqlite_store.py::test_lists_roundtrip_uses_excel_payload_shape -q`
Expected: FAIL because list methods are missing.

- [ ] **Step 3: Implement list and entry methods**

Add `load_lists()`, `save_lists()`, `add_list_value()`, `remove_list_value()`,
`save_product_entry()`, and `search_product_entries()`. Normalize values with
the existing Excel utility rules where possible.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_sqlite_store.py -q`
Expected: PASS.

---

### Task 4: Active Data Store Resolver

**Files:**
- Create: `picorgftp_sql/data_store.py`
- Modify: `picorgftp_sql/config.py`
- Modify: `picorgftp_sql/excel_utils.py`
- Test: `tests/test_data_store.py`

- [ ] **Step 1: Write failing resolver tests**

```python
from unittest.mock import patch

from picorgftp_sql import data_store, storage_settings


def test_active_store_defaults_to_legacy():
    with patch.object(storage_settings, "load_bootstrap_settings", return_value={}):
        store = data_store.get_active_store()
    assert store.mode == "legacy"


def test_active_store_uses_sqlite_when_configured(tmp_path):
    with (
        patch.object(
            storage_settings,
            "load_bootstrap_settings",
            return_value={
                "data_mode": "sqlite",
                "database_location_mode": "custom",
                "database_path": str(tmp_path / "data.sqlite"),
            },
        ),
    ):
        store = data_store.get_active_store()
    assert store.mode == "sqlite"
```

- [ ] **Step 2: Run test and verify it fails**

Run: `python -m pytest tests/test_data_store.py -q`
Expected: FAIL because `data_store.py` does not exist.

- [ ] **Step 3: Implement `LegacyDataStore`, `SqliteDataStoreAdapter`, and resolver**

`LegacyDataStore` delegates to existing file helpers. `SqliteDataStoreAdapter`
wraps `SqliteStore`. Add `reset_active_store_cache()` for tests and runtime
switching.

- [ ] **Step 4: Wire config and Excel helpers**

In `config.load_config()` and `config.save_config()`, use the active store when
mode is SQLite and preserve the existing JSON code path when mode is legacy.
In `excel_utils.prepare_excel_lists()`, `add_to_list()`, `remove_from_list()`,
and `save_ean_entry()`, route to the active store when mode is SQLite.

- [ ] **Step 5: Run parity tests**

Run: `python -m pytest tests/test_data_store.py tests/test_config.py tests/test_excel_utils.py -q`
Expected: PASS.

---

### Task 5: Legacy Import Into SQLite

**Files:**
- Create: `picorgftp_sql/legacy_import.py`
- Modify: `picorgftp_sql/sqlite_store.py`
- Test: `tests/test_legacy_import.py`

- [ ] **Step 1: Write failing import test**

```python
import json
from pathlib import Path
from openpyxl import Workbook

from picorgftp_sql.legacy_import import import_legacy_to_sqlite
from picorgftp_sql.sqlite_store import SqliteStore


def test_import_legacy_files_to_sqlite(tmp_path):
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    (legacy_dir / "config.json").write_text(
        json.dumps({"db_type": "mysql", "sql_available_columns": ["img_01"]}),
        encoding="utf-8",
    )
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet in ["NAZWY", "TYPY", "MODELE", "KOLORY", "DODATKI"]:
        ws = workbook.create_sheet(sheet)
        ws.append(["MAGGIORE" if sheet == "NAZWY" else "TEST"])
    entries = workbook.create_sheet("ENTRIES")
    entries.append(["EAN", "NAZWA", "TYP", "MODEL", "KOLOR1", "KOLOR2", "KOLOR3", "DODATKI", "PRODUCT_ID"])
    entries.append(["5901234567890", "MAGGIORE", "KOMODA", "MA03", "BIALY", "", "", "NO-LED", "PRD-1"])
    workbook.save(legacy_dir / "lists.xlsx")
    (legacy_dir / "web_users.json").write_text("[]", encoding="utf-8")
    (legacy_dir / "web_history.json").write_text("[]", encoding="utf-8")

    result = import_legacy_to_sqlite(str(legacy_dir), str(tmp_path / "data.sqlite"))
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    assert result["ok"] is True
    assert store.load_config()["db_type"] == "mysql"
    assert store.load_lists()["__ENTRY_RECORDS__"][0]["PRODUCT_ID"] == "PRD-1"
```

- [ ] **Step 2: Run test and verify it fails**

Run: `python -m pytest tests/test_legacy_import.py -q`
Expected: FAIL because importer does not exist.

- [ ] **Step 3: Implement importer**

Read legacy files directly from the provided directory, normalize config through
existing config helper functions, load workbook sheets with `openpyxl`, copy web
JSON files if present, and write all SQLite data in one transaction.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_legacy_import.py tests/test_sqlite_store.py -q`
Expected: PASS.

---

### Task 6: Web Users, History, and Settings Use Active Store

**Files:**
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/app.py`
- Test: `tests/test_web_data_users.py`
- Test: `tests/test_web_smoke_ci.py`

- [ ] **Step 1: Write failing tests for SQLite-backed web data**

Add tests that patch bootstrap settings to SQLite and verify:

```python
def test_sqlite_mode_persists_web_user(tmp_path):
    settings_payload = {
        "data_mode": "sqlite",
        "database_location_mode": "custom",
        "database_path": str(tmp_path / "data.sqlite"),
    }
    with patch.object(web_data.storage_settings, "load_bootstrap_settings", return_value=settings_payload):
        web_data.data_store.reset_active_store_cache()
        web_data.add_user("operator", "secret", role="user")
        users = web_data.load_users()
    assert any(user["username"] == "operator" for user in users)


def test_sqlite_mode_records_history(tmp_path):
    settings_payload = {
        "data_mode": "sqlite",
        "database_location_mode": "custom",
        "database_path": str(tmp_path / "data.sqlite"),
    }
    with patch.object(web_data.storage_settings, "load_bootstrap_settings", return_value=settings_payload):
        web_data.data_store.reset_active_store_cache()
        web_data.record_history(username="admin", action="save", ean="5901234567890")
        snapshot = web_data.history_snapshot()
    assert snapshot["groups"][0]["ean"] == "5901234567890"


def test_settings_snapshot_exposes_storage_locations(tmp_path):
    settings_payload = {
        "data_mode": "sqlite",
        "database_location_mode": "custom",
        "database_path": str(tmp_path / "data.sqlite"),
    }
    with patch.object(web_data.storage_settings, "load_bootstrap_settings", return_value=settings_payload):
        snapshot = web_data.settings_snapshot()
    assert snapshot["data_mode"] == "sqlite"
    assert snapshot["database_location_mode"] == "custom"
    assert snapshot["database_path"].endswith("data.sqlite")
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest tests/test_web_data_users.py -q`
Expected: FAIL for missing SQLite routing and missing snapshot fields.

- [ ] **Step 3: Route web users and history through active store**

Update `load_user_records()`, `save_users()`, `_load_history_records()`, and
`_save_history_records()` to use SQLite methods in SQLite mode and current JSON
files in legacy mode.

- [ ] **Step 4: Extend settings update/snapshot**

Expose and update `data_mode`, `image_dir`, `database_location_mode`,
`database_path`, and import results. On data mode/path changes call
`data_store.reset_active_store_cache()` and reload config.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_web_data_users.py tests/test_web_smoke_ci.py -q`
Expected: PASS.

---

### Task 7: Shared SQL Column Detection and Web Endpoint

**Files:**
- Modify: `picorgftp_sql/services/sql_service.py`
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/web/static/app.js`
- Test: `tests/test_sql_service.py`
- Test: `tests/test_web_smoke_ci.py`
- Test: `tests/test_source_integrity.py`

- [ ] **Step 1: Write failing service test**

```python
from unittest.mock import patch

from picorgftp_sql.services.sql_service import detect_available_columns


def test_detect_available_columns_returns_columns_and_preview():
    class Cursor:
        def execute(self, query, params=()):
            self.query = query
            self.params = params
        def fetchall(self):
            return [("img_01",), ("img_02",)]
        def close(self):
            pass
    class Conn:
        def cursor(self):
            return Cursor()
        def close(self):
            pass
    with patch("picorgftp_sql.services.sql_service.connect_db", return_value=Conn()):
        result = detect_available_columns(
            {"sql_query": "UPDATE object_query_1 SET img = '' WHERE EAN = '{ean}'", "db_type": "mysql"}
        )
    assert result["ok"] is True
    assert result["columns"] == ["img_01", "img_02"]
```

- [ ] **Step 2: Run test and verify it fails**

Run: `python -m pytest tests/test_sql_service.py::SqlServiceTests::test_detect_available_columns_returns_columns_and_preview -q`
Expected: FAIL because `detect_available_columns` does not exist.

- [ ] **Step 3: Implement shared detection**

Add `detect_available_columns(config_dict)` to `sql_service.py`. It uses
`build_column_detection_query()`, `connect_db()`, normalizes duplicate column
names, and returns `ok`, `columns`, `table`, `preview`, and `message`.

- [ ] **Step 4: Add web endpoint and UI button**

Add `POST /api/settings/sql-columns/detect` requiring admin. It calls the
service, persists `SQL_AVAILABLE_COLUMNS_KEY` through `update_settings()` or
active store save, returns the fresh `settings_snapshot()`, and updates the
datalist in `renderSettingsSlots()`. Add a button labeled `Wykryj pola SQL`.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_sql_service.py tests/test_web_smoke_ci.py tests/test_source_integrity.py -q`
Expected: PASS.

---

### Task 8: Desktop Settings UI Uses New Storage Controls

**Files:**
- Modify: `picorgftp_sql/app.py`
- Test: `tests/test_source_integrity.py`
- Test: `tests/test_desktop_smoke_ci.py`

- [ ] **Step 1: Add source integrity tests**

Add assertions that desktop settings source includes:

```python
"data_mode"
"database_location_mode"
"database_path"
"Importuj stare dane do SQLite"
"Wykryj pola SQL"
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest tests/test_source_integrity.py::SourceIntegrityTests -q`
Expected: FAIL for missing storage controls.

- [ ] **Step 3: Implement desktop controls**

In the system/settings tab, add data mode selector, image directory picker,
SQLite location mode selector, custom SQLite path entry/button, and import
button. Reuse existing base-dir unlock/admin behavior. Keep the existing SQL
column detection button but replace direct connection code with
`detect_available_columns()`.

- [ ] **Step 4: Run desktop-focused tests**

Run: `python -m pytest tests/test_source_integrity.py tests/test_desktop_smoke_ci.py -q`
Expected: PASS.

---

### Task 9: Web Settings UI Storage Controls

**Files:**
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.css`
- Test: `tests/test_source_integrity.py`
- Test: `tests/test_web_ui_integrity.py`

- [ ] **Step 1: Add UI integrity tests**

Assert that `renderSettingsApp()` contains fields for `data_mode`,
`image_dir`, `database_location_mode`, `database_path`, and a legacy import
button action.

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest tests/test_source_integrity.py tests/test_web_ui_integrity.py -q`
Expected: FAIL for missing web controls.

- [ ] **Step 3: Implement web controls**

Update the settings app tab:

```javascript
selectField("data_mode", "Tryb danych", s.data_mode, [["legacy", "Pliki legacy"], ["sqlite", "SQLite"]])
inputField("image_dir", "Lokalizacja zdjec", s.image_dir)
selectField("database_location_mode", "Lokalizacja SQLite", s.database_location_mode, [
  ["image_dir", "Przy zdjeciach"],
  ["custom", "Wskazana sciezka"],
  ["exe_dir", "Przy backendzie"],
])
inputField("database_path", "Plik SQLite", s.database_path)
```

Add a button that posts to `/api/settings/import-legacy`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_source_integrity.py tests/test_web_ui_integrity.py -q`
Expected: PASS.

---

### Task 10: Full Verification

**Files:**
- Modify as needed based on failures.

- [ ] **Step 1: Run targeted suite**

Run:

```powershell
python -m pytest tests/test_storage_settings.py tests/test_sqlite_store.py tests/test_data_store.py tests/test_legacy_import.py tests/test_sql_service.py tests/test_config.py tests/test_excel_utils.py tests/test_web_data_users.py tests/test_web_smoke_ci.py tests/test_source_integrity.py tests/test_web_ui_integrity.py -q
```

Expected: PASS.

- [ ] **Step 2: Run broader existing suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 3: Manual smoke notes**

Start web panel, open settings, verify the SQL detection button populates slot
SQL field suggestions, switch data mode in a temp workspace, import legacy
data, and switch back to legacy without deleting files.
