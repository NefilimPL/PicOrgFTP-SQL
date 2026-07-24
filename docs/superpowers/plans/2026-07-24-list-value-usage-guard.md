# List-value usage guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Block deletion of list values used by saved products in SQLite and legacy Excel modes, then let the operator open a blocking product from web and desktop UI.

**Architecture:** Add a SQLite equivalent of the Excel usage lookup and route the shared find_list_value_usage helper to the active storage adapter. Preserve backend deletion authority and the existing HTTP 409 shape; both UIs reuse their current product-load paths.

**Tech Stack:** Python 3, SQLite (sqlite3), OpenPyXL, FastAPI, vanilla JavaScript, Tkinter, pytest/unittest.

## Global Constraints

- Do not change the SQLite schema or SCHEMA_VERSION; this reads product_entries.
- Support NAZWY, TYPY, MODELE, all three fields of KOLORY, and DODATKI.
- Ignore case and diacritics; _ and - must be equivalent for DODATKI.
- Explicitly transliterate Polish Ł/ł to L/l before Unicode decomposition; Unicode NFKD alone does not decompose this character.
- A detected usage must prevent physical deletion on the backend.
- Preserve successful-delete responses and HTTP 409 keys: message, list_key, value, used_by.
- Use createElement and textContent; do not add innerHTML.

---

## File structure

- picorgftp_sql/sqlite_store.py: SQLite usage query and legacy-compatible records.
- picorgftp_sql/data_store.py: active SQLite adapter forwarder.
- picorgftp_sql/excel_utils.py: common lookup dispatcher, retaining its Excel branch.
- picorgftp_sql/web/static/app.js: web Wczytaj action for blocking records.
- picorgftp_sql/web/static/index.html: cache-key bump for JavaScript.
- picorgftp_sql/app.py: desktop usage picker and record conversion.
- Tests: test_sqlite_store.py, test_excel_utils.py, test_web_data_users.py, test_web_smoke_ci.py, test_web_ui_integrity.py, test_app_lookup_state.py, test_source_integrity.py.

### Task 1: Query usages from SQLite with legacy-compatible records

**Files:**

- Modify: picorgftp_sql/sqlite_store.py:11-20, 671-685, 3263-3428
- Test: tests/test_sqlite_store.py:860-922

**Interfaces:**

- Produces SqliteStore.find_list_value_usage(sheet: str, value: object, *, limit: int = 100) -> list[dict[str, str]].
- A result has product_id, ean, name, type_name, model, color1, color2, color3, extra, fields, and label.
- Task 2 consumes this method from SqliteDataStoreAdapter.

- [ ] **Step 1: Write failing SQLite lookup tests**

Append this helper and tests after test_add_and_remove_list_value.

~~~python
def _usage_entry() -> dict[str, str]:
    return {
        "EAN": "5901234567890", "NAZWA": "ŻYRANDOL", "TYP": "STÓŁ",
        "MODEL": "MA-03", "KOLOR1": "BIAŁY", "KOLOR2": "DĄB",
        "KOLOR3": "BIAŁY", "DODATKI": "LED-RGB", "PRODUCT_ID": "PRD-USAGE-1",
    }


def test_find_list_value_usage_matches_every_sqlite_list_field(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()
    store.save_product_entry(_usage_entry())
    expected = {
        "NAZWY": ("zyrandol", "NAZWA"), "TYPY": ("stol", "TYP"),
        "MODELE": ("ma-03", "MODEL"), "KOLORY": ("bialy", "KOLOR1, KOLOR3"),
        "DODATKI": ("led_rgb", "DODATKI"),
    }
    for sheet, (value, fields) in expected.items():
        usage = store.find_list_value_usage(sheet, value)
        assert len(usage) == 1
        assert usage[0]["product_id"] == "PRD-USAGE-1"
        assert usage[0]["fields"] == fields
        assert usage[0]["label"].startswith("ŻYRANDOL | STÓŁ | MA-03")


def test_find_list_value_usage_rejects_unknown_or_blank_list_lookups(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()
    store.save_product_entry(_usage_entry())
    assert store.find_list_value_usage("NIEZNANA", "ŻYRANDOL") == []
    assert store.find_list_value_usage("NAZWY", "") == []
~~~

- [ ] **Step 2: Run the new tests and confirm RED**

Run: python -m pytest tests/test_sqlite_store.py -k "find_list_value_usage" -q

Expected: FAIL with AttributeError because the store method is absent.

- [ ] **Step 3: Implement normalization, field mapping, and lookup**

Import unicodedata. Beside _list_value, add a map and helpers that mirror Excel normalization.

~~~python
_LIST_USAGE_FIELDS = {
    "NAZWY": (("name", NAME_HEADER),),
    "TYPY": (("type_name", TYPE_HEADER),),
    "MODELE": (("model", MODEL_HEADER),),
    "KOLORY": (
        ("color1", COLOR1_HEADER), ("color2", COLOR2_HEADER), ("color3", COLOR3_HEADER),
    ),
    "DODATKI": (("extra", EXTRA_HEADER),),
}


def _list_usage_value(sheet: str, value: object) -> str:
    text = unicodedata.normalize("NFKD", _text(value)).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char)).upper()
    return text.replace("_", "-") if sheet == "DODATKI" else text


def _usage_label(entry: dict[str, str]) -> str:
    parts = [entry["name"], entry["type_name"], entry["model"]]
    colors = " / ".join(value for value in (entry["color1"], entry["color2"], entry["color3"]) if value)
    if colors:
        parts.append(colors)
    if entry["extra"]:
        parts.append(entry["extra"])
    label = " | ".join(value for value in parts if value)
    suffix = entry["ean"] or entry["product_id"]
    return f"{label} - {suffix}" if label and suffix else label or suffix
~~~

Add this method directly before remove_list_value. It selects product columns once, retains rowid order, returns all matched color headers, and preserves the limit contract.

~~~python
def find_list_value_usage(self, sheet: str, value: object, *, limit: int = 100) -> list[dict[str, str]]:
    fields = _LIST_USAGE_FIELDS.get(sheet)
    needle = _list_usage_value(sheet, value)
    if not fields or not needle:
        return []
    self.initialize()
    with self.connection() as conn:
        rows = conn.execute(
            "SELECT product_id, ean, name, type_name, model, color1, color2, color3, extra "
            "FROM product_entries ORDER BY rowid"
        ).fetchall()
    usage = []
    for row in rows:
        entry = {key: _text(row[key]) for key in row.keys()}
        matched = [header for column, header in fields if _list_usage_value(sheet, entry[column]) == needle]
        if matched:
            usage.append({**entry, "fields": ", ".join(matched), "label": _usage_label(entry)})
        if len(usage) >= max(1, int(limit or 100)):
            break
    return usage
~~~

- [ ] **Step 4: Run focused storage checks and confirm GREEN**

Run: python -m pytest tests/test_sqlite_store.py -k "find_list_value_usage or lists_roundtrip or add_and_remove_list_value" -q

Expected: PASS.

- [ ] **Step 5: Commit the storage behavior**

~~~powershell
git add picorgftp_sql/sqlite_store.py tests/test_sqlite_store.py
git commit -m "feat: find list value usage in sqlite"
~~~

### Task 2: Dispatch through active storage and preserve backend blocking

**Files:**

- Modify: picorgftp_sql/data_store.py:44-56
- Modify: picorgftp_sql/excel_utils.py:409-477
- Test: tests/test_excel_utils.py:47-75
- Test: tests/test_web_data_users.py:252-272
- Test: tests/test_web_smoke_ci.py

**Interfaces:**

- Consumes SqliteStore.find_list_value_usage from Task 1.
- Produces SqliteDataStoreAdapter.find_list_value_usage(sheet, value, *, limit=100).
- Preserves web_data.remove_list_value raising ListValueInUseError and /api/lists/{list_key} returning 409 with used_by.

- [ ] **Step 1: Write failing dispatcher and HTTP contract tests**

Add the following to tests/test_excel_utils.py (import Mock with unittest.mock).

~~~python
def test_find_list_value_usage_dispatches_to_active_sqlite_store() -> None:
    adapter = Mock()
    adapter.find_list_value_usage.return_value = [{"product_id": "PRD-1"}]
    with patch.object(excel_utils, "_active_sqlite_store", return_value=adapter):
        result = excel_utils.find_list_value_usage("NAZWY", "MAGGIORE")
    assert result == [{"product_id": "PRD-1"}]
    adapter.find_list_value_usage.assert_called_once_with("NAZWY", "MAGGIORE", limit=100)
~~~

Add the following to WebSmokeCiTests.

~~~python
def test_list_remove_route_serializes_blocking_products(self) -> None:
    client = TestClient(web_app.app)
    usage = [{"product_id": "PRD-1", "ean": "5901234567890", "fields": "NAZWA"}]
    error = web_data.ListValueInUseError("names", "MAGGIORE", usage)
    with (
        patch.object(web_app, "_require_user", return_value={"username": "operator"}),
        patch.object(web_app, "remove_list_value", side_effect=error),
    ):
        response = client.request("DELETE", "/api/lists/names", json={"value": "MAGGIORE"})
    self.assertEqual(response.status_code, 409)
    self.assertEqual(response.json()["detail"], {
        "message": str(error), "list_key": "names", "value": "MAGGIORE", "used_by": usage,
    })
~~~

Keep and extend the current web_data test asserting that remove_from_list is not called.
Add a legacy-workbook regression that saves STÓŁ in TYP and confirms
find_list_value_usage("TYPY", "stol") reports TYP, so the same rule protects
both persistence modes.

- [ ] **Step 2: Run tests and confirm RED**

Run: python -m pytest tests/test_excel_utils.py tests/test_web_data_users.py tests/test_web_smoke_ci.py -k "list_value_usage or list_remove_route" -q

Expected: FAIL because the adapter and dispatcher method are absent.

- [ ] **Step 3: Add adapter forwarding and common dispatch**

In SqliteDataStoreAdapter add:

~~~python
def find_list_value_usage(self, sheet: str, value: object, *, limit: int = 100) -> list[dict[str, str]]:
    return self.store.find_list_value_usage(sheet, value, limit=limit)
~~~

At the beginning of excel_utils.find_list_value_usage, before opening the workbook, add:

~~~python
sqlite_store = _active_sqlite_store()
if sqlite_store is not None:
    return sqlite_store.find_list_value_usage(sheet_name, value, limit=limit)
~~~

In _normalize_list_usage_value, transliterate Ł/ł before the existing NFKD
normalization so its behavior matches the SQLite helper exactly:

~~~python
raw = _normalize_cell(value).replace("Ł", "L").replace("ł", "l")
text = unicodedata.normalize("NFKD", raw).casefold()
~~~

Leave the Excel branch, web_data.remove_list_value, and FastAPI route unchanged; they already turn a non-empty result into backend blocking and the required 409 payload.

- [ ] **Step 4: Run focused guard checks and confirm GREEN**

Run: python -m pytest tests/test_excel_utils.py tests/test_web_data_users.py tests/test_web_smoke_ci.py -k "list_value_usage or list_remove_route" -q

Expected: PASS.

- [ ] **Step 5: Commit integration**

~~~powershell
git add picorgftp_sql/data_store.py picorgftp_sql/excel_utils.py tests/test_excel_utils.py tests/test_web_data_users.py tests/test_web_smoke_ci.py
git commit -m "fix: block used list values in sqlite mode"
~~~

### Task 3: Open a blocking product from the web modal

**Files:**

- Modify: picorgftp_sql/web/static/app.js:2174-2208
- Modify: picorgftp_sql/web/static/index.html:7-8
- Test: tests/test_web_ui_integrity.py

**Interfaces:**

- Consumes 409 detail.used_by records and fillForm(entry, { loadPhotos: true }).
- Produces a Wczytaj action per renderListUsageModal row.

- [ ] **Step 1: Write the failing web UI contract**

~~~python
def test_list_usage_modal_opens_the_selected_blocking_product(self) -> None:
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("function renderListUsageModal")
    end = source.index("const trackedProductFields", start)
    renderer = source[start:end]
    self.assertIn('button.textContent = "Wczytaj"', renderer)
    self.assertIn("fillForm(item, { loadPhotos: true });", renderer)
    self.assertIn("closeModals();", renderer)
    self.assertIn("row.append(text, button);", renderer)
    self.assertNotIn("innerHTML", renderer)
~~~

- [ ] **Step 2: Run the contract test and confirm RED**

Run: python -m pytest tests/test_web_ui_integrity.py -k "list_usage_modal" -q

Expected: FAIL because each row appends only text.

- [ ] **Step 3: Add the safe per-product button and refresh cache key**

Inside renderListUsageModal, use the renderEntryModal button pattern.

~~~javascript
const button = document.createElement("button");
button.type = "button";
button.textContent = "Wczytaj";
button.addEventListener("click", () => {
  fillForm(item, { loadPhotos: true });
  closeModals();
});
text.append(title, details);
row.append(text, button);
~~~

The usage record already includes all fillForm fields; do not add a new endpoint. Change both app.css and app.js query strings in index.html to the identical cache value 20260724-list-usage-guard1.

- [ ] **Step 4: Run web static and smoke checks**

Run: python -m pytest tests/test_web_ui_integrity.py tests/test_web_smoke_ci.py -q

Expected: PASS.

- [ ] **Step 5: Commit the web action**

~~~powershell
git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/index.html tests/test_web_ui_integrity.py
git commit -m "feat: open products from list usage modal"
~~~

### Task 4: Open a blocking product from the desktop picker

**Files:**

- Modify: picorgftp_sql/app.py:1904-1979, 7055-7088
- Test: tests/test_app_lookup_state.py
- Test: tests/test_source_integrity.py

**Interfaces:**

- Produces App._record_from_list_usage(item) and App._show_list_usage_dialog(value, list_label, usage).
- Consumes usage records plus entries_by_id / entries and calls existing App._load_entry_record(record).

- [ ] **Step 1: Write failing desktop helper and contract tests**

Add this headless test to tests/test_app_lookup_state.py.

~~~python
def test_record_from_list_usage_prefers_cached_product_id_and_has_fallback(self) -> None:
    cached = {"PRODUCT_ID": "PRD-1", "EAN": "5901234567890", "NAZWA": "MAGGIORE"}
    harness = type("Harness", (), {"entries_by_id": {"PRD-1": cached}, "entries": {}})()
    self.assertEqual(App._record_from_list_usage(harness, {"product_id": "prd-1"}), cached)
    fallback = App._record_from_list_usage(harness, {
        "product_id": "PRD-2", "ean": "5900000000000", "name": "LUNA",
        "type_name": "STOL", "model": "L-01", "color1": "BIALY",
        "color2": "", "color3": "", "extra": "NO-LED",
    })
    self.assertEqual(fallback["PRODUCT_ID"], "PRD-2")
    self.assertEqual(fallback["NAZWA"], "LUNA")
~~~

Add this static contract to tests/test_source_integrity.py.

~~~python
def test_desktop_list_usage_dialog_loads_the_selected_product(self) -> None:
    source = (Path(__file__).resolve().parents[1] / "picorgftp_sql" / "app.py").read_text(encoding="utf-8")
    self.assertIn("def _record_from_list_usage", source)
    self.assertIn("def _show_list_usage_dialog", source)
    self.assertIn('text="Wczytaj zaznaczony"', source)
    self.assertIn("A._load_entry_record(record)", source)
~~~

- [ ] **Step 2: Run the desktop tests and confirm RED**

Run: python -m pytest tests/test_app_lookup_state.py tests/test_source_integrity.py -k "list_usage" -q

Expected: FAIL because neither helper exists.

- [ ] **Step 3: Add record conversion and modal picker**

Put both helpers beside _prompt_select_entry_record. Resolve product_id in entries_by_id, then EAN in entries, then build a normalized Excel-header record.

~~~python
def _record_from_list_usage(A, item):
    product_id = G(item.get("product_id") or B).strip().upper()
    if product_id and product_id in A.entries_by_id:
        return dict(A.entries_by_id[product_id])
    ean = G(item.get("ean") or B).strip().upper()
    if ean and ean in A.entries:
        record = dict(A.entries[ean])
        record[EAN_HEADER] = ean
        return record
    return {
        PRODUCT_ID_HEADER: product_id, EAN_HEADER: ean,
        NAME_HEADER: G(item.get("name") or B).strip().upper(),
        TYPE_HEADER: G(item.get("type_name") or B).strip().upper(),
        MODEL_HEADER: G(item.get("model") or B).strip().upper(),
        COLOR1_HEADER: G(item.get("color1") or B).strip().upper(),
        COLOR2_HEADER: G(item.get("color2") or B).strip().upper(),
        COLOR3_HEADER: G(item.get("color3") or B).strip().upper(),
        EXTRA_HEADER: G(item.get("extra") or B).strip().upper(),
    }
~~~

Implement the picker with this complete body; it intentionally uses the same Tk aliases and focus restoration pattern as the existing selector.

~~~python
def _show_list_usage_dialog(A, value, list_label, usage):
    if not usage:
        return
    A._last_focus_widget = A.focus_get()
    win = F.Toplevel(A)
    win.title(LIST_REMOVE_DIALOG_TITLE)
    win.transient(A)
    win.grab_set()
    C.Label(
        win,
        text=f"Nie usunieto '{value}' z listy {list_label}, bo wpis jest uzywany.",
    ).pack(padx=10, pady=(10, 6), anchor="w")
    body = C.Frame(win)
    body.pack(fill=z, expand=J, padx=10, pady=(0, 8))
    listbox = F.Listbox(body, height=min(8, Q(usage)), exportselection=0)
    scroll = C.Scrollbar(body, orient=An, command=listbox.yview)
    listbox.configure(yscrollcommand=scroll.set)
    scroll.pack(side=AV, fill="y")
    listbox.pack(side=Am, fill=z, expand=J)
    for item in usage:
        product_id = G(item.get("product_id") or B).strip() or "BRAK-ID"
        ean = G(item.get("ean") or B).strip() or q
        fields = G(item.get("fields") or B).strip() or "-"
        label = G(item.get("label") or B).strip() or "-"
        listbox.insert(F.END, f"{product_id} | EAN: {ean} | {fields} | {label}")
    listbox.selection_set(0)

    def _cancel():
        win.destroy()

    def _choose():
        selection = listbox.curselection()
        if not selection:
            return
        record = A._record_from_list_usage(usage[selection[0]])
        win.destroy()
        A._load_entry_record(record)
        editor = Aj(A, "_list_editor_window", I)
        close_editor = getattr(editor, "_close_window", I)
        if callable(close_editor):
            close_editor()
        A.deiconify()
        A.lift()
        A.focus_force()

    buttons = C.Frame(win)
    buttons.pack(fill="x", padx=10, pady=(0, 10))
    C.Button(buttons, text="Wczytaj zaznaczony", command=_choose).pack(side=Am)
    C.Button(buttons, text=CANCEL_LABEL, command=_cancel).pack(side=AV)
    listbox.bind("<Double-Button-1>", lambda _event: _choose())
    win.protocol("WM_DELETE_WINDOW", _cancel)
    A.wait_window(win)
    A._restore_focus()
~~~

Replace the lines/showwarning branch in _remove_list_item with:

~~~python
if usage:
    A._show_list_usage_dialog(C_, G_, usage)
    return
~~~

The return prevents remove_from_list after the picker closes.

- [ ] **Step 4: Run targeted desktop checks and confirm GREEN**

Run: python -m pytest tests/test_app_lookup_state.py tests/test_source_integrity.py tests/test_desktop_smoke_ci.py -q

Expected: PASS without a GUI display.

- [ ] **Step 5: Commit the desktop picker**

~~~powershell
git add picorgftp_sql/app.py tests/test_app_lookup_state.py tests/test_source_integrity.py
git commit -m "feat: load products from desktop list usage"
~~~

### Task 5: Regression verification

**Files:**

- Review: all files changed in Tasks 1-4

- [ ] **Step 1: Compile Python sources**

Run: python -m compileall -q picorgftp_sql tests

Expected: exit code 0 and no output.

- [ ] **Step 2: Run all directly related tests**

Run: python -m pytest tests/test_sqlite_store.py tests/test_excel_utils.py tests/test_web_data_users.py tests/test_web_smoke_ci.py tests/test_web_ui_integrity.py tests/test_app_lookup_state.py tests/test_source_integrity.py tests/test_desktop_smoke_ci.py -q

Expected: PASS.

- [ ] **Step 3: Run the full suite**

Run: python -m pytest -q

Expected: PASS with no failures or errors.

- [ ] **Step 4: Check scope and whitespace**

Run: git diff --check

Expected: exit code 0 and no output.

Run: git status --short

Expected: no uncommitted implementation files; only this plan may remain uncommitted if intentionally left out of task commits.
