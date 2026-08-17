# Zaznaczanie i przeciąganie układu eksportu Pimcore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Umożliwić szybkie zaznaczanie i przenoszenie grup pozycji układu eksportu oraz wstawianie pustych kolumn w dowolnym miejscu.

**Architecture:** Stan modalu pozostaje w `pimcoreExportLayoutDraft`; dodatkowy zbiór wybranych indeksów i dane przeciągania istnieją tylko w pamięci klienta. Render listy doda elementy wstawiania przed, między i po wierszach. Operacja upuszczenia utworzy nową tablicę z usuniętą, zachowaną w kolejności grupą i wstawi ją pod wskazanym indeksem.

**Tech Stack:** HTML, CSS, JavaScript, pytest oraz Node.js do kontroli składni.

## Global Constraints

- `export_columns` i zachowanie eksportu CSV/XLSX nie mogą się zmienić.
- Zaznaczenie jest tymczasowym stanem modalu, nie częścią zapisanej konfiguracji.
- Zwykłe kliknięcie kontrolek edycji wiersza nie może uruchamiać zaznaczenia ani przeciągania.
- Przycisk dodania pustej kolumny między pozycjami jest widoczny wyłącznie po najechaniu jego strefy.
- Przyciski przesuwania pojedynczego wiersza zostają usunięte.

---

### Task 1: Renderowanie stref wstawiania i zaznaczanie wielu pozycji

**Files:**
- Modify: `picorgftp_sql/web/static/app.js:444-451, 11407-11486`
- Modify: `picorgftp_sql/web/static/app.css:1773-1809`
- Modify: `tests/test_web_ui_integrity.py:2599-2607`

**Interfaces:**
- Produces: `pimcoreExportLayoutSelection: Set<number>`, zawierający indeksy zaznaczonych wierszy.
- Produces: `insertPimcoreExportBlankColumn(index: number): void`, która zachowuje aktualne wartości edytowanych nagłówków i wstawia `{ type: "blank", header: "" }`.
- Consumes: `pimcoreExportLayoutDraft` oraz `collectPimcoreExportColumns()`.

- [x] **Step 1: Write the failing UI integrity test**

```python
def test_pimcore_export_layout_supports_between_slots_insert_and_selection(self) -> None:
    source = APP_JS.read_text(encoding="utf-8")
    css = APP_CSS.read_text(encoding="utf-8")

    self.assertIn("insertPimcoreExportBlankColumn", source)
    self.assertIn("pimcoreExportLayoutSelection", source)
    self.assertIn("pimcore-export-layout-insert", source)
    self.assertIn("pimcore-export-layout-selected", source)
    self.assertIn(".pimcore-export-layout-insert:hover", css)
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_web_ui_integrity.py -k "between_slots_insert_and_selection" -q`

Expected: FAIL because the current UI has no between-slot insertion control or selection state.

- [x] **Step 3: Implement selection and insertion**

Replace the up/down buttons in `renderPimcoreExportLayout` with:
- a `pimcore-export-layout-insert` element before the first row, between rows, and after the last row;
- a `+` button in each element whose `aria-label` identifies the insertion position;
- mouse handlers on free row space for normal rectangle selection and `Ctrl` toggling;
- an absolute rectangle overlay on the list during background drag that selects intersecting row bounds.

Before every list mutation, synchronize `pimcoreExportLayoutDraft = collectPimcoreExportColumns()`. The insertion helper must use `splice(index, 0, { type: "blank", header: "" })`, remove no existing rows, clear no current header text, and render the updated list.

Add styles that hide the plus button until `:hover` or `:focus-within`, and visibly apply `.pimcore-export-layout-selected` to selected rows.

- [x] **Step 4: Run the UI test and JavaScript parser**

Run: `python -m pytest tests/test_web_ui_integrity.py -k "between_slots_insert_and_selection or pimcore" -q`

Run: `node --check picorgftp_sql/web/static/app.js`

Expected: PASS for both commands.

- [x] **Step 5: Commit**

```powershell
git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py
git commit -m "feat: add Pimcore export layout multi-selection"
```

### Task 2: Przeciąganie i upuszczanie zaznaczonej grupy

**Files:**
- Modify: `picorgftp_sql/web/static/app.js:11407-11531`
- Modify: `picorgftp_sql/web/static/app.css:1773-1809`
- Modify: `tests/test_web_ui_integrity.py:2599-2607`

**Interfaces:**
- Consumes: `pimcoreExportLayoutSelection: Set<number>` and `pimcoreExportLayoutDraft: Array<object>`.
- Produces: `movePimcoreExportColumns(dropIndex: number): void`; it moves every selected column in original order.
- Produces: `pimcore-export-layout-drop-target`, displayed for the current valid insertion position.

- [x] **Step 1: Extend the failing UI integrity test**

```python
self.assertIn("function movePimcoreExportColumns", source)
self.assertIn("dragstart", source)
self.assertIn("dragover", source)
self.assertIn("drop", source)
self.assertIn("pimcore-export-layout-drop-target", css)
self.assertNotIn('moveUp.textContent = "↑"', source)
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_web_ui_integrity.py -k "between_slots_insert_and_selection" -q`

Expected: FAIL because the list still relies on single-row arrows.

- [x] **Step 3: Implement group drag and drop**

Set `row.draggable = true` only on a row’s free surface and preserve form-control editing. On drag start:
- synchronize the draft from the DOM;
- if the dragged index is not selected, replace the selection with that one index;
- store the selected indexes in `dataTransfer` and add a dragging class to every selected row.

On drag over an insertion zone, set `dropEffect = "move"`, record its original-list insertion index, and render that zone with `.pimcore-export-layout-drop-target`. On drop:
- ignore an index lying inside the selected contiguous target range;
- construct `moving = draft.filter((_column, index) => selection.has(index))`;
- construct `remaining = draft.filter((_column, index) => !selection.has(index))`;
- subtract the number of selected indexes below the old drop index;
- execute `remaining.splice(adjustedDropIndex, 0, ...moving)`;
- replace the draft, select the inserted contiguous range, and render.

Clear temporary drag classes and the drop target on drop, drag end, and modal close.

- [x] **Step 4: Run focused verification**

Run: `python -m pytest tests/test_web_ui_integrity.py -k "pimcore" -q`

Run: `node --check picorgftp_sql/web/static/app.js`

Run: `& .\\tmp_pyenv\\Scripts\\python.exe -m pytest tests/test_pimcore_config.py tests/test_pimcore_web.py -q`

Expected: PASS; configuration and generated CSV/XLSX remain unchanged.

- [x] **Step 5: Commit**

```powershell
git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py
git commit -m "feat: drag groups in Pimcore export layout"
```

### Task 3: Final verification

**Files:**
- Verify only: changed UI files and tests.

- [x] **Step 1: Verify cache and UI checks**

Run: `python -m pytest tests/test_source_integrity.py -k "web_static_asset_cache_key_matches_current_resource_bundle" -q`

Run: `python -m pytest tests/test_web_ui_integrity.py -k "pimcore" -q`

Expected: PASS.

- [x] **Step 2: Verify diff and worktree**

Run: `git diff HEAD~2..HEAD --check` and `git status --short`

Expected: no whitespace errors and no unrelated changes.
