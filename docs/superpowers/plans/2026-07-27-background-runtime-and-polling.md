# Background Runtime and Polling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Budzić worker powiadomień według pracy/terminu, skonsolidować statusowe requesty frontendu i wykonywać persistence aktywnych klientów poza blokadą requestu.

**Architecture:** `WakeableDeadlineScheduler` łączy condition, wake generation i maksymalny fallback 60 s. Worker po cyklu oblicza najbliższy termin z trwałego store, a każda operacja enqueue go budzi. `ActiveClientRegistry` oddziela pamięciowy lock od jednego writera I/O. `/api/runtime-status` zwraca health i wersje lekkich podsystemów; jeden scheduler JS pobiera szczegóły tylko po zmianie wersji.

**Tech Stack:** Python 3.14, `threading.Condition`, `ThreadPoolExecutor(max_workers=1)`, FastAPI, vanilla JavaScript, Node `node:test`, pytest.

## Global Constraints

- Maksymalny bezczynny polling awaryjny workera wynosi 60 s.
- Nowe zadanie budzi worker natychmiast; restart nadal odtwarza pracę z SQLite.
- Shutdown workera nie czeka na pełny timeout scheduler.
- Istniejące endpointy health/file-index/process/presence pozostają kompatybilne.
- Logi nadal używają istniejącego SSE; runtime status nie zwraca pełnych logów.
- Aktywni klienci nadal są zapisywani atomowo w dotychczasowym formacie JSON.
- Serializacja i I/O aktywnych klientów nie mogą odbywać się pod lockiem rejestru.
- Nie zmieniaj treści, odbiorców, kanałów ani retry policy powiadomień.

## File Structure

- Create: `picorgftp_sql/notification_scheduler.py`
- Create: `picorgftp_sql/web/active_clients.py`
- Create: `picorgftp_sql/web/runtime_status.py`
- Create: `picorgftp_sql/web/static/runtime-status.js`
- Create: `tests/test_notification_scheduler.py`
- Create: `tests/test_active_clients_registry.py`
- Create: `tests/test_runtime_status.py`
- Create: `tests/js/runtime-status.test.js`
- Create: `tests/test_background_runtime_performance.py`
- Modify: `picorgftp_sql/notification_service.py:1184-1201,1364-1495`
- Modify: `picorgftp_sql/sqlite_store.py:2432-2804`
- Modify: `picorgftp_sql/data_store.py:183-260`
- Modify: `picorgftp_sql/web/app.py:193-197,4005-4256,4905-4915,5083-5090,5340-5355,6651-6668`
- Modify: `picorgftp_sql/web/static/app.js:150-180,882-920,4295-4345,6579-6650,7330-7370`
- Modify: `picorgftp_sql/web/static/index.html:710`
- Modify: testy notification/web/static.

---

### Task 1: Wakeable deadline scheduler

**Files:**

- Create: `picorgftp_sql/notification_scheduler.py`
- Create: `tests/test_notification_scheduler.py`

**Interfaces:**

- Produces: `WakeableDeadlineScheduler.wait(stop_event, delay_seconds) -> str`; `wake() -> None`.
- Consumes: maksymalny fallback 60 s i zewnętrzny stop event.

- [ ] **Step 1: Napisz test natychmiastowego wake**

```python
def test_scheduler_wake_interrupts_wait():
    scheduler = WakeableDeadlineScheduler(max_idle_seconds=60)
    stop = threading.Event()
    result = []
    thread = threading.Thread(
        target=lambda: result.append(scheduler.wait(stop, delay_seconds=60))
    )
    thread.start()
    assert scheduler.wait_until_waiting(timeout=1.0)
    scheduler.wake()
    thread.join(timeout=1.0)

    assert result == ["wake"]
```

- [ ] **Step 2: Napisz test stop oraz ograniczenia deadline**

`stop.set(); scheduler.wake()` zwraca `stop`. `delay_seconds=120` kończy się po wstrzykniętym zegarze/condition timeout równym 60, nie 120. Użyj fake condition zamiast realnego oczekiwania minuty.

- [ ] **Step 3: Uruchom test i potwierdź brak modułu**

Run: `python -m pytest tests/test_notification_scheduler.py -v`

Expected: FAIL podczas importu.

- [ ] **Step 4: Zaimplementuj generation-based wake**

```python
class WakeableDeadlineScheduler:
    def __init__(self, max_idle_seconds: float = 60.0):
        self._condition = threading.Condition()
        self._generation = 0
        self._max_idle = max_idle_seconds

    def wake(self) -> None:
        with self._condition:
            self._generation += 1
            self._condition.notify_all()

    def wait(self, stop_event, delay_seconds: float | None) -> str:
        timeout = self._max_idle
        if delay_seconds is not None:
            timeout = max(0.0, min(timeout, float(delay_seconds)))
        with self._condition:
            generation = self._generation
            if stop_event.is_set():
                return "stop"
            self._condition.wait_for(
                lambda: stop_event.is_set() or self._generation != generation,
                timeout=timeout,
            )
            if stop_event.is_set():
                return "stop"
            return "wake" if self._generation != generation else "deadline"
```

- [ ] **Step 5: Uruchom testy scheduler**

Run: `python -m pytest tests/test_notification_scheduler.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add picorgftp_sql/notification_scheduler.py tests/test_notification_scheduler.py
git commit -m "feat: add wakeable notification scheduler"
```

### Task 2: Terminy trwałe i integracja workera

**Files:**

- Modify: `picorgftp_sql/sqlite_store.py:2432-2804`
- Modify: `picorgftp_sql/data_store.py:183-260`
- Modify: `picorgftp_sql/notification_service.py:1184-1201,1364-1495`
- Modify: `tests/test_notification_scheduler.py`
- Modify: `tests/test_notification_service.py:898-1035,1264-1335`

**Interfaces:**

- Produces: `next_notification_due_at() -> str`; `wake_notification_worker() -> None`.
- Consumes: pending deliveries/outbox, daily summary i scheduler z Task 1.

- [ ] **Step 1: Napisz test najbliższego trwałego terminu**

```python
def seed_pending_delivery(store, delivery_id, next_attempt_at):
    with store.connection() as conn:
        conn.execute(
            """
            INSERT INTO notification_deliveries (
                id, severity, status, primary_channel, message_json,
                created_at, updated_at, next_attempt_at
            ) VALUES (?, 'warning', 'pending', 'smtp', '{}', ?, ?, ?)
            """,
            (
                delivery_id,
                "2026-07-27T10:00:00Z",
                "2026-07-27T10:00:00Z",
                next_attempt_at,
            ),
        )


def test_next_notification_due_at_returns_oldest_pending(tmp_path):
    store = SqliteStore(str(tmp_path / "notifications.sqlite"))
    store.initialize()
    seed_pending_delivery(store, delivery_id="late", next_attempt_at="2026-07-27T12:00:00Z")
    seed_pending_delivery(store, delivery_id="early", next_attempt_at="2026-07-27T11:00:00Z")
    assert store.next_notification_due_at() == "2026-07-27T11:00:00Z"
```

- [ ] **Step 2: Uruchom test i potwierdź brak store API**

Run: `python -m pytest tests/test_notification_scheduler.py -k "next_notification_due" -v`

Expected: FAIL z `AttributeError`.

- [ ] **Step 3: Dodaj indeksowane zapytanie terminu**

Zapytanie pobiera `MIN(next_attempt_at)` wyłącznie dla statusów pending/retry zgodnych z obecną logiką. Dodaj delegację adaptera. Nie skanuj ani nie materializuj dostaw.

- [ ] **Step 4: Przełącz worker loop**

Po `process_pending_batch` i monitorze Entra oblicz delay do najbliższego terminu, raportu dziennego oraz następnego prune. Wywołaj `_WORKER_SCHEDULER.wait(stop_event, delay)`.

`stop_notification_worker()` po `stop_event.set()` zawsze wywołuje scheduler `wake()`.

- [ ] **Step 5: Podłącz wake do wszystkich enqueue**

Po udanym trwałym utworzeniu intencji/dostawy wywołaj `wake_notification_worker()`. Nie budź przed commitem. Test spy ma wykazać jedno wake po sukcesie i zero po rollbacku/błędzie.

- [ ] **Step 6: Dodaj test restartu bez pamięciowego wake**

Seeduj zaległą dostawę przed startem workera, uruchom worker i oczekuj próby bez wywołania `wake`. To potwierdza, że sygnał jest optymalizacją, nie źródłem prawdy.

- [ ] **Step 7: Uruchom testy workera**

Run: `python -m pytest tests/test_notification_scheduler.py tests/test_notification_service.py tests/test_notification_outbox.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add picorgftp_sql/sqlite_store.py picorgftp_sql/data_store.py picorgftp_sql/notification_service.py tests/test_notification_scheduler.py tests/test_notification_service.py tests/test_notification_outbox.py
git commit -m "perf: wake notification worker on due work"
```

### Task 3: `ActiveClientRegistry` z writerem poza lockiem

**Files:**

- Create: `picorgftp_sql/web/active_clients.py`
- Create: `tests/test_active_clients_registry.py`
- Modify: `picorgftp_sql/web/app.py:193-197,4087-4256`
- Modify: `tests/test_web_app_files.py:2067-2258`

**Interfaces:**

- Produces: `ActiveClientRegistry.record`, `remove`, `snapshot`, `schedule_flush`, `flush`, `close`, `generation`.
- Consumes: obecny payload klienta i path pliku JSON.

- [ ] **Step 1: Napisz test, że writer nie trzyma locka**

```python
def client_record(username: str, generation: int) -> dict[str, object]:
    return {
        "username": username,
        "client_id": f"browser-{generation}",
        "last_seen_epoch": float(generation),
        "last_seen": "2026-07-27 10:00:00",
        "method": "GET",
        "path": "/",
        "status_code": 200,
        "remote_address": "127.0.0.1",
        "remote_port": 12345,
        "user_agent": "test",
    }


def test_writer_serializes_without_holding_registry_lock(tmp_path):
    lock_was_free = []

    def serializer(payload):
        acquired = registry.acquire_lock_for_test(blocking=False)
        lock_was_free.append(acquired)
        if acquired:
            registry.release_lock_for_test()
        return json.dumps(payload)

    registry = ActiveClientRegistry(tmp_path / "active.json", serializer=serializer)
    registry.record(client_record("alice", generation=1))
    registry.flush(force=True)

    assert lock_was_free == [True]
```

- [ ] **Step 2: Napisz test generacji zmienionej podczas I/O**

Serializer blokuje się eventem. Po rozpoczęciu zapisu dodaj drugi rekord, zwolnij event i oczekuj drugiego flushu oraz obu rekordów w pliku.

- [ ] **Step 3: Uruchom test i potwierdź brak modułu**

Run: `python -m pytest tests/test_active_clients_registry.py -v`

Expected: FAIL podczas importu.

- [ ] **Step 4: Zaimplementuj snapshot/write/ack**

Pod lockiem kopiuj listę, `generation` i ustawiaj `_write_scheduled`. Po zwolnieniu locka serializuj, zapisz sibling temp file i `os.replace`. Pod lockiem ustaw `_persisted_generation`; jeżeli `generation` wzrosła, submituj kolejny write do jednego `ThreadPoolExecutor(max_workers=1)`.

Minimalny odstęp zwykłego flushu to 15 s. `force=True` omija interwał, ale nie uruchamia drugiego writera równolegle.

- [ ] **Step 5: Przełącz web app**

Zastąp globalne dict/lock/dirty wywołaniami rejestru. Middleware `record` tylko modyfikuje pamięć i planuje flush. Presence endpoint pobiera snapshot. Leave wywołuje remove i force flush bez I/O pod lockiem.

Lifespan przy shutdown wywołuje `registry.close(timeout=5.0)`.

- [ ] **Step 6: Uruchom active presence regression**

Run: `python -m pytest tests/test_active_clients_registry.py tests/test_web_app_files.py -k "active_presence or active_client" -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/web/active_clients.py picorgftp_sql/web/app.py tests/test_active_clients_registry.py tests/test_web_app_files.py
git commit -m "perf: persist active clients outside request lock"
```

### Task 4: Lekki `/api/runtime-status`

**Files:**

- Create: `picorgftp_sql/web/runtime_status.py`
- Create: `tests/test_runtime_status.py`
- Modify: `picorgftp_sql/web/app.py:4905-4915,5083-5090,5340-5355,6651-6668`

**Interfaces:**

- Produces: `RuntimeStatusService.snapshot(user_context) -> dict`; GET `/api/runtime-status`.
- Consumes: istniejący health snapshot, file-index status, process queue summary i active registry generation.

- [ ] **Step 1: Napisz test minimalnego kontraktu**

```python
def runtime_payload():
    return {
        "observed_at": "2026-07-27T10:00:00Z",
        "health": {"ok": True, "status": "online"},
        "versions": {
            "file_index": "index-1",
            "process_queue": "queue-1",
            "active_clients": "clients-1",
        },
        "summary": {
            "file_index_state": "ready",
            "process_active": 0,
            "active_users_enabled": False,
        },
    }


@pytest.fixture
def client():
    return TestClient(web_app.app)


def test_runtime_status_contains_summaries_not_detail_lists(client):
    response = client.get("/api/runtime-status")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"observed_at", "health", "versions", "summary"}
    assert "jobs" not in payload
    assert "users" not in payload
    assert "events" not in payload
```

- [ ] **Step 2: Napisz test uprawnień**

Użytkownik bez prawa do presence otrzymuje tylko `active_users_enabled=False` i nie otrzymuje liczby/nazw. Admin otrzymuje liczbę oraz generation, nigdy pełną listę w runtime status.

- [ ] **Step 3: Uruchom test i potwierdź 404**

Run: `python -m pytest tests/test_runtime_status.py -v`

Expected: FAIL z HTTP 404.

- [ ] **Step 4: Zaimplementuj snapshot**

```python
{
    "observed_at": iso_now,
    "health": {"ok": health_ok, "status": health_status},
    "versions": {
        "file_index": file_index_version,
        "process_queue": process_queue_version,
        "active_clients": active_clients_version,
    },
    "summary": {
        "file_index_state": file_index_state,
        "process_active": process_active_count,
        "active_users_enabled": presence_allowed,
        "active_users_count": allowed_count,
    },
}
```

Wersje są stabilnymi wartościami: `generated_at/state` indeksu, generation
kolejki i generation rejestru. Dodaj `/api/runtime-status` do dokładnego
zbioru wykluczeń middleware obok `/api/health`, `/api/logout` oraz
`/api/server/presence/leave`, aby endpoint nie zapisywał obecności sam dla
siebie.

- [ ] **Step 5: Dodaj kontrolowany partial failure**

Błąd jednego providera daje jego wersję `"unknown"` i summary status `"unknown"`, a endpoint nadal 200. Nie zwracaj tracebacka.

- [ ] **Step 6: Uruchom API tests**

Run: `python -m pytest tests/test_runtime_status.py tests/test_web_app_files.py -k "health or file_index or process_jobs or presence" -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/web/runtime_status.py picorgftp_sql/web/app.py tests/test_runtime_status.py tests/test_web_app_files.py
git commit -m "feat: add consolidated runtime status"
```

### Task 5: Jeden scheduler statusu w JavaScript

**Files:**

- Create: `picorgftp_sql/web/static/runtime-status.js`
- Create: `tests/js/runtime-status.test.js`
- Modify: `picorgftp_sql/web/static/app.js:150-180,882-920,4295-4345,6579-6650,7330-7370`
- Modify: `picorgftp_sql/web/static/index.html:710`
- Modify: test assetów w `tests/test_web_app_files.py`

**Interfaces:**

- Produces: `window.PicOrg.RuntimeStatusPoller`.
- Consumes: callback `fetchStatus`, `onVersionChanged`, visibility provider i timer API.

- [ ] **Step 1: Napisz test pojedynczego requestu i interwałów**

```javascript
const test = require("node:test");
const assert = require("node:assert/strict");
global.window = { PicOrg: {} };
require("../../picorgftp_sql/web/static/runtime-status.js");

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

test("poller does not overlap and uses hidden interval", async () => {
  const calls = [];
  const pending = deferred();
  const poller = new window.PicOrg.RuntimeStatusPoller({
    fetchStatus: () => {
      calls.push("fetch");
      return pending.promise;
    },
    activeIntervalMs: 5000,
    hiddenIntervalMs: 30000,
    isHidden: () => true,
  });
  const first = poller.pollNow();
  const second = poller.pollNow();
  assert.equal(calls.length, 1);
  pending.resolve({ versions: {} });
  await Promise.all([first, second]);
  assert.equal(poller.nextDelayMs(), 30000);
});
```

- [ ] **Step 2: Uruchom test i potwierdź brak modułu**

Run: `node --test tests/js/runtime-status.test.js`

Expected: FAIL z `MODULE_NOT_FOUND`.

- [ ] **Step 3: Zaimplementuj poller**

Poller utrzymuje jedno promise in-flight, poprzednie versions, active 5000 ms, hidden 30000 ms i backoff maksymalnie 60000 ms. Po `visibilitychange` do visible anuluje timer i wykonuje natychmiastowy poll.

- [ ] **Step 4: Przełącz `app.js`**

Usuń osobne harmonogramy health/fileIndex/processQueue/activeUsers. Jeden poll runtime:

1. aktualizuje health summary;
2. porównuje versions;
3. wywołuje `refreshFileIndexStatus`, `refreshProcessQueue` lub `refreshActiveUsersPresence` tylko po zmianie właściwej wersji albo otwarciu widoku;
4. nie uruchamia `pollLogStatus`, gdy aktywny jest SSE.

Istniejące funkcje szczegółowe i endpointy pozostają.

- [ ] **Step 5: Dodaj asset i test braku starych pollerów**

Załaduj `runtime-status.js` przed `app.js`. Test źródła sprawdza brak `createPoller("fileIndex"`, `"processQueue"` i `"activeUsers"` oraz obecność jednego `RuntimeStatusPoller`.

- [ ] **Step 6: Uruchom JS**

Run: `node --test tests/js/runtime-status.test.js`

Run: `node --check picorgftp_sql/web/static/runtime-status.js`

Run: `node --check picorgftp_sql/web/static/app.js`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/web/static/runtime-status.js picorgftp_sql/web/static/app.js picorgftp_sql/web/static/index.html tests/js/runtime-status.test.js tests/test_web_app_files.py
git commit -m "perf: consolidate frontend runtime polling"
```

### Task 6: Benchmark bezczynności i pełna regresja

**Files:**

- Create: `tests/test_background_runtime_performance.py`
- Modify: `docs/superpowers/specs/2026-07-27-background-runtime-and-polling-design.md`

**Interfaces:**

- Consumes: scheduler workera, runtime endpoint/poller i active registry.
- Produces: liczniki cykli, requestów, czasu wake i lock wait.

- [ ] **Step 1: Dodaj benchmark 60 s z fake clock**

Przesuń fake clock o 60 s bez pracy. Oczekuj najwyżej dwóch wywołań `process_pending_batch`. Następnie enqueue i wake; oczekuj próby przetworzenia przed kolejnym fallback deadline.

- [ ] **Step 2: Dodaj test czasu stop**

Uruchom realny scheduler czekający 60 s, wywołaj stop i zmierz join:

```python
assert stop_elapsed < 1.0
```

- [ ] **Step 3: Dodaj symulację pięciu klientów**

Każdy fake poller działa minutę aktywnie i minutę hidden. Oczekuj najwyżej 12 aktywnych i 2 hidden runtime requestów per klient, bez nakładania. Szczegółowe endpointy nie są wywoływane przy niezmienionych versions.

- [ ] **Step 4: Dodaj contention aktywnych klientów**

W czasie zablokowanego writer I/O wykonaj 100 `record()`. Mierz czas lock wait i sprawdź, że wszystkie rekordy trafiają do następnej generacji.

- [ ] **Step 5: Uruchom pakiet**

Run: `python -m pytest tests/test_notification_scheduler.py tests/test_notification_service.py tests/test_notification_outbox.py tests/test_active_clients_registry.py tests/test_runtime_status.py tests/test_background_runtime_performance.py tests/test_web_app_files.py -q`

Run: `node --test tests/js/runtime-status.test.js`

Expected: PASS.

- [ ] **Step 6: Uruchom pełną regresję**

Run: `python -m pytest -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_background_runtime_performance.py docs/superpowers/specs/2026-07-27-background-runtime-and-polling-design.md
git commit -m "test: cover background runtime efficiency"
```

## Final Verification

- [ ] Run: `python -m pytest -q`
- [ ] Run: `node --test tests/js/runtime-status.test.js`
- [ ] Run: `node --check picorgftp_sql/web/static/runtime-status.js`
- [ ] Run: `node --check picorgftp_sql/web/static/app.js`
- [ ] Run: `git diff --check`
- [ ] Potwierdź wake po commit, odtworzenie po restarcie i stop poniżej 1 s.
- [ ] Potwierdź brak I/O pod active-client lock i brak pełnych danych w runtime status.
