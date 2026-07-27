# Module Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wydzielić odpowiedzialności dotknięte przez pakiety 1–6 z największych modułów bez zmiany zachowania i bez jednorazowego rewrite.

**Architecture:** `web/app.py` pozostaje composition root i rejestruje routery przez jawne dependency dataclasses. `app.py` pozostaje warstwą Tk, ale deleguje ładowanie danych i lifecycle podglądu FTP do kontrolerów bez Tk. Frontend ładuje klasyczne skrypty IIFE pod jednym `window.PicOrg`; `app.js` uruchamia moduły i zachowuje niewydzielony UI. Każde wydzielenie ma characterization test, osobny commit i zerową zmianę kontraktu.

**Tech Stack:** Python 3.14, FastAPI `APIRouter`, Tkinter, vanilla JavaScript IIFE, Node `node:test`, AST import checks, PyInstaller PowerShell workflow, pytest.

## Global Constraints

- Wykonuj ten plan po pakietach 1–6.
- Każdy commit refaktoryzacyjny ma być niezależnie odwracalny i nie może zmieniać algorytmu.
- Nie wprowadzaj bundlera, frameworka JS, mikroserwisów ani masowej zmiany nazw.
- Moduły usługowe nie importują `web.app` ani głównej klasy Tk.
- Wspólny kod web/desktop nie importuje FastAPI ani Tk.
- Nowe klasyczne skrypty używają wyłącznie `window.PicOrg` i są ładowane przed `app.js`.
- Publiczne endpointy, payloady, teksty UI, kolejność startu i config pozostają zgodne.
- Różnica benchmarku czystego refaktoru nie może przekraczać 5% na tej samej maszynie.

## File Structure

- Create: `picorgftp_sql/web/process_models.py`
- Create: `picorgftp_sql/web/process_api.py`
- Create: `picorgftp_sql/web/runtime_api.py`
- Create: `picorgftp_sql/desktop_ftp_preview.py`
- Create: `picorgftp_sql/web/static/autocomplete.js`
- Create: `picorgftp_sql/web/static/process-jobs.js`
- Create: `tests/test_module_boundaries.py`
- Create: `tests/test_web_process_api.py`
- Create: `tests/test_web_runtime_api.py`
- Create: `tests/test_desktop_ftp_preview.py`
- Create: `tests/fixtures/api-route-contract.json`
- Create: `tests/js/helpers.js`
- Create: `tests/js/autocomplete.test.js`
- Create: `tests/js/process-jobs.test.js`
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/app.py`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `Generator exe/build_common.ps1`
- Modify: `tests/test_build_exe_workflow.py`
- Modify: istniejące testy web/desktop/static.

---

### Task 1: Characterization i reguły zależności

**Files:**

- Create: `tests/test_module_boundaries.py`
- Modify: `tests/test_web_app_files.py`
- Modify: `tests/test_app_performance_helpers.py`

**Interfaces:**

- Produces: helper AST `module_imports(path) -> set[str]`; testy kontraktowe route table, startup i publicznych funkcji.
- Consumes: stan repo po pakietach 1–6.

- [ ] **Step 1: Zapisz snapshot tras web**

```python
def test_route_contract_snapshot():
    routes = sorted(
        (route.path, tuple(sorted(route.methods or ())))
        for route in web_app.app.routes
        if route.path.startswith("/api/")
    )
    expected = json.loads(
        Path("tests/fixtures/api-route-contract.json").read_text(encoding="utf-8")
    )
    assert routes == [(path, tuple(methods)) for path, methods in expected]
```

W tym samym commicie dodaj rzeczywisty fixture wygenerowany z aktualnego stanu po pakietach 1–6. Fixture nie może zawierać sekretów ani danych runtime.

- [ ] **Step 2: Dodaj test importów zakazanych**

```python
SERVICE_ROOTS = [
    Path("picorgftp_sql/web/process_queue.py"),
    Path("picorgftp_sql/web/upload_staging.py"),
    Path("picorgftp_sql/web/active_clients.py"),
    Path("picorgftp_sql/image_pipeline.py"),
    Path("picorgftp_sql/desktop_data_loader.py"),
]


def test_services_do_not_import_composition_roots():
    forbidden = {"picorgftp_sql.web.app", "picorgftp_sql.app"}
    for path in SERVICE_ROOTS:
        assert module_imports(path).isdisjoint(forbidden), path
```

`module_imports` używa `ast.Import` i `ast.ImportFrom`, nie regexu.

- [ ] **Step 3: Dodaj bazowy benchmark composition root**

Zmierz 100 importów w świeżych subprocessach osobno dla web i headless desktop albo użyj pięciu powtórzeń, jeśli 100 przekracza budżet CI. Zapisz medianę jako artefakt PR, nie jako stałą zależną od maszyny.

- [ ] **Step 4: Uruchom characterization**

Run: `python -m pytest tests/test_module_boundaries.py tests/test_web_app_files.py tests/test_app_performance_helpers.py -q`

Expected: PASS przed refaktorem.

- [ ] **Step 5: Commit**

```bash
git add tests/test_module_boundaries.py tests/fixtures/api-route-contract.json tests/test_web_app_files.py tests/test_app_performance_helpers.py
git commit -m "test: characterize application module boundaries"
```

### Task 2: Wydziel modele i router procesu

**Files:**

- Create: `picorgftp_sql/web/process_models.py`
- Create: `picorgftp_sql/web/process_api.py`
- Create: `tests/test_web_process_api.py`
- Modify: `picorgftp_sql/web/app.py:1400-1650,3001-3959,6651-6744`
- Modify: `tests/test_module_boundaries.py`

**Interfaces:**

- Produces: `ProcessApiDependencies`; `build_process_router(dependencies) -> APIRouter`; współdzielone dataclasses form/job response.
- Consumes: `ProcessQueueService`, `UploadStagingService`, processor callable, auth/current-user callback i cache-scope callback.

- [ ] **Step 1: Napisz test routera z fake dependencies**

```python
def test_process_router_submits_background_job():
    queue = Mock()
    reservation = Mock()
    reservation.token = "r-1"
    queue.reserve.return_value = reservation
    queue.submit.return_value = 1
    dependencies = ProcessApiDependencies(
        queue=queue,
        stage_form=AsyncMock(return_value=Mock(spec=ProcessFormSnapshot)),
        current_user=lambda _request: "alice",
        cache_scope=lambda _request, _user: "scope-a",
        job_store=Mock(spec=ProcessJobStore),
    )
    app = FastAPI()
    app.include_router(build_process_router(dependencies))
    response = TestClient(app).post(
        "/api/process/background",
        files={
            "file_01": (
                "photo.jpg",
                b"\xff\xd8\xff\xd9",
                "image/jpeg",
            )
        },
        data={
            "ean": "5901234567890",
            "name": "ALFA",
            "type_name": "STÓŁ",
            "model": "A1",
        },
    )
    assert response.status_code == 200
    queue.reserve.assert_called_once_with("scope-a")
```

- [ ] **Step 2: Uruchom test i potwierdź brak modułu**

Run: `python -m pytest tests/test_web_process_api.py -v`

Expected: FAIL podczas importu.

- [ ] **Step 3: Przenieś typy bez zmiany pól**

Przenieś `_ProcessFormSnapshot` i typy request/response używane wyłącznie przez process do `process_models.py`. Zachowaj nazwy pól i wartości domyślne. `process_models.py` nie importuje `web.app`.

- [ ] **Step 4: Zbuduj router z dependency dataclass**

```python
@dataclass(frozen=True)
class ProcessApiDependencies:
    queue: ProcessQueueService
    stage_form: Callable[[Request, object], Awaitable[ProcessFormSnapshot]]
    current_user: Callable[[Request], str]
    cache_scope: Callable[[Request, str], str]
    job_store: ProcessJobStore
```

Router definiuje obecne ścieżki i mapuje te same wyjątki/statusy. Nie importuje globali z `web.app`.

- [ ] **Step 5: Przełącz composition root**

`web/app.py` tworzy `process_dependencies` z istniejących obiektów i
wykonuje `app.include_router(build_process_router(process_dependencies))`.
Usuń stare dekorowane funkcje dopiero po przejściu route snapshot.

- [ ] **Step 6: Uruchom process regression i import guard**

Run: `python -m pytest tests/test_web_process_api.py tests/test_module_boundaries.py tests/test_web_app_files.py -k "process or route_contract or services_do_not_import" -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/web/process_models.py picorgftp_sql/web/process_api.py picorgftp_sql/web/app.py tests/test_web_process_api.py tests/test_module_boundaries.py tests/test_web_app_files.py
git commit -m "refactor: extract process api router"
```

### Task 3: Wydziel runtime/presence router

**Files:**

- Create: `picorgftp_sql/web/runtime_api.py`
- Create: `tests/test_web_runtime_api.py`
- Modify: `picorgftp_sql/web/app.py:4000-4256,4905-4915,5083-5090,5340-5355`
- Modify: `tests/test_module_boundaries.py`
- Modify: `tests/test_runtime_status.py`
- Modify: `tests/test_active_clients_registry.py`

**Interfaces:**

- Produces: `RuntimeApiDependencies`; `build_runtime_router(dependencies) -> APIRouter`.
- Consumes: `RuntimeStatusService`, `ActiveClientRegistry`, file index provider i auth callbacks.

- [ ] **Step 1: Napisz izolowany test routera**

```python
def runtime_payload():
    return {
        "observed_at": "2026-07-27T10:00:00Z",
        "health": {"ok": True, "status": "online"},
        "versions": {},
        "summary": {},
    }


def client_record(username: str, generation: int):
    return {
        "username": username,
        "client_id": f"browser-{generation}",
        "last_seen_epoch": float(generation),
    }


def test_runtime_router_delegates_status_and_presence():
    runtime = Mock()
    runtime.snapshot.return_value = runtime_payload()
    registry = Mock()
    registry.snapshot.return_value = [client_record("alice", generation=1)]
    dependencies = RuntimeApiDependencies(
        runtime_status=runtime,
        active_clients=registry,
        current_user=lambda _request: "admin",
        presence_payload=lambda clients, _user: {"enabled": True, "users": clients},
    )
    app = FastAPI()
    app.include_router(build_runtime_router(dependencies))
    client = TestClient(app)
    assert client.get("/api/runtime-status").json() == runtime_payload()
    assert client.get("/api/server/presence").status_code == 200
```

- [ ] **Step 2: Uruchom test i potwierdź brak routera**

Run: `python -m pytest tests/test_web_runtime_api.py -v`

Expected: FAIL podczas importu.

- [ ] **Step 3: Przenieś wyłącznie endpointy**

Router obejmuje runtime status, file-index status/refresh, presence GET/leave i lekkie process summary tylko wtedy, gdy było częścią runtime service. Rejestr aktywnych klientów pozostaje w `active_clients.py`; router nie dotyka jego locków.

- [ ] **Step 4: Zachowaj middleware record w composition root**

Middleware w `web/app.py` nadal wyznacza request context, ale deleguje jeden call `active_clients.record`. Nie przenoś auth/session parsing do routera.

- [ ] **Step 5: Przełącz i usuń stare definicje**

Dołącz router raz. Route snapshot musi pozostać identyczny. Sprawdź, że `/api/runtime-status` i `/api/health` pozostają wykluczone z presence recording zgodnie z pakietem 6.

- [ ] **Step 6: Uruchom runtime regression**

Run: `python -m pytest tests/test_web_runtime_api.py tests/test_runtime_status.py tests/test_active_clients_registry.py tests/test_module_boundaries.py tests/test_web_app_files.py -k "runtime or presence or file_index or route_contract" -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/web/runtime_api.py picorgftp_sql/web/app.py tests/test_web_runtime_api.py tests/test_runtime_status.py tests/test_active_clients_registry.py tests/test_module_boundaries.py tests/test_web_app_files.py
git commit -m "refactor: extract runtime api router"
```

### Task 4: Wydziel kontroler podglądu FTP desktopu

**Files:**

- Create: `picorgftp_sql/desktop_ftp_preview.py`
- Create: `tests/test_desktop_ftp_preview.py`
- Modify: `picorgftp_sql/app.py:6087-6300`
- Modify: `tests/test_app_performance_helpers.py`
- Modify: `tests/test_module_boundaries.py`

**Interfaces:**

- Produces: `DesktopFtpPreviewController.request`, `cancel_current`, `close`; `FtpPreviewResult`.
- Consumes: FTP downloader, `FtpTempManager`, scheduler `after` i callbacki UI.

- [ ] **Step 1: Napisz test odrzucenia starego wyniku**

```python
@dataclass(frozen=True)
class PreviewResult:
    ean: str
    files: tuple[str, ...]


def preview_result(ean: str) -> PreviewResult:
    return PreviewResult(ean=ean, files=(f"{ean}_01.jpg",))


class ControlledDownloader:
    def __init__(self):
        self.requests = {}

    def __call__(self, request_id, ean, cancel_event, complete):
        self.requests[request_id] = (ean, cancel_event, complete)

    def finish(self, request_id, result):
        self.requests[request_id][2](result)


def test_preview_controller_publishes_only_latest_request():
    scheduled = []
    results = []
    errors = []
    downloader = ControlledDownloader()
    controller = DesktopFtpPreviewController(
        downloader=downloader,
        temp_manager=FakeTempManager(),
        schedule=lambda callback: scheduled.append(callback),
    )
    first = controller.request("5901", on_success=results.append, on_error=errors.append)
    second = controller.request("5902", on_success=results.append, on_error=errors.append)
    downloader.finish(first, preview_result("5901"))
    downloader.finish(second, preview_result("5902"))
    for callback in scheduled:
        callback()
    assert [item.ean for item in results] == ["5902"]
```

- [ ] **Step 2: Uruchom test i potwierdź brak modułu**

Run: `python -m pytest tests/test_desktop_ftp_preview.py -v`

Expected: FAIL podczas importu.

- [ ] **Step 3: Zaimplementuj kontroler bez Tk**

Kontroler utrzymuje request ID i cancel event pod lockiem. Worker wywołuje downloader bez odwołań do widgetów. Publikacja przez `schedule` sprawdza ponownie request ID przed callbackiem.

- [ ] **Step 4: Przełącz `App`**

`App._load_existing_files` buduje parametry i wywołuje controller. Callback sukcesu wykonuje obecne aktualizacje slotów na głównym wątku. `destroy` wywołuje `controller.close()` przed zniszczeniem root.

- [ ] **Step 5: Dodaj import guard**

AST test potwierdza brak importu `tkinter` i `picorgftp_sql.app` w `desktop_ftp_preview.py`.

- [ ] **Step 6: Uruchom desktop/FTP regression**

Run: `python -m pytest tests/test_desktop_ftp_preview.py tests/test_app_performance_helpers.py tests/test_ftp_service.py tests/test_module_boundaries.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/desktop_ftp_preview.py picorgftp_sql/app.py tests/test_desktop_ftp_preview.py tests/test_app_performance_helpers.py tests/test_module_boundaries.py
git commit -m "refactor: extract desktop ftp preview controller"
```

### Task 5: Wydziel pełny moduł autocomplete JavaScript

**Files:**

- Create: `picorgftp_sql/web/static/autocomplete.js`
- Create: `tests/js/autocomplete.test.js`
- Modify: `picorgftp_sql/web/static/app.js:1900-2120`
- Modify: `picorgftp_sql/web/static/index.html:710`
- Modify: `tests/test_module_boundaries.py`

**Interfaces:**

- Produces: `window.PicOrg.AutocompleteController`.
- Consumes: `LatestRequest`, callbacki `localSuggestions`, `remoteSuggestions`, `render`, `commit`, timer API.

- [ ] **Step 1: Napisz test publicznego API**

```javascript
const test = require("node:test");
const assert = require("node:assert/strict");
const { deferred } = require("./helpers.js");
global.window = { PicOrg: {} };
require("../../picorgftp_sql/web/static/latest-request.js");
require("../../picorgftp_sql/web/static/autocomplete.js");

test("controller renders local immediately and latest remote result", async () => {
  const rendered = [];
  const remote = deferred();
  const controller = new window.PicOrg.AutocompleteController({
    fieldName: "name",
    localSuggestions: () => ["LOCAL"],
    remoteSuggestions: () => remote.promise,
    render: (values) => rendered.push(values),
    delayMs: 0,
    setTimer: (callback) => {
      callback();
      return 1;
    },
    clearTimer: () => {},
  });
  controller.refresh();
  assert.deepEqual(rendered, [["LOCAL"]]);
  remote.resolve(["REMOTE"]);
  await controller.pendingForTest();
  assert.deepEqual(rendered.at(-1), ["LOCAL", "REMOTE"]);
});
```

- [ ] **Step 2: Dodaj współdzielony helper promise**

```javascript
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

module.exports = { deferred };
```

Zapisz go jako `tests/js/helpers.js`.

- [ ] **Step 3: Uruchom test i potwierdź brak modułu**

Run: `node --test tests/js/autocomplete.test.js`

Expected: FAIL z `MODULE_NOT_FOUND`.

- [ ] **Step 4: Przenieś lifecycle bez DOM-specific globals**

Controller obsługuje debounce, LatestRequest, merge/unique i cancel. DOM
tworzenie panelu, ARIA, keyboard i commit są częścią eksportowanej funkcji
`window.PicOrg.setupAutocomplete(autocompleteDependencies)` w tym samym
module. Moduł nie uruchamia się przy load; `app.js` wywołuje tę funkcję
jednokrotnie po zbudowaniu `autocompleteDependencies`.

- [ ] **Step 5: Przełącz `app.js`**

`app.js` przekazuje current form payload, requestJson i istniejące callbacki render/commit. Usuń stare definicje dopiero po `rg` wykazującym jeden `setupAutocomplete`.

- [ ] **Step 6: Dodaj script order**

Kolejność: `latest-request.js`, `autocomplete.js`, `runtime-status.js`, `process-jobs.js` po jego utworzeniu, `app.js`. Wszystkie używają tego samego version token.

- [ ] **Step 7: Uruchom JS i source guards**

Run: `node --test tests/js/latest-request.test.js tests/js/autocomplete.test.js`

Run: `node --check picorgftp_sql/web/static/autocomplete.js`

Run: `node --check picorgftp_sql/web/static/app.js`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add picorgftp_sql/web/static/autocomplete.js picorgftp_sql/web/static/app.js picorgftp_sql/web/static/index.html tests/js/helpers.js tests/js/autocomplete.test.js tests/test_module_boundaries.py
git commit -m "refactor: extract autocomplete frontend module"
```

### Task 6: Wydziel moduł frontendowy kolejki procesów

**Files:**

- Create: `picorgftp_sql/web/static/process-jobs.js`
- Create: `tests/js/process-jobs.test.js`
- Modify: `picorgftp_sql/web/static/app.js:3950-4380,12900-12960`
- Modify: `picorgftp_sql/web/static/index.html:710`
- Modify: `tests/test_module_boundaries.py`

**Interfaces:**

- Produces: `window.PicOrg.ProcessJobsController`.
- Consumes: `requestJson`, render callback, runtime-version notification i timer.

- [ ] **Step 1: Napisz test deduplikacji refreshu**

```javascript
const test = require("node:test");
const assert = require("node:assert/strict");
const { deferred } = require("./helpers.js");
global.window = { PicOrg: {} };
require("../../picorgftp_sql/web/static/process-jobs.js");


test("process jobs controller shares one in-flight refresh", async () => {
  const pending = deferred();
  let requests = 0;
  const controller = new window.PicOrg.ProcessJobsController({
    fetchJobs: () => {
      requests += 1;
      return pending.promise;
    },
    render: () => {},
  });
  const first = controller.refresh();
  const second = controller.refresh();
  assert.equal(requests, 1);
  pending.resolve({ jobs: [] });
  await Promise.all([first, second]);
});
```

- [ ] **Step 2: Uruchom test i potwierdź brak modułu**

Run: `node --test tests/js/process-jobs.test.js`

Expected: FAIL z `MODULE_NOT_FOUND`.

- [ ] **Step 3: Przenieś fetch/state/render orchestration**

Controller utrzymuje jedno in-flight promise, ostatnią wersję runtime i aktywny job. Nie tworzy własnego stałego pollera; reaguje na `RuntimeStatusPoller` lub jawne `refresh`.

- [ ] **Step 4: Przełącz `app.js`**

Zachowaj istniejące DOM render helpers jako callbacki albo przenieś je razem, jeśli są używane wyłącznie przez kolejkę. Usuń `scheduleProcessJobPoll` i osobne timery, jeśli pakiet 6 ich jeszcze nie usunął.

- [ ] **Step 5: Uruchom JS**

Run: `node --test tests/js/process-jobs.test.js tests/js/runtime-status.test.js`

Run: `node --check picorgftp_sql/web/static/process-jobs.js`

Run: `node --check picorgftp_sql/web/static/app.js`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add picorgftp_sql/web/static/process-jobs.js picorgftp_sql/web/static/app.js picorgftp_sql/web/static/index.html tests/js/helpers.js tests/js/process-jobs.test.js tests/test_module_boundaries.py
git commit -m "refactor: extract process jobs frontend module"
```

### Task 7: Usuń shimy, zaktualizuj build i porównaj benchmark

**Files:**

- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/app.py`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `Generator exe/build_common.ps1`
- Modify: `tests/test_build_exe_workflow.py`
- Modify: `tests/test_module_boundaries.py`
- Modify: `docs/superpowers/specs/2026-07-27-module-boundaries-design.md`

**Interfaces:**

- Consumes: wszystkie nowe routery, kontrolery i skrypty.
- Produces: composition roots bez duplikatów i build zawierający nowe pliki.

- [ ] **Step 1: Wyszukaj stare shimy i podwójne definicje**

Run: `rg -n "def (_save_upload|_queue_process_job|_flush_active_clients_locked)|function (setupAutocomplete|scheduleProcessJobPoll)" picorgftp_sql`

Expected: każda odpowiedzialność ma jedną kanoniczną implementację; stare shimy są jawnie zidentyfikowane przed usunięciem.

- [ ] **Step 2: Usuń shimy po potwierdzeniu call sites**

Dla każdego kandydata uruchom osobne `rg` po nazwie. Usuń funkcję dopiero, gdy wyniki wskazują wyłącznie definicję/test przeznaczony do aktualizacji. Nie pozostawiaj szerokich import fallbacków.

- [ ] **Step 3: Zaktualizuj pakowanie static assets**

Dodaj `latest-request.js`, `autocomplete.js`, `runtime-status.js` i `process-jobs.js` do tego samego mechanizmu danych co `app.js`. Test build workflow sprawdza obecność każdego basename w wygenerowanej komendzie/spec.

- [ ] **Step 4: Uruchom characterization oraz pełne testy**

Run: `python -m pytest tests/test_module_boundaries.py tests/test_web_process_api.py tests/test_web_runtime_api.py tests/test_desktop_ftp_preview.py tests/test_build_exe_workflow.py tests/test_web_app_files.py tests/test_app_performance_helpers.py -q`

Run: `node --test tests/js/latest-request.test.js tests/js/autocomplete.test.js tests/js/runtime-status.test.js tests/js/process-jobs.test.js`

Expected: PASS.

- [ ] **Step 5: Porównaj benchmark przed/po**

Na tej samej maszynie wykonaj zapisany w Task 1 benchmark import/start oraz smoke głównych endpointów. Oblicz:

```python
relative_change = abs(after - before) / before
assert relative_change <= 0.05
```

Jeżeli szum przekracza 5%, wykonaj co najmniej pięć powtórzeń i porównaj mediany. Jeżeli nadal przekracza, znajdź regresję przed merge.

- [ ] **Step 6: Uruchom test workflow builda**

Run: `python -m pytest tests/test_build_exe_workflow.py -v`

Expected: PASS i asercja obecności wszystkich czterech dodatkowych assetów w
generowanej konfiguracji PyInstaller. Ten krok nie publikuje artefaktów ani
nie uruchamia pełnego builda EXE.

- [ ] **Step 7: Uruchom pełną regresję**

Run: `python -m pytest -q`

Run: `python -m compileall -q picorgftp_sql tests`

Run: `node --check picorgftp_sql/web/static/app.js`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add picorgftp_sql "Generator exe/build_common.ps1" tests docs/superpowers/specs/2026-07-27-module-boundaries-design.md
git commit -m "refactor: finalize performance module boundaries"
```

## Final Verification

- [ ] Run: `python -m pytest -q`
- [ ] Run: `python -m compileall -q picorgftp_sql tests`
- [ ] Run: `node --test tests/js/latest-request.test.js tests/js/autocomplete.test.js tests/js/runtime-status.test.js tests/js/process-jobs.test.js`
- [ ] Run: `node --check picorgftp_sql/web/static/app.js`
- [ ] Run: `git diff --check`
- [ ] Potwierdź identyczny route snapshot, brak cykli importów i kompletne assety builda.
- [ ] Potwierdź brak nowych globali poza `window.PicOrg` i różnicę benchmarku nie większą niż 5%.
