# Konfigurowalny układ eksportu importowego Pimcore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eksportować dane zgłoszeń Pimcore do CSV i XLSX w zapisanej kolejności, z technicznymi lub własnymi nagłówkami oraz pustymi kolumnami wymaganymi przez importer.

**Architecture:** Konfiguracja `pimcore.export_columns` będzie normalizowaną listą niezależną od mapowań formularza. Warstwa eksportu przetłumaczy pozycje typu `field` na mapowania według `pimcore_field`, a pozycje `blank` na puste komórki. Modal w panelu webowym będzie edytować tę listę i zapisze ją przez istniejący endpoint ustawień.

**Tech Stack:** Python 3, FastAPI, OpenPyXL, pytest, HTML, JavaScript i CSS.

## Global Constraints

- Eksport CSV i XLSX musi używać identycznej kolejności i nagłówków.
- Domyślny nagłówek pola to techniczna nazwa `pimcore_field`.
- Własny nagłówek jest opcjonalny; pusta kolumna może mieć pusty nagłówek.
- Układ eksportu nie może wpływać na kolejność ani definicję mapowań formularza Pimcore.
- Nie dodawać funkcji przeciągania; kolejność zmieniają przyciski góra/dół.

---

### Task 1: Model i normalizacja układu eksportu

**Files:**
- Modify: `picorgftp_sql/pimcore_config.py:24-44, 283-330`
- Modify: `tests/test_pimcore_config.py:1-70`

**Interfaces:**
- Produces: `normalize_pimcore_settings(raw) -> dict[str, Any]` z kluczem `export_columns: list[dict[str, str]]`.
- Produces: pozycje `{"type": "field", "pimcore_field": str, "header": str}` albo `{"type": "blank", "header": str}`.
- Consumes: `field_mappings`, aby utworzyć kompatybilny domyślny układ i sprawdzić, czy wskazane pole nadal istnieje.

- [ ] **Step 1: Write the failing configuration tests**

```python
def test_normalize_pimcore_settings_builds_import_export_columns_from_mappings():
    result = normalize_pimcore_settings({
        "field_mappings": [
            {"source": "EAN", "pimcore_field": "ean", "type": "input"},
            {"source": "STOCK", "pimcore_field": "stock", "type": "numeric"},
        ]
    })

    assert result["export_columns"] == [
        {"type": "field", "pimcore_field": "ean", "header": "ean"},
        {"type": "field", "pimcore_field": "stock", "header": "stock"},
    ]


def test_normalize_pimcore_settings_keeps_custom_headers_and_blank_columns():
    result = normalize_pimcore_settings({
        "field_mappings": [{"source": "EAN", "pimcore_field": "ean", "type": "input"}],
        "export_columns": [
            {"type": "blank", "header": "parentId"},
            {"type": "field", "pimcore_field": "ean", "header": "kod"},
        ],
    })

    assert result["export_columns"] == [
        {"type": "blank", "header": "parentId"},
        {"type": "field", "pimcore_field": "ean", "header": "kod"},
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_pimcore_config.py -q`

Expected: FAIL because normalized settings do not contain `export_columns`.

- [ ] **Step 3: Write minimal implementation**

Add `"export_columns": []` to `DEFAULT_PIMCORE_SETTINGS`, and introduce helpers with these contracts:

```python
def _default_export_columns(mappings: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"type": "field", "pimcore_field": item["pimcore_field"], "header": item["pimcore_field"]}
        for item in mappings
    ]


def _normalize_export_columns(raw: object, mappings: list[dict[str, Any]]) -> list[dict[str, str]]:
    allowed = {str(item["pimcore_field"]).strip() for item in mappings}
    columns: list[dict[str, str]] = []
    seen_fields: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        column_type = str(item.get("type") or "").strip().lower()
        header = str(item.get("header") or "").strip()
        if column_type == "blank":
            columns.append({"type": "blank", "header": header})
        elif column_type == "field":
            field = str(item.get("pimcore_field") or "").strip()
            if field in allowed and field not in seen_fields:
                columns.append({"type": "field", "pimcore_field": field, "header": header or field})
                seen_fields.add(field)
    return columns
```

The normalizer accepts blank positions and only fields that exist in the current mappings; it removes duplicate fields. In `normalize_pimcore_settings`, use `_default_export_columns(mappings)` only when the `export_columns` key is absent; preserve an explicitly saved empty list.

- [ ] **Step 4: Run the configuration tests to verify they pass**

Run: `python -m pytest tests/test_pimcore_config.py -q`

Expected: PASS.

- [ ] **Step 5: Add invalid-input regression coverage and verify it**

Add a test that unknown types, missing/nonexistent `pimcore_field` values, and repeated field positions are omitted while a valid blank position remains. Run `python -m pytest tests/test_pimcore_config.py -q`; expected PASS.

- [ ] **Step 6: Commit**

```powershell
git add picorgftp_sql/pimcore_config.py tests/test_pimcore_config.py
git commit -m "feat: add Pimcore export column layout"
```

### Task 2: Generate import-compatible CSV and XLSX from the layout

**Files:**
- Modify: `picorgftp_sql/web_data.py:2961-3065`
- Modify: `tests/test_pimcore_web.py:455-610`

**Interfaces:**
- Consumes: normalized `config.CONFIG["pimcore"]["export_columns"]`.
- Consumes: saved submission `values`, resolved through the source of matching `field_mappings`.
- Produces: `_pimcore_submission_export_table(rows) -> tuple[list[str], list[list[object]]]` used without format-specific changes by `export_pimcore_submissions`.

- [ ] **Step 1: Write the failing export tests**

```python
def test_export_pimcore_submissions_uses_custom_import_layout_for_csv():
    cfg["pimcore"]["export_columns"] = [
        {"type": "field", "pimcore_field": "stock", "header": "stock"},
        {"type": "blank", "header": "parentId"},
        {"type": "field", "pimcore_field": "ean", "header": "code"},
    ]

    exported = web_data.export_pimcore_submissions(export_format="csv")

    assert list(csv.reader(io.StringIO(exported["content"]))) == [
        ["stock", "parentId", "code"],
        ["12", "", "5901234567890"],
    ]
```

Create an analogous XLSX test, asserting `["stock", "parentId", "code"]` in row 1 and `["12", None, "5901234567890"]` in row 2.

- [ ] **Step 2: Run the export tests to verify they fail**

Run: `python -m pytest tests/test_pimcore_web.py -k "export_pimcore_submissions" -q`

Expected: FAIL because the exporter still emits mapping labels and mapping order.

- [ ] **Step 3: Write minimal implementation**

Change `_pimcore_submission_export_mappings` to derive an ordered sequence from `export_columns`, with a lookup from mapped `pimcore_field` to source name. In `_pimcore_submission_export_table`, append `""` for `blank`; for `field`, obtain the source value through `_pimcore_mapping_value` and normalize it through `_pimcore_export_cell`. The returned headers are always the configured `header` values.

- [ ] **Step 4: Run focused export tests to verify they pass**

Run: `python -m pytest tests/test_pimcore_web.py -k "export_pimcore_submissions" -q`

Expected: PASS.

- [ ] **Step 5: Run the endpoint response regression test**

Run: `python -m pytest tests/test_pimcore_web.py -k "admin_can_export_pimcore_submissions_as_xlsx_response" -q`

Expected: PASS, proving the download route still serves an XLSX response.

- [ ] **Step 6: Commit**

```powershell
git add picorgftp_sql/web_data.py tests/test_pimcore_web.py
git commit -m "feat: export Pimcore submissions in configured layout"
```

### Task 3: Add the saved export-layout editor to the Pimcore settings UI

**Files:**
- Modify: `picorgftp_sql/web/static/index.html:608-620`
- Modify: `picorgftp_sql/web/static/app.js:438-443, 10697-10705, 11365-11398, 11730-11835, 13163-13172`
- Modify: `picorgftp_sql/web/static/app.css` near existing `.pimcore-*` modal and list rules
- Modify: `tests/test_web_ui_integrity.py:2570-2596`

**Interfaces:**
- Consumes: `state.settings.pimcore.field_mappings` and `state.settings.pimcore.export_columns`.
- Produces: `savePimcoreExportColumns(columns)`, posting `{ pimcore: { ...state.settings.pimcore, export_columns: columns } }` to `/api/settings` and replacing `state.settings` with the response.
- Produces: modal controls with IDs `pimcoreExportLayoutModal`, `pimcoreExportLayoutOpenButton`, `pimcoreExportLayoutSaveButton`, `pimcoreExportLayoutAddFieldButton`, and `pimcoreExportLayoutAddBlankButton`.

- [ ] **Step 1: Write the failing UI-integrity test**

```python
def test_pimcore_settings_has_saved_import_export_layout_editor(self) -> None:
    source = APP_JS.read_text(encoding="utf-8")
    html = INDEX_HTML.read_text(encoding="utf-8")

    self.assertIn("pimcoreExportLayoutModal", html)
    self.assertIn("pimcoreExportLayoutOpenButton", source)
    self.assertIn("function savePimcoreExportColumns", source)
    self.assertIn("pimcoreExportLayoutAddFieldButton", source)
    self.assertIn("pimcoreExportLayoutAddBlankButton", source)
    self.assertIn("export_columns", source)
```

- [ ] **Step 2: Run the UI-integrity test to verify it fails**

Run: `python -m pytest tests/test_web_ui_integrity.py -k "saved_import_export_layout_editor" -q`

Expected: FAIL because no layout modal or save function exists.

- [ ] **Step 3: Add the modal structure and accessible styles**

In `index.html`, add a nested modal after `pimcoreExportModal` with a title, close button, list container, both add buttons, cancel button, and save button. In `app.css`, add compact grid/flex rules for an export-layout row, make its text input shrink safely, and style move/remove controls consistently with existing ghost buttons.

- [ ] **Step 4: Implement client-side row editing and persistence**

Add DOM references and event listeners. Implement row creation, collection, open/close, move and remove handlers. A field row offers only mapped `pimcore_field` values not already selected in another field row; a blank row has no field selector. On save, disable the button, post the full Pimcore settings with the edited `export_columns`, replace `state.settings` with the response, report success or server error in `settingsStatus`, and close the modal only after success.

Change `pimcoreSettingsExportButton()` to return the existing export button and `pimcoreExportLayoutOpenButton()` labeled „Edytuj kolejność pól do eksportu”.

- [ ] **Step 5: Run the UI-integrity test to verify it passes**

Run: `python -m pytest tests/test_web_ui_integrity.py -k "pimcore" -q`

Expected: PASS.

- [ ] **Step 6: Run focused backend and configuration regression tests**

Run: `python -m pytest tests/test_pimcore_config.py tests/test_pimcore_web.py tests/test_web_ui_integrity.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py
git commit -m "feat: add Pimcore export layout editor"
```

### Task 4: Final verification

**Files:**
- Verify only: repository working tree and the files changed in Tasks 1-3.

- [ ] **Step 1: Check formatting and diff scope**

Run: `git diff HEAD~3..HEAD --check` and `git status --short`

Expected: no whitespace errors and no unrelated files.

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest -q`

Expected: PASS with zero failures.

- [ ] **Step 3: Check the requirements against the implementation**

Verify that configuration defaults to `pimcore_field` headers, the editor can reorder/add/remove fields and blanks, custom headers are retained, and both formats use the same ordered layout.
