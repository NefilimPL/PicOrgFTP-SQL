# Pimcore Guided Setup And Existing Product Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the low-level Pimcore settings form with an administrator-only first-run wizard and compact maintenance screen, correct Pimcore 6.6 EAN filtering, and let ordinary users safely edit selected fields of existing Pimcore products.

**Architecture:** Extend the normalized Pimcore configuration without changing encrypted-secret persistence, add structured legacy REST discovery/update helpers to the existing service, and expose thin admin/runtime FastAPI routes through `web_data.py`. Keep the vanilla JavaScript application architecture, but separate first-run setup state, compact settings state, and runtime edit state so disabled/incomplete integrations never trigger network calls.

**Tech Stack:** Python 3, FastAPI, standard-library `urllib`/`json`, existing encrypted JSON/SQLite settings and audit stores, vanilla JavaScript, HTML/CSS, pytest/unittest, Playwright with installed Microsoft Edge for final browser verification.

**Design:** `docs/superpowers/specs/2026-07-02-pimcore-guided-setup-and-editing-design.md`

**Pimcore references:**

- `https://github.com/pimcore/pimcore/blob/v6.6.11/bundles/AdminBundle/Controller/Rest/Element/DataObjectController.php#L381-L420`
- `https://github.com/pimcore/pimcore/blob/v6.6.11/bundles/AdminBundle/Controller/Rest/Helper.php#L24-L117`
- `https://github.com/pimcore/pimcore/blob/v6.6.11/bundles/AdminBundle/Controller/Rest/Element/DataObjectController.php#L243-L331`
- `https://github.com/pimcore/pimcore/blob/v6.6.11/models/Webservice/Data/DataObject/Concrete.php#L77-L120`

---

## File Responsibility Map

- `picorgftp_sql/pimcore_config.py`: normalized setup state, migration inference, EAN mapping rules, and field-type/parser inference.
- `picorgftp_sql/services/pimcore_service.py`: legacy REST transport, structured filters, discovery normalization, diagnostics, complete-object update merge, conflict detection, and write verification.
- `picorgftp_sql/web_data.py`: safe settings snapshots, unsaved discovery adapters, atomic setup completion, runtime gating, create/update audit records, and edit form schemas.
- `picorgftp_sql/web/app.py`: authenticated admin discovery/setup routes and ordinary-user runtime read/update routes.
- `picorgftp_sql/web/static/index.html`: first-run wizard, runtime edit button, and edit modal structure.
- `picorgftp_sql/web/static/app.js`: wizard/compact settings rendering, dependency-aware diagnostics, runtime control visibility, and edit interaction.
- `picorgftp_sql/web/static/app.css`: responsive wizard, compact field table, expandable diagnostics, and edit modal layout.
- `tests/test_pimcore_config.py`: config migration/inference tests.
- `tests/test_pimcore_service.py`: REST filter/discovery/diagnostic/update tests.
- `tests/test_pimcore_web.py`: settings adapter and FastAPI route tests.
- `tests/test_pimcore_operations.py`: audit redaction and operation-kind coverage where registry behavior changes.
- `tests/test_web_ui_integrity.py`: required HTML structure.
- `tests/test_source_integrity.py`: JavaScript wiring and no-mutation-on-cancel contracts.
- `README.md`: administrator setup, runtime create/edit, permissions, and failure recovery.

---

### Task 1: Guided Setup Configuration And Migration

**Files:**
- Modify: `picorgftp_sql/pimcore_config.py`
- Modify: `tests/test_pimcore_config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for guided defaults, legacy migration, and inferred field mappings**

Add these imports and tests to `tests/test_pimcore_config.py`:

```python
from picorgftp_sql.pimcore_config import (
    infer_field_mapping,
    normalize_pimcore_settings,
)


def test_guided_setup_defaults_hide_technical_choices():
    result = normalize_pimcore_settings({})

    assert result["setup_complete"] is False
    assert result["class_id"] == ""
    assert result["class_name"] == ""
    assert result["parent_path"] == ""
    assert result["object_key_template"] == "{EAN}"
    assert result["timeout_seconds"] == 30


def test_complete_legacy_configuration_infers_setup_complete():
    result = normalize_pimcore_settings(
        {
            "base_url": "http://10.10.0.5",
            "api_key": "secret",
            "class_name": "product",
            "parent_id": "6626",
            "field_mappings": [
                {
                    "source": "EAN",
                    "pimcore_field": "EAN",
                    "type": "input",
                    "required": True,
                    "parser": "text",
                }
            ],
        }
    )

    assert result["setup_complete"] is True
    assert result["existence_fields"] == ["EAN"]
    assert result["object_key_template"] == "{EAN}"


def test_explicit_disabled_complete_setup_stays_complete():
    result = normalize_pimcore_settings(
        {
            "setup_complete": True,
            "enabled": False,
            "class_name": "product",
            "parent_id": "6626",
            "field_mappings": [],
        }
    )

    assert result["setup_complete"] is True
    assert result["enabled"] is False


def test_infer_field_mapping_uses_class_type_and_locks_ean():
    ean = infer_field_mapping(
        source="EAN",
        label="EAN",
        pimcore_field="eanCode",
        field_type="input",
        required=False,
    )
    weight = infer_field_mapping(
        source="TOTAL WEIGHT",
        label="Waga calkowita",
        pimcore_field="totalWeight",
        field_type="numeric",
        required=False,
    )

    assert ean == {
        "source": "EAN",
        "label": "EAN",
        "pimcore_field": "eanCode",
        "type": "input",
        "language": None,
        "required": True,
        "default": "",
        "parser": "text",
    }
    assert weight["parser"] == "decimal_comma"
```

Update the existing default assertions that expect `Product`, `{SKU}`, or timeout `10` to expect an empty class, `{EAN}`, and `30`.

- [ ] **Step 2: Run the focused tests and verify the new behavior is missing**

Run:

```powershell
pytest tests/test_pimcore_config.py tests/test_config.py -v
```

Expected: FAIL because `infer_field_mapping` and the new normalized keys/defaults do not exist.

- [ ] **Step 3: Implement setup-state normalization and field inference**

In `picorgftp_sql/pimcore_config.py`, extend the defaults and add the inference helpers:

```python
SUPPORTED_FIELD_PARSERS = {
    "input": "text",
    "textarea": "text",
    "numeric": "decimal_comma",
    "checkbox": "boolean",
    "select": "text",
}

DEFAULT_PIMCORE_SETTINGS: dict[str, Any] = {
    "setup_complete": False,
    "enabled": False,
    "base_url": "http://10.10.0.5",
    PIMCORE_API_KEY: "",
    "class_id": "",
    "class_name": "",
    "parent_id": "",
    "parent_path": "",
    "published": True,
    "object_key_template": "{EAN}",
    "existence_fields": ["EAN"],
    "timeout_seconds": 30,
    "verify_tls": True,
    "field_mappings": [],
}


def infer_field_mapping(
    *,
    source: object,
    label: object,
    pimcore_field: object,
    field_type: object,
    language: object = None,
    required: bool = False,
) -> dict[str, Any]:
    source_text = _text(source)
    target = _text(pimcore_field)
    normalized_type = _text(field_type).lower()
    if not source_text or not PIMCORE_FIELD_NAME.fullmatch(target):
        raise ValueError("Pole formularza i pole Pimcore sa wymagane.")
    if normalized_type not in SUPPORTED_FIELD_PARSERS:
        raise ValueError(f"Nieobslugiwany typ pola Pimcore: {normalized_type or '[pusty]' }.")
    is_ean = source_text.casefold() == "ean"
    return {
        "source": "EAN" if is_ean else source_text,
        "label": _text(label) or source_text,
        "pimcore_field": target,
        "type": normalized_type,
        "language": _text(language) or None,
        "required": True if is_ean else bool(required),
        "default": "",
        "parser": SUPPORTED_FIELD_PARSERS[normalized_type],
    }


def _legacy_setup_is_complete(settings: dict[str, Any]) -> bool:
    mappings = settings.get("field_mappings") or []
    ean_mapping = next(
        (
            item
            for item in mappings
            if str(item.get("source") or "").casefold() == "ean"
            and bool(item.get("required"))
        ),
        None,
    )
    return bool(
        settings.get("base_url")
        and settings.get(PIMCORE_API_KEY)
        and settings.get("class_name")
        and settings.get("parent_id")
        and ean_mapping
    )
```

In `normalize_pimcore_settings`, normalize `class_id`, `parent_path`, and mappings before setup inference. Force `{EAN}`, derive `existence_fields` from the normalized EAN target when present, default timeout to `30`, and use this final setup assignment:

```python
    settings["class_id"] = _text(source.get("class_id"))
    settings["class_name"] = _text(source.get("class_name"))
    settings["parent_path"] = _text(source.get("parent_path"))
    settings["object_key_template"] = "{EAN}"
    ean_targets = [
        item["pimcore_field"]
        for item in mappings
        if item["source"].casefold() == "ean"
    ]
    settings["existence_fields"] = ean_targets or fields or ["EAN"]
    if "setup_complete" in source:
        settings["setup_complete"] = bool(source.get("setup_complete"))
    else:
        settings["setup_complete"] = _legacy_setup_is_complete(settings)
```

- [ ] **Step 4: Prove encrypted persistence and blank-secret preservation still work**

Add to `tests/test_config.py` a round-trip assertion containing `setup_complete`, `class_id`, and `parent_path`, while retaining the existing assertion that the raw API key is encrypted. Run:

```powershell
pytest tests/test_pimcore_config.py tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the configuration model**

```powershell
git add picorgftp_sql/pimcore_config.py tests/test_pimcore_config.py tests/test_config.py
git commit -m "feat: add guided pimcore setup state"
```

---

### Task 2: Structured EAN Filters And Read-Only Discovery

**Files:**
- Modify: `picorgftp_sql/services/pimcore_service.py`
- Modify: `tests/test_pimcore_service.py`

- [ ] **Step 1: Replace the condition test with a failing structured-query test**

Replace `test_ean_condition_rejects_unsafe_field_names` and add a transport test:

```python
from urllib.parse import parse_qs, urlsplit

from picorgftp_sql.services.pimcore_service import (
    build_ean_filter,
    discover_classes,
    discover_fields,
    discover_folders,
)


def test_ean_filter_is_structured_and_rejects_unsafe_names():
    assert build_ean_filter("5904804578169", ["EAN"]) == {
        "EAN": "5904804578169"
    }
    assert build_ean_filter(
        "5904804578169", ["EAN", "Towar_powiazany_z_SKU"]
    ) == {
        "$or": [
            {"EAN": "5904804578169"},
            {"Towar_powiazany_z_SKU": "5904804578169"},
        ]
    }
    with pytest.raises(ValueError, match="Niepoprawna nazwa pola"):
        build_ean_filter("5904804578169", ["EAN OR 1=1"])


def test_object_list_uses_q_and_object_class_not_removed_parameters():
    captured = {}

    def opener(request, timeout, context):
        captured["url"] = request.full_url
        return FakeResponse({"success": True, "data": []})

    client = PimcoreClient(
        {"base_url": "http://10.10.0.5", "api_key": "secret"},
        opener=opener,
    )
    client.object_list({"EAN": "5904804578169"}, object_class="product", limit=2)

    query = parse_qs(urlsplit(captured["url"]).query)
    assert json.loads(query["q"][0]) == {"EAN": "5904804578169"}
    assert query["objectClass"] == ["product"]
    assert query["limit"] == ["2"]
    assert "condition" not in query
    assert "className" not in query


def test_find_product_rejects_ambiguous_ean_results():
    client = Mock()
    client.object_list.return_value = {
        "data": [
            {"id": 91, "key": "5904804578169", "fullPath": "/Produkty/5904804578169"},
            {"id": 92, "key": "duplicate", "fullPath": "/Produkty/duplicate"},
        ]
    }

    with pytest.raises(ValueError, match="wiele produktow"):
        find_product_by_ean(
            PRODUCT_CONFIG,
            "5904804578169",
            client=client,
        )
```

- [ ] **Step 2: Add failing discovery normalization tests**

Append:

```python
class DiscoveryClient:
    def classes(self):
        return {"data": [{"id": "7", "name": "product"}, {"id": 3, "name": "category"}]}

    def class_definition(self, class_id):
        assert str(class_id) == "7"
        return {
            "data": {
                "layoutDefinitions": {
                    "children": [
                        {"fieldtype": "input", "name": "EAN", "title": "EAN"},
                        {"fieldtype": "numeric", "name": "totalWeight", "title": "Waga"},
                        {"fieldtype": "manyToManyObjectRelation", "name": "related"},
                    ]
                }
            }
        }

    def object_list(self, query_filter=None, object_class="", limit=100, offset=0):
        assert query_filter == {"type": "folder"}
        assert object_class == ""
        return {"data": [{"id": 6626, "type": "folder", "fullPath": "/Produkty"}]}


def test_discovery_normalizes_classes_fields_and_folders():
    client = DiscoveryClient()

    assert discover_classes(client) == [
        {"id": "3", "name": "category"},
        {"id": "7", "name": "product"},
    ]
    assert discover_fields(client, "7") == [
        {
            "name": "EAN",
            "label": "EAN",
            "type": "input",
            "language": None,
            "parser": "text",
            "supported": True,
            "unsupported_reason": "",
        },
        {
            "name": "related",
            "label": "related",
            "type": "manytomanyobjectrelation",
            "language": None,
            "parser": "",
            "supported": False,
            "unsupported_reason": "Typ manytomanyobjectrelation nie jest obslugiwany.",
        },
        {
            "name": "totalWeight",
            "label": "Waga",
            "type": "numeric",
            "language": None,
            "parser": "decimal_comma",
            "supported": True,
            "unsupported_reason": "",
        },
    ]
    assert discover_folders(client) == [
        {"id": 6626, "path": "/Produkty", "key": "Produkty"}
    ]
```

- [ ] **Step 3: Run the tests and verify old signatures fail**

Run:

```powershell
pytest tests/test_pimcore_service.py -v
```

Expected: FAIL because `build_ean_filter`, discovery helpers, and the new `object_list` signature are absent.

- [ ] **Step 4: Implement structured object-list transport**

Replace `PimcoreClient.object_list` and add update transport now so later tasks use one stable client contract:

```python
    def object_list(
        self,
        query_filter: dict[str, object] | None = None,
        *,
        object_class: str = "",
        limit: int = 2,
        offset: int = 0,
    ) -> dict[str, Any]:
        query: dict[str, object] = {
            "limit": max(1, min(1000, int(limit))),
            "offset": max(0, int(offset)),
        }
        if query_filter:
            query["q"] = json.dumps(query_filter, ensure_ascii=False, separators=(",", ":"))
        if str(object_class or "").strip():
            query["objectClass"] = str(object_class).strip()
        return self.request_json("GET", "/webservice/rest/object-list", query=query)

    def update_object(self, object_id: object, payload: dict[str, object]) -> dict[str, Any]:
        return self.request_json(
            "PUT",
            f"/webservice/rest/object/id/{quote(str(object_id))}",
            body=payload,
        )
```

Replace `build_ean_condition` with:

```python
def build_ean_filter(ean: object, field_names: list[str]) -> dict[str, object]:
    value = validate_ean(ean)
    fields: list[str] = []
    for field in field_names:
        name = str(field or "").strip()
        if not PIMCORE_FIELD_NAME.fullmatch(name):
            raise ValueError(f"Niepoprawna nazwa pola Pimcore: {name}")
        if name not in fields:
            fields.append(name)
    if not fields:
        raise ValueError("Brak pol do sprawdzania EAN.")
    clauses = [{name: value} for name in fields]
    return clauses[0] if len(clauses) == 1 else {"$or": clauses}
```

Update `find_product_by_ean` and settings diagnostics to call the structured transport. In `find_product_by_ean`, reject multiple records instead of enabling edit for an arbitrary object:

```python
    payload = api.object_list(
        build_ean_filter(ean, config["existence_fields"]),
        object_class=config["class_name"],
        limit=2,
    )
    records = _list_records(payload, ("data", "objects", "items"))
    if len(records) > 1:
        raise ValueError("Znaleziono wiele produktow Pimcore z tym samym EAN.")
    return normalize_object_identity(records[0]) if records else None
```

- [ ] **Step 5: Implement discovery normalizers**

Import `SUPPORTED_FIELD_PARSERS` and add:

```python
def discover_classes(api: PimcoreClient) -> list[dict[str, str]]:
    records = _list_records(api.classes(), ("data", "classes", "items"))
    result = [
        {"id": str(item.get("id") or item.get("classId") or ""), "name": str(item.get("name") or "").strip()}
        for item in records
        if str(item.get("id") or item.get("classId") or "").strip()
        and str(item.get("name") or "").strip()
    ]
    return sorted(result, key=lambda item: item["name"].casefold())


def extract_class_field_records(payload: object) -> list[dict[str, object]]:
    fields: dict[str, dict[str, object]] = {}

    def visit(node: object, language: str | None = None) -> None:
        if isinstance(node, dict):
            node_type = str(node.get("fieldtype") or node.get("datatype") or "").lower()
            name = str(node.get("name") or "").strip()
            current_language = str(node.get("language") or language or "").strip() or None
            if name and node_type:
                parser = SUPPORTED_FIELD_PARSERS.get(node_type, "")
                fields[name] = {
                    "name": name,
                    "label": str(node.get("title") or node.get("label") or name).strip(),
                    "type": node_type,
                    "language": current_language,
                    "parser": parser,
                    "supported": bool(parser),
                    "unsupported_reason": "" if parser else f"Typ {node_type} nie jest obslugiwany.",
                }
            for value in node.values():
                visit(value, current_language)
        elif isinstance(node, list):
            for value in node:
                visit(value, language)

    visit(payload)
    return sorted(fields.values(), key=lambda item: str(item["name"]).casefold())


def discover_fields(api: PimcoreClient, class_id: object) -> list[dict[str, object]]:
    return extract_class_field_records(api.class_definition(class_id))


def discover_folders(api: PimcoreClient, limit: int = 500) -> list[dict[str, object]]:
    bounded_limit = min(500, max(1, int(limit)))
    records: list[dict[str, object]] = []
    page_size = min(100, bounded_limit)
    for offset in range(0, bounded_limit, page_size):
        payload = api.object_list(
            {"type": "folder"},
            limit=min(page_size, bounded_limit - offset),
            offset=offset,
        )
        page = _list_records(payload, ("data", "objects", "items"))
        records.extend(page)
        if len(page) < page_size:
            break
    folders: list[dict[str, object]] = []
    for record in records:
        identity = normalize_object_identity(record)
        if not identity["id"]:
            continue
        path = identity["path"]
        key = identity["key"]
        if not path:
            detail = api.object_by_id(identity["id"])
            source = detail.get("data") if isinstance(detail.get("data"), dict) else detail
            path = extract_object_path(source)
            key = str(source.get("key") or key) if isinstance(source, dict) else key
        folders.append({"id": identity["id"], "path": path, "key": key})
    return sorted(folders, key=lambda item: str(item["path"] or item["key"]).casefold())
```

- [ ] **Step 6: Update test doubles and run the service suite**

Change every mock `object_list(self, class_name, condition, limit=2)` to `object_list(self, query_filter=None, object_class="", limit=2, offset=0)` and assert structured filters. Run:

```powershell
pytest tests/test_pimcore_service.py -v
```

Expected: PASS and captured URLs contain no `condition` or `className` query keys.

- [ ] **Step 7: Commit the REST compatibility and discovery layer**

```powershell
git add picorgftp_sql/services/pimcore_service.py tests/test_pimcore_service.py
git commit -m "fix: use supported pimcore object filters"
```

---

### Task 3: Dependency-Aware Settings Diagnostics

**Files:**
- Modify: `picorgftp_sql/services/pimcore_service.py`
- Modify: `picorgftp_sql/web_data.py`
- Modify: `tests/test_pimcore_service.py`
- Modify: `tests/test_pimcore_web.py`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `tests/test_source_integrity.py`

- [ ] **Step 1: Write failing tests for skipped dependent checks**

Append to `tests/test_pimcore_service.py`:

```python
def test_settings_test_skips_remote_dependents_after_missing_class():
    class MissingClassClient(DiagnosticClient):
        def classes(self):
            return {"data": [{"id": 2, "name": "other"}]}

        def object_list(self, *args, **kwargs):
            raise AssertionError("object-list must be skipped without a valid class")

    report = run_settings_test(VALID_DIAGNOSTIC_CONFIG, client=MissingClassClient())
    checks = {item["key"]: item for item in report["checks"]}

    assert checks["class_exists"]["status"] == "error"
    assert checks["mapping_fields"]["status"] == "skipped"
    assert checks["object_list"]["status"] == "skipped"


def test_settings_test_marks_empty_mapping_as_error_not_success():
    report = run_settings_test(
        {
            "base_url": "http://10.10.0.5",
            "api_key": "secret",
            "class_name": "product",
            "parent_id": "6626",
            "field_mappings": [],
        },
        client=Mock(),
    )
    checks = {item["key"]: item for item in report["checks"]}

    assert checks["test_form_schema"]["status"] == "error"
    assert checks["mapping_fields"]["status"] == "skipped"


def test_api_error_keeps_sanitized_audit_detail_out_of_public_dict():
    secret = "api-secret-value"

    def opener(request, timeout, context):
        raise HTTPError(
            request.full_url,
            500,
            "failure",
            {},
            BytesIO(f"full trace {secret} final-line".encode("utf-8")),
        )

    client = PimcoreClient(
        {"base_url": "http://10.10.0.5", "api_key": secret},
        opener=opener,
    )
    with pytest.raises(PimcoreApiError) as captured:
        client.server_info()

    error = captured.value
    assert "final-line" in error.response_detail
    assert secret not in error.response_detail
    assert "response_detail" not in error.as_dict()
    assert error.as_dict(include_detail=True)["response_detail"] == error.response_detail
```

Add to `tests/test_pimcore_web.py`:

```python
def test_settings_diagnostic_persists_full_detail_but_returns_public_report():
    report = {
        "ok": False,
        "checks": [
            {
                "key": "server_info",
                "status": "error",
                "response_excerpt": "short trace",
                "response_detail": "complete sanitized trace",
            }
        ],
    }
    with (
        patch.object(web_data, "run_settings_test", return_value=report),
        patch.object(web_data, "record_history") as record,
    ):
        result = web_data.test_pimcore_settings({}, "admin")

    assert "response_detail" not in result["checks"][0]
    persisted = record.call_args.kwargs["details"]["pimcore_settings_test"]
    assert persisted["checks"][0]["response_detail"] == "complete sanitized trace"
```

- [ ] **Step 2: Run the two tests and verify misleading success remains**

```powershell
pytest tests/test_pimcore_service.py::test_settings_test_skips_remote_dependents_after_missing_class tests/test_pimcore_service.py::test_settings_test_marks_empty_mapping_as_error_not_success -v
```

Expected: FAIL because the current diagnostic appends `ok` mapping/object-list results after failed prerequisites.

- [ ] **Step 3: Add explicit skipped checks and prerequisite gates**

Extend `PimcoreApiError` without changing public API error payloads:

```python
@dataclass
class PimcoreApiError(Exception):
    message: str
    endpoint: str
    status_code: int | None = None
    response_excerpt: str = ""
    response_detail: str = ""
    kind: str = "request"

    def __str__(self) -> str:
        return self.message

    def as_dict(self, *, include_detail: bool = False) -> dict[str, object]:
        result = {
            "message": self.message,
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "response_excerpt": self.response_excerpt,
            "kind": self.kind,
        }
        if include_detail:
            result["response_detail"] = self.response_detail
        return result


def _response_detail(value: object, secret: object = "") -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    secret_text = str(secret or "")
    return text.replace(secret_text, "[REDACTED]") if secret_text else text
```

In every `request_json` error branch that has a response/exception body, set both:

```python
response_excerpt=_response_excerpt(_response_detail(raw, self.settings[PIMCORE_API_KEY])),
response_detail=_response_detail(raw, self.settings[PIMCORE_API_KEY]),
```

Use the exception text instead of `raw` in the network branch. Extend `_check` with a `response_detail` keyword and include it in the returned dictionary. Pass `exc.response_detail` from `timed`. Public HTTP errors continue calling `exc.as_dict()`; operation-event errors call `exc.as_dict(include_detail=True)` so full sanitized details are available in live/persistent logs.

Add this helper beside `_check`:

```python
def _skipped(key: str, message: str, suggested_fix: str = "") -> dict[str, object]:
    return _check(
        key,
        "skipped",
        message,
        suggested_fix=suggested_fix,
    )
```

After appending all local checks, use the following concrete gate structure inside `run_settings_test`. Keep the existing `_check` message text and `timed` wrapper, but replace the unconditional remote sequence with these branches:

```python
    remote_prerequisites = base_ok and key_ok
    server_ready = False
    if not remote_prerequisites:
        checks.extend(
            [
                _skipped("server_info", "Pominieto test serwera z powodu bledow lokalnych."),
                _skipped("classes", "Pominieto pobieranie klas."),
                _skipped("class_exists", "Pominieto sprawdzanie klasy."),
                _skipped("class_definition", "Pominieto pobieranie definicji klasy."),
                _skipped("mapping_fields", "Pominieto zgodnosc pol klasy."),
                _skipped("object_list", "Pominieto test wyszukiwania EAN."),
            ]
        )
        if config["parent_id"]:
            checks.append(_skipped("parent", "Pominieto sprawdzanie folderu docelowego."))
    else:
        api = client or PimcoreClient(config)
        server_info = timed("server_info", "/webservice/rest/server-info", api.server_info)
        if server_info is None:
            checks.extend(
                [
                    _skipped("classes", "Pominieto pobieranie klas po bledzie serwera."),
                    _skipped("class_exists", "Pominieto sprawdzanie klasy."),
                    _skipped("class_definition", "Pominieto pobieranie definicji klasy."),
                    _skipped("mapping_fields", "Pominieto zgodnosc pol klasy."),
                    _skipped("object_list", "Pominieto test wyszukiwania EAN."),
                ]
            )
            if config["parent_id"]:
                checks.append(_skipped("parent", "Pominieto sprawdzanie folderu docelowego."))
        else:
            server_ready = True
            append_version_check(checks, server_info)
            classes_payload = timed("classes", "/webservice/rest/classes", api.classes)
            if classes_payload is None:
                checks.extend(
                    [
                        _skipped("class_exists", "Pominieto sprawdzanie klasy."),
                        _skipped("class_definition", "Pominieto pobieranie definicji klasy."),
                        _skipped("mapping_fields", "Pominieto zgodnosc pol klasy."),
                        _skipped("object_list", "Pominieto test wyszukiwania EAN."),
                    ]
                )
            else:
                class_record = find_class_record(classes_payload, config["class_name"])
                checks.append(class_exists_check(config["class_name"], class_record))
                fields: dict[str, str] = {}
                if class_record:
                    class_id = class_record.get("id") or class_record.get("classId")
                    class_payload = timed(
                        "class_definition",
                        f"/webservice/rest/class/id/{class_id}",
                        lambda: api.class_definition(class_id),
                    )
                    if class_payload is not None:
                        fields = extract_class_fields(class_payload)
                else:
                    checks.append(_skipped("class_definition", "Klasa nie istnieje."))

                mapping_ready = bool(config["field_mappings"]) and local_ok and bool(fields)
                if fields and config["field_mappings"]:
                    mapping_errors = mapping_field_errors(config["field_mappings"], fields)
                    checks.append(mapping_fields_check(mapping_errors))
                    mapping_ready = mapping_ready and not mapping_errors
                else:
                    checks.append(_skipped("mapping_fields", "Brak klasy albo mapowania."))

                if mapping_ready:
                    timed(
                        "object_list",
                        "/webservice/rest/object-list",
                        lambda: api.object_list(
                            build_ean_filter("0000000000000", config["existence_fields"]),
                            object_class=config["class_name"],
                            limit=2,
                        ),
                    )
                else:
                    checks.append(_skipped("object_list", "Klasa lub mapowanie EAN nie jest gotowe."))

        if server_ready and config["parent_id"]:
            timed(
                "parent",
                f"/webservice/rest/object/id/{config['parent_id']}",
                lambda: api.object_by_id(config["parent_id"]),
            )

    checks.append(
        _check(
            "create_permission",
            "info",
            "Uprawnienie tworzenia nie zostalo sprawdzone. Uruchom testowe dodanie obiektu.",
        )
    )
    return {
        "ok": not any(item["status"] == "error" for item in checks),
        "checks": checks,
        "total_ms": int((time.perf_counter() - started) * 1000),
    }
```

Extract the small pure helpers used above from the current inline code so they can be unit-tested without transport:

```python
def find_class_record(payload: object, class_name: str) -> dict[str, object] | None:
    return next(
        (
            item
            for item in _list_records(payload, ("data", "classes", "items"))
            if str(item.get("name") or "") == class_name
        ),
        None,
    )


def mapping_field_errors(
    mappings: list[dict[str, object]], fields: dict[str, str]
) -> list[str]:
    targets = [str(item["pimcore_field"]) for item in mappings]
    missing = [name for name in targets if name not in fields]
    return (
        (["Brak pol w klasie: " + ", ".join(missing)] if missing else [])
        + mapping_compatibility_issues(mappings, fields)
    )


def append_version_check(checks: list[dict[str, object]], server_info: object) -> None:
    version_text = json.dumps(server_info, ensure_ascii=True)
    compatible = "6." in version_text or "version" not in version_text.lower()
    checks.append(
        _check(
            "version",
            "ok" if compatible else "warning",
            "Wersja Pimcore jest zgodna." if compatible else "Serwer nie zglosil wersji Pimcore 6.x.",
        )
    )


def class_exists_check(
    class_name: str, class_record: dict[str, object] | None
) -> dict[str, object]:
    return _check(
        "class_exists",
        "ok" if class_record else "error",
        f"Znaleziono klase {class_name}." if class_record else f"Nie znaleziono klasy {class_name}.",
        suggested_fix="" if class_record else "Wybierz klase z listy pobranej z Pimcore.",
    )


def mapping_fields_check(errors: list[str]) -> dict[str, object]:
    return _check(
        "mapping_fields",
        "error" if errors else "ok",
        " | ".join(errors) if errors else "Wszystkie mapowane pola istnieja i maja zgodne typy.",
        suggested_fix="Zmien przypisanie pol zgodnie z definicja klasy Pimcore." if errors else "",
    )
```

Include `skipped` in the preflight severity conversion:

```python
        severity = {
            "ok": "success",
            "warning": "warning",
            "error": "error",
            "skipped": "info",
            "info": "info",
        }.get(str(check.get("status")), "info")
```

In `web_data.test_pimcore_settings`, persist the complete redacted report first and return a public copy with `response_detail` removed from every check:

```python
    report = run_settings_test(merged, client=PimcoreClient(merged))
    audit_report = redact_pimcore_log_value(report)
    record_history(
        username=username,
        action="pimcore_settings_test",
        summary=(
            "Test ustawien Pimcore zakonczony poprawnie."
            if report["ok"]
            else "Test ustawien Pimcore wykryl bledy."
        ),
        details={"pimcore_settings_test": audit_report},
    )
    return {
        **report,
        "checks": [
            {key: value for key, value in check.items() if key != "response_detail"}
            for check in report.get("checks", [])
        ],
    }
```

- [ ] **Step 4: Make checklist technical details expandable**

Add a source-integrity assertion:

```python
def test_pimcore_diagnostics_use_expandable_details(self) -> None:
    source = self._read("picorgftp_sql/web/static/app.js")
    self.assertIn('document.createElement("details")', source)
    self.assertIn('document.createElement("summary")', source)
    self.assertIn('status === "skipped"', source)
```

Change `renderPimcoreChecklist` to accept an optional target so the settings screen and wizard never share output accidentally. Each row contains the concise title and a `<details>` element only when endpoint/status/excerpt/fix exists:

```javascript
function renderPimcoreChecklist(report = {}, target = null) {
    const output = target || document.querySelector("#pimcoreSettingsChecklist");
    if (!output) return;
    output.textContent = "";
    output.className = "pimcore-checklist";
    const checks = Array.isArray(report.checks) ? report.checks : [];
    if (!checks.length) {
      output.className = "pimcore-checklist empty-state";
      output.textContent = report.ok
        ? "Test zakonczony bez dodatkowych komunikatow."
        : "Brak wynikow testu.";
      return;
    }
    for (const check of checks) {
      const row = document.createElement("div");
      const title = document.createElement("strong");
      const status = check.status || "info";
      row.className = `pimcore-check-row ${status}`;
      title.textContent = `${status}: ${check.message || check.key || "kontrola"}`;
    const technical = [
      check.endpoint,
      check.status_code ? `HTTP ${check.status_code}` : "",
      `${Number(check.elapsed_ms || 0)} ms`,
      check.response_excerpt,
      check.suggested_fix,
    ].filter(Boolean);
    row.appendChild(title);
    if (technical.length) {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      const detail = document.createElement("pre");
      summary.textContent = "Szczegoly techniczne";
      detail.textContent = technical.join("\n");
      details.append(summary, detail);
      row.appendChild(details);
    }
      output.appendChild(row);
    }
}
```

Map `skipped` to a neutral CSS modifier in Task 6; do not render it as success.

- [ ] **Step 5: Run diagnostic and source tests**

```powershell
pytest tests/test_pimcore_service.py tests/test_pimcore_web.py tests/test_source_integrity.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit dependency-aware diagnostics**

```powershell
git add picorgftp_sql/services/pimcore_service.py picorgftp_sql/web_data.py picorgftp_sql/web/static/app.js tests/test_pimcore_service.py tests/test_pimcore_web.py tests/test_source_integrity.py
git commit -m "fix: report pimcore diagnostic dependencies"
```

---

### Task 4: Safe Discovery And Atomic Setup Routes

**Files:**
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/app.py`
- Modify: `tests/test_pimcore_web.py`

- [ ] **Step 1: Write failing adapter tests for unsaved discovery and setup completion**

Change the mock import before adding the adapters/tests:

```python
from unittest.mock import Mock, patch
```

Import the new adapters and append:

```python
def test_discovery_uses_unsaved_key_without_persisting_or_returning_it():
    captured = {}
    fake_client = Mock()
    with (
        patch.object(web_data.config, "CONFIG", {"pimcore": {"api_key": "saved"}}),
        patch.object(web_data, "PimcoreClient", return_value=fake_client) as client_type,
        patch.object(
            web_data,
            "discover_classes",
            return_value=[{"id": "7", "name": "product"}],
        ) as discover,
    ):
        client_type.side_effect = lambda settings: (
            captured.setdefault("settings", settings), fake_client
        )[1]
        result = web_data.discover_pimcore_classes(
            {"base_url": "http://10.10.0.5", "api_key": "temporary"}
        )

    assert captured["settings"]["api_key"] == "temporary"
    assert result == {"items": [{"id": "7", "name": "product"}]}
    assert "temporary" not in json.dumps(result)
    discover.assert_called_once_with(fake_client)


def test_complete_setup_saves_only_after_successful_report():
    payload = {
        "base_url": "http://10.10.0.5",
        "api_key": "secret",
        "class_id": "7",
        "class_name": "product",
        "parent_id": "6626",
        "parent_path": "/Produkty",
        "field_mappings": [
            {"source": "EAN", "pimcore_field": "EAN", "type": "input", "required": True, "parser": "text"}
        ],
    }
    with (
        patch.object(web_data, "test_pimcore_settings", return_value={"ok": True, "checks": []}),
        patch.object(web_data, "update_settings", return_value={"pimcore": {"setup_complete": True}}) as save,
    ):
        result = web_data.complete_pimcore_setup(payload, "admin")

    assert result["saved"] is True
    saved = save.call_args.args[0]["pimcore"]
    assert saved["setup_complete"] is True
    assert saved["enabled"] is True
    assert saved["object_key_template"] == "{EAN}"
```

Also test a report with `ok=False` and assert `update_settings` is not called.

- [ ] **Step 2: Run adapter tests and verify missing functions**

```powershell
pytest tests/test_pimcore_web.py -v
```

Expected: FAIL because discovery and setup-completion adapters are absent.

- [ ] **Step 3: Implement unsaved settings merge and discovery adapters**

In `web_data.py`, import `discover_classes`, `discover_fields`, and `discover_folders`, then add:

```python
def _merged_pimcore_settings(overrides: object = None) -> dict[str, object]:
    saved = normalize_pimcore_settings(config.CONFIG.get(PIMCORE_SETTINGS_KEY))
    merged = dict(saved)
    if isinstance(overrides, dict):
        merged.update(overrides)
        if not _text(overrides.get(PIMCORE_API_KEY)):
            merged[PIMCORE_API_KEY] = saved[PIMCORE_API_KEY]
    return normalize_pimcore_settings(merged)


def discover_pimcore_classes(overrides: object = None) -> dict[str, object]:
    settings_payload = _merged_pimcore_settings(overrides)
    return {"items": discover_classes(PimcoreClient(settings_payload))}


def discover_pimcore_fields(overrides: object, class_id: object) -> dict[str, object]:
    settings_payload = _merged_pimcore_settings(overrides)
    return {"items": discover_fields(PimcoreClient(settings_payload), class_id)}


def discover_pimcore_folders(overrides: object = None) -> dict[str, object]:
    settings_payload = _merged_pimcore_settings(overrides)
    return {"items": discover_folders(PimcoreClient(settings_payload))}


def complete_pimcore_setup(payload: object, username: str) -> dict[str, object]:
    submitted = dict(payload) if isinstance(payload, dict) else {}
    submitted["object_key_template"] = "{EAN}"
    submitted["published"] = True
    submitted["setup_complete"] = False
    report = test_pimcore_settings(submitted, username)
    if not report.get("ok"):
        return {"saved": False, "report": report}
    submitted["setup_complete"] = True
    submitted["enabled"] = True
    snapshot = update_settings({PIMCORE_SETTINGS_KEY: submitted})
    return {"saved": True, "report": report, "settings": snapshot}
```

Use `_merged_pimcore_settings` inside `test_pimcore_settings` to remove duplicate secret-preservation logic.

- [ ] **Step 4: Write failing admin route tests**

Append:

```python
def test_pimcore_discovery_and_setup_routes_are_admin_only():
    client = TestClient(web_app.app)
    admin = {"username": "admin", "role": "admin"}
    with (
        patch.object(web_app, "_require_admin", return_value=admin) as require_admin,
        patch.object(web_app, "discover_pimcore_classes", return_value={"items": [{"id": "7", "name": "product"}]}),
        patch.object(web_app, "discover_pimcore_fields", return_value={"items": []}),
        patch.object(web_app, "discover_pimcore_folders", return_value={"items": []}),
        patch.object(web_app, "complete_pimcore_setup", return_value={"saved": True, "report": {"ok": True}}),
    ):
        classes = client.post("/api/settings/pimcore/discover/classes", json={"settings": {}})
        fields = client.post("/api/settings/pimcore/discover/fields", json={"settings": {}, "class_id": "7"})
        folders = client.post("/api/settings/pimcore/discover/folders", json={"settings": {}})
        saved = client.post("/api/settings/pimcore/setup", json={"settings": {}})

    assert classes.status_code == fields.status_code == folders.status_code == saved.status_code == 200
    assert require_admin.call_count == 4
```

- [ ] **Step 5: Add thin FastAPI routes with structured failures**

Import the four adapters into `web/app.py` and add adjacent to the existing settings test route:

```python
    @app.post("/api/settings/pimcore/discover/classes")
    async def pimcore_discover_classes_api(request: Request) -> JSONResponse:
        _require_admin(request)
        payload = await request.json()
        settings_payload = payload.get("settings") if isinstance(payload, dict) else None
        try:
            result = await run_in_threadpool(discover_pimcore_classes, settings_payload)
        except PimcoreApiError as exc:
            raise HTTPException(status_code=502, detail=exc.as_dict()) from exc
        return JSONResponse(result)

    @app.post("/api/settings/pimcore/discover/fields")
    async def pimcore_discover_fields_api(request: Request) -> JSONResponse:
        _require_admin(request)
        payload = await request.json()
        if not isinstance(payload, dict) or not str(payload.get("class_id") or "").strip():
            raise HTTPException(status_code=400, detail="Wybierz klase Pimcore.")
        try:
            result = await run_in_threadpool(
                discover_pimcore_fields,
                payload.get("settings"),
                payload.get("class_id"),
            )
        except PimcoreApiError as exc:
            raise HTTPException(status_code=502, detail=exc.as_dict()) from exc
        return JSONResponse(result)

    @app.post("/api/settings/pimcore/discover/folders")
    async def pimcore_discover_folders_api(request: Request) -> JSONResponse:
        _require_admin(request)
        payload = await request.json()
        try:
            result = await run_in_threadpool(
                discover_pimcore_folders,
                payload.get("settings") if isinstance(payload, dict) else None,
            )
        except PimcoreApiError as exc:
            raise HTTPException(status_code=502, detail=exc.as_dict()) from exc
        return JSONResponse(result)

    @app.post("/api/settings/pimcore/setup")
    async def pimcore_setup_api(request: Request) -> JSONResponse:
        user = _require_admin(request)
        payload = await request.json()
        settings_payload = payload.get("settings") if isinstance(payload, dict) else None
        result = await run_in_threadpool(
            complete_pimcore_setup,
            settings_payload,
            str(user.get("username") or "admin"),
        )
        return JSONResponse(result, status_code=200 if result.get("saved") else 422)
```

- [ ] **Step 6: Run all Pimcore web tests**

```powershell
pytest tests/test_pimcore_web.py tests/test_pimcore_config.py -v
```

Expected: PASS with no API key in serialized responses.

- [ ] **Step 7: Commit discovery and atomic setup routes**

```powershell
git add picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_pimcore_web.py
git commit -m "feat: discover pimcore setup metadata"
```

---

### Task 5: Administrator First-Run Wizard

**Files:**
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_web_ui_integrity.py`
- Modify: `tests/test_source_integrity.py`

- [ ] **Step 1: Write failing wizard structure and wiring tests**

Add to `tests/test_web_ui_integrity.py`:

```python
def test_pimcore_setup_wizard_has_four_steps_and_admin_controls(self) -> None:
    html = self._html("picorgftp_sql/web/static/index.html")
    for element_id in (
        "pimcoreSetupModal",
        "pimcoreSetupForm",
        "pimcoreSetupStepTitle",
        "pimcoreSetupBody",
        "pimcoreSetupBackButton",
        "pimcoreSetupNextButton",
        "pimcoreSetupCancelButton",
        "pimcoreSetupStatus",
    ):
        self.assertIn(element_id, html.ids)
```

Add to `tests/test_source_integrity.py`:

```python
def test_pimcore_wizard_discovers_then_completes_setup(self) -> None:
    source = self._read("picorgftp_sql/web/static/app.js")
    self.assertIn("openPimcoreSetupWizard", source)
    self.assertIn("/api/settings/pimcore/discover/classes", source)
    self.assertIn("/api/settings/pimcore/discover/folders", source)
    self.assertIn("/api/settings/pimcore/discover/fields", source)
    self.assertIn("/api/settings/pimcore/setup", source)
    self.assertIn("setup_complete", source)
```

- [ ] **Step 2: Run UI tests and verify missing wizard IDs**

```powershell
pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py -v
```

Expected: FAIL because the wizard does not exist.

- [ ] **Step 3: Add the wizard modal shell**

Insert after `settingsView` in `index.html`:

```html
<div id="pimcoreSetupModal" class="modal-view nested-modal">
  <section class="manager-panel pimcore-setup-panel">
    <div class="section-heading">
      <div>
        <h1>Konfiguracja Pimcore</h1>
        <span id="pimcoreSetupStepTitle">Krok 1 z 4: Polaczenie</span>
      </div>
      <button id="pimcoreSetupCancelButton" type="button" class="ghost-button modal-close">Zamknij</button>
    </div>
    <ol id="pimcoreSetupProgress" class="pimcore-setup-progress" aria-label="Postep konfiguracji">
      <li class="active">Polaczenie</li>
      <li>Miejsce zapisu</li>
      <li>Pola produktu</li>
      <li>Test i zapis</li>
    </ol>
    <form id="pimcoreSetupForm">
      <div id="pimcoreSetupBody" class="pimcore-setup-body"></div>
    </form>
    <div class="pimcore-setup-actions">
      <button id="pimcoreSetupBackButton" type="button" class="secondary-button">Wstecz</button>
      <button id="pimcoreSetupNextButton" type="button">Dalej</button>
      <span id="pimcoreSetupStatus" role="status"></span>
    </div>
  </section>
</div>
```

Change both static asset query strings to `v=20260702-pimcore-setup`.

- [ ] **Step 4: Add isolated wizard state and step renderers**

Extend the global state with:

```javascript
  pimcoreSetup: {
    step: 1,
    settings: null,
    classes: [],
    folders: [],
    fields: [],
    mappings: [],
    manualLocation: false,
    eanTarget: "",
  },
```

Cache the new DOM IDs and add these shared render primitives and dispatcher:

```javascript
function pimcoreSetupInput(name, labelText, value = "", type = "text") {
  const label = document.createElement("label");
  const title = document.createElement("span");
  const input = document.createElement("input");
  title.textContent = labelText;
  input.name = name;
  input.type = type;
  input.value = value || "";
  input.autocomplete = type === "password" ? "new-password" : "off";
  label.append(title, input);
  return label;
}


function pimcoreSetupSelect(name, labelText, items, selected, valueKey, textBuilder) {
  const label = document.createElement("label");
  const title = document.createElement("span");
  const select = document.createElement("select");
  const placeholder = document.createElement("option");
  title.textContent = labelText;
  select.name = name;
  placeholder.value = "";
  placeholder.textContent = "Wybierz...";
  placeholder.disabled = true;
  placeholder.selected = !selected;
  select.appendChild(placeholder);
  for (const item of items) {
    const option = document.createElement("option");
    option.value = String(item[valueKey] ?? "");
    option.textContent = textBuilder(item);
    option.selected = option.value === String(selected || "");
    select.appendChild(option);
  }
  label.append(title, select);
  return label;
}


function openPimcoreSetupWizard() {
  const saved = state.settings?.pimcore || {};
  state.pimcoreSetup = {
    step: 1,
    settings: { ...saved, api_key: "" },
    classes: [],
    folders: [],
    fields: [],
    mappings: Array.isArray(saved.field_mappings) ? [...saved.field_mappings] : [],
    manualLocation: false,
    eanTarget: (saved.field_mappings || []).find((item) => item.source === "EAN")?.pimcore_field || "",
    report: null,
  };
  pimcoreSetupModal.classList.add("active");
  renderPimcoreSetupStep();
}


function renderPimcoreSetupStep() {
  const setup = state.pimcoreSetup;
  pimcoreSetupBody.textContent = "";
  [...pimcoreSetupProgress.children].forEach((item, index) => {
    item.classList.toggle("active", index + 1 === setup.step);
  });
  const renderers = {
    1: renderPimcoreConnectionStep,
    2: renderPimcoreLocationStep,
    3: renderPimcoreFieldsStep,
    4: renderPimcoreVerifyStep,
  };
  renderers[setup.step]();
  pimcoreSetupBackButton.disabled = setup.step === 1;
  pimcoreSetupNextButton.textContent = setup.step === 4 ? "Zapisz i wlacz integracje" : "Dalej";
}
```

Implement each renderer with concrete fields and discovery actions:

```javascript
function renderPimcoreConnectionStep() {
  const setup = state.pimcoreSetup;
  const grid = document.createElement("div");
  const test = document.createElement("button");
  const manual = document.createElement("button");
  grid.className = "pimcore-setup-grid";
  grid.append(
    pimcoreSetupInput("base_url", "Adres Pimcore", setup.settings.base_url),
    pimcoreSetupInput("api_key", "Klucz API", setup.settings.api_key || "", "password")
  );
  test.type = "button";
  test.className = "secondary-button";
  test.textContent = "Sprawdz polaczenie i pobierz klasy";
  test.addEventListener("click", async () => {
    capturePimcoreSetupStep();
    test.disabled = true;
    try {
      setup.classes = await requestPimcoreDiscovery("classes");
      pimcoreSetupStatus.textContent = `Pobrano ${setup.classes.length} klas.`;
    } catch (error) {
      pimcoreSetupStatus.textContent = error.message;
    } finally {
      test.disabled = false;
    }
  });
  manual.type = "button";
  manual.className = "ghost-button";
  manual.textContent = "Kontynuuj z recznym wpisaniem klasy i folderu";
  manual.addEventListener("click", () => {
    capturePimcoreSetupStep();
    if (!setup.settings.base_url || (!setup.settings.api_key && !state.settings?.pimcore?.api_key_set)) {
      pimcoreSetupStatus.textContent = "Podaj adres Pimcore i klucz API.";
      return;
    }
    setup.manualLocation = true;
    setup.step = 2;
    renderPimcoreSetupStep();
  });
  pimcoreSetupBody.append(grid, test, manual);
}


function renderPimcoreLocationStep() {
  const setup = state.pimcoreSetup;
  const grid = document.createElement("div");
  const refresh = document.createElement("button");
  grid.className = "pimcore-setup-grid";
  grid.append(
    pimcoreSetupSelect(
      "class_id", "Klasa produktu", setup.classes, setup.settings.class_id, "id",
      (item) => `${item.name} (ID ${item.id})`
    ),
    pimcoreSetupSelect(
      "parent_id", "Folder docelowy", setup.folders, setup.settings.parent_id, "id",
      (item) => `${item.path || item.key} (ID ${item.id})`
    )
  );
  refresh.type = "button";
  refresh.className = "secondary-button";
  refresh.textContent = "Odswiez foldery";
  refresh.addEventListener("click", async () => {
    capturePimcoreSetupStep();
    try {
      setup.folders = await requestPimcoreDiscovery("folders");
      renderPimcoreSetupStep();
    } catch (error) {
      pimcoreSetupStatus.textContent = `${error.message}. Wpisz ID folderu recznie.`;
    }
  });
  pimcoreSetupBody.append(grid, refresh, pimcoreManualLocationFallback());
}


function renderPimcoreFieldsStep() {
  const setup = state.pimcoreSetup;
  const supported = setup.fields.filter((field) => field.supported);
  if (!setup.eanTarget) {
    setup.eanTarget = supported.find((field) => field.name.toUpperCase() === "EAN")?.name || "";
  }
  const eanTarget = pimcoreSetupSelect(
    "ean_target",
    "Pole EAN w Pimcore",
    supported,
    setup.eanTarget,
    "name",
    (item) => `${item.label || item.name} (${item.name})`
  );
  const table = document.createElement("div");
  table.className = "pimcore-setup-field-list";
  for (const field of setup.fields) {
    const row = pimcoreSetupFieldRow(field, setup.mappings, setup.eanTarget);
    table.appendChild(row);
  }
  eanTarget.querySelector("select").addEventListener("change", (event) => {
    setup.mappings = collectPimcoreSetupMappings(pimcoreSetupBody)
      .filter((item) => item.source !== "EAN");
    setup.eanTarget = event.target.value;
    renderPimcoreSetupStep();
  });
  pimcoreSetupBody.append(eanTarget, table);
}


function renderPimcoreVerifyStep() {
  const run = document.createElement("button");
  const output = pimcoreChecklistElement();
  run.type = "button";
  run.className = "secondary-button";
  run.textContent = "Sprawdz konfiguracje";
  run.addEventListener("click", async () => {
    const report = await requestJson("/api/settings/pimcore/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings: buildPimcoreSetupPayload() }),
      timeoutMs: 120000,
    });
    state.pimcoreSetup.report = report;
    renderPimcoreChecklist(report, output);
    pimcoreSetupNextButton.disabled = !report.ok;
  });
  pimcoreSetupNextButton.disabled = !state.pimcoreSetup.report?.ok;
  pimcoreSetupBody.append(run, output);
}
```

Define the remaining pure DOM helpers as follows:

```javascript
function pimcoreManualLocationFallback() {
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  const grid = document.createElement("div");
  const setup = state.pimcoreSetup;
  const classKnown = setup.classes.some(
    (item) => String(item.id) === String(setup.settings.class_id || "")
  );
  const folderKnown = setup.folders.some(
    (item) => String(item.id) === String(setup.settings.parent_id || "")
  );
  summary.textContent = "Wpisz wartosci recznie";
  grid.className = "pimcore-setup-grid";
  grid.append(
    pimcoreSetupInput("manual_class_name", "Nazwa klasy", classKnown ? "" : setup.settings.class_name),
    pimcoreSetupInput("manual_class_id", "ID klasy", classKnown ? "" : setup.settings.class_id),
    pimcoreSetupInput("manual_parent_id", "ID folderu", folderKnown ? "" : setup.settings.parent_id),
    pimcoreSetupInput("manual_parent_path", "Sciezka folderu", folderKnown ? "" : setup.settings.parent_path)
  );
  details.append(summary, grid);
  return details;
}


function pimcoreSetupFieldRow(field, mappings, eanTarget) {
  const existing = mappings.find((item) => item.pimcore_field === field.name) || {};
  const row = document.createElement("div");
  const use = document.createElement("input");
  const label = document.createElement("input");
  const required = document.createElement("input");
  const isEan = field.name === eanTarget;
  row.className = "pimcore-setup-field-row";
  row.dataset.fieldName = field.name;
  row.dataset.fieldType = field.type;
  row.dataset.fieldLanguage = field.language || "";
  row.dataset.fieldParser = field.parser || "";
  use.type = "checkbox";
  use.name = "mapping_use";
  use.checked = isEan || Boolean(existing.pimcore_field);
  use.disabled = !field.supported || isEan;
  label.name = "mapping_label";
  label.value = existing.label || field.label || field.name;
  label.disabled = !field.supported;
  required.type = "checkbox";
  required.name = "mapping_required";
  required.checked = isEan || Boolean(existing.required);
  required.disabled = isEan || !field.supported;
  row.append(use, document.createTextNode(field.name), label, required);
  if (!field.supported) row.title = field.unsupported_reason || "Pole nie jest obslugiwane.";
  return row;
}


function collectPimcoreSetupMappings(container) {
  const eanTarget = container.querySelector('[name="ean_target"]')?.value || state.pimcoreSetup.eanTarget;
  return [...container.querySelectorAll(".pimcore-setup-field-row")]
    .filter(
      (row) => row.dataset.fieldName === eanTarget
        || row.querySelector('[name="mapping_use"]')?.checked
    )
    .map((row) => {
      const source = row.dataset.fieldName === eanTarget ? "EAN" : row.dataset.fieldName;
      return {
        source,
        label: row.querySelector('[name="mapping_label"]').value.trim() || source,
        pimcore_field: row.dataset.fieldName,
        type: row.dataset.fieldType,
        language: row.dataset.fieldLanguage || null,
        required: source === "EAN" || row.querySelector('[name="mapping_required"]').checked,
        default: "",
        parser: row.dataset.fieldParser,
      };
    });
}
```

Capture each step before navigation and build the payload with stable field names:

```javascript
function capturePimcoreSetupStep() {
  const setup = state.pimcoreSetup;
  const data = new FormData(pimcoreSetupForm);
  for (const key of ["base_url", "api_key", "class_id", "parent_id"]) {
    if (data.has(key)) setup.settings[key] = String(data.get(key) || "").trim();
  }
  if (setup.step === 2) {
    const selectedClass = setup.classes.find((item) => String(item.id) === setup.settings.class_id);
    const selectedFolder = setup.folders.find((item) => String(item.id) === setup.settings.parent_id);
    if (selectedClass) setup.settings.class_name = selectedClass.name;
    if (selectedFolder) setup.settings.parent_path = selectedFolder.path;
    const manualClassId = String(data.get("manual_class_id") || "").trim();
    const manualClassName = String(data.get("manual_class_name") || "").trim();
    const manualParentId = String(data.get("manual_parent_id") || "").trim();
    const manualParentPath = String(data.get("manual_parent_path") || "").trim();
    if (manualClassId || manualClassName) {
      setup.settings.class_id = manualClassId;
      setup.settings.class_name = manualClassName;
    }
    if (manualParentId) {
      setup.settings.parent_id = manualParentId;
      setup.settings.parent_path = manualParentPath;
    }
  }
  if (setup.step === 3) setup.mappings = collectPimcoreSetupMappings(pimcoreSetupBody);
}


function buildPimcoreSetupPayload() {
  const setup = state.pimcoreSetup;
  return {
    ...setup.settings,
    enabled: true,
    setup_complete: false,
    published: true,
    object_key_template: "{EAN}",
    field_mappings: setup.mappings,
  };
}
```

Wire navigation with explicit validation and no mutation on cancel:

```javascript
async function advancePimcoreSetup() {
  const setup = state.pimcoreSetup;
  pimcoreSetupStatus.textContent = "";
  capturePimcoreSetupStep();
  try {
    if (setup.step === 1) {
      if (!setup.settings.base_url || (!setup.settings.api_key && !state.settings?.pimcore?.api_key_set)) {
        throw new Error("Podaj adres Pimcore i klucz API.");
      }
      if (!setup.classes.length) {
        setup.classes = await requestPimcoreDiscovery("classes");
      }
      if (!setup.classes.length) throw new Error("Nie znaleziono klas Pimcore.");
      try {
        setup.folders = await requestPimcoreDiscovery("folders");
      } catch (error) {
        setup.folders = [];
        pimcoreSetupStatus.textContent = `Nie pobrano folderow: ${error.message}. Wpisz folder recznie.`;
      }
      setup.step = 2;
    } else if (setup.step === 2) {
      if (!setup.settings.class_id || !setup.settings.class_name || !setup.settings.parent_id) {
        throw new Error("Wybierz klase produktu i folder docelowy albo wpisz je recznie.");
      }
      setup.fields = await requestPimcoreDiscovery("fields", {
        class_id: setup.settings.class_id,
      });
      if (!setup.fields.length) throw new Error("Klasa nie udostepnia pol do przypisania.");
      setup.step = 3;
    } else if (setup.step === 3) {
      const ean = setup.mappings.find((item) => item.source === "EAN" && item.required);
      if (!ean) throw new Error("Wybierz wymagane pole EAN.");
      setup.report = null;
      setup.step = 4;
    } else {
      await savePimcoreSetup();
      return;
    }
    renderPimcoreSetupStep();
  } catch (error) {
    pimcoreSetupStatus.textContent = error.message;
  }
}


pimcoreSetupNextButton.addEventListener("click", advancePimcoreSetup);
pimcoreSetupBackButton.addEventListener("click", () => {
  capturePimcoreSetupStep();
  state.pimcoreSetup.step = Math.max(1, state.pimcoreSetup.step - 1);
  renderPimcoreSetupStep();
});
pimcoreSetupCancelButton.addEventListener("click", () => {
  pimcoreSetupModal.classList.remove("active");
  state.pimcoreSetup = null;
});
```

Use one shared request helper for all discovery calls:

```javascript
async function requestPimcoreDiscovery(kind, extra = {}) {
  const setup = state.pimcoreSetup;
  const payload = await requestJson(`/api/settings/pimcore/discover/${kind}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings: setup.settings, ...extra }),
    timeoutMs: 120000,
  });
  return Array.isArray(payload.items) ? payload.items : [];
}
```

Complete setup with:

```javascript
async function savePimcoreSetup() {
  pimcoreSetupNextButton.disabled = true;
  pimcoreSetupStatus.textContent = "Zapisywanie konfiguracji...";
  try {
    const result = await requestJson("/api/settings/pimcore/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings: buildPimcoreSetupPayload() }),
      timeoutMs: 120000,
    });
    state.settings = result.settings || state.settings;
    pimcoreSetupModal.classList.remove("active");
    renderSettingsPimcore();
  } catch (error) {
    pimcoreSetupStatus.textContent = error.message;
  } finally {
    pimcoreSetupNextButton.disabled = false;
  }
}
```

Add `pimcoreSetupPrompted: false` to state. When `renderSettingsPimcore` sees `pimcore.setup_complete !== true`, render a short administrator note and button. Open the wizard automatically once per page load only for an administrator:

```javascript
if (pimcore.setup_complete !== true) {
  form.append(settingsNote("Integracja Pimcore wymaga pierwszej konfiguracji."));
  const start = document.createElement("button");
  start.type = "button";
  start.textContent = "Uruchom kreator";
  start.addEventListener("click", openPimcoreSetupWizard);
  form.appendChild(start);
  settingsOutput.appendChild(form);
  if (state.currentUser?.role === "admin" && !state.pimcoreSetupPrompted) {
    state.pimcoreSetupPrompted = true;
    queueMicrotask(openPimcoreSetupWizard);
  }
  return;
}
```

Closing the wizard changes only local wizard state and performs no request.

- [ ] **Step 5: Add responsive wizard styles**

Add stable dimensions and responsive rules:

```css
.pimcore-setup-panel { width: min(1080px, calc(100vw - 32px)); }
.pimcore-setup-progress { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 0 0 14px; padding: 0; list-style: none; }
.pimcore-setup-progress li { border-bottom: 3px solid var(--line); padding: 8px 4px; color: var(--muted); }
.pimcore-setup-progress li.active { border-color: var(--accent); color: var(--accent-strong); font-weight: 700; }
.pimcore-setup-body { min-height: 420px; overflow: auto; }
.pimcore-setup-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.pimcore-setup-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 14px; }

@media (max-width: 700px) {
  .pimcore-setup-progress, .pimcore-setup-grid { grid-template-columns: 1fr; }
  .pimcore-setup-body { min-height: 0; }
}
```

- [ ] **Step 6: Run UI and route tests**

```powershell
pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py tests/test_pimcore_web.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit the first-run wizard**

```powershell
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py tests/test_source_integrity.py
git commit -m "feat: add pimcore setup wizard"
```

---

### Task 6: Compact Settings And Advanced Fallbacks

**Files:**
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_source_integrity.py`
- Modify: `tests/test_web_ui_integrity.py`

- [ ] **Step 1: Write failing compact-settings tests**

Add:

```python
def test_pimcore_compact_settings_hide_technical_controls(self) -> None:
    source = self._read("picorgftp_sql/web/static/app.js")
    self.assertIn("pimcoreAdvancedSettings", source)
    self.assertIn('advanced.open = false', source)
    self.assertIn("Odśwież klasy i foldery", source)
    self.assertIn("Typ danych wykryty automatycznie", source)
    self.assertIn("pimcoreCsvImportButton", source)
```

Use the repository's existing ASCII display convention if source encoding tests require `Odswiez` instead of `Odśwież`; the rendered semantics must remain the same.

- [ ] **Step 2: Run the focused source test and verify failure**

```powershell
pytest tests/test_source_integrity.py::SourceIntegrityTests::test_pimcore_compact_settings_hide_technical_controls -v
```

Expected: FAIL because the current form exposes every technical field.

- [ ] **Step 3: Replace the normal mapping row with a simplified row**

Make the normal row save the same backend shape while showing only use, label, target, and required. Put technical values in hidden inputs and expose them inside a nested `<details>` only when the administrator opens Advanced. Use this concrete row builder:

```javascript
function pimcoreSimpleMappingRow(mapping = {}, fields = []) {
  const row = document.createElement("div");
  const use = document.createElement("input");
  const label = document.createElement("input");
  const target = document.createElement("select");
  const required = document.createElement("input");
  const remove = document.createElement("button");
  const isEan = String(mapping.source || "").toUpperCase() === "EAN";
  row.className = "pimcore-simple-mapping-row";
  use.type = "checkbox";
  use.name = "mapping_use";
  use.checked = true;
  label.name = "mapping_label";
  label.value = mapping.label || mapping.source || "";
  target.name = "mapping_target";
  const availableFields = [...fields];
  if (
    mapping.pimcore_field
    && !availableFields.some((field) => field.name === mapping.pimcore_field)
  ) {
    availableFields.push({
      name: mapping.pimcore_field,
      label: mapping.pimcore_field,
      type: mapping.type || "input",
      parser: mapping.parser || "text",
      language: mapping.language || "",
      supported: true,
    });
  }
  for (const field of availableFields) {
    const option = document.createElement("option");
    option.value = field.name;
    option.textContent = `${field.label || field.name} · ${field.type}`;
    option.disabled = !field.supported;
    option.selected = field.name === mapping.pimcore_field;
    option.dataset.type = field.type;
    option.dataset.parser = field.parser;
    option.dataset.language = field.language || "";
    target.appendChild(option);
  }
  required.type = "checkbox";
  required.name = "mapping_required";
  required.checked = isEan || Boolean(mapping.required);
  required.disabled = isEan;
  remove.type = "button";
  remove.className = "ghost-button";
  remove.textContent = "Usun";
  remove.disabled = isEan;
  remove.addEventListener("click", () => row.remove());
  row.dataset.source = isEan ? "EAN" : String(mapping.source || mapping.pimcore_field || "");
  row.append(use, label, target, required, remove);
  return row;
}


function collectSimplePimcoreMappings(form) {
  return [...form.querySelectorAll(".pimcore-simple-mapping-row")]
    .filter((row) => row.querySelector('[name="mapping_use"]').checked)
    .map((row) => {
      const select = row.querySelector('[name="mapping_target"]');
      const option = select.selectedOptions[0];
      const source = row.dataset.source;
      return {
        source,
        label: row.querySelector('[name="mapping_label"]').value.trim() || source,
        pimcore_field: select.value,
        type: option?.dataset.type || "input",
        language: option?.dataset.language || null,
        required: source === "EAN" || row.querySelector('[name="mapping_required"]').checked,
        default: "",
        parser: option?.dataset.parser || "text",
      };
    });
}
```

Populate `fields` from `state.pimcoreSetup.fields` or a fresh field-discovery response. Unsupported options are disabled and include the server-provided reason. Replace `collectPimcoreMappings(form)` in the compact form payload with `collectSimplePimcoreMappings(form)`.

Add a compact collector so display metadata and setup state survive every later save:

```javascript
function collectCompactPimcoreSettings(form) {
  const data = new FormData(form);
  const classSelect = form.querySelector('[name="class_id"]');
  const parentSelect = form.querySelector('[name="parent_id"]');
  const selectedClass = classSelect?.selectedOptions[0];
  const selectedParent = parentSelect?.selectedOptions[0];
  return {
    setup_complete: true,
    enabled: data.has("enabled"),
    base_url: data.get("base_url"),
    api_key: data.get("api_key"),
    class_id: data.get("manual_class_id") || classSelect?.value || "",
    class_name: data.get("manual_class_name") || selectedClass?.dataset.name || "",
    parent_id: data.get("manual_parent_id") || parentSelect?.value || "",
    parent_path: data.get("manual_parent_path") || selectedParent?.dataset.path || "",
    published: true,
    object_key_template: "{EAN}",
    existence_fields: collectSimplePimcoreMappings(form)
      .filter((item) => item.source === "EAN")
      .map((item) => item.pimcore_field),
    timeout_seconds: Number(data.get("timeout_seconds") || 30),
    verify_tls: data.has("verify_tls"),
    field_mappings: collectSimplePimcoreMappings(form),
  };
}
```

Class options must set `option.dataset.name`; folder options must set `option.dataset.path`. Use this collector for save, read-only test, and discovery snapshots. The enabled checkbox remains visible at the top of the connection group so an administrator can intentionally disable and later re-enable a completed setup.

- [ ] **Step 4: Rebuild the compact settings groups**

For complete setup, build the form with this top-level structure:

1. connection status/base URL/masked key and `Sprawdz i pobierz dane`;
2. class/folder dropdowns with refresh and manual fallback;
3. simplified selected fields;
4. test/history/save actions;
5. collapsed `details#pimcoreAdvancedSettings` containing timeout, TLS, CSV import, and technical mapping details.

```javascript
const advanced = document.createElement("details");
const advancedSummary = document.createElement("summary");
const advancedBody = document.createElement("div");
advanced.id = "pimcoreAdvancedSettings";
advanced.className = "pimcore-advanced-settings";
advanced.open = false;
advancedSummary.textContent = "Zaawansowane";
advancedBody.className = "settings-field-group";
advancedBody.append(
  inputField("timeout_seconds", "Timeout [s]", pimcore.timeout_seconds || 30, {
    type: "number", min: "1", max: "120",
  }),
  checkField("verify_tls", "Weryfikuj certyfikat TLS", pimcore.verify_tls !== false),
  pimcoreCsvImportButton(mappings),
  settingsNote("Klucz obiektu: {EAN}. Pole wyszukiwania EAN wynika z przypisania EAN.")
);
advanced.append(advancedSummary, advancedBody);
form.append(connectionGroup, locationGroup, mappingGroup, testGroup, advanced);
```

Use existing `settingsFieldGroup`, `inputField`, `checkField`, `actionRow`, and `settingsSaveButton` helpers for the named groups. Build `connectionGroup` with `checkField("enabled", "Integracja wlaczona", pimcore.enabled)` and use `collectCompactPimcoreSettings(form)` for all form actions. Add:

```javascript
function settingsNote(text) {
  const note = document.createElement("p");
  note.className = "settings-note wide-field";
  note.textContent = text;
  return note;
}
```

Do not render editable `object_key_template` or `existence_fields`; render read-only text that they are derived from the EAN mapping.

- [ ] **Step 5: Add compact and skipped-status CSS**

Add:

```css
.pimcore-check-row.skipped { border-left-color: var(--muted); opacity: .82; }
.pimcore-check-row details { margin-top: 6px; }
.pimcore-check-row pre { margin: 6px 0 0; max-height: 220px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
.pimcore-advanced-settings { grid-column: 1 / -1; border: 1px solid var(--line); border-radius: 6px; background: var(--surface-2); }
.pimcore-simple-mapping-row { display: grid; grid-template-columns: 42px minmax(140px, 1fr) minmax(180px, 1.2fr) 92px auto; gap: 8px; align-items: center; }
@media (max-width: 920px) { .pimcore-simple-mapping-row { grid-template-columns: 1fr; } }
```

- [ ] **Step 6: Run all settings UI tests**

```powershell
pytest tests/test_source_integrity.py tests/test_web_ui_integrity.py tests/test_pimcore_web.py -v
```

Expected: PASS with CSV import present only under the advanced details element.

- [ ] **Step 7: Commit the compact settings screen**

```powershell
git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_source_integrity.py tests/test_web_ui_integrity.py
git commit -m "feat: simplify pimcore settings"
```

---

### Task 7: Runtime Gating And Reliable Create Prompt

**Files:**
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `tests/test_pimcore_web.py`
- Modify: `tests/test_source_integrity.py`
- Modify: `tests/test_web_ui_integrity.py`

- [ ] **Step 1: Write failing backend gating tests**

Replace the disabled-result expectation and append:

```python
def test_runtime_status_is_disabled_when_setup_is_incomplete():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update({"enabled": True, "setup_complete": False})
    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "find_product_by_ean") as lookup,
    ):
        result = web_data.find_pimcore_product_by_ean("5904804578169")

    assert result == {
        "enabled": False,
        "setup_complete": False,
        "exists": False,
        "object": None,
        "form_schema": [],
    }
    lookup.assert_not_called()


def test_bootstrap_exposes_only_runtime_pimcore_flags():
    client = TestClient(web_app.app)
    with (
        patch.object(web_app, "_require_user", return_value="operator"),
        patch.object(web_app, "load_web_data", return_value={}),
        patch.object(web_app, "pimcore_runtime_capabilities", return_value={"enabled": True, "setup_complete": True}),
    ):
        response = client.get("/api/bootstrap")
    assert response.json()["pimcore"] == {"enabled": True, "setup_complete": True}
```

- [ ] **Step 2: Implement public runtime capabilities and strict gating**

Add:

```python
def pimcore_runtime_capabilities() -> dict[str, bool]:
    settings_payload = normalize_pimcore_settings(config.CONFIG.get(PIMCORE_SETTINGS_KEY))
    complete = bool(settings_payload["setup_complete"])
    return {
        "enabled": bool(settings_payload["enabled"] and complete),
        "setup_complete": complete,
    }


def _active_pimcore_runtime_settings() -> dict[str, object]:
    settings_payload = normalize_pimcore_settings(
        config.CONFIG.get(PIMCORE_SETTINGS_KEY)
    )
    if not settings_payload["setup_complete"]:
        raise ValueError("Integracja Pimcore nie zostala skonfigurowana.")
    if not settings_payload["enabled"]:
        raise ValueError("Integracja Pimcore jest wylaczona.")
    return settings_payload
```

Use `_active_pimcore_runtime_settings()` in `create_pimcore_product`. In lookup, return the disabled shape without raising when either flag is false. Add the capability value after the existing `**load_web_data()` expansion so it cannot be overwritten:

```python
        return {
            # existing bootstrap keys stay unchanged
            **load_web_data(),
            "pimcore": pimcore_runtime_capabilities(),
        }
```

Expose no class, parent, mapping, or secret data there.

- [ ] **Step 3: Add the edit button shell beside product matching**

In `index.html`, add inside `.lookup-actions`:

```html
<button id="pimcoreEditButton" type="button" class="secondary-button" hidden disabled>Edytuj dane Pimcore</button>
```

Add a UI integrity assertion for the ID and update the asset query strings if Task 5 did not already do so.

- [ ] **Step 4: Make status lookup control visibility without false missing prompts**

Add state:

```javascript
  pimcoreRuntimeEnabled: false,
  pimcoreExistingObject: null,
```

Add these UI gates and call `applyPimcoreRuntimeCapabilities(payload.pimcore)` in `loadBootstrap` after assigning `state.currentUser`:

```javascript
function applyPimcoreRuntimeCapabilities(capabilities = {}) {
  state.pimcoreRuntimeEnabled = capabilities.enabled === true;
  state.pimcoreExistingObject = null;
  state.pimcoreLastCheckedEan = "";
  pimcoreEditButton.hidden = !state.pimcoreRuntimeEnabled;
  pimcoreEditButton.disabled = true;
}


function handlePimcoreEanInput() {
  state.pimcoreExistingObject = null;
  pimcoreEditButton.disabled = true;
  if (!state.pimcoreRuntimeEnabled) return;
  schedulePimcoreStatusLookup();
}
```

Replace the existing EAN listener with:

```javascript
productForm.elements.ean?.addEventListener("input", handlePimcoreEanInput);
```

Start `schedulePimcoreStatusLookup` with `if (!state.pimcoreRuntimeEnabled) return;` so disabled/incomplete integrations issue no request.

Update successful lookup handling:

```javascript
  if (!payload.enabled || payload.available === false) {
    state.pimcoreExistingObject = null;
    pimcoreEditButton.disabled = true;
    return;
  }
  if (payload.exists) {
    state.pimcoreExistingObject = payload.object;
    pimcoreEditButton.disabled = false;
    return;
  }
  state.pimcoreExistingObject = null;
  pimcoreEditButton.disabled = true;
  state.pimcoreCreateSchema = Array.isArray(payload.form_schema) ? payload.form_schema : [];
  state.pimcoreMissingEan = ean;
  pimcoreMissingModal.classList.add("active");
```

Catch lookup errors without opening the missing modal. Preserve `available=False` behavior from the backend.

- [ ] **Step 5: Rename runtime create action and keep publication immediate**

Change the create submit label to `Zapisz i opublikuj`. Keep `published=True` in normal creation and `published=False` in test creation. Add a source test asserting the normal create modal closes only after a successful response and cancel contains no request call.

- [ ] **Step 6: Run runtime gating tests**

```powershell
pytest tests/test_pimcore_web.py tests/test_source_integrity.py tests/test_web_ui_integrity.py tests/test_pimcore_service.py -v
```

Expected: PASS; disabled/incomplete settings cause zero Pimcore network calls.

- [ ] **Step 7: Commit runtime gating**

```powershell
git add picorgftp_sql/web_data.py picorgftp_sql/web/app.py picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js tests/test_pimcore_web.py tests/test_source_integrity.py tests/test_web_ui_integrity.py
git commit -m "fix: gate pimcore runtime controls"
```

---

### Task 8: Complete-Object Editing And Conflict Detection

**Files:**
- Modify: `picorgftp_sql/services/pimcore_service.py`
- Modify: `tests/test_pimcore_service.py`

- [ ] **Step 1: Write failing tests for edit loading, merge preservation, and conflicts**

Add imports and tests:

```python
from picorgftp_sql.services.pimcore_service import (
    PimcoreConflictError,
    fetch_product_for_edit,
    merge_product_update_payload,
    update_product,
)


EDIT_OBJECT = {
    "id": 91,
    "parentId": 6626,
    "key": "5904804578169",
    "className": "product",
    "published": True,
    "modificationDate": 100,
    "elements": [
        {"type": "input", "name": "EAN", "value": "5904804578169", "language": None},
        {"type": "input", "name": "SKU", "value": "OLD", "language": None},
        {"type": "input", "name": "untouched", "value": "KEEP", "language": None},
    ],
}


def test_fetch_product_for_edit_returns_only_configured_values():
    client = Mock()
    client.object_by_id.return_value = {"data": EDIT_OBJECT}

    result = fetch_product_for_edit(PRODUCT_CONFIG, 91, client=client)

    assert result["object"]["id"] == 91
    assert result["marker"] == "100"
    assert result["values"] == {"SKU": "OLD", "EAN": "5904804578169"}


def test_merge_product_update_preserves_parent_and_unconfigured_elements():
    payload = merge_product_update_payload(
        PRODUCT_CONFIG,
        EDIT_OBJECT,
        {"SKU": "NEW", "EAN": "5904804578169"},
    )

    by_name = {item["name"]: item for item in payload["elements"]}
    assert payload["parentId"] == 6626
    assert payload["key"] == "5904804578169"
    assert payload["published"] is True
    assert by_name["SKU"]["value"] == "NEW"
    assert by_name["untouched"]["value"] == "KEEP"


def test_merge_product_update_replaces_nested_localized_value_only():
    config = json.loads(json.dumps(PRODUCT_CONFIG))
    config["field_mappings"].append(
        {
            "source": "NAME_EN",
            "label": "Nazwa EN",
            "pimcore_field": "name",
            "type": "input",
            "language": "en",
            "required": False,
            "default": "",
            "parser": "text",
        }
    )
    current = json.loads(json.dumps(EDIT_OBJECT))
    current["elements"].append(
        {
            "type": "localizedfields",
            "name": "localizedfields",
            "value": [
                {"type": "input", "name": "name", "language": "en", "value": "Old"},
                {"type": "input", "name": "name", "language": "pl", "value": "Bez zmian"},
            ],
        }
    )

    payload = merge_product_update_payload(
        config,
        current,
        {"SKU": "OLD", "EAN": "5904804578169", "NAME_EN": ""},
    )

    localized = next(item for item in payload["elements"] if item["name"] == "localizedfields")
    by_language = {item["language"]: item["value"] for item in localized["value"]}
    assert by_language == {"en": "", "pl": "Bez zmian"}


def test_update_product_rejects_changed_marker_before_put():
    client = Mock()
    changed = dict(EDIT_OBJECT, modificationDate=101)
    client.object_by_id.return_value = {"data": changed}

    with pytest.raises(PimcoreConflictError, match="zmieniony"):
        update_product(
            PRODUCT_CONFIG,
            91,
            "100",
            {"SKU": "NEW", "EAN": "5904804578169"},
            client=client,
            emit=lambda *args, **kwargs: None,
        )

    client.update_object.assert_not_called()


def test_update_product_uses_content_marker_when_timestamp_is_missing():
    original = {key: value for key, value in EDIT_OBJECT.items() if key != "modificationDate"}
    load_client = Mock()
    load_client.object_by_id.return_value = {"data": original}
    loaded = fetch_product_for_edit(PRODUCT_CONFIG, 91, client=load_client)

    changed = json.loads(json.dumps(original))
    changed["elements"][1]["value"] = "CHANGED"
    update_client = Mock()
    update_client.object_by_id.return_value = {"data": changed}
    with pytest.raises(PimcoreConflictError, match="zmieniony"):
        update_product(
            PRODUCT_CONFIG,
            91,
            loaded["marker"],
            {"SKU": "NEW", "EAN": "5904804578169"},
            client=update_client,
            emit=lambda *args, **kwargs: None,
        )

    update_client.update_object.assert_not_called()
```

- [ ] **Step 2: Run the tests and verify editing functions are absent**

```powershell
pytest tests/test_pimcore_service.py -v
```

Expected: FAIL during import of editing functions.

- [ ] **Step 3: Implement payload extraction and selected-value merge**

Import `hashlib`, then add:

```python
@dataclass
class PimcoreConflictError(Exception):
    message: str
    object_id: int
    expected_marker: str
    current_marker: str

    def __str__(self) -> str:
        return self.message


def _object_data(payload: object) -> dict[str, object]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return dict(payload["data"])
    if isinstance(payload, dict) and isinstance(payload.get("object"), dict):
        return dict(payload["object"])
    return dict(payload) if isinstance(payload, dict) else {}


def _object_marker(data: dict[str, object]) -> str:
    timestamp = str(data.get("modificationDate") or data.get("modification_date") or "")
    if timestamp:
        return timestamp
    canonical = json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _configured_values(config: dict[str, object], data: dict[str, object]) -> dict[str, object]:
    elements = data.get("elements") if isinstance(data.get("elements"), list) else []
    indexed: dict[tuple[str, str], object] = {}

    def visit(node: object) -> None:
        if isinstance(node, dict):
            name = str(node.get("name") or "")
            language = str(node.get("language") or "")
            if name and "value" in node and not isinstance(node.get("value"), (dict, list)):
                indexed[(name, language)] = node.get("value")
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(elements)
    return {
        mapping["source"]: indexed.get(
            (mapping["pimcore_field"], str(mapping.get("language") or "")),
            "",
        )
        for mapping in config["field_mappings"]
    }


def fetch_product_for_edit(
    settings: object,
    object_id: object,
    *,
    client: PimcoreClient | None = None,
) -> dict[str, object]:
    config = normalize_pimcore_settings(settings)
    api = client or PimcoreClient(config)
    data = _object_data(api.object_by_id(object_id))
    identity = normalize_object_identity(data)
    return {
        "object": identity,
        "marker": _object_marker(data),
        "values": _configured_values(config, data),
    }
```

Refactor element construction from `build_create_payload` into this shared helper and make `build_create_payload` use its returned elements/effective values:

```python
def _mapped_elements(
    config: dict[str, object],
    values: dict[str, object],
    *,
    use_defaults: bool,
    include_empty: bool = False,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    errors: list[str] = []
    elements: list[dict[str, object]] = []
    effective_values = dict(values or {})
    for mapping in config["field_mappings"]:
        source = mapping["source"]
        if source not in effective_values and not use_defaults:
            continue
        raw = effective_values.get(source)
        if (raw is None or str(raw).strip() == "") and use_defaults:
            raw = mapping["default"]
        if mapping["required"] and (raw is None or str(raw).strip() == ""):
            errors.append(f"Pole {mapping['label']} jest wymagane.")
            continue
        if (
            (raw is None or str(raw).strip() == "")
            and not include_empty
            and mapping["parser"] != "empty_to_null"
        ):
            continue
        try:
            parsed = parse_mapping_value(raw, mapping["parser"])
        except (TypeError, ValueError) as exc:
            errors.append(f"Pole {mapping['label']}: {exc}")
            continue
        effective_values[source] = parsed
        elements.append(
            {
                "type": mapping["type"],
                "name": mapping["pimcore_field"],
                "value": parsed,
                "language": mapping["language"],
            }
        )
    if errors:
        raise ValueError(" ".join(errors))
    return elements, effective_values
```

Then implement:

```python
def merge_product_update_payload(
    settings: object,
    current_data: dict[str, object],
    values: dict[str, object],
) -> dict[str, object]:
    config = normalize_pimcore_settings(settings)
    submitted_ean = validate_ean(values.get("EAN"))
    current_values = _configured_values(config, current_data)
    if current_values.get("EAN") and str(current_values["EAN"]) != submitted_ean:
        raise ValueError("EAN istniejacego produktu nie moze zostac zmieniony.")
    replacements, _effective_values = _mapped_elements(
        config,
        values,
        use_defaults=False,
        include_empty=True,
    )
    replacement_keys = {
        (item["name"], str(item.get("language") or "")): item for item in replacements
    }
    existing = current_data.get("elements") if isinstance(current_data.get("elements"), list) else []
    used: set[tuple[str, str]] = set()

    def merge_node(raw: object) -> object:
        if isinstance(raw, list):
            return [merge_node(item) for item in raw]
        if not isinstance(raw, dict):
            return raw
        item = dict(raw)
        key = (str(item.get("name") or ""), str(item.get("language") or ""))
        replacement = replacement_keys.get(key)
        if replacement:
            used.add(key)
            item.update(replacement)
            return item
        for field, value in list(item.items()):
            if isinstance(value, (dict, list)):
                item[field] = merge_node(value)
        return item

    merged_elements = [merge_node(item) for item in existing]
    merged_elements.extend(
        dict(item) for key, item in replacement_keys.items() if key not in used
    )
    payload = dict(current_data)
    payload["elements"] = merged_elements
    payload["published"] = True
    return payload
```

- [ ] **Step 4: Implement conflict-safe PUT and verification**

Add the complete update function:

```python
def update_product(
    settings: object,
    object_id: object,
    expected_marker: object,
    values: dict[str, object],
    *,
    client: PimcoreClient | None = None,
    emit: Callable[..., None],
) -> dict[str, object]:
    config = normalize_pimcore_settings(settings)
    api = client or PimcoreClient(config)
    numeric_id = int(object_id)
    stage_started = time.perf_counter()
    current_payload = api.object_by_id(numeric_id)
    current_data = _object_data(current_payload)
    current_marker = _object_marker(current_data)
    if current_marker != str(expected_marker or ""):
        emit(
            "conflict",
            "warning",
            "Obiekt zostal zmieniony w Pimcore.",
            object_id=numeric_id,
            expected_marker=str(expected_marker or ""),
            current_marker=current_marker,
            stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000),
        )
        raise PimcoreConflictError(
            "Obiekt zostal zmieniony w Pimcore. Otworz go ponownie.",
            numeric_id,
            str(expected_marker or ""),
            current_marker,
        )

    payload = merge_product_update_payload(config, current_data, values)
    emit(
        "payload",
        "success",
        "Polaczono zmiany z aktualnym obiektem.",
        object_id=numeric_id,
        stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000),
    )

    stage_started = time.perf_counter()
    try:
        response = api.update_object(numeric_id, payload)
    except PimcoreApiError as exc:
        emit(
            "update",
            "error",
            str(exc),
            method="PUT",
            endpoint=f"/webservice/rest/object/id/{numeric_id}",
            error=exc.as_dict(),
            stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000),
        )
        raise
    emit(
        "update",
        "success",
        "Zaktualizowano i opublikowano produkt Pimcore.",
        object_id=numeric_id,
        method="PUT",
        endpoint=f"/webservice/rest/object/id/{numeric_id}",
        status_code=_last_status_code(api),
        response_excerpt=_response_excerpt(json.dumps(response, ensure_ascii=True)),
        stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000),
    )

    stage_started = time.perf_counter()
    verified_payload = api.object_by_id(numeric_id)
    verified_data = _object_data(verified_payload)
    verified_values = _configured_values(config, verified_data)
    _elements, expected_values = _mapped_elements(config, values, use_defaults=False)
    mismatches = [
        source
        for source, expected in expected_values.items()
        if str(verified_values.get(source, ""))
        != str(expected if expected is not None else "")
    ]
    if mismatches:
        raise ValueError(
            "Pimcore nie potwierdzil zapisanych wartosci: " + ", ".join(mismatches)
        )
    identity = normalize_object_identity(verified_data)
    emit(
        "verify",
        "success",
        "Potwierdzono zapisane wartosci.",
        object_id=numeric_id,
        object_path=identity["path"],
        stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000),
    )
    return {
        "object": identity,
        "values": verified_values,
        "marker": _object_marker(verified_data),
    }
```

- [ ] **Step 5: Run service tests**

```powershell
pytest tests/test_pimcore_service.py -v
```

Expected: PASS, including preservation of `parentId`, `key`, and `untouched` element.

- [ ] **Step 6: Commit safe editing service**

```powershell
git add picorgftp_sql/services/pimcore_service.py tests/test_pimcore_service.py
git commit -m "feat: safely update pimcore products"
```

---

### Task 9: Runtime Edit Routes And Persistent Audit

**Files:**
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `tests/test_pimcore_web.py`
- Modify: `tests/test_pimcore_operations.py`

- [ ] **Step 1: Write failing web-adapter tests for load and update audit**

Add these imports, then append:

```python
import pytest

from picorgftp_sql.services.pimcore_service import PimcoreConflictError
```

```python
def test_edit_adapter_requires_enabled_complete_setup():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update({"enabled": False, "setup_complete": True})
    with patch.object(web_data.config, "CONFIG", cfg):
        with pytest.raises(ValueError, match="wylaczona"):
            web_data.get_pimcore_product_for_edit(91)


def test_update_adapter_persists_manual_update_audit():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update({"enabled": True, "setup_complete": True})
    expected = {"object": {"id": 91, "path": "/Produkty/5904"}, "values": {"EAN": "5904804578169"}}
    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "update_product", return_value=expected),
        patch.object(web_data, "_persist_pimcore_operation") as persist,
    ):
        result = web_data.update_pimcore_product(
            91,
            "100",
            {"EAN": "5904804578169"},
            "operator",
        )

    assert result == expected
    report = persist.call_args.args[0]
    assert report["operation_type"] == "manual_update"
    assert report["username"] == "operator"


def test_create_adapter_uses_manual_create_operation_kind():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update({"enabled": True, "setup_complete": True})
    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(
            web_data,
            "create_product",
            return_value={"created": True, "duplicate": False, "object": {"id": 91}},
        ),
        patch.object(web_data, "_persist_pimcore_operation") as persist,
    ):
        web_data.create_pimcore_product({"EAN": "5904804578169"}, "operator")

    assert persist.call_args.args[0]["operation_type"] == "manual_create"
```

- [ ] **Step 2: Implement gated edit adapters and operation-kind audit**

Add `_active_pimcore_runtime_settings()` that raises unless enabled and complete; use it in create, edit load, and edit update. Add:

```python
def get_pimcore_product_for_edit(object_id: object) -> dict[str, object]:
    settings_payload = _active_pimcore_runtime_settings()
    result = fetch_product_for_edit(settings_payload, object_id)
    result["form_schema"] = _pimcore_runtime_form_schema(settings_payload)
    return result


def update_pimcore_product(
    object_id: object,
    marker: object,
    values: object,
    username: str,
) -> dict[str, object]:
    settings_payload = _active_pimcore_runtime_settings()
    submitted = dict(values) if isinstance(values, dict) else {}
    operation_id = secrets.token_hex(12)
    started = time.time()
    events: list[dict[str, object]] = []
    result: dict[str, object] = {}
    status = "failed"

    def emit(stage: str, severity: str, message: str, **details: object) -> None:
        now = time.time()
        event = {
            "sequence": len(events) + 1,
            "timestamp": now,
            "elapsed_ms": int(max(0, now - started) * 1000),
            "stage": stage,
            "severity": severity,
            "message": message,
        }
        event.update(details)
        events.append(event)

    try:
        result = update_product(
            settings_payload,
            object_id,
            str(marker or ""),
            submitted,
            emit=emit,
        )
        status = "completed"
        return result
    except PimcoreConflictError:
        status = "conflict"
        raise
    except Exception as exc:
        emit("finish", "error", str(exc) or exc.__class__.__name__)
        raise
    finally:
        finished = time.time()
        _persist_pimcore_operation(
            {
                "operation_id": operation_id,
                "operation_type": "manual_update",
                "username": username,
                "values": submitted,
                "status": status,
                "started_at": started,
                "finished_at": finished,
                "total_ms": int(max(0, finished - started) * 1000),
                "events": events,
                "result": result,
            }
        )
```

Rename the existing creation operation kind from `manual` to `manual_create`. Update `_persist_pimcore_operation` with explicit action selection while retaining the current rejected-create action:

```python
    operation_type = _text(report.get("operation_type"))
    if operation_type == "test":
        action = "pimcore_test_create"
    elif operation_type == "manual_update":
        action = "pimcore_product_update"
    elif report.get("status") in {"duplicate", "failed"}:
        action = "pimcore_product_create_rejected"
    else:
        action = "pimcore_product_create"
```

In `index.html`, replace the history option `value="manual"` with `value="manual_create"`, add `value="manual_update"` labelled `Edycja reczna`, and add a `conflict` result option. Old `manual` records remain visible under the unfiltered history view.

- [ ] **Step 3: Write failing route tests for ordinary-user edit and HTTP 409**

Append:

```python
def test_runtime_edit_routes_allow_logged_in_user():
    client = TestClient(web_app.app)
    loaded = {"object": {"id": 91}, "marker": "100", "values": {"EAN": "5904804578169"}, "form_schema": []}
    updated = {"object": {"id": 91}, "values": {"EAN": "5904804578169"}}
    with (
        patch.object(web_app, "_require_user", return_value="operator"),
        patch.object(web_app, "get_pimcore_product_for_edit", return_value=loaded),
        patch.object(web_app, "update_pimcore_product", return_value=updated),
    ):
        get_response = client.get("/api/pimcore/products/91")
        put_response = client.put(
            "/api/pimcore/products/91",
            json={"marker": "100", "values": {"EAN": "5904804578169"}},
        )

    assert get_response.json() == loaded
    assert put_response.json() == updated


def test_runtime_edit_conflict_returns_409():
    client = TestClient(web_app.app)
    error = PimcoreConflictError("Obiekt zostal zmieniony.", 91, "100", "101")
    with (
        patch.object(web_app, "_require_user", return_value="operator"),
        patch.object(web_app, "update_pimcore_product", side_effect=error),
    ):
        response = client.put(
            "/api/pimcore/products/91",
            json={"marker": "100", "values": {"EAN": "5904804578169"}},
        )
    assert response.status_code == 409
    assert response.json()["detail"]["current_marker"] == "101"
```

- [ ] **Step 4: Add runtime GET and PUT routes**

Import edit adapters and `PimcoreConflictError`, then add:

```python
    @app.get("/api/pimcore/products/{object_id}")
    async def pimcore_product_edit_data_api(request: Request, object_id: int) -> JSONResponse:
        _require_user(request)
        try:
            result = await run_in_threadpool(get_pimcore_product_for_edit, object_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PimcoreApiError as exc:
            raise HTTPException(status_code=502, detail=exc.as_dict()) from exc
        return JSONResponse(result)

    @app.put("/api/pimcore/products/{object_id}")
    async def pimcore_product_update_api(request: Request, object_id: int) -> JSONResponse:
        username = _require_user(request)
        payload = await request.json()
        values = payload.get("values") if isinstance(payload, dict) else None
        marker = payload.get("marker") if isinstance(payload, dict) else None
        if not isinstance(values, dict) or not str(marker or ""):
            raise HTTPException(status_code=400, detail="Brak danych albo wersji produktu Pimcore.")
        try:
            result = await run_in_threadpool(
                update_pimcore_product,
                object_id,
                marker,
                values,
                username,
            )
        except PimcoreConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": str(exc),
                    "object_id": exc.object_id,
                    "expected_marker": exc.expected_marker,
                    "current_marker": exc.current_marker,
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PimcoreApiError as exc:
            raise HTTPException(status_code=502, detail=exc.as_dict()) from exc
        return JSONResponse(result)
```

- [ ] **Step 5: Run adapter, route, and redaction tests**

```powershell
pytest tests/test_pimcore_web.py tests/test_pimcore_operations.py -v
```

Expected: PASS with `manual_update` records redacted by the existing recursive redactor.

- [ ] **Step 6: Commit runtime edit API and audit**

```powershell
git add picorgftp_sql/web_data.py picorgftp_sql/web/app.py picorgftp_sql/web/static/index.html tests/test_pimcore_web.py tests/test_pimcore_operations.py
git commit -m "feat: expose audited pimcore product editing"
```

---

### Task 10: Runtime Edit Modal And Interaction

**Files:**
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_web_ui_integrity.py`
- Modify: `tests/test_source_integrity.py`

- [ ] **Step 1: Write failing modal and no-mutation-on-cancel tests**

Add:

```python
def test_runtime_pimcore_edit_modal_exists(self) -> None:
    html = self._html("picorgftp_sql/web/static/index.html")
    for element_id in (
        "pimcoreEditButton",
        "pimcoreEditModal",
        "pimcoreEditForm",
        "pimcoreEditSubmitButton",
        "pimcoreEditCancelButton",
        "pimcoreEditStatus",
    ):
        self.assertIn(element_id, html.ids)
```

Add source assertions:

```python
def test_pimcore_edit_loads_selected_fields_and_cancel_does_not_put(self) -> None:
    source = self._read("picorgftp_sql/web/static/app.js")
    self.assertIn("openPimcoreEditModal", source)
    self.assertIn('requestJson(`/api/pimcore/products/${encodeURIComponent(objectId)}`)', source)
    self.assertIn('method: "PUT"', source)
    self.assertIn("pimcoreEditEan.readOnly = true", source)
    cancel_block = source.split('pimcoreEditCancelButton?.addEventListener("click"', 1)[1].split("});", 1)[0]
    self.assertNotIn("requestJson", cancel_block)
```

- [ ] **Step 2: Run tests and verify the edit modal is absent**

```powershell
pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py -v
```

Expected: FAIL for missing edit modal IDs/functions.

- [ ] **Step 3: Add the edit modal structure**

Insert after the create modal:

```html
<div id="pimcoreEditModal" class="modal-view">
  <section class="manager-panel pimcore-edit-panel">
    <div class="section-heading">
      <div>
        <h1>Edytuj dane Pimcore</h1>
        <span id="pimcoreEditObjectInfo"></span>
      </div>
      <button id="pimcoreEditCancelButton" type="button" class="ghost-button modal-close">Anuluj</button>
    </div>
    <form id="pimcoreEditForm" class="pimcore-runtime-fields"></form>
    <div class="heading-actions">
      <button id="pimcoreEditSubmitButton" type="submit" form="pimcoreEditForm">Zapisz i opublikuj</button>
      <span id="pimcoreEditStatus" role="status"></span>
    </div>
  </section>
</div>
```

- [ ] **Step 4: Implement load, render, cancel, and PUT behavior**

Extend state:

```javascript
  pimcoreEditObjectId: 0,
  pimcoreEditMarker: "",
  pimcoreEditSchema: [],
```

Implement load/render so the modal opens only after a successful GET and only configured fields are rendered:

```javascript
async function openPimcoreEditModal() {
  const objectId = state.pimcoreExistingObject?.id;
  if (!objectId) return;
  pimcoreEditButton.disabled = true;
  try {
    const payload = await requestJson(
      `/api/pimcore/products/${encodeURIComponent(objectId)}`
    );
    pimcoreEditForm.textContent = "";
    state.pimcoreEditObjectId = Number(payload.object?.id || objectId);
    state.pimcoreEditMarker = String(payload.marker || "");
    state.pimcoreEditSchema = Array.isArray(payload.form_schema) ? payload.form_schema : [];
    for (const mapping of state.pimcoreEditSchema) {
      const label = document.createElement("label");
      const title = document.createElement("span");
      const input = document.createElement("input");
      title.textContent = `${mapping.label || mapping.source}${mapping.required ? " *" : ""}`;
      input.name = mapping.source;
      input.value = payload.values?.[mapping.source] ?? "";
      input.required = Boolean(mapping.required);
      input.autocomplete = "off";
      if (mapping.source === "EAN") input.id = "pimcoreEditEan";
      label.append(title, input);
      pimcoreEditForm.appendChild(label);
    }
    const pimcoreEditEan = pimcoreEditForm.querySelector("#pimcoreEditEan");
    if (pimcoreEditEan) pimcoreEditEan.readOnly = true;
    pimcoreEditObjectInfo.textContent = [
      `ID ${state.pimcoreEditObjectId}`,
      payload.object?.path || "",
    ].filter(Boolean).join(" · ");
    pimcoreEditStatus.textContent = "";
    pimcoreEditModal.classList.add("active");
  } catch (error) {
    formStatus.textContent = `Nie mozna pobrac danych Pimcore: ${error.message}`;
  } finally {
    pimcoreEditButton.disabled = !state.pimcoreExistingObject?.id;
  }
}


function closePimcoreEditModal() {
  pimcoreEditModal.classList.remove("active");
  pimcoreEditForm.textContent = "";
  pimcoreEditStatus.textContent = "";
  state.pimcoreEditObjectId = 0;
  state.pimcoreEditMarker = "";
  state.pimcoreEditSchema = [];
}
```

Implement submit:

```javascript
async function submitPimcoreRuntimeEdit(event) {
  event.preventDefault();
  if (!pimcoreEditForm.reportValidity()) return;
  pimcoreEditSubmitButton.disabled = true;
  pimcoreEditStatus.textContent = "Zapisywanie i publikowanie...";
  try {
    const values = Object.fromEntries(new FormData(pimcoreEditForm).entries());
    const result = await requestJson(
      `/api/pimcore/products/${encodeURIComponent(state.pimcoreEditObjectId)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ marker: state.pimcoreEditMarker, values }),
        timeoutMs: 120000,
      }
    );
    state.pimcoreEditMarker = result.marker || state.pimcoreEditMarker;
    state.pimcoreExistingObject = result.object || state.pimcoreExistingObject;
    pimcoreEditStatus.textContent = `Zapisano obiekt ${result.object?.id || state.pimcoreEditObjectId}.`;
  } catch (error) {
    pimcoreEditStatus.textContent = error.status === 409
      ? "Produkt zostal zmieniony w Pimcore. Zamknij okno i otworz go ponownie."
      : error.message;
  } finally {
    pimcoreEditSubmitButton.disabled = false;
  }
}
```

Do not close the edit modal after save; only cancel/close dismisses it. Wire handlers explicitly; the cancel handler only clears local state:

```javascript
pimcoreEditButton?.addEventListener("click", openPimcoreEditModal);
pimcoreEditForm?.addEventListener("submit", submitPimcoreRuntimeEdit);
pimcoreEditCancelButton?.addEventListener("click", () => {
  closePimcoreEditModal();
});
```

- [ ] **Step 5: Add responsive edit styles and stable controls**

```css
.pimcore-edit-panel { width: min(980px, calc(100vw - 32px)); }
.pimcore-edit-panel .pimcore-runtime-fields { max-height: min(70vh, 760px); overflow: auto; }
.lookup-actions #pimcoreEditButton { min-width: 170px; }
@media (max-width: 700px) { .lookup-actions #pimcoreEditButton { width: 100%; } }
```

- [ ] **Step 6: Run runtime UI and API tests**

```powershell
pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py tests/test_pimcore_web.py tests/test_pimcore_service.py -v
```

Expected: PASS; edit button visibility follows integration state and cancel contains no mutation call.

- [ ] **Step 7: Commit runtime editing UI**

```powershell
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py tests/test_source_integrity.py
git commit -m "feat: edit existing pimcore product data"
```

---

### Task 11: Documentation, Regression, Browser Review, And Real Pimcore Verification

**Files:**
- Modify: `README.md`
- Verify: all changed source and tests

- [ ] **Step 1: Update administrator and runtime documentation**

Replace the existing Pimcore setup instructions with these facts:

- first setup is an administrator-only four-step wizard;
- class, object folder, and fields can be discovered; manual class/parent entry is fallback only;
- CSV is optional under Advanced;
- object folder means the Objects-tree parent, not an image folder;
- normal create/update publishes immediately; test create stays unpublished;
- ordinary users see no Pimcore controls or prompts while integration is disabled/incomplete;
- edit updates only configured fields and rejects concurrent modifications;
- required Pimcore API permissions include server info/classes/objects read, create/update, and delete only for delete-cleanup tests.

- [ ] **Step 2: Run placeholder, secret, and removed-parameter checks**

```powershell
git diff --check
rg -n "T[B]D|T[O]DO|F[I]XME|X-API-Key.*api_key.*query|[?&](condition|className)=" picorgftp_sql tests README.md
```

Expected: no new placeholders, no API key in URLs, and no removed Pimcore object-list query parameters.

- [ ] **Step 3: Run the focused Pimcore suite**

```powershell
pytest tests/test_pimcore_config.py tests/test_pimcore_service.py tests/test_pimcore_operations.py tests/test_pimcore_web.py tests/test_web_ui_integrity.py tests/test_source_integrity.py -v
```

Expected: PASS with zero failures.

- [ ] **Step 4: Run the complete repository suite**

```powershell
pytest -q
```

Expected: zero failures.

- [ ] **Step 5: Start the web server and run Playwright desktop/mobile review**

Run:

```powershell
python -m uvicorn picorgftp_sql.web.app:app --host 127.0.0.1 --port 8000
```

Use installed Microsoft Edge through Playwright at `1440x1000` and `390x844`. Verify:

1. admin with incomplete setup sees the four-step wizard;
2. ordinary user never sees the wizard;
3. completed setup shows the compact screen with Advanced collapsed;
4. dropdowns and mapping rows have no overlaps or horizontal overflow;
5. disabled integration hides runtime edit and missing-product prompt;
6. enabled integration shows a disabled edit button before lookup and enables it only for an existing object;
7. create/edit cancel sends no POST/PUT;
8. edit save leaves the modal open and displays result/conflict status;
9. diagnostic details are expandable and long traces stay scrollable.

Capture screenshots outside the repository and inspect them with `view_image`.

- [ ] **Step 6: Run real read-only discovery against Pimcore**

Using the saved base URL/API key, discover classes, select the real product class, discover folders, select `/Produkty`, fetch class fields, map EAN, and run the read-only checklist. Confirm requests use `q` and `objectClass` and no `condition` error remains.

- [ ] **Step 7: Run controlled real write tests**

1. Test create with delete cleanup and confirm create/fetch/verify/delete timings.
2. Test create with keep cleanup, inspect the unpublished object, then remove it manually.
3. Create a missing EAN through the main panel and verify publication.
4. Edit one configured non-EAN field and confirm unconfigured fields/parent remain unchanged.
5. Modify the same object in Pimcore between load/save and confirm HTTP 409 handling.
6. Disable integration and confirm no runtime Pimcore call or control remains.

Do not use production EAN values for write tests; use isolated values agreed for testing.

- [ ] **Step 8: Commit documentation and final verified adjustments**

```powershell
git add README.md
git commit -m "docs: explain guided pimcore integration"
```

If browser or real-server verification required a code correction, commit each correction with its focused regression test before this documentation commit.

- [ ] **Step 9: Inspect final branch state**

```powershell
git status --short --branch
git log --oneline --decorate -15
```

Expected: clean `dev` worktree with ordered Tasks 1-11 commits and no running local verification server.
