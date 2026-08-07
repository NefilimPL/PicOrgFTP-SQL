# Complete Integration Throughput Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete package 5, fix the runtime-poller timeout at its cause, and create one operational status register.

**Architecture:** Preserve current public web and desktop contracts while moving resource ownership into explicit contexts. SQL connections, translation values, and standard photo updates become bounded, reusable units; callers retain legacy fallbacks. `STATUS.md` becomes the sole mutable execution register.

**Tech Stack:** Python 3.11+, FastAPI, requests, urllib compatibility adapter, SQLite/MySQL/MSSQL connectors, Node.js test runner, pytest.

## Global Constraints

- Keep Pimcore profiles, secrets, endpoints, headers, TLS, timeouts, and operation semantics compatible.
- Retry exactly one transport-network failure only for `GET`; never retry `POST`, `PUT`, or `DELETE`.
- Never log API keys, passwords, or fingerprints derived from secrets.
- Keep route paths, response shapes, and desktop UI behavior unchanged.
- Use at most four workers for independent template work; do not concurrently use one SQL connection.
- Cache translation successes only; a result carrying a warning must call its loader again.
- Use one standard SQL statement only for recognized standard photo templates; retain the existing per-slot fallback otherwise.
- Do not hide the poller failure by increasing its timeout, skipping it, or weakening its request-budget assertions.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `picorgftp_sql/services/pimcore_service.py` | client ownership and GET-only retry |
| `picorgftp_sql/services/sql_execution_context.py` | render-local SQL connection ownership |
| `picorgftp_sql/services/pimcore_sql_service.py` | query execution with an optional caller-owned connection |
| `picorgftp_sql/services/translation_cache.py` | bounded TTL/LRU singleflight cache |
| `picorgftp_sql/services/translation_service.py` | normalized cache key and cache invalidation entry point |
| `picorgftp_sql/services/photo_sql_batch.py` | conservative standard-update recognizer and batch builder |
| `picorgftp_sql/web_data.py` | composition of Pimcore scope, render context, and bounded operations |
| `picorgftp_sql/web/app.py`, `picorgftp_sql/app.py` | opt into photo SQL batch with legacy fallback |
| `picorgftp_sql/web/static/runtime-status.js` | correct timer/promise lifecycle |
| `tests/test_*` and `tests/js/runtime-status.test.js` | unit, contract, and throughput coverage |
| `docs/superpowers/STATUS.md` | sole mutable status register |

### Task 1: Make the poller failure deterministic and repair its lifecycle

**Files:**
- Modify: `picorgftp_sql/web/static/runtime-status.js`
- Modify: `tests/test_background_runtime_performance.py`
- Modify: `tests/js/runtime-status.test.js`

**Interfaces:**
- Consumes: `RuntimeStatusPoller({ fetchStatus, timerApi, isHidden, onVersionChanged })`.
- Produces: exactly one pending timer after each settled poll and one in-flight request at most.

- [ ] **Step 1: Add a failing Node-level test for settling a visibility transition**

```javascript
test("visibility transition leaves one scheduled poll after a settled flight", async () => {
  const timer = new FakeTimer();
  const poller = new window.PicOrg.RuntimeStatusPoller({
    fetchStatus: async () => ({ versions: {} }), timerApi: timer,
    isHidden: () => false, visibilityTarget: { addEventListener: () => {} },
  });
  await poller.start();
  await timer.runNext(poller);
  assert.equal(timer.pending.size, 1);
});
```

- [ ] **Step 2: Run the Node test and the existing five-client benchmark**

Run: `node --test tests/js/runtime-status.test.js` and `python -m pytest tests/test_background_runtime_performance.py -k javascript -v`.

Expected: capture the pre-fix failure or, if it occurs only in the five-client benchmark, retain its exact trace and request counts before changing code.

- [ ] **Step 3: Change only the proven lifecycle branch**

Keep `inFlight`, `timer`, and `pollImmediatelyAfterFlight` mutually exclusive after a flight settles. A scheduled callback must clear its own timer before calling `pollNow`, and completion must schedule only through `schedule()`.

```javascript
this.timer = this.timerApi.setTimeout(() => {
  this.timer = null;
  void this.pollNow().catch(() => {});
}, Math.max(0, delayMs));
```

- [ ] **Step 4: Verify active/hidden budgets and syntax**

Run: `node --test tests/js/runtime-status.test.js`; `node --check picorgftp_sql/web/static/runtime-status.js`; `python -m pytest tests/test_background_runtime_performance.py -q`.

Expected: all pass without raising the ten-second subprocess timeout.

### Task 2: Close every owned Pimcore client and preserve supplied ownership

**Files:**
- Modify: `picorgftp_sql/services/pimcore_service.py:850-1450`
- Modify: `picorgftp_sql/web_data.py:1751-1785,2557-2730`
- Modify: `tests/test_pimcore_transport.py`, `tests/test_pimcore_service.py`, `tests/test_pimcore_operations.py`, `tests/test_pimcore_web.py`

**Interfaces:**
- Consumes: `pimcore_client_scope(config, supplied=None, factory=PimcoreClient)`.
- Produces: functions that use `with pimcore_client_scope(config, client) as api:` and never close a supplied client.

- [ ] **Step 1: Extend ownership and retry tests**

```python
def test_client_scope_closes_owned_but_not_supplied_client():
    owned = Mock()
    with pimcore_client_scope(SETTINGS, factory=lambda _: owned):
        pass
    owned.close.assert_called_once()
    supplied = Mock()
    with pimcore_client_scope(SETTINGS, supplied=supplied) as api:
        assert api is supplied
    supplied.close.assert_not_called()
```

Add a GET test that raises `PimcoreTransportNetworkError` once and records two sessions, plus POST/PUT tests that record one request only.

- [ ] **Step 2: Run focused transport tests**

Run: `python -m pytest tests/test_pimcore_transport.py -k "client_scope or retry" -v`.

Expected: failures identify every call site that still constructs `PimcoreClient` without a scope.

- [ ] **Step 3: Convert discovery, settings test, fetch, lookup, create, update, and test-create paths**

```python
with pimcore_client_scope(config, client) as api:
    return create_product(api, values)
```

Use the existing `request_json` GET retry implementation. Do not add retry logic to operation-level functions.

- [ ] **Step 4: Run the Pimcore regression set**

Run: `python -m pytest tests/test_pimcore_transport.py tests/test_pimcore_service.py tests/test_pimcore_operations.py tests/test_pimcore_web.py -q`.

Expected: pass with no API key in raised error details.

### Task 3: Reuse SQL connections only within one template render

**Files:**
- Create: `picorgftp_sql/services/sql_execution_context.py`
- Modify: `picorgftp_sql/services/pimcore_sql_service.py`
- Modify: `picorgftp_sql/web_data.py:2133-2290`
- Create: `tests/test_sql_execution_context.py`
- Modify: `tests/test_pimcore_sql_service.py`, `tests/test_pimcore_templates.py`

**Interfaces:**
- Produces: `SqlExecutionContext(connector=connect_profile)` and `execute(profile, query, product_values, pimcore_values, mappings) -> SqlValueResult`.
- Consumes: `execute_sql_value_query(..., connection=None, connector=connect_profile)`.

- [ ] **Step 1: Write the connection-ownership test**

```python
with SqlExecutionContext(connector=connector) as context:
    first = context.execute(PROFILE, "SELECT 1", {}, {}, [])
    second = context.execute(PROFILE, "SELECT 2", {}, {}, [])
assert [first.value, second.value] == ["A", "B"]
connector.assert_called_once_with(PROFILE)
assert connection.close_count == 1
```

- [ ] **Step 2: Run the new test before implementation**

Run: `python -m pytest tests/test_sql_execution_context.py -v`.

Expected: fail at import until the context exists.

- [ ] **Step 3: Add the context and optional connection branch**

```python
def execute_sql_value_query(..., connection=None, connector=connect_profile):
    conn = connection if connection is not None else connector(profile)
    owns_connection = connection is None
```

Always close the cursor; close `conn` only when `owns_connection`. Fingerprint `type`, `host`, `user`, `database`, and password identity without logging it.

- [ ] **Step 4: Wrap `_render_templates` in one context and verify**

Run: `python -m pytest tests/test_sql_execution_context.py tests/test_pimcore_sql_service.py tests/test_pimcore_templates.py -q`.

Expected: same rendered values and exactly one close per profile connection.

### Task 4: Cache successful translations with per-key singleflight

**Files:**
- Create: `picorgftp_sql/services/translation_cache.py`
- Modify: `picorgftp_sql/services/translation_service.py`, `picorgftp_sql/web_data.py:3026-3150`
- Create: `tests/test_translation_cache.py`
- Modify: `tests/test_translation_service.py`, `tests/test_pimcore_templates.py`

**Interfaces:**
- Produces: `TranslationCache(max_entries=2048, ttl_seconds=3600)`, `get_or_translate(key, loader, now=None)`, and `clear_translation_cache()`.

- [ ] **Step 1: Write success, warning, expiry, and concurrent-loader tests**

```python
with ThreadPoolExecutor(max_workers=10) as pool:
    results = list(pool.map(lambda _: cache.get_or_translate(KEY, loader, now=100.0), range(10)))
assert calls == 1
assert {item.text for item in results} == {"Hello"}
```

For a `TranslationResult` containing `warning`, call twice and assert `calls == 2`.

- [ ] **Step 2: Run the focused tests**

Run: `python -m pytest tests/test_translation_cache.py tests/test_translation_service.py -v`.

Expected: fail until cache wiring is present.

- [ ] **Step 3: Implement bounded LRU and configuration-safe key construction**

Use `OrderedDict`, `threading.Condition`, and `time.monotonic`. Build an HMAC fingerprint from provider, API URL, and API key; use it only as part of the cache key. Call `clear_translation_cache()` after accepted translation-setting updates.

- [ ] **Step 4: Verify translation consumers**

Run: `python -m pytest tests/test_translation_cache.py tests/test_translation_service.py tests/test_pimcore_templates.py -k translat -q`.

Expected: duplicate translations share one loader and errors remain uncached.

### Task 5: Bound independent template execution without reordering results

**Files:**
- Modify: `picorgftp_sql/web_data.py:2133-2290`
- Modify: `picorgftp_sql/services/sql_execution_context.py`
- Modify: `tests/test_pimcore_templates.py`, `tests/test_sql_execution_context.py`

**Interfaces:**
- Produces: `classify_template_operation(mapping) -> MappingDependencies` and `execute_independent_operations(operations, max_workers=4)`.

- [ ] **Step 1: Write dependency, concurrency, and ordering tests**

```python
assert classify_template_operation({"source": "sql", "query": "SELECT {product.ean}"}).independent
assert not classify_template_operation({"source": "sql", "query": "SELECT {pimcore.title}"}).independent
assert peak_active <= 4
assert rendered_sources == original_sources
```

- [ ] **Step 2: Run focused template tests**

Run: `python -m pytest tests/test_pimcore_templates.py -k "classify or parallel" -v`.

- [ ] **Step 3: Classify using the existing placeholder parser and group work**

Use `placeholder_sources` and the source catalog; do not use substring matching. Submit only immutable-product/literal operations to `ThreadPoolExecutor(max_workers=4)`, retain same-profile SQL work in one lane, collect by original index, and cancel futures that have not started after the first required error.

- [ ] **Step 4: Verify render behavior**

Run: `python -m pytest tests/test_pimcore_templates.py tests/test_sql_execution_context.py -q`.

Expected: output order and required/optional warning semantics match the serial baseline.

### Task 6: Batch only safe standard photo SQL updates

**Files:**
- Create: `picorgftp_sql/services/photo_sql_batch.py`
- Modify: `picorgftp_sql/web/app.py:1900-2140`, `picorgftp_sql/app.py:8010-8120`
- Create: `tests/test_photo_sql_batch.py`
- Modify: `tests/test_web_app_files.py`

**Interfaces:**
- Produces: `PhotoSqlBatch(query: str, params: tuple[str, ...])` and `build_photo_sql_batch(table, where_clause, assignments, db_type, template) -> PhotoSqlBatch | None`.

- [ ] **Step 1: Write standard, custom-fallback, rollback, and zero-row tests**

```python
batch = build_photo_sql_batch("products", " WHERE ean = '5901234567890'",
    {"photo_1": "5901234567890_01.jpg", "photo_2": ""}, "mssql",
    "UPDATE {table} SET {column} = '{filename}' {where}")
assert batch.params == ("5901234567890_01.jpg", "")
assert batch.query == "UPDATE products SET photo_1 = ?, photo_2 = ? WHERE ean = '5901234567890'"
```

- [ ] **Step 2: Run the new test**

Run: `python -m pytest tests/test_photo_sql_batch.py -v`.

- [ ] **Step 3: Implement the closed recognizer and switch both callers**

Normalize whitespace and accept only existing standard `UPDATE {table} SET {column} = '{filename}' {where}` forms, including `{col}` alias. Validate every identifier with the existing safe identifier helper. Use `?` for MSSQL and `%s` for MySQL. If the builder returns `None`, execute the existing loop unchanged.

- [ ] **Step 4: Verify SQL sync semantics**

Run: `python -m pytest tests/test_photo_sql_batch.py tests/test_web_app_files.py -k "sql_sync or photo_sql" -q`.

Expected: one rollback on batch failure; rowcount zero remains skipped/unchanged.

### Task 7: Add an integration benchmark, consolidate progress, and commit

**Files:**
- Create: `tests/test_integration_throughput_performance.py`
- Create: `docs/superpowers/STATUS.md`
- Modify: `docs/superpowers/README.md`, `docs/superpowers/plans/README.md`, `docs/superpowers/specs/README.md`, `docs/superpowers/specs/2026-07-27-integration-throughput-design.md`

- [ ] **Step 1: Add deterministic integration counters**

```python
assert report.pimcore_sessions == 1
assert report.sql_connections == 2
assert report.translation_requests == 4
assert report.photo_update_statements == 1
assert report.peak_mapping_workers <= 4
```

Use fakes with 20 ms work, three Pimcore requests, eight SQL mappings on two profiles, six translations with two duplicates, and five photo slots.

- [ ] **Step 2: Write the single status register**

Use one table with package, task, state, commit, and verification columns. Record completed packages 1–6, the just-completed package 5, pending package 7, and environmental verification prerequisites. Replace status tables in the three README files with a one-paragraph link to `STATUS.md`.

- [ ] **Step 3: Run package and full verification in a clean environment**

Run: `python -m pytest tests/test_pimcore_transport.py tests/test_pimcore_service.py tests/test_pimcore_operations.py tests/test_sql_execution_context.py tests/test_pimcore_sql_service.py tests/test_pimcore_templates.py tests/test_translation_cache.py tests/test_translation_service.py tests/test_photo_sql_batch.py tests/test_integration_throughput_performance.py -q`; `python -m pytest -q`; `python -m compileall -q picorgftp_sql tests`; `node --test tests/js/runtime-status.test.js`; `git diff --check`.

Expected: all pass in the clean environment; retain a truthful environment note in `STATUS.md` if an external prerequisite prevents a local command.

- [ ] **Step 4: Commit the completed first stage**

```bash
git add picorgftp_sql tests docs/superpowers
git commit -m "perf: complete integration throughput improvements"
```

