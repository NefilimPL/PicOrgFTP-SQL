# Deduplikacja EAN w eksporcie Pimcore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eksport Pimcore zwraca jeden importowalny wiersz dla każdego EAN-u, preferując najnowszą udaną operację.

**Architecture:** Czysta funkcja w `web_data.py` wybierze indeks każdego rekordu na podstawie już posortowanej historii SQLite. Dla EAN-u zachowa pierwszy rekord `completed`, a gdy go nie ma — pierwszy rekord dowolnego statusu; następnie zwróci wybrane rekordy w kolejności historii. Funkcja eksportująca przekaże wynik do istniejącego mapowania CSV/XLSX.

**Tech Stack:** Python, SQLite store mockowany przez pytest, CSV, openpyxl.

## Global Constraints

- Tabela SQLite `pimcore_submissions` oraz historia audytowa nie mogą być modyfikowane.
- Rekord `completed` jest jedynym statusem traktowanym jako sukces; `duplicate` nie jest sukcesem.
- Rekord bez EAN-u pozostaje niezależnym wierszem eksportu.
- Układ `export_columns`, nazwy kolumn i format CSV/XLSX nie mogą się zmienić.
- Deduplikacja działa wyłącznie na rekordach pobranych w istniejącym limicie endpointu.

---

### Task 1: Wybór jednego rekordu dla EAN-u

**Files:**
- Modify: `picorgftp_sql/web_data.py:2993-3045`
- Test: `tests/test_pimcore_web.py:454-665`

**Interfaces:**
- Produces: `_deduplicate_pimcore_submission_export_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]`.
- Consumes: `ean`, `status` oraz kolejność listy zwróconej przez `query_pimcore_submissions()`.

- [x] **Step 1: Write the failing tests**

```python
def test_pimcore_submission_export_rows_prefer_latest_completed_ean():
    rows = [
        {"ean": "5906199310317", "status": "failed", "operation_id": "new-failure"},
        {"ean": "5900000000001", "status": "completed", "operation_id": "other-success"},
        {"ean": "5906199310317", "status": "completed", "operation_id": "older-success"},
    ]
    assert web_data._deduplicate_pimcore_submission_export_rows(rows) == [rows[1], rows[2]]


def test_pimcore_submission_export_rows_fall_back_and_keep_blank_eans():
    rows = [
        {"ean": "5906199310317", "status": "conflict", "operation_id": "new-conflict"},
        {"ean": "", "status": "completed", "operation_id": "blank-one"},
        {"ean": "5906199310317", "status": "failed", "operation_id": "old-failure"},
        {"ean": "", "status": "failed", "operation_id": "blank-two"},
    ]
    assert web_data._deduplicate_pimcore_submission_export_rows(rows) == [rows[0], rows[1], rows[3]]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `& .\tmp_pyenv\Scripts\python.exe -m pytest tests/test_pimcore_web.py -k "deduplicate_pimcore_submission_export_rows" -q`

Expected: FAIL because the helper does not exist.

- [x] **Step 3: Implement the minimal selector**

```python
def _deduplicate_pimcore_submission_export_rows(rows):
    fallback_by_ean, completed_by_ean = {}, {}
    for index, row in enumerate(rows):
        ean = _text(row.get("ean")).casefold()
        if ean:
            fallback_by_ean.setdefault(ean, index)
            if _text(row.get("status")).casefold() == "completed":
                completed_by_ean.setdefault(ean, index)
    selected_indexes = {
        completed_by_ean.get(ean, fallback_index)
        for ean, fallback_index in fallback_by_ean.items()
    }
    return [row for index, row in enumerate(rows) if not _text(row.get("ean")) or index in selected_indexes]
```

- [x] **Step 4: Run focused tests**

Run: `& .\tmp_pyenv\Scripts\python.exe -m pytest tests/test_pimcore_web.py -k "deduplicate_pimcore_submission_export_rows" -q`

Expected: PASS.

- [x] **Step 5: Commit**

```powershell
git add picorgftp_sql/web_data.py tests/test_pimcore_web.py
git commit -m "feat: deduplicate Pimcore export rows by EAN"
```

### Task 2: Podłączenie selektora do eksportu i regresja CSV/XLSX

**Files:**
- Modify: `picorgftp_sql/web_data.py:3034-3063`
- Test: `tests/test_pimcore_web.py:454-665`

**Interfaces:**
- Consumes: `_deduplicate_pimcore_submission_export_rows(rows)`.
- Produces: CSV, XLSX i JSON z `count` zgodnym z liczbą wybranych EAN-ów.

- [x] **Step 1: Write the failing export regression test**

```python
def test_export_pimcore_submissions_deduplicates_ean_using_latest_completed():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"]["field_mappings"] = [
        {"source": "EAN", "pimcore_field": "ean", "type": "input", "parser": "text"},
        {"source": "STOCK", "pimcore_field": "stock", "type": "numeric", "parser": "integer"},
    ]
    store = Mock()
    store.query_pimcore_submissions.return_value = [
        {"ean": "5906199310317", "status": "failed", "values": {"EAN": "5906199310317", "STOCK": "8"}},
        {"ean": "5906199310317", "status": "completed", "values": {"EAN": "5906199310317", "STOCK": "12"}},
    ]
    with patch.object(web_data.config, "CONFIG", cfg), patch.object(web_data, "_active_sqlite_store", return_value=store):
        exported = web_data.export_pimcore_submissions(export_format="csv")
    assert exported["count"] == 1
    assert list(csv.reader(io.StringIO(exported["content"]))) == [["ean", "stock"], ["5906199310317", "12"]]
```

- [x] **Step 2: Run the test to verify it fails**

Run: `& .\tmp_pyenv\Scripts\python.exe -m pytest tests/test_pimcore_web.py -k "deduplicates_ean_using_latest_completed" -q`

Expected: FAIL because the exporter maps all audit rows.

- [x] **Step 3: Apply the selector before table mapping**

```python
rows = _deduplicate_pimcore_submission_export_rows(rows)
columns, table_rows = _pimcore_submission_export_table(rows)
```

Place it in `export_pimcore_submissions()` after querying the store and before `_pimcore_submission_export_table(rows)`.

- [x] **Step 4: Run all Pimcore export tests**

Run: `& .\tmp_pyenv\Scripts\python.exe -m pytest tests/test_pimcore_web.py -k "export_pimcore_submissions or deduplicate_pimcore_submission_export_rows" -q`

Expected: PASS.

- [x] **Step 5: Commit**

```powershell
git add picorgftp_sql/web_data.py tests/test_pimcore_web.py
git commit -m "feat: export one Pimcore row per EAN"
```

### Task 3: Final verification

**Files:**
- Verify only: `picorgftp_sql/web_data.py`, `tests/test_pimcore_web.py`.

- [x] **Step 1: Run syntax and targeted regression suite**

Run: `& .\tmp_pyenv\Scripts\python.exe -m pytest tests/test_pimcore_config.py tests/test_pimcore_web.py -q`

Expected: PASS.

- [ ] **Step 2: Inspect committed diff**

Run: `git show --check --format=oneline HEAD; git status --short`

Expected: no whitespace errors and clean worktree.
