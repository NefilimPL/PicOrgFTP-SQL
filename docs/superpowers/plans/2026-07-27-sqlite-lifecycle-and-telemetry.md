# SQLite Lifecycle and Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wykonywać inicjalizację schematu SQLite raz na instancję, skonfigurować bezpieczną współbieżność i scalić nadmiarowe zapisy postępu.

**Architecture:** `SqliteStore` zachowuje publiczne `initialize()`, ale deleguje pełny DDL do chronionej, jednokrotnej inicjalizacji. Rejestr w `data_store.py` zwraca jedną instancję dla kanonicznej ścieżki, a każde krótkie połączenie otrzymuje wspólną politykę PRAGMA. Osobny gate postępu aktualizuje stan pamięciowy przy każdym wywołaniu, lecz zapisuje snapshot najwyżej co 500 ms lub na zmianie etapu/stanu.

**Tech Stack:** Python 3.14, `sqlite3`, `threading`, `concurrent.futures`, FastAPI, pytest.

## Global Constraints

- `PRAGMA busy_timeout` domyślnie wynosi 5000 ms.
- `PRAGMA synchronous=NORMAL` jest używane tylko po skutecznym uruchomieniu WAL.
- Nieudane włączenie WAL nie może uniemożliwić startu.
- Jedno połączenie `sqlite3` nie jest współdzielone między wątkami.
- Zdarzenia `warning`, `error` i `critical` nie są throttlowane.
- Stan końcowy joba jest zawsze zapisywany synchronicznie.
- Nie zmieniaj publicznych kontraktów data store, API, schematu domenowego ani formatu backupów.
- Nie optymalizuj odczytu `local_settings.json`; nie znajduje się w zatwierdzonym zakresie.

## File Structure

- Create: `picorgftp_sql/sqlite_connection.py` — konfiguracja połączenia i bezpieczne uruchomienie WAL.
- Create: `picorgftp_sql/web/process_progress.py` — czysty, testowalny gate zapisu postępu.
- Create: `tests/test_sqlite_lifecycle.py` — wyścigi inicjalizacji, rejestr store i PRAGMA.
- Create: `tests/test_process_progress.py` — throttling i trwałość stanów końcowych.
- Create: `tests/test_sqlite_concurrency_performance.py` — mieszany workload i liczniki SQL.
- Modify: `picorgftp_sql/sqlite_store.py:718-1120` — lifecycle i connection policy.
- Modify: `picorgftp_sql/data_store.py:26-41,301-329` — rejestr instancji SQLite.
- Modify: `picorgftp_sql/observability.py:86-91` — reuse instancji z rejestru.
- Modify: `picorgftp_sql/web/app.py:3001-3039,3673-3711,3918-3935` — gate postępu i deduplikacja etapów.
- Modify: `tests/test_sqlite_store.py` — regresja istniejącego schematu.
- Modify: `tests/test_web_app_files.py:50-213` — trwały stan jobów i eventy etapów.

---

### Task 1: Jednokrotna inicjalizacja `SqliteStore`

**Files:**

- Modify: `picorgftp_sql/sqlite_store.py:718-1120`
- Create: `tests/test_sqlite_lifecycle.py`
- Test: `tests/test_sqlite_store.py`

**Interfaces:**

- Consumes: istniejący konstruktor `SqliteStore(path: str)` i publiczne `initialize() -> None`.
- Produces: `SqliteStore._initialize_schema() -> None`; `initialize()` pozostaje kompatybilnym, thread-safe wrapperem.

- [ ] **Step 1: Napisz test wyścigu pierwszej inicjalizacji**

```python
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from picorgftp_sql.sqlite_store import SqliteStore


def test_initialize_runs_schema_once_for_parallel_callers(tmp_path, monkeypatch):
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    original = store._initialize_schema
    calls = 0
    calls_lock = Lock()

    def counted():
        nonlocal calls
        with calls_lock:
            calls += 1
        original()

    monkeypatch.setattr(store, "_initialize_schema", counted)
    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(lambda _index: store.initialize(), range(20)))

    assert calls == 1
```

- [ ] **Step 2: Uruchom test i potwierdź czerwony stan**

Run: `python -m pytest tests/test_sqlite_lifecycle.py::test_initialize_runs_schema_once_for_parallel_callers -v`

Expected: FAIL z `AttributeError: 'SqliteStore' object has no attribute '_initialize_schema'`.

- [ ] **Step 3: Rozdziel wrapper od istniejącego DDL**

```python
import threading


class SqliteStore:
    def __init__(self, path: str):
        self.path = str(Path(path))
        self._initialize_lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._initialize_lock:
            if self._initialized:
                return
            self._initialize_schema()
            self._initialized = True
```

Zmień nazwę obecnej metody `initialize` na `_initialize_schema` bez zmian w
jej ciele, a powyższy wrapper dodaj pod nazwą `initialize`.

Nie ustawiaj `_initialized` w `finally`. Wyjątek migracji musi pozostawić flagę `False`, aby retry było możliwe.

- [ ] **Step 4: Dodaj test ponowienia po błędzie**

```python
def test_initialize_retries_after_schema_failure(tmp_path, monkeypatch):
    store = SqliteStore(str(tmp_path / "retry.sqlite"))
    original = store._initialize_schema
    attempts = 0

    def flaky():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("migration failed")
        original()

    monkeypatch.setattr(store, "_initialize_schema", flaky)
    with pytest.raises(RuntimeError, match="migration failed"):
        store.initialize()
    store.initialize()

    assert attempts == 2
```

- [ ] **Step 5: Uruchom testy lifecycle i schematu**

Run: `python -m pytest tests/test_sqlite_lifecycle.py tests/test_sqlite_store.py::test_schema_creates_expected_tables -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add picorgftp_sql/sqlite_store.py tests/test_sqlite_lifecycle.py
git commit -m "perf: initialize sqlite schema once per store"
```

### Task 2: Rejestr jednej instancji store na ścieżkę

**Files:**

- Modify: `picorgftp_sql/data_store.py:26-41,301-329`
- Modify: `picorgftp_sql/observability.py:86-91`
- Modify: `tests/test_sqlite_lifecycle.py`

**Interfaces:**

- Consumes: `SqliteStore(path: str)`, `SqliteDataStoreAdapter`.
- Produces: `get_sqlite_store(database_path: str) -> SqliteStore`; `reset_active_store_cache() -> None` czyści adapter i rejestr.

- [ ] **Step 1: Napisz test kanonicznej ścieżki i współbieżnego reuse**

```python
def test_get_sqlite_store_reuses_instance_for_canonical_path(tmp_path):
    first = get_sqlite_store(str(tmp_path / "." / "app.sqlite"))
    second = get_sqlite_store(str(tmp_path / "app.sqlite"))
    assert first is second


def test_get_sqlite_store_is_thread_safe(tmp_path):
    path = str(tmp_path / "parallel.sqlite")
    with ThreadPoolExecutor(max_workers=12) as pool:
        stores = list(pool.map(lambda _index: get_sqlite_store(path), range(40)))
    assert len({id(store) for store in stores}) == 1
```

- [ ] **Step 2: Uruchom test i potwierdź brak interfejsu**

Run: `python -m pytest tests/test_sqlite_lifecycle.py -k get_sqlite_store -v`

Expected: FAIL podczas importu `get_sqlite_store`.

- [ ] **Step 3: Dodaj chroniony rejestr i podłącz adapter**

```python
_STORE_REGISTRY_LOCK = threading.Lock()
_SQLITE_STORES: dict[str, SqliteStore] = {}


def get_sqlite_store(database_path: str) -> SqliteStore:
    key = str(Path(database_path).resolve())
    with _STORE_REGISTRY_LOCK:
        store = _SQLITE_STORES.get(key)
        if store is None:
            store = SqliteStore(key)
            store.initialize()
            _SQLITE_STORES[key] = store
        return store


class SqliteDataStoreAdapter:
    def __init__(self, database_path: str):
        self.store = get_sqlite_store(database_path)
```

`get_sqlite_store` nie może trzymać globalnej blokady podczas zewnętrznych operacji. Inicjalizacja jest dozwolona pod tą blokadą, ponieważ Task 1 gwarantuje krótki pojedynczy lifecycle i zapobiega publikacji częściowo gotowej instancji.

- [ ] **Step 4: Przełącz observability i reset**

```python
def observability_store() -> SqliteStore:
    return get_sqlite_store(storage_settings.resolve_sqlite_path())


def reset_active_store_cache() -> None:
    global _ACTIVE_STORE, _ACTIVE_STORE_KEY
    with _STORE_REGISTRY_LOCK:
        _ACTIVE_STORE = None
        _ACTIVE_STORE_KEY = None
        _SQLITE_STORES.clear()
```

Dodaj test, że `observability_store()` i aktywny adapter zwracają tę samą instancję przy tej samej ścieżce.

- [ ] **Step 5: Uruchom testy store i observability**

Run: `python -m pytest tests/test_sqlite_lifecycle.py tests/test_sqlite_store.py tests/test_web_app_files.py -k "process_job or lifecycle or schema" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add picorgftp_sql/data_store.py picorgftp_sql/observability.py tests/test_sqlite_lifecycle.py
git commit -m "perf: reuse sqlite store instances"
```

### Task 3: Polityka połączeń i bezpieczny WAL

**Files:**

- Create: `picorgftp_sql/sqlite_connection.py`
- Modify: `picorgftp_sql/sqlite_store.py:718-752`
- Modify: `tests/test_sqlite_lifecycle.py`

**Interfaces:**

- Produces: `SQLiteConnectionSettings`; `configure_connection(conn, settings, *, wal_active) -> None`; `try_enable_wal(conn) -> str`.
- Consumes: standardowe `sqlite3.Connection`.

- [ ] **Step 1: Napisz test konfiguracji zwykłego połączenia**

```python
def test_connection_policy_sets_foreign_keys_and_busy_timeout(tmp_path):
    store = SqliteStore(str(tmp_path / "policy.sqlite"))
    store.initialize()
    with store.connection() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
```

Dodaj drugi test, który po inicjalizacji oczekuje `journal_mode == "wal"` albo kontrolowanego fallbacku zwróconego przez store.

- [ ] **Step 2: Uruchom test i potwierdź brak polityki**

Run: `python -m pytest tests/test_sqlite_lifecycle.py -k "connection_policy or journal_mode" -v`

Expected: FAIL, ponieważ `busy_timeout` i jawny stan journal nie są częścią store.

- [ ] **Step 3: Utwórz moduł polityki**

```python
from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True)
class SQLiteConnectionSettings:
    busy_timeout_ms: int = 5000
    connect_timeout_seconds: float = 5.0


def configure_connection(
    conn: sqlite3.Connection,
    settings: SQLiteConnectionSettings,
    *,
    wal_active: bool,
) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {settings.busy_timeout_ms:d}")
    if wal_active:
        conn.execute("PRAGMA synchronous = NORMAL")


def try_enable_wal(conn: sqlite3.Connection) -> str:
    row = conn.execute("PRAGMA journal_mode = WAL").fetchone()
    return str(row[0] if row else "").strip().lower()
```

- [ ] **Step 4: Podłącz politykę bez współdzielenia connection**

W `SqliteStore.__init__` dodaj `_connection_settings` i `_journal_mode = ""`. `connect()` przekazuje `timeout=settings.connect_timeout_seconds`, ustawia `row_factory`, funkcje i wywołuje:

```python
configure_connection(
    conn,
    self._connection_settings,
    wal_active=self._journal_mode == "wal",
)
```

W `_initialize_schema()` po otwarciu połączenia:

```python
try:
    self._journal_mode = try_enable_wal(conn)
except sqlite3.DatabaseError as exc:
    self._journal_mode = str(
        conn.execute("PRAGMA journal_mode").fetchone()[0]
    ).lower()
    self._wal_fallback_reason = type(exc).__name__
configure_connection(
    conn,
    self._connection_settings,
    wal_active=self._journal_mode == "wal",
)
```

Nie loguj pełnej ścieżki ani treści mogącej zawierać dane użytkownika.

- [ ] **Step 5: Dodaj test fallbacku**

Użyj mockowanego `try_enable_wal`, który podnosi `sqlite3.OperationalError`, i sprawdź:

```python
assert store._initialized is True
assert store._journal_mode != "wal"
assert store._wal_fallback_reason == "OperationalError"
```

- [ ] **Step 6: Uruchom testy SQLite**

Run: `python -m pytest tests/test_sqlite_lifecycle.py tests/test_sqlite_store.py tests/test_sqlite_backup.py tests/test_sqlite_maintenance.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/sqlite_connection.py picorgftp_sql/sqlite_store.py tests/test_sqlite_lifecycle.py
git commit -m "perf: configure sqlite concurrency policy"
```

### Task 4: Jawne unieważnianie po zmianie i restore

**Files:**

- Modify: `picorgftp_sql/data_store.py:301-329`
- Modify: `picorgftp_sql/storage_settings.py:84-98`
- Modify: `picorgftp_sql/sqlite_backup.py`
- Modify: `picorgftp_sql/sqlite_maintenance.py`
- Modify: `tests/test_sqlite_lifecycle.py`
- Modify: `tests/test_sqlite_backup.py`
- Modify: `tests/test_sqlite_maintenance.py`

**Interfaces:**

- Produces: `invalidate_sqlite_store(database_path: str | None = None) -> None`.
- Consumes: zakończony sukcesem zapis bootstrap settings, restore i replace bazy.

- [ ] **Step 1: Napisz test unieważnienia konkretnej ścieżki**

```python
def test_invalidate_sqlite_store_replaces_only_target(tmp_path):
    first_path = str(tmp_path / "first.sqlite")
    second_path = str(tmp_path / "second.sqlite")
    first = get_sqlite_store(first_path)
    second = get_sqlite_store(second_path)

    invalidate_sqlite_store(first_path)

    assert get_sqlite_store(first_path) is not first
    assert get_sqlite_store(second_path) is second
```

- [ ] **Step 2: Uruchom test i potwierdź brak funkcji**

Run: `python -m pytest tests/test_sqlite_lifecycle.py::test_invalidate_sqlite_store_replaces_only_target -v`

Expected: FAIL podczas importu `invalidate_sqlite_store`.

- [ ] **Step 3: Dodaj precyzyjną invalidację**

```python
def invalidate_sqlite_store(database_path: str | None = None) -> None:
    global _ACTIVE_STORE, _ACTIVE_STORE_KEY
    with _STORE_REGISTRY_LOCK:
        if database_path is None:
            _SQLITE_STORES.clear()
        else:
            _SQLITE_STORES.pop(str(Path(database_path).resolve()), None)
        if database_path is None or (
            _ACTIVE_STORE_KEY
            and _ACTIVE_STORE_KEY[1] == str(Path(database_path).resolve())
        ):
            _ACTIVE_STORE = None
            _ACTIVE_STORE_KEY = None
```

- [ ] **Step 4: Podłącz invalidację wyłącznie po sukcesie mutacji**

Po atomowym restore/repair/replace wywołaj `invalidate_sqlite_store(active_path)`.
Po zmianie ustawień storage wywołaj `reset_active_store_cache()` dopiero po
udanym `write_text`. W `storage_settings.py` wykonaj lokalny import funkcji
resetującej wewnątrz ścieżki sukcesu, aby nie tworzyć importu cyklicznego
`storage_settings -> data_store -> storage_settings`.

Dodaj regresję: nieudany restore nie unieważnia działającej instancji.

- [ ] **Step 5: Uruchom testy backupu i maintenance**

Run: `python -m pytest tests/test_sqlite_lifecycle.py tests/test_sqlite_backup.py tests/test_sqlite_maintenance.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add picorgftp_sql/data_store.py picorgftp_sql/storage_settings.py picorgftp_sql/sqlite_backup.py picorgftp_sql/sqlite_maintenance.py tests/test_sqlite_lifecycle.py tests/test_sqlite_backup.py tests/test_sqlite_maintenance.py
git commit -m "fix: invalidate sqlite store after database replacement"
```

### Task 5: Gate trwałego zapisu postępu

**Files:**

- Create: `picorgftp_sql/web/process_progress.py`
- Create: `tests/test_process_progress.py`
- Modify: `picorgftp_sql/web/app.py:3673-3711,3918-3935`
- Modify: `tests/test_web_app_files.py:50-155`

**Interfaces:**

- Produces: `ProcessProgressGate.should_persist(job_id, *, stage, status, now, force=False) -> bool`; `forget(job_id) -> None`.
- Consumes: `_set_process_job_progress` i wszystkie terminalne ścieżki joba.

- [ ] **Step 1: Napisz test reguł 500 ms**

```python
from picorgftp_sql.web.process_progress import ProcessProgressGate


def test_progress_gate_coalesces_percent_only_updates():
    gate = ProcessProgressGate(min_interval_seconds=0.5)
    assert gate.should_persist("job-1", stage="images", status="running", now=0.0)
    assert not gate.should_persist("job-1", stage="images", status="running", now=0.1)
    assert not gate.should_persist("job-1", stage="images", status="running", now=0.49)
    assert gate.should_persist("job-1", stage="images", status="running", now=0.5)


def test_progress_gate_persists_stage_status_and_force():
    gate = ProcessProgressGate(min_interval_seconds=0.5)
    assert gate.should_persist("job-1", stage="validate", status="running", now=0.0)
    assert gate.should_persist("job-1", stage="images", status="running", now=0.1)
    assert gate.should_persist("job-1", stage="images", status="failed", now=0.2)
    assert gate.should_persist(
        "job-1", stage="images", status="failed", now=0.21, force=True
    )
```

- [ ] **Step 2: Uruchom test i potwierdź brak modułu**

Run: `python -m pytest tests/test_process_progress.py -v`

Expected: FAIL podczas importu `process_progress`.

- [ ] **Step 3: Zaimplementuj gate**

```python
from dataclasses import dataclass
import threading


@dataclass
class _PersistedProgress:
    stage: str
    status: str
    at: float


class ProcessProgressGate:
    def __init__(self, min_interval_seconds: float = 0.5):
        self._interval = min_interval_seconds
        self._items: dict[str, _PersistedProgress] = {}
        self._lock = threading.Lock()

    def should_persist(self, job_id, *, stage, status, now, force=False):
        with self._lock:
            previous = self._items.get(job_id)
            due = (
                force
                or previous is None
                or previous.stage != stage
                or previous.status != status
                or now - previous.at >= self._interval
            )
            if due:
                self._items[job_id] = _PersistedProgress(stage, status, now)
            return due

    def forget(self, job_id: str) -> None:
        with self._lock:
            self._items.pop(job_id, None)
```

- [ ] **Step 4: Podłącz gate do web app**

`_set_process_job_progress()` zawsze aktualizuje `_PROCESS_JOBS`, ale wywołuje `_persist_process_job()` tylko po `should_persist`. Terminalne ścieżki `completed`, `failed`, `cancelled` przekazują `force=True`, a następnie `forget(job_id)`.

W testach zamockuj `_persist_process_job`, wykonaj 100 aktualizacji z kontrolowanym `time.monotonic()` i oczekuj najwyżej trzech zapisów przy stałym etapie.

- [ ] **Step 5: Uruchom testy postępu i jobów**

Run: `python -m pytest tests/test_process_progress.py tests/test_web_app_files.py -k "process_job or progress or active_stage" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add picorgftp_sql/web/process_progress.py picorgftp_sql/web/app.py tests/test_process_progress.py tests/test_web_app_files.py
git commit -m "perf: coalesce process progress persistence"
```

### Task 6: Deduplikacja informacyjnych eventów etapów

**Files:**

- Modify: `picorgftp_sql/web/app.py:3001-3039`
- Modify: `tests/test_web_app_files.py:157-213`

**Interfaces:**

- Consumes: lokalna funkcja `mark` w `_process_upload_snapshot`.
- Produces: najwyżej jeden `process.stage_started` dla pary `job_id`, `stage`; wszystkie eventy błędów bez zmian.

- [ ] **Step 1: Rozszerz istniejący test eventów o powtórzony etap**

```python
stage_events = [
    event
    for event in emitted
    if event["event_type"] == "process.stage_started"
]
stage_keys = [(event["job_id"], event["stage"]) for event in stage_events]
assert len(stage_keys) == len(set(stage_keys))
```

Wykorzystaj obecny fixture
`test_process_snapshot_emits_correlated_stage_and_validation_events`, który
już przechwytuje `emitted`, i dopisz powyższą asercję po wywołaniu procesu.

- [ ] **Step 2: Uruchom regresję i potwierdź duplikat**

Run: `python -m pytest tests/test_web_app_files.py -k "stage_started_once" -v`

Expected: FAIL z `assert 2 == 1`.

- [ ] **Step 3: Dodaj lokalny zbiór wyemitowanych etapów**

```python
emitted_stages: set[str] = set()

def mark(
    percent: int,
    label: str,
    *,
    current_key: str = "",
    current_label: str = "",
) -> None:
    if current_key and current_key not in emitted_stages:
        emitted_stages.add(current_key)
        emit_event(
            severity="info",
            event_type="process.stage_started",
            module="web.process",
            stage=current_key,
            username=username,
            job_id=job_id,
            summary=current_label or label,
            details={"percent": percent, "label": label},
        )
```

Po tym bloku pozostaw bez zmian istniejące wywołanie callbacku `progress`.
Nie deduplikuj `process.stage_failed`, wyjątków ani eventów integracji.

- [ ] **Step 4: Uruchom testy observability procesu**

Run: `python -m pytest tests/test_web_app_files.py -k "stage or event or process_job" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add picorgftp_sql/web/app.py tests/test_web_app_files.py
git commit -m "perf: deduplicate process stage info events"
```

### Task 7: Test współbieżności i raport benchmarku

**Files:**

- Create: `tests/test_sqlite_concurrency_performance.py`
- Modify: `tests/test_ci_performance_smoke.py`
- Modify: `docs/superpowers/specs/2026-07-27-sqlite-lifecycle-and-telemetry-design.md`

**Interfaces:**

- Consumes: ukończony lifecycle, politykę connection i gate postępu.
- Produces: deterministyczny test regresji oraz opcjonalny benchmark oznaczony markerem `performance`.

- [ ] **Step 1: Dodaj mieszany workload**

```python
def test_concurrent_readers_and_writers_do_not_lock_database(tmp_path):
    store = SqliteStore(str(tmp_path / "concurrent.sqlite"))
    store.initialize()

    def writer(index):
        store.upsert_job_run({
            "id": f"job-{index}",
            "status": "running",
            "created_at": "2026-07-27T10:00:00.000Z",
        })

    def reader(_index):
        store.query_job_runs(limit=20)

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [
            pool.submit(writer if index % 5 == 0 else reader, index)
            for index in range(1000)
        ]
        for future in futures:
            future.result()
```

- [ ] **Step 2: Dodaj licznik instrukcji inicjalizacyjnych**

W testowym subclassie store licz wywołania `_initialize_schema`; po 1000 operacjach oczekuj `1`. Nie mierz czasu w tym teście funkcjonalnym.

- [ ] **Step 3: Dodaj osobny benchmark czasu i zapisów**

Benchmark ma raportować JSON z:

```python
{
    "operations": 1000,
    "schema_initializations": schema_calls,
    "locked_errors": locked_errors,
    "elapsed_seconds": elapsed,
    "progress_updates": 100,
    "progress_persists": persist_calls,
}
```

Budżet smoke: brak `locked_errors`, jedna inicjalizacja oraz najwyżej trzy zapisy dla 100 aktualizacji w jednej sekundzie.

- [ ] **Step 4: Uruchom pakiet docelowy**

Run: `python -m pytest tests/test_sqlite_lifecycle.py tests/test_process_progress.py tests/test_sqlite_concurrency_performance.py tests/test_sqlite_store.py tests/test_web_app_files.py tests/test_notification_service.py -q`

Expected: PASS, 0 failures.

- [ ] **Step 5: Uruchom pełny zestaw**

Run: `python -m pytest -q`

Expected: PASS, 0 failures.

- [ ] **Step 6: Zapisz wynik przed/po w opisie PR i zaktualizuj status specyfikacji**

W specyfikacji nie wpisuj wyniku z innej maszyny. W opisie PR podaj oba uruchomienia na tej samej maszynie, tryb journal oraz liczbę zapisów.

- [ ] **Step 7: Commit**

```bash
git add tests/test_sqlite_concurrency_performance.py tests/test_ci_performance_smoke.py docs/superpowers/specs/2026-07-27-sqlite-lifecycle-and-telemetry-design.md
git commit -m "test: cover sqlite concurrency performance"
```

## Final Verification

- [ ] Run: `python -m pytest -q`
- [ ] Run: `python -m compileall -q picorgftp_sql tests`
- [ ] Run: `git diff --check`
- [ ] Potwierdź, że backup/restore unieważnia store dopiero po sukcesie.
- [ ] Potwierdź, że `warning`, `error`, `critical` i terminalny stan joba nie są pomijane.
- [ ] Dołącz benchmark przed/po z tej samej maszyny i tej samej bazy testowej.
