# Wydajna historia zmian — plan wdrożenia

For agentic workers: use superpowers:executing-plans task-by-task.

Goal: Lista historii pobiera lekkie podsumowania, a pełne zmiany tylko po kliknięciu EAN.

Architecture: web_data zwróci stronę podsumowań albo jedną pełną grupę. API wystawi drugi, chroniony endpoint szczegółów. UI zachowa istniejące modale, anuluje przestarzałe pobranie listy i pobierze pełną grupę po wyborze.

Tech Stack: Python 3.14, FastAPI, SQLite/JSON legacy, JavaScript, unittest/pytest.

## Global constraints

- Nie zmieniać danych trwałych, migracji ani zależności.
- Zachować redakcję danych i istniejące wymaganie zalogowanego użytkownika.
- Zachować automatyczne loadHistory podczas openModal("history").
- Pełna odpowiedź szczegółów pozostawia zgodny kształt items dla renderHistoryDetails.

## File structure

- picorgftp_sql/web_data.py: filtrowanie, podsumowania i pełna grupa.
- picorgftp_sql/web/app.py: chroniony endpoint szczegółów.
- picorgftp_sql/web/static/app.js: pobieranie, anulowanie i renderowanie.
- tests/test_web_data_users.py: kontrakt projekcji danych.
- tests/test_observability_api.py: kontrakt HTTP.
- tests/test_web_ui_integrity.py: kontrakt UI.

### Task 1: Lightweight history summaries

Files:

- Modify: picorgftp_sql/web_data.py, funkcje historii w okolicy linii 543.
- Test: tests/test_web_data_users.py, test historii w okolicy linii 274.

Interfaces:

- Produces history_snapshot(*, user="", query="", page=1, page_size=50).
- Produces history_group_snapshot(*, ean, user="", query="").

- [ ] Step 1: Write the failing data-layer tests.

    def test_history_snapshot_returns_paged_summaries_after_one_load(self) -> None:
        records = [
            {
                "ts": 1000 - index,
                "ean": f"5900000000{index:02}",
                "user": "alice" if index % 2 else "bob",
                "details": {
                    "entry": {"NAZWA": f"Name {index}"},
                    "timing": {"stages": ["large"]},
                },
            }
            for index in range(60)
        ]
        loader = Mock(return_value=records)

        with patch.object(web_data, "_load_history_records", loader):
            payload = web_data.history_snapshot(page=2, page_size=50)

        self.assertEqual(loader.call_count, 1)
        self.assertEqual(payload["page"], 2)
        self.assertEqual(len(payload["groups"]), 10)
        self.assertEqual(
            set(payload["groups"][0]),
            {"ean", "latest_ts", "change_count", "entry"},
        )
        self.assertNotIn("items", payload["groups"][0])

    def test_history_group_snapshot_returns_only_filtered_ean_items(self) -> None:
        records = [
            {
                "ean": "5901",
                "user": "alice",
                "ts": 2,
                "details": {"entry": {"NAZWA": "A"}},
            },
            {"ean": "5901", "user": "bob", "ts": 1, "details": {}},
            {"ean": "5902", "user": "alice", "ts": 3, "details": {}},
        ]

        with patch.object(web_data, "_load_history_records", return_value=records):
            payload = web_data.history_group_snapshot(ean="5901", user="alice")

        self.assertEqual(payload["ean"], "5901")
        self.assertEqual([item["user"] for item in payload["items"]], ["alice"])

- [ ] Step 2: Verify RED.

Run:

    & 'C:/Users/k.bober/AppData/Local/uv/cache/builds-v0/.tmpsIPEAe/Scripts/python.exe' -m pytest tests/test_web_data_users.py -k history -v

Expected: FAIL because groups expose items and history_group_snapshot is absent.

- [ ] Step 3: Implement the shared projection.

    def _filtered_history_records(
        *, user: str = "", query: str = ""
    ) -> list[dict[str, object]]:
        records = sorted(
            _load_history_records(),
            key=_history_timestamp_value,
            reverse=True,
        )
        user_filter = _text(user).lower()
        query_filter = _text(query).casefold()
        if user_filter:
            records = [
                item for item in records
                if _text(item.get("user")).lower() == user_filter
            ]
        if query_filter:
            records = [
                item for item in records
                if query_filter in _history_record_search_text(item)
            ]
        return records

    def history_group_snapshot(
        *, ean: str, user: str = "", query: str = ""
    ) -> dict[str, object] | None:
        normalized_ean = _text(ean) or "BRAK-EAN"
        items = [
            item for item in _filtered_history_records(user=user, query=query)
            if (_text(item.get("ean")) or "BRAK-EAN") == normalized_ean
        ]
        if not items:
            return None
        return {
            "ean": normalized_ean,
            "latest_ts": _history_timestamp_value(items[0]),
            "items": items,
        }

Refactor history_snapshot to call _filtered_history_records once, derive users from the one collection before filters, paginate every matching EAN group, and return only ean, latest_ts, change_count, and entry for selected groups. entry is the first dictionary in details.entry, or {}.

- [ ] Step 4: Verify GREEN.

Run:

    & 'C:/Users/k.bober/AppData/Local/uv/cache/builds-v0/.tmpsIPEAe/Scripts/python.exe' -m pytest tests/test_web_data_users.py -k history -v

Expected: PASS.

### Task 2: Authenticated detail endpoint

Files:

- Modify: picorgftp_sql/web/app.py, history API in the 5087-5103 range.
- Test: tests/test_observability_api.py after the api_environment fixture.

Interfaces:

- Consumes history_group_snapshot(ean, user, query).
- Produces GET /api/history/details with ean, user, and query parameters.

- [ ] Step 1: Write failing API tests.

    def test_history_details_requires_login(api_environment) -> None:
        client, _store = api_environment
        assert client.get("/api/history/details?ean=5901").status_code == 401

    def test_history_details_returns_one_filtered_group(api_environment) -> None:
        client, store = api_environment
        _login(client)
        store.save_history([
            {"id": "a", "ean": "5901", "user": "alice", "ts": 2, "details": {}},
            {"id": "b", "ean": "5901", "user": "bob", "ts": 1, "details": {}},
        ])

        response = client.get("/api/history/details?ean=5901&user=alice")

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == ["a"]
        assert client.get("/api/history/details?ean=missing").status_code == 404

- [ ] Step 2: Verify RED.

Run:

    & 'C:/Users/k.bober/AppData/Local/uv/cache/builds-v0/.tmpsIPEAe/Scripts/python.exe' -m pytest tests/test_observability_api.py -k history_details -v

Expected: FAIL because the route does not exist.

- [ ] Step 3: Add the guarded route.

    @app.get("/api/history/details")
    def history_details_api(
        request: Request, ean: str, user: str = "", query: str = ""
    ) -> Dict[str, Any]:
        _require_user(request)
        payload = history_group_snapshot(ean=ean, user=user, query=query)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail="Nie znaleziono historii dla wybranego EAN.",
            )
        return payload

Remove limit from history_api and from its call to history_snapshot.

- [ ] Step 4: Verify GREEN.

Run:

    & 'C:/Users/k.bober/AppData/Local/uv/cache/builds-v0/.tmpsIPEAe/Scripts/python.exe' -m pytest tests/test_observability_api.py -k history_details -v

Expected: PASS.

### Task 3: Lazy browser detail loading

Files:

- Modify: picorgftp_sql/web/static/app.js in the history helpers and list renderer.
- Test: tests/test_web_ui_integrity.py near the history UI tests.

Interfaces:

- Consumes summary groups from /api/history.
- Consumes one complete group from /api/history/details.
- Produces abortable loadHistory and loadHistoryDetails(group).

- [ ] Step 1: Write the failing UI test.

    def test_history_ui_uses_abortable_summary_and_lazy_detail_requests(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        history_start = source.index("async function loadHistory")
        history_end = source.index("function showHistoryLoadError", history_start)
        history_source = source[history_start:history_end]

        self.assertIn("AbortController", history_source)
        self.assertIn("signal: controller.signal", history_source)
        self.assertNotIn('limit: "1000"', history_source)
        self.assertIn("async function loadHistoryDetails", source)
        self.assertIn('"/api/history/details?"', source)
        self.assertIn("group.change_count", source)
        self.assertIn("group.entry", source)

- [ ] Step 2: Verify RED.

Run:

    & 'C:/Users/k.bober/AppData/Local/uv/cache/builds-v0/.tmpsIPEAe/Scripts/python.exe' -m pytest tests/test_web_ui_integrity.py -k lazy_detail_requests -v

Expected: FAIL because list rows use group.items and no detail request exists.

- [ ] Step 3: Implement the browser change.

    let historyLoadController = null;

    async function loadHistoryDetails(group) {
        historyDetailTitle.textContent = "Historia EAN " + group.ean;
        historyDetailOutput.className = "history-detail-output empty-state";
        historyDetailOutput.textContent = "Wczytywanie szczegolow historii...";
        document.querySelector("#historyDetailModal")?.classList.add("active");
        const params = new URLSearchParams({
            ean: group.ean || "",
            user: historyUserFilter?.value || "",
            query: historySearchInput?.value || "",
        });
        const payload = await requestJson(
            "/api/history/details?" + params.toString()
        );
        renderHistoryDetails(payload);
    }

Before a list request, abort the old historyLoadController, create the next controller, pass signal: controller.signal to requestJson, and render only if that controller remains current. Ignore AbortError in showHistoryLoadError. Render summaries from group.entry, group.change_count, and group.latest_ts. Clicking a summary calls loadHistoryDetails(group).catch(showHistoryDetailLoadError). Keep renderHistoryDetails unchanged.

- [ ] Step 4: Verify GREEN.

Run:

    & 'C:/Users/k.bober/AppData/Local/uv/cache/builds-v0/.tmpsIPEAe/Scripts/python.exe' -m pytest tests/test_web_ui_integrity.py -k lazy_detail_requests -v

Expected: PASS.

### Task 4: Full verification

Files:

- Verify: tests/test_web_data_users.py, tests/test_observability_api.py, tests/test_web_ui_integrity.py, tests/test_source_integrity.py, tests/test_web_app_files.py.

- [ ] Step 1: Run focused tests.

    & 'C:/Users/k.bober/AppData/Local/uv/cache/builds-v0/.tmpsIPEAe/Scripts/python.exe' -m pytest tests/test_web_data_users.py tests/test_observability_api.py tests/test_web_ui_integrity.py -v

Expected: PASS.

- [ ] Step 2: Run source and web-file integrity tests.

    & 'C:/Users/k.bober/AppData/Local/uv/cache/builds-v0/.tmpsIPEAe/Scripts/python.exe' -m pytest tests/test_source_integrity.py tests/test_web_app_files.py -v

Expected: PASS.

- [ ] Step 3: Inspect the diff.

    git diff --check
    git status --short

Expected: no whitespace errors; only plan and implementation changes are present.

## Plan self-review

- Tasks 1–2 make server responses bounded while preserving filters and authorization.
- Task 3 preserves automatic loading on modal open and prevents stale overlapping list results.
- Task 4 supplies regression evidence.
- Summary fields ean, latest_ts, change_count, and entry and detail fields ean, latest_ts, and items are consistent across all layers.
