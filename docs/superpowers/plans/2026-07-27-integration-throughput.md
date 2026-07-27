# Integration Throughput Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ponownie używać połączeń w granicach jednej operacji, równolegle wykonywać tylko niezależne mapowania i aktualizować zgodne sloty jednym SQL-em.

**Architecture:** `PimcoreClient` otrzymuje transport z lifecycle i sesję `requests.Session` prywatną dla jednej operacji; jawnie wstrzyknięty legacy opener zachowuje obecną ścieżkę testową/fallback. `SqlExecutionContext` leniwie otwiera jedno połączenie per profil w czasie renderowania. Niezależne operacje są klasyfikowane przed wykonaniem i ograniczone do czterech workerów. Tłumaczenia korzystają z bounded TTL cache i singleflight. Standardowy photo update buduje jedną parametryczną instrukcję, a custom template pozostaje na legacy path.

**Tech Stack:** Python 3.14, `requests>=2.31,<3`, `certifi`, MySQL Connector, pyodbc, `concurrent.futures`, pytest.

## Global Constraints

- Zachowaj istniejące profile, sekrety, endpointy, auth, nagłówki, timeouty, proxy i TLS.
- Jedna mutowalna `requests.Session` nie może być współdzielona między jobami ani wątkami.
- Domyślny limit niezależnych operacji wynosi 4.
- Nie wykonuj automatycznego retry POST/PUT po niepewnym wyniku.
- Odczyty weryfikacyjne Pimcore pozostają.
- Mapowania zależne zachowują kolejność i dotychczasowy wynik.
- Custom SQL template, którego nie można bezpiecznie sklasyfikować, używa obecnego fallbacku per slot.
- Nie zmieniaj plików konfiguracji ani lokalizacji sekretów.

## File Structure

- Create: `picorgftp_sql/services/pimcore_transport.py`
- Create: `picorgftp_sql/services/sql_execution_context.py`
- Create: `picorgftp_sql/services/translation_cache.py`
- Create: `picorgftp_sql/services/photo_sql_batch.py`
- Create: `tests/test_pimcore_transport.py`
- Create: `tests/test_sql_execution_context.py`
- Create: `tests/test_translation_cache.py`
- Create: `tests/test_photo_sql_batch.py`
- Create: `tests/test_integration_throughput_performance.py`
- Modify: `picorgftp_sql/services/pimcore_service.py:74-235,667-900,996-1380`
- Modify: `picorgftp_sql/services/pimcore_sql_service.py:174-260`
- Modify: `picorgftp_sql/services/translation_service.py:34-170`
- Modify: `picorgftp_sql/web_data.py:1710-1770,2112-2296`
- Modify: `picorgftp_sql/web/app.py:1953-2120`
- Modify: `picorgftp_sql/app.py:8019-8100`
- Modify: istniejące testy Pimcore, SQL i translation.

---

### Task 1: Transport Pimcore z prywatną sesją

**Files:**

- Create: `picorgftp_sql/services/pimcore_transport.py`
- Create: `tests/test_pimcore_transport.py`
- Modify: `picorgftp_sql/services/pimcore_service.py:74-178`
- Modify: `tests/test_pimcore_service.py`

**Interfaces:**

- Produces: `PimcoreTransport.request_json`; `RequestsPimcoreTransport`; `LegacyPimcoreTransport`; `PimcoreClient.close`, `__enter__`, `__exit__`.
- Consumes: znormalizowane settings i istniejący opener.

- [ ] **Step 1: Napisz test jednej sesji dla wielu requestów**

```python
SETTINGS = {
    "base_url": "https://pimcore.example.test",
    "api_key": "test-secret",
    "verify_tls": True,
    "timeout_seconds": 5,
}


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.text = json.dumps(payload)
        self.headers = {}


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.request_count = 0
        self.close_count = 0

    def request(self, **request):
        self.request_count += 1
        return next(self.responses)

    def close(self):
        self.close_count += 1


def test_client_reuses_private_session_and_closes_it():
    session = FakeSession([
        FakeResponse(200, {"data": []}),
        FakeResponse(200, {"success": True}),
        FakeResponse(200, {"data": {"id": 7}}),
    ])
    with PimcoreClient(SETTINGS, session_factory=lambda: session) as client:
        client.object_list("Product")
        client.create_object({"key": "p-1"})
        client.object_by_id(7)

    assert session.request_count == 3
    assert session.close_count == 1
```

Zaimportuj `json` w pliku testowym. Fake session ma również zapisywać
przekazane request descriptors w liście, aby Step 5 porównał oba transporty.

- [ ] **Step 2: Uruchom test i potwierdź brak session API**

Run: `python -m pytest tests/test_pimcore_transport.py::test_client_reuses_private_session_and_closes_it -v`

Expected: FAIL, konstruktor nie przyjmuje `session_factory`.

- [ ] **Step 3: Zdefiniuj transport requests**

```python
class RequestsPimcoreTransport:
    def __init__(self, session, *, verify_tls: bool):
        self._session = session
        self._verify = certifi.where() if verify_tls else False

    def request(self, method, url, *, headers, query, body, timeout):
        return self._session.request(
            method=method,
            url=url,
            headers=headers,
            params=query or None,
            json=body,
            timeout=(timeout, timeout),
            verify=self._verify,
        )

    def close(self) -> None:
        self._session.close()
```

Nie ustawiaj `trust_env=False`; obecne proxy środowiskowe ma pozostać aktywne.

- [ ] **Step 4: Zachowaj legacy opener**

Jeżeli caller jawnie poda `opener` różny od `_default_opener`, konstruktor tworzy `LegacyPimcoreTransport`. W przeciwnym razie używa transportu requests. W obu ścieżkach `PimcoreClient.request_json` odpowiada za jednolitą walidację statusu, JSON i redakcję.

- [ ] **Step 5: Dodaj test zgodności requestu**

Dla obu transportów sprawdź identyczne: metoda, ścieżka, query, JSON body, `X-api-key`, `Accept`, `Content-Type`, timeout i verify TLS. Sprawdź, że API key nie trafia do URL ani publicznego wyjątku.

- [ ] **Step 6: Uruchom transport i istniejące testy klienta**

Run: `python -m pytest tests/test_pimcore_transport.py tests/test_pimcore_service.py -k "client or api_error or settings_test" -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/services/pimcore_transport.py picorgftp_sql/services/pimcore_service.py tests/test_pimcore_transport.py tests/test_pimcore_service.py
git commit -m "perf: reuse pimcore http session per operation"
```

### Task 2: Własność klienta, close i bezpieczne retry

**Files:**

- Modify: `picorgftp_sql/services/pimcore_service.py:667-900,996-1380`
- Modify: `picorgftp_sql/web_data.py:1710-1770`
- Modify: `tests/test_pimcore_transport.py`
- Modify: `tests/test_pimcore_service.py`
- Modify: `tests/test_pimcore_operations.py`

**Interfaces:**

- Produces: `pimcore_client_scope(config, supplied=None)` context manager.
- Consumes: funkcje, które opcjonalnie przyjmują istniejącego `PimcoreClient`.

- [ ] **Step 1: Napisz test własności supplied client**

```python
def test_client_scope_closes_owned_but_not_supplied_client():
    owned = Mock()
    with pimcore_client_scope(SETTINGS, factory=lambda _config: owned):
        pass
    owned.close.assert_called_once()

    supplied = Mock()
    with pimcore_client_scope(SETTINGS, supplied=supplied) as client:
        assert client is supplied
    supplied.close.assert_not_called()
```

- [ ] **Step 2: Uruchom test i potwierdź brak scope**

Run: `python -m pytest tests/test_pimcore_transport.py -k "client_scope" -v`

Expected: FAIL podczas importu.

- [ ] **Step 3: Dodaj context manager i przełącz call sites**

```python
@contextmanager
def pimcore_client_scope(config, supplied=None, factory=PimcoreClient):
    if supplied is not None:
        yield supplied
        return
    client = factory(config)
    try:
        yield client
    finally:
        client.close()
```

Użyj go w discovery, settings test, fetch/edit, lookup, create, update i test create. Nie zamykaj klienta dostarczonego przez test/callera.

- [ ] **Step 4: Dodaj retry wyłącznie dla idempotentnego GET**

Transport może jednokrotnie powtórzyć GET po wyjątku połączenia na nowej sesji. Test POST i PUT wstrzykuje timeout po wysłaniu i oczekuje dokładnie jednego requestu. Test GET oczekuje dwóch prób i zamknięcia uszkodzonej sesji.

- [ ] **Step 5: Uruchom pełne testy Pimcore**

Run: `python -m pytest tests/test_pimcore_transport.py tests/test_pimcore_service.py tests/test_pimcore_operations.py tests/test_pimcore_web.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add picorgftp_sql/services/pimcore_service.py picorgftp_sql/web_data.py tests/test_pimcore_transport.py tests/test_pimcore_service.py tests/test_pimcore_operations.py tests/test_pimcore_web.py
git commit -m "fix: close owned pimcore clients safely"
```

### Task 3: Jedno połączenie SQL per profil i render

**Files:**

- Create: `picorgftp_sql/services/sql_execution_context.py`
- Create: `tests/test_sql_execution_context.py`
- Modify: `picorgftp_sql/services/pimcore_sql_service.py:174-260`
- Modify: `picorgftp_sql/web_data.py:2112-2296`
- Modify: `tests/test_pimcore_sql_service.py`
- Modify: `tests/test_pimcore_templates.py`

**Interfaces:**

- Produces: `SqlExecutionContext.execute(profile, query, product_values, pimcore_values, mappings) -> SqlValueResult`; context manager lifecycle.
- Consumes: `bind_sql_value_query` i `connect_profile`.

- [ ] **Step 1: Napisz test jednego connect/close**

```python
PROFILE = {
    "type": "mysql",
    "host": "sql.example.test",
    "user": "operator",
    "password": "test-secret",
    "database": "products",
}


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchmany(self, limit):
        return self.rows[:limit]

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.close_count = 0

    def cursor(self):
        return FakeCursor([self.rows.pop(0)])

    def close(self):
        self.close_count += 1


def test_context_reuses_one_connection_for_same_profile():
    connection = FakeConnection(rows=["A", "B"])
    connector = Mock(return_value=connection)
    with SqlExecutionContext(connector=connector) as context:
        first = context.execute(PROFILE, "SELECT 1", {}, {}, mappings=[])
        second = context.execute(PROFILE, "SELECT 2", {}, {}, mappings=[])

    assert first.value == "A"
    assert second.value == "B"
    connector.assert_called_once_with(PROFILE)
    assert connection.close_count == 1
```

- [ ] **Step 2: Uruchom test i potwierdź brak context**

Run: `python -m pytest tests/test_sql_execution_context.py::test_context_reuses_one_connection_for_same_profile -v`

Expected: FAIL podczas importu.

- [ ] **Step 3: Zaimplementuj kontekst**

Fingerprint profilu jest lokalny dla renderu i obejmuje type/host/user/database oraz tożsamość hasła, ale nie jest logowany. `execute` otwiera nowy cursor per zapytanie, zamyka cursor w `finally`, nie zamyka connection. `__exit__` zamyka wszystkie połączenia dokładnie raz.

- [ ] **Step 4: Rozszerz `execute_sql_value_query` o supplied connection**

Dodaj keyword-only `connection=None`. Gdy podano connection, funkcja nie wywołuje connector i nie zamyka connection; nadal zamyka cursor. Domyślna ścieżka zachowuje obecne zachowanie.

- [ ] **Step 5: Owiń cały `_render_templates` jednym contextem**

Zachowaj obecną kolejność pętli. Każde wywołanie SQL deleguje do `context.execute`, dzięki czemu mapowania tego samego profilu współdzielą connection bez zmiany wyniku.

- [ ] **Step 6: Uruchom SQL/template regression**

Run: `python -m pytest tests/test_sql_execution_context.py tests/test_pimcore_sql_service.py tests/test_pimcore_templates.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/services/sql_execution_context.py picorgftp_sql/services/pimcore_sql_service.py picorgftp_sql/web_data.py tests/test_sql_execution_context.py tests/test_pimcore_sql_service.py tests/test_pimcore_templates.py
git commit -m "perf: reuse sql profile connections during render"
```

### Task 4: Cache i singleflight tłumaczeń

**Files:**

- Create: `picorgftp_sql/services/translation_cache.py`
- Create: `tests/test_translation_cache.py`
- Modify: `picorgftp_sql/services/translation_service.py:34-170`
- Modify: `tests/test_translation_service.py`

**Interfaces:**

- Produces: `TranslationCache(max_entries=2048, ttl_seconds=3600)`; `get_or_translate(key, loader, now=None)`.
- Consumes: provider, target, source text i fingerprint konfiguracji.

- [ ] **Step 1: Napisz test TTL i singleflight**

```python
def test_translation_cache_reuses_success_and_singleflights():
    cache = TranslationCache(max_entries=8, ttl_seconds=3600)
    calls = 0

    def loader():
        nonlocal calls
        calls += 1
        return TranslationResult("Hello")

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(
            pool.map(
                lambda _index: cache.get_or_translate(
                    ("google", "en", "Cześć", "cfg-1"),
                    loader,
                    now=100.0,
                ),
                range(10),
            )
        )

    assert calls == 1
    assert {result.text for result in results} == {"Hello"}
```

- [ ] **Step 2: Dodaj test błędu bez cache**

Loader zwraca
`TranslationResult(source, {"code": "translation_failed", "message": "offline"})`;
drugie wywołanie ma ponownie uruchomić loader. Cache zapisuje tylko sukces
bez warning.

- [ ] **Step 3: Uruchom test i potwierdź brak modułu**

Run: `python -m pytest tests/test_translation_cache.py -v`

Expected: FAIL podczas importu.

- [ ] **Step 4: Zaimplementuj bounded LRU**

Użyj `OrderedDict`, `Condition` per key i monotonic clock. Po zapisie przenieś klucz na koniec, usuń najstarsze ponad 2048. Fingerprint konfiguracji jest procesowym HMAC obejmującym provider/api_url/api_key; nie loguj go ani sekretu.

- [ ] **Step 5: Podłącz do `translate_text`**

Zbuduj klucz po walidacji source/target/provider. Wstrzyknięty `opener` w testach nadal jest loaderem. Dodaj `clear_translation_cache()` wywoływane po zapisie ustawień tłumaczeń.

- [ ] **Step 6: Uruchom testy translation**

Run: `python -m pytest tests/test_translation_cache.py tests/test_translation_service.py tests/test_pimcore_templates.py -k "translat" -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/services/translation_cache.py picorgftp_sql/services/translation_service.py tests/test_translation_cache.py tests/test_translation_service.py
git commit -m "perf: cache repeated translations"
```

### Task 5: Kontrolowana równoległość niezależnych mapowań

**Files:**

- Modify: `picorgftp_sql/web_data.py:2112-2296`
- Modify: `picorgftp_sql/services/sql_execution_context.py`
- Modify: `tests/test_pimcore_templates.py`
- Modify: `tests/test_sql_execution_context.py`

**Interfaces:**

- Produces: `classify_template_operation(mapping) -> MappingDependencies`; `execute_independent_operations(operations, max_workers=4)`.
- Consumes: placeholdery istniejącego binder i kolejność mapowań.

- [ ] **Step 1: Napisz test klasyfikacji zależności**

```python
@pytest.mark.parametrize(
    ("mapping", "independent"),
    [
        ({"source": "sql", "query": "SELECT {product.ean}"}, True),
        ({"source": "sql", "query": "SELECT {pimcore.title}"}, False),
        ({"source": "translation", "value": "{product.name}"}, True),
        ({"source": "translation", "value": "{pimcore.description}"}, False),
    ],
)
def test_classify_template_operation(mapping, independent):
    assert classify_template_operation(mapping).independent is independent
```

- [ ] **Step 2: Uruchom test i potwierdź brak klasyfikatora**

Run: `python -m pytest tests/test_pimcore_templates.py -k "classify_template_operation" -v`

Expected: FAIL podczas importu.

- [ ] **Step 3: Klasyfikuj przez istniejący katalog placeholderów**

Nie używaj luźnego wyszukiwania substringów. Wykorzystaj ten sam parser placeholderów co `bind_sql_value_query`. Operacja jest independent tylko wtedy, gdy wszystkie źródła pochodzą z immutable `product_values` lub literalnej konfiguracji.

- [ ] **Step 4: Wykonuj bezpieczne grupy**

Niezależne tłumaczenia i różne profile SQL mogą działać w `ThreadPoolExecutor(max_workers=4)`. Operacje tego samego profilu SQL pozostają w jednym sekwencyjnym lane, aby nie współdzielić connection równocześnie.

Wyniki są składane według pierwotnego indeksu mapowania. Pierwszy błąd wymaganej operacji anuluje jeszcze nierozpoczęte futures; działające bezpiecznie kończą pracę przed zamknięciem contextu.

- [ ] **Step 5: Dodaj test limitu i kolejności**

Użyj bariery i licznika aktywnych loaderów. Oczekuj `peak_active <= 4`, zachowania wyniku w oryginalnej kolejności oraz sekwencyjności dwóch zapytań tego samego profilu.

- [ ] **Step 6: Uruchom template regression**

Run: `python -m pytest tests/test_pimcore_templates.py tests/test_sql_execution_context.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/web_data.py picorgftp_sql/services/sql_execution_context.py tests/test_pimcore_templates.py tests/test_sql_execution_context.py
git commit -m "perf: parallelize independent template mappings"
```

### Task 6: Jeden parametryczny UPDATE standardowych slotów

**Files:**

- Create: `picorgftp_sql/services/photo_sql_batch.py`
- Create: `tests/test_photo_sql_batch.py`
- Modify: `picorgftp_sql/web/app.py:1953-2120`
- Modify: `picorgftp_sql/app.py:8019-8100`
- Modify: `tests/test_web_app_files.py:1268-1504`

**Interfaces:**

- Produces: `PhotoSqlBatch`; `build_photo_sql_batch(table, where_clause, assignments, db_type, template) -> PhotoSqlBatch | None`.
- Consumes: walidowane identyfikatory i standardowy configured template.

- [ ] **Step 1: Napisz test jednego SQL**

```python
def test_builds_one_parameterized_update_for_standard_template():
    batch = build_photo_sql_batch(
        table="products",
        where_clause=" WHERE ean = '5901234567890'",
        assignments={"photo_1": "5901234567890_01.jpg", "photo_2": ""},
        db_type="mssql",
        template="UPDATE {table} SET {column} = '{filename}' {where}",
    )
    assert batch.query == (
        "UPDATE products SET photo_1 = ?, photo_2 = ? "
        "WHERE ean = '5901234567890'"
    )
    assert batch.params == ("5901234567890_01.jpg", "")
```

- [ ] **Step 2: Napisz test custom fallback**

Template zawierający dodatkową funkcję, drugą instrukcję lub nieznany symbol
szablonu ma zwrócić `None`, nie próbować parsowania ani wykonania.

- [ ] **Step 3: Uruchom test i potwierdź brak buildera**

Run: `python -m pytest tests/test_photo_sql_batch.py -v`

Expected: FAIL podczas importu.

- [ ] **Step 4: Zaimplementuj zamkniętą klasyfikację template**

Akceptuj wyłącznie dokładnie wspierane warianty standardowego update po normalizacji whitespace i aliasów `{col}/{column}`. Table/columns przechodzą istniejący `_safe_sql_identifier`. Parametry to `%s` dla MySQL i `?` dla MSSQL.

- [ ] **Step 5: Przełącz web i desktop z fallbackiem**

Zbuduj assignments dla wszystkich poprawnych saved/clear slots. Gdy batch istnieje, wykonaj jedno `cur.execute(batch.query, batch.params)`. `rowcount != 0` oznacza sukces wszystkich assignments; zachowaj `updated`, `cleared`, per-slot status i dotychczasową semantykę `rows` przez pomnożenie dodatniego rowcount przez liczbę assignments.

Gdy builder zwraca `None`, wykonaj obecną pętlę bez zmian.

- [ ] **Step 6: Dodaj rollback i rowcount regression**

Test jednego wyjątku oczekuje jednego rollbacku, zerowych sukcesów i statusu error wszystkich attempted slots. Test `rowcount == 0` zachowuje dotychczasowy skipped/unchanged wynik.

- [ ] **Step 7: Uruchom SQL sync tests**

Run: `python -m pytest tests/test_photo_sql_batch.py tests/test_web_app_files.py -k "sql_sync or photo_sql" -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add picorgftp_sql/services/photo_sql_batch.py picorgftp_sql/web/app.py picorgftp_sql/app.py tests/test_photo_sql_batch.py tests/test_web_app_files.py
git commit -m "perf: batch standard photo sql updates"
```

### Task 7: Benchmark integracji i regresja konfiguracji

**Files:**

- Create: `tests/test_integration_throughput_performance.py`
- Modify: `docs/superpowers/specs/2026-07-27-integration-throughput-design.md`

**Interfaces:**

- Consumes: transport, context SQL, translation cache, parallel executor i batch update.
- Produces: raport liczby sesji/połączeń/requestów/instrukcji i p50/p95.

- [ ] **Step 1: Zbuduj deterministyczne fake integrations**

Każdy fake rejestruje connect/request/execute, czeka 20 ms i zwraca stabilny wynik. Zestaw obejmuje 3 requesty Pimcore, 8 mapowań SQL w 2 profilach, 6 tłumaczeń z 2 duplikatami i 5 slotów zdjęć.

- [ ] **Step 2: Asercje round-trip**

```python
assert pimcore_sessions == 1
assert pimcore_requests == 3
assert sql_connections == 2
assert translation_requests == 4
assert photo_update_statements == 1
assert peak_mapping_workers <= 4
```

- [ ] **Step 3: Test zgodności konfiguracji**

Serializuj request descriptor obu transportów i porównaj method/path/query/body/headers/timeout/TLS. Sprawdź brak API key w descriptorze publicznym i brak zmian w pliku config po operacji.

- [ ] **Step 4: Uruchom pakiet integracji**

Run: `python -m pytest tests/test_pimcore_transport.py tests/test_pimcore_service.py tests/test_pimcore_operations.py tests/test_sql_execution_context.py tests/test_pimcore_sql_service.py tests/test_pimcore_templates.py tests/test_translation_cache.py tests/test_translation_service.py tests/test_photo_sql_batch.py tests/test_integration_throughput_performance.py -q`

Expected: PASS.

- [ ] **Step 5: Uruchom pełny zestaw**

Run: `python -m pytest -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_integration_throughput_performance.py docs/superpowers/specs/2026-07-27-integration-throughput-design.md
git commit -m "test: benchmark integration connection reuse"
```

## Final Verification

- [ ] Run: `python -m pytest -q`
- [ ] Run: `python -m compileall -q picorgftp_sql tests`
- [ ] Run: `git diff --check`
- [ ] Potwierdź jeden prywatny transport per Pimcore operation i brak retry POST/PUT.
- [ ] Potwierdź zgodność config/auth/TLS/proxy oraz działający custom SQL fallback.
- [ ] Dołącz przed/po: sesje HTTP, połączenia SQL, requesty tłumaczeń i instrukcje photo update.
