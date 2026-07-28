# Product Query and Desktop Startup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zastąpić pełne skany produktów selektywnymi zapytaniami store i uruchamiać desktop przed zakończeniem ładowania katalogu.

**Architecture:** Warstwa data store otrzyma wspólny kontrakt lookup/search/suggest. SQLite zrealizuje go przez indeksowane SQL z twardymi limitami, a Excel przez cache'owany snapshot i czyste funkcje filtrujące. Web deleguje wyszukiwanie do store i anuluje nieaktualne autocomplete, natomiast desktop publikuje kompletny snapshot z workera do głównego wątku Tk.

**Tech Stack:** Python 3.14, SQLite, openpyxl, Tkinter, FastAPI, JavaScript, Node `node:test`, pytest.

## Global Constraints

- Zachowaj nazwy pól, normalizację, kolejność trafień i format istniejących odpowiedzi API.
- SQLite nie może używać fallbacku, który wywołuje `load_lists()` dla lookup/search/suggest.
- Każde wyszukiwanie i podpowiedź ma twardy limit po stronie serwera.
- Excel pozostaje wspierany i nie utrzymuje otwartego uchwytu workbooka.
- Worker desktopowy nie wywołuje metod Tk.
- Błąd ładowania desktopu pozostawia działające okno i możliwość retry.
- Nie usuwaj pełnej listy produktów z bootstrapu webowego w tym pakiecie; zmiana początkowego UX nie jest zatwierdzona.
- Nie zmieniaj wyglądu formularza ani publicznych nazw endpointów.

## File Structure

- Create: `picorgftp_sql/product_queries.py` — typ kryteriów i zgodny fallback dla rekordów pamięciowych.
- Create: `picorgftp_sql/desktop_data_loader.py` — niemutowalny snapshot oraz praca poza Tk.
- Create: `picorgftp_sql/web/static/latest-request.js` — anulowanie poprzedniego requestu pola.
- Create: `tests/test_product_queries.py` — wspólne kontrakty SQLite/legacy.
- Create: `tests/test_desktop_data_loader.py` — worker, publikacja i retry.
- Create: `tests/js/latest-request.test.js` — zachowanie AbortController.
- Modify: `picorgftp_sql/sqlite_store.py:3293-3488` — selektywne SQL i indeksy.
- Modify: `picorgftp_sql/data_store.py:14-64` — wspólny interfejs adapterów.
- Modify: `picorgftp_sql/web_data.py:951-1013,1442-1546` — delegacja do store.
- Modify: `picorgftp_sql/excel_utils.py:325-411,603-700` — cache snapshotu po mtime.
- Modify: `picorgftp_sql/app.py:250-300` — start workera i publikacja do Tk.
- Modify: `picorgftp_sql/web/static/app.js:1920-2090,7370-7420` — signal i ostatnia odpowiedź.
- Modify: `picorgftp_sql/web/static/index.html:710` — załadowanie helpera przed `app.js`.
- Modify: testy API produktów i `tests/test_app_performance_helpers.py`.

---

### Task 1: Wspólny kontrakt zapytań produktowych

**Files:**

- Create: `picorgftp_sql/product_queries.py`
- Modify: `picorgftp_sql/data_store.py:14-64`
- Create: `tests/test_product_queries.py`

**Interfaces:**

- Produces: `ProductSearchCriteria`; `filter_product_records(records, criteria, limit) -> list[dict[str, str]]`; metody adapterów `get_product_by_id`, `get_product_by_ean`, `search_product_entries`, `suggest_product_field`.
- Consumes: rekordy w obecnym kształcie Excel/SQLite i stałe nagłówków z `excel_utils.py`.

- [ ] **Step 1: Napisz test dokładnych lookupów fallbacku**

```python
from picorgftp_sql.product_queries import (
    ProductSearchCriteria,
    filter_product_records,
)


RECORDS = [
    {"PRODUCT_ID": "P-1", "EAN": "5901", "NAZWA": "ALFA", "TYP": "STÓŁ", "MODEL": "A1"},
    {"PRODUCT_ID": "P-2", "EAN": "5902", "NAZWA": "BETA", "TYP": "SZAFA", "MODEL": "B1"},
]


def test_filter_product_records_prefers_exact_identity_and_limits():
    criteria = ProductSearchCriteria(product_id="p-1")
    assert filter_product_records(RECORDS, criteria, limit=1) == [RECORDS[0]]
```

- [ ] **Step 2: Uruchom test i potwierdź brak modułu**

Run: `python -m pytest tests/test_product_queries.py::test_filter_product_records_prefers_exact_identity_and_limits -v`

Expected: FAIL podczas importu `picorgftp_sql.product_queries`.

- [ ] **Step 3: Dodaj typ i pamięciowy fallback**

```python
from dataclasses import dataclass
from picorgftp_sql.excel_utils import (
    EAN_HEADER,
    MODEL_HEADER,
    NAME_HEADER,
    PRODUCT_ID_HEADER,
    TYPE_HEADER,
)


@dataclass(frozen=True)
class ProductSearchCriteria:
    product_id: str = ""
    ean: str = ""
    name: str = ""
    type_name: str = ""
    model: str = ""


def _key(value: object) -> str:
    return str(value or "").strip().casefold()


def filter_product_records(records, criteria: ProductSearchCriteria, limit: int):
    bounded_limit = max(1, min(int(limit), 100))
    result = []
    for record in records:
        if criteria.product_id and _key(record.get(PRODUCT_ID_HEADER)) != _key(criteria.product_id):
            continue
        if criteria.ean and _key(record.get(EAN_HEADER)) != _key(criteria.ean):
            continue
        if criteria.name and _key(record.get(NAME_HEADER)) != _key(criteria.name):
            continue
        if criteria.type_name and _key(record.get(TYPE_HEADER)) != _key(criteria.type_name):
            continue
        if criteria.model and _key(record.get(MODEL_HEADER)) != _key(criteria.model):
            continue
        result.append(dict(record))
        if len(result) == bounded_limit:
            break
    return result
```

- [ ] **Step 4: Dodaj metody obu adapterów**

`LegacyDataStore` używa `prepare_excel_lists()[ENTRY_RECORDS_KEY]` i powyższego fallbacku. `SqliteDataStoreAdapter` deleguje do metod store o tych samych nazwach:

```python
def get_product_by_ean(self, ean: str):
    return self.store.get_product_by_ean(ean)

def get_product_by_id(self, product_id: str):
    return self.store.get_product_by_id(product_id)

def search_product_entries(self, criteria: ProductSearchCriteria, limit: int = 50):
    return self.store.search_product_entries(criteria, limit=limit)

def suggest_product_field(
    self,
    field: str,
    prefix: str,
    context: dict[str, str],
    limit: int = 20,
):
    return self.store.suggest_product_field(
        field,
        prefix,
        context,
        limit=limit,
    )
```

- [ ] **Step 5: Uruchom kontrakt fallbacku**

Run: `python -m pytest tests/test_product_queries.py -k "filter or legacy" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add picorgftp_sql/product_queries.py picorgftp_sql/data_store.py tests/test_product_queries.py
git commit -m "refactor: define product query contract"
```

### Task 2: Indeksowane lookupy i wyszukiwanie SQLite

**Files:**

- Modify: `picorgftp_sql/sqlite_store.py:752-1120,3293-3488`
- Modify: `tests/test_product_queries.py`
- Modify: `tests/test_sqlite_store.py:878-975`

**Interfaces:**

- Consumes: `ProductSearchCriteria`.
- Produces: cztery metody `SqliteStore` zgodne z adapterem z Task 1.

- [ ] **Step 1: Napisz test zakazujący `load_lists()`**

```python
def test_sqlite_identity_lookup_does_not_load_all_lists(tmp_path, monkeypatch):
    adapter = SqliteDataStoreAdapter(str(tmp_path / "products.sqlite"))
    adapter.save_product_entry({
        "product_id": "P-1",
        "ean": "5901234567890",
        "name": "ALFA",
        "type_name": "STÓŁ",
        "model": "A1",
    })
    monkeypatch.setattr(
        adapter.store,
        "load_lists",
        lambda: (_ for _ in ()).throw(AssertionError("full load")),
    )
    assert adapter.get_product_by_ean("5901234567890")["product_id"] == "P-1"
```

- [ ] **Step 2: Uruchom test i potwierdź brak metody store**

Run: `python -m pytest tests/test_product_queries.py::test_sqlite_identity_lookup_does_not_load_all_lists -v`

Expected: FAIL z `AttributeError` dla `get_product_by_ean`.

- [ ] **Step 3: Dodaj lookupy dokładne**

```python
def get_product_by_ean(self, ean: str) -> dict[str, str] | None:
    self.initialize()
    with self.connection() as conn:
        row = conn.execute(
            "SELECT * FROM product_entries WHERE ean = ? LIMIT 1",
            (_text(ean),),
        ).fetchone()
    return self._product_entry_from_row(row) if row else None
```

Dodaj `_product_entry_from_row`, `get_product_by_id` i użyj istniejących nazw kolumn. Nie konwertuj całej tabeli do listy.

- [ ] **Step 4: Dodaj bezpieczny builder kryteriów**

Użyj stałej mapy pól zamiast interpolowania wejścia:

```python
_PRODUCT_SEARCH_COLUMNS = {
    "product_id": "product_id",
    "ean": "ean",
    "name": "name",
    "type_name": "type_name",
    "model": "model",
}
```

Buduj `WHERE` wyłącznie z tej mapy, przekazuj wartości jako parametry i dodaj `LIMIT ?`. Dokładne ID/EAN mają pierwszeństwo przed polami formularza.

- [ ] **Step 5: Dodaj indeksy i test planu zapytania**

W inicjalizacji zachowaj obecne indeksy i dodaj brakujące indeksy odpowiadające finalnym zapytaniom. Test:

```python
plan = conn.execute(
    "EXPLAIN QUERY PLAN SELECT * FROM product_entries WHERE ean = ? LIMIT 1",
    ("5901234567890",),
).fetchall()
assert any("INDEX" in str(row).upper() for row in plan)
assert not any("SCAN PRODUCT_ENTRIES" in str(row).upper() for row in plan)
```

- [ ] **Step 6: Dodaj `suggest_product_field`**

Waliduj `field` przez zamkniętą mapę kolumn. Kontekst dodaje parametryczne warunki równości. Zapytanie używa `SELECT DISTINCT`, odrzuca puste wartości, stabilnie sortuje i kończy `LIMIT ?`.

- [ ] **Step 7: Uruchom testy SQLite produktu**

Run: `python -m pytest tests/test_product_queries.py tests/test_sqlite_store.py -k "product or lists or entry" -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add picorgftp_sql/sqlite_store.py tests/test_product_queries.py tests/test_sqlite_store.py
git commit -m "perf: query sqlite products selectively"
```

### Task 3: Delegacja web search/suggestions/save do store

**Files:**

- Modify: `picorgftp_sql/web_data.py:951-1013,1442-1546`
- Modify: testy endpointów webowych produktów
- Modify: `tests/test_product_queries.py`

**Interfaces:**

- Consumes: metody aktywnego store z Tasks 1–2.
- Produces: niezmienione `field_suggestions`, `search_entries`, `find_entry_by_identity`, `save_web_entry`.

- [ ] **Step 1: Dodaj test z aktywnym spy store**

```python
def test_search_entries_delegates_to_active_store(monkeypatch):
    store = Mock()
    store.search_product_entries.return_value = [
        {"product_id": "P-1", "ean": "5901", "name": "ALFA"}
    ]
    monkeypatch.setattr(web_data, "get_active_store", lambda: store)

    result = web_data.search_entries(ean="5901", limit=10)

    assert result[0]["product_id"] == "P-1"
    store.search_product_entries.assert_called_once()
```

Dodaj analogiczny test podpowiedzi i lookupu przed zapisem.

- [ ] **Step 2: Uruchom test i potwierdź starą pełną ścieżkę**

Run: `python -m pytest tests/test_product_queries.py -k "delegates_to_active_store" -v`

Expected: FAIL, spy store nie zostaje wywołany.

- [ ] **Step 3: Zastąp materializację delegacją**

```python
def find_entry_by_identity(*, product_id: str = "", ean: str = ""):
    store = get_active_store()
    if product_id:
        return store.get_product_by_id(product_id)
    if ean:
        return store.get_product_by_ean(ean)
    return None
```

`search_entries` tworzy `ProductSearchCriteria`; `field_suggestions` przekazuje pole, wpisany prefix i jawny słownik kontekstu. `save_web_entry` wykonuje dokładnie jeden lookup tożsamości.

- [ ] **Step 4: Dodaj test limitu endpointu**

Wywołaj `/api/entries/search` oraz `/api/suggestions` z limitem większym od 100 i sprawdź, że store otrzymał limit równy serwerowej granicy.

- [ ] **Step 5: Uruchom testy web data**

Run: `python -m pytest tests/test_product_queries.py tests/test_web_app_files.py -k "entry or suggestion or product" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add picorgftp_sql/web_data.py tests/test_product_queries.py tests/test_web_app_files.py
git commit -m "perf: delegate product search to data store"
```

### Task 4: Anulowanie nieaktualnego autocomplete

**Files:**

- Create: `picorgftp_sql/web/static/latest-request.js`
- Create: `tests/js/latest-request.test.js`
- Modify: `picorgftp_sql/web/static/index.html:710`
- Modify: `picorgftp_sql/web/static/app.js:1920-2090`
- Modify: test assetów w `tests/test_web_app_files.py`

**Interfaces:**

- Produces: `window.PicOrg.LatestRequest`.
- Consumes: `requestJson(path, {signal})` i lokalny lifecycle jednego pola autocomplete.

- [ ] **Step 1: Napisz test Node dla anulowania**

```javascript
const test = require("node:test");
const assert = require("node:assert/strict");
global.window = { PicOrg: {} };
require("../../picorgftp_sql/web/static/latest-request.js");

test("next aborts the previous request and marks only latest current", () => {
  const latest = new window.PicOrg.LatestRequest();
  const first = latest.next();
  const second = latest.next();
  assert.equal(first.signal.aborted, true);
  assert.equal(first.isCurrent(), false);
  assert.equal(second.signal.aborted, false);
  assert.equal(second.isCurrent(), true);
});
```

- [ ] **Step 2: Uruchom test i potwierdź brak pliku**

Run: `node --test tests/js/latest-request.test.js`

Expected: FAIL z `MODULE_NOT_FOUND`.

- [ ] **Step 3: Dodaj helper bez zależności od DOM**

```javascript
(function registerLatestRequest(global) {
  global.PicOrg = global.PicOrg || {};
  global.PicOrg.LatestRequest = class LatestRequest {
    constructor() {
      this.controller = null;
      this.version = 0;
    }
    next() {
      if (this.controller) this.controller.abort();
      this.controller = new AbortController();
      const version = ++this.version;
      return {
        signal: this.controller.signal,
        isCurrent: () => version === this.version,
      };
    }
    cancel() {
      if (this.controller) this.controller.abort();
      this.version += 1;
    }
  };
})(window);
```

- [ ] **Step 4: Podłącz helper do każdego pola**

Zmień `remoteSuggestions(fieldName)` na `remoteSuggestions(fieldName, signal)` i przekaż `{signal}` do `requestJson`. W `setupAutocomplete()` utwórz jeden `LatestRequest` na pole. Przed nowym timerem wywołaj `next()`, a wynik renderuj tylko przy `token.isCurrent()` i aktywnym panelu. `AbortError` ignoruj; inne błędy zachowują istniejącą obsługę.

- [ ] **Step 5: Dodaj asset przed `app.js` i test kolejności**

```html
<script src="/static/latest-request.js?v=20260727-product-query1"></script>
<script src="/static/app.js?v=20260727-product-query1"></script>
```

Test Python odczytuje `index.html` i sprawdza, że indeks pierwszego src jest mniejszy od indeksu `app.js`.

- [ ] **Step 6: Uruchom JS i testy assetów**

Run: `node --test tests/js/latest-request.test.js`

Run: `node --check picorgftp_sql/web/static/latest-request.js`

Run: `node --check picorgftp_sql/web/static/app.js`

Run: `python -m pytest tests/test_web_app_files.py -k "static or asset" -v`

Expected: wszystkie polecenia PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/web/static/latest-request.js picorgftp_sql/web/static/app.js picorgftp_sql/web/static/index.html tests/js/latest-request.test.js tests/test_web_app_files.py
git commit -m "perf: cancel stale autocomplete requests"
```

### Task 5: Cache legacy workbooka po mtime

**Files:**

- Modify: `picorgftp_sql/excel_utils.py:325-411,603-700`
- Modify: `tests/test_product_queries.py`
- Test: istniejące testy Excel/list.

**Interfaces:**

- Produces: `_workbook_snapshot_key(path) -> tuple[str, int, int]`; `clear_excel_snapshot_cache(path: str | None = None) -> None`.
- Consumes: `prepare_excel_lists()` i wszystkie udane zapisy workbooka.

- [ ] **Step 1: Napisz test jednego odczytu workbooka**

```python
def test_prepare_excel_lists_reuses_snapshot_until_mtime_changes(monkeypatch, tmp_path):
    workbook_path = tmp_path / "data.xlsx"
    write_product_workbook(workbook_path)
    loads = 0
    original_load_workbook = excel_utils.load_workbook

    def fake_load_workbook(*args, **kwargs):
        nonlocal loads
        loads += 1
        return original_load_workbook(*args, **kwargs)

    monkeypatch.setattr(excel_utils, "load_workbook", fake_load_workbook)
    monkeypatch.setattr(
        excel_utils.settings,
        "LISTS_WORKBOOK_PATH",
        str(workbook_path),
    )
    clear_excel_snapshot_cache()

    excel_utils.prepare_excel_lists()
    excel_utils.prepare_excel_lists()

    assert loads == 1
```

Na początku `tests/test_product_queries.py` dodaj helper:

```python
def write_product_workbook(path: Path) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name in ("NAZWY", "TYPY", "MODELE", "KOLORY", "DODATKI"):
        workbook.create_sheet(sheet_name)
    entries = workbook.create_sheet("ENTRIES")
    entries.append(excel_utils.ENTRY_HEADERS)
    entries.append([
        "5901234567890",
        "ALFA",
        "STÓŁ",
        "A1",
        "BIAŁY",
        "",
        "",
        "NO-LED",
        "P-1",
    ])
    workbook.save(path)
```

Zaimportuj `Path` oraz `Workbook` z `openpyxl`.

- [ ] **Step 2: Uruchom test i potwierdź dwa odczyty**

Run: `python -m pytest tests/test_product_queries.py -k "reuses_snapshot" -v`

Expected: FAIL z `assert 2 == 1`.

- [ ] **Step 3: Dodaj cache chroniony blokadą**

Klucz zawiera `Path.resolve()`, `st_mtime_ns` i `st_size`. Wartość jest głęboką, niemutowalną kopią danych potrzebnych przez aplikację, nie obiektem `Workbook`. Każdy zwracany payload jest kopią, aby konsument nie modyfikował cache.

```python
def clear_excel_snapshot_cache(path: str | None = None) -> None:
    with _EXCEL_CACHE_LOCK:
        if path is None:
            _EXCEL_CACHE.clear()
        else:
            resolved = str(Path(path).resolve())
            for key in list(_EXCEL_CACHE):
                if key[0] == resolved:
                    _EXCEL_CACHE.pop(key, None)
```

- [ ] **Step 4: Unieważnij cache po każdym udanym zapisie**

Wywołaj `clear_excel_snapshot_cache(active_path)` dopiero po sukcesie `workbook.save`. Dodaj test: nieudany save zachowuje poprzedni kompletny snapshot, udany save wymusza kolejny odczyt.

- [ ] **Step 5: Uruchom testy Excel**

Run: `python -m pytest tests/test_product_queries.py tests -k "excel and (list or product or entry)" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add picorgftp_sql/excel_utils.py tests/test_product_queries.py
git commit -m "perf: cache legacy excel product snapshot"
```

### Task 6: Asynchroniczny start danych desktopu

**Files:**

- Create: `picorgftp_sql/desktop_data_loader.py`
- Create: `tests/test_desktop_data_loader.py`
- Modify: `picorgftp_sql/app.py:250-300`
- Modify: `tests/test_app_performance_helpers.py`

**Interfaces:**

- Produces: `DesktopDataSnapshot`; `load_desktop_data() -> DesktopDataSnapshot`; `DesktopDataLoader.start(on_success, on_error) -> bool`.
- Consumes: istniejące `prepare_excel_lists()` i dane formularza desktopowego.

- [ ] **Step 1: Napisz test workera bez wywołania callbacku z obcego wątku**

```python
def test_loader_posts_result_through_scheduler():
    scheduled = []
    received = []
    errors = []
    loader = DesktopDataLoader(
        load=lambda: DesktopDataSnapshot(lists={"NAZWY": ["ALFA"]}, entries=()),
        schedule=lambda callback: scheduled.append(callback),
    )

    assert loader.start(on_success=lambda snapshot: received.append(snapshot), on_error=errors.append)
    loader.join_for_test(timeout=1.0)

    assert received == []
    scheduled[0]()
    assert received[0].lists["NAZWY"] == ["ALFA"]
```

- [ ] **Step 2: Uruchom test i potwierdź brak modułu**

Run: `python -m pytest tests/test_desktop_data_loader.py -v`

Expected: FAIL podczas importu.

- [ ] **Step 3: Zaimplementuj loader**

`DesktopDataSnapshot` jest `@dataclass(frozen=True)`. Loader używa jednego daemon thread, blokady zapobiegającej podwójnemu startowi i przekazanego `schedule`, które w aplikacji będzie wrapperem `self.after(0, callback)`.

Worker wywołuje tylko `load`; sukces i błąd przekazuje przez `schedule`.

- [ ] **Step 4: Podłącz minimalny UI**

W konstruktorze `App`:

1. zbuduj widgety i stan `data_loading=True`;
2. wyłącz akcje wymagające produktów;
3. uruchom `DesktopDataLoader`;
4. w `_apply_desktop_data_snapshot` podmień cały snapshot, odśwież listy i włącz akcje;
5. w `_handle_desktop_data_error` zachowaj UI, pokaż istniejący komunikat i przycisk retry.

Nie odczytuj ani nie modyfikuj widgetu wewnątrz `load_desktop_data`.

- [ ] **Step 5: Dodaj test kolejności startu**

Zamockuj wolny loader bramką `threading.Event`. Utwórz App w trybie headless, sprawdź istnienie głównego widoku i stan loading przed zwolnieniem bramki, następnie opublikuj snapshot i sprawdź stan ready.

- [ ] **Step 6: Uruchom testy desktopu**

Run: `python -m pytest tests/test_desktop_data_loader.py tests/test_app_performance_helpers.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/desktop_data_loader.py picorgftp_sql/app.py tests/test_desktop_data_loader.py tests/test_app_performance_helpers.py
git commit -m "perf: load desktop product data after ui startup"
```

### Task 7: Benchmark 100 000 produktów i pełna regresja

**Files:**

- Modify: `tests/test_ci_performance_smoke.py`
- Modify: `tests/test_product_queries.py`
- Modify: `docs/superpowers/specs/2026-07-27-product-query-and-desktop-startup-design.md`

**Interfaces:**

- Consumes: selektywne zapytania, autocomplete helper, cache Excel i desktop loader.
- Produces: powtarzalny generator danych i raport p50/p95.

- [ ] **Step 1: Dodaj generator 100 000 rekordów bez workbooka**

Użyj `executemany` bezpośrednio w testowym SQLite po `store.initialize()`. Dane mają unikalne ID/EAN oraz powtarzalne nazwy/typy/modele, aby podpowiedzi miały realistyczne duplikaty.

- [ ] **Step 2: Dodaj asercję planu oraz budżety**

Zmierz osobno 200 ciepłych lookupów i 100 podpowiedzi z limitem 50. Oblicz p95 przez `statistics.quantiles(samples, n=100)[94]`.

Budżety:

```python
assert lookup_p95 < 0.050
assert suggestion_p95 < 0.200
assert len(suggestions) <= 50
```

Test oznacz markerem `performance`, aby wolniejszy benchmark 100k był jawny.

- [ ] **Step 3: Uruchom testy pakietu**

Run: `python -m pytest tests/test_product_queries.py tests/test_desktop_data_loader.py tests/test_app_performance_helpers.py -q`

Run: `node --test tests/js/latest-request.test.js`

Expected: PASS.

- [ ] **Step 4: Uruchom benchmark**

Run: `python -m pytest tests/test_product_queries.py -m performance -v`

Expected: PASS na maszynie referencyjnej; zapisz p50/p95 i `EXPLAIN QUERY PLAN` w opisie PR.

- [ ] **Step 5: Uruchom pełny zestaw**

Run: `python -m pytest -q`

Run: `node --check picorgftp_sql/web/static/app.js`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_ci_performance_smoke.py tests/test_product_queries.py docs/superpowers/specs/2026-07-27-product-query-and-desktop-startup-design.md
git commit -m "test: benchmark selective product queries"
```

## Final Verification

- [ ] Run: `python -m pytest -q`
- [ ] Run: `node --test tests/js/latest-request.test.js`
- [ ] Run: `node --check picorgftp_sql/web/static/latest-request.js`
- [ ] Run: `node --check picorgftp_sql/web/static/app.js`
- [ ] Run: `git diff --check`
- [ ] Potwierdź brak `load_lists()` w SQLite lookup/search/suggest przez test spy.
- [ ] Potwierdź identyczny kontrakt odpowiedzi API oraz działający fallback Excel.
