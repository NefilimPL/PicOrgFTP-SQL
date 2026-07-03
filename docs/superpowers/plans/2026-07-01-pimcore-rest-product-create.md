# Pimcore REST Product Creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Pimcore 6.6 REST integration that validates configuration, creates missing products from the main EAN workflow, and provides an isolated settings write-test modal with live logs and persistent audit history.

**Architecture:** Keep Pimcore configuration normalization independent from transport, place the `urllib` REST client and payload builders in a focused service, and run settings write tests through a thread-safe operation registry with numbered events. Reuse the existing FastAPI authentication, encrypted config persistence, and JSON/SQLite web history; add only thin web adapters and DOM-based UI code.

**Tech Stack:** Python 3, FastAPI, standard-library `urllib`/`ssl`/`csv`, existing JSON/SQLite stores, vanilla JavaScript, HTML/CSS, pytest/unittest.

---

## File Structure

- Create `picorgftp_sql/pimcore_config.py`: constants, defaults, mapping normalization, parser compatibility, and mapped-value conversion.
- Create `picorgftp_sql/services/pimcore_service.py`: authenticated REST transport, response normalization, diagnostics, EAN lookup, payload building, create/fetch/delete workflows.
- Create `picorgftp_sql/pimcore_operations.py`: active settings-test operations, numbered live events, timing, retention, and executor ownership.
- Modify `picorgftp_sql/common.py`: register the default `pimcore` config section.
- Modify `picorgftp_sql/config.py`: load, normalize, encrypt, preserve, and save the Pimcore API key and settings.
- Modify `picorgftp_sql/web_data.py`: expose safe snapshots, update Pimcore settings, parse CSV headers, bridge REST functions, and persist/query Pimcore audit records.
- Modify `picorgftp_sql/web/app.py`: add admin settings/test/history routes and authenticated runtime lookup/create routes.
- Modify `picorgftp_sql/web/static/index.html`: add the Pimcore settings tab and the runtime/test/history modals.
- Modify `picorgftp_sql/web/static/app.js`: render mappings, run diagnostics, stream operation events by polling, and integrate missing-EAN creation.
- Modify `picorgftp_sql/web/static/app.css`: add dense mapping, two-pane test modal, live log, checklist, and responsive layouts.
- Create `tests/test_pimcore_config.py`: configuration, parsers, and secret persistence coverage.
- Create `tests/test_pimcore_service.py`: REST requests, payloads, diagnostics, lookup, and error coverage.
- Create `tests/test_pimcore_operations.py`: event sequencing, cleanup policies, partial failures, retention, and redaction.
- Create `tests/test_pimcore_web.py`: settings adapters, CSV import, routes, roles, history, and runtime create coverage.
- Modify `tests/test_web_ui_integrity.py`: required Pimcore tab/modal/control structure.
- Modify `tests/test_source_integrity.py`: live polling, non-closing modal, EAN debounce, and endpoint wiring.
- Modify `README.md`: Pimcore 6.6 setup, permissions, configuration, tests, and failure recovery.

Official version-pinned references:

- `https://github.com/pimcore/pimcore/blob/v6.6.11/doc/Development_Documentation/24_Web_Services/README.md`
- `https://github.com/pimcore/pimcore/blob/v6.6.11/doc/Development_Documentation/24_Web_Services/01_Query_Filters.md`

### Task 1: Pimcore Configuration And Secret Persistence

**Files:**
- Create: `picorgftp_sql/pimcore_config.py`
- Modify: `picorgftp_sql/common.py:1-55,204-330`
- Modify: `picorgftp_sql/config.py:1-55,218-318,326-520,541-650`
- Modify: `picorgftp_sql/web_data.py:120-145,1470-1490`
- Create: `tests/test_pimcore_config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing normalization and parser tests**

```python
# tests/test_pimcore_config.py
from picorgftp_sql.pimcore_config import (
    PIMCORE_API_KEY,
    PIMCORE_SETTINGS_KEY,
    field_mapping_issues,
    normalize_pimcore_settings,
    parse_mapping_value,
)


def test_normalize_pimcore_settings_cleans_mappings_and_bounds_timeout():
    result = normalize_pimcore_settings(
        {
            "enabled": 1,
            "base_url": " http://10.10.0.5/ ",
            PIMCORE_API_KEY: "secret-key",
            "class_name": " Product ",
            "parent_id": "123",
            "timeout_seconds": 999,
            "existence_fields": ["EAN", "EAN", "Bad field", "Towar_powiazany_z_SKU"],
            "field_mappings": [
                {
                    "source": "EAN",
                    "label": "Kod EAN",
                    "pimcore_field": "EAN",
                    "type": "input",
                    "required": True,
                    "parser": "text",
                },
                {"source": "", "pimcore_field": "ignored"},
            ],
        }
    )

    assert result["base_url"] == "http://10.10.0.5"
    assert result["timeout_seconds"] == 120
    assert result["existence_fields"] == ["EAN", "Towar_powiazany_z_SKU"]
    assert result["field_mappings"] == [
        {
            "source": "EAN",
            "label": "Kod EAN",
            "pimcore_field": "EAN",
            "type": "input",
            "language": None,
            "required": True,
            "default": "",
            "parser": "text",
        }
    ]


def test_mapping_parsers_accept_polish_csv_values():
    assert parse_mapping_value(" 62,5 ", "decimal_comma") == 62.5
    assert parse_mapping_value("12", "integer") == 12
    assert parse_mapping_value("tak", "boolean") is True
    assert parse_mapping_value("nie", "boolean") is False
    assert parse_mapping_value("  ", "empty_to_null") is None


def test_default_section_keeps_integration_disabled():
    result = normalize_pimcore_settings(None)
    assert result[PIMCORE_API_KEY] == ""
    assert result["enabled"] is False
    assert result["class_name"] == "Product"
    assert PIMCORE_SETTINGS_KEY == "pimcore"


def test_field_mapping_issues_report_exact_row_and_problem():
    issues = field_mapping_issues(
        [
            {"source": "", "pimcore_field": "EAN", "type": "input", "parser": "text"},
            {"source": "WEIGHT", "pimcore_field": "TOTAL_WEIGHT", "type": "input", "parser": "decimal_comma"},
            {"source": "WEIGHT", "pimcore_field": "OTHER_WEIGHT", "type": "numeric", "parser": "decimal_comma"},
        ]
    )
    assert issues == [
        "Mapowanie 1: brak kolumny zrodlowej.",
        "Mapowanie 2: parser decimal_comma nie pasuje do typu input.",
        "Mapowanie 3: zduplikowana kolumna zrodlowa WEIGHT.",
    ]
```

- [ ] **Step 2: Run the tests and verify the missing module failure**

Run: `pytest tests/test_pimcore_config.py -v`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'picorgftp_sql.pimcore_config'`.

- [ ] **Step 3: Add the focused configuration module**

```python
# picorgftp_sql/pimcore_config.py
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

PIMCORE_SETTINGS_KEY = "pimcore"
PIMCORE_API_KEY = "api_key"
PIMCORE_FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SUPPORTED_ELEMENT_TYPES = {"input", "textarea", "numeric", "checkbox", "select"}
SUPPORTED_PARSERS = {"text", "integer", "decimal_comma", "boolean", "empty_to_null"}

DEFAULT_PIMCORE_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "base_url": "http://10.10.0.5",
    PIMCORE_API_KEY: "",
    "class_name": "Product",
    "parent_id": "",
    "published": True,
    "object_key_template": "{SKU}",
    "existence_fields": ["EAN", "Towar_powiazany_z_SKU"],
    "timeout_seconds": 10,
    "verify_tls": True,
    "field_mappings": [],
}


def _text(value: object) -> str:
    return str(value or "").strip()


def default_pimcore_settings() -> dict[str, Any]:
    return deepcopy(DEFAULT_PIMCORE_SETTINGS)


def normalize_field_mapping(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    source = _text(raw.get("source"))
    target = _text(raw.get("pimcore_field"))
    if not source or not PIMCORE_FIELD_NAME.fullmatch(target):
        return None
    element_type = _text(raw.get("type")).lower() or "input"
    parser = _text(raw.get("parser")).lower() or "text"
    if element_type not in SUPPORTED_ELEMENT_TYPES:
        element_type = "input"
    if parser not in SUPPORTED_PARSERS:
        parser = "text"
    language = _text(raw.get("language")) or None
    return {
        "source": source,
        "label": _text(raw.get("label")) or source,
        "pimcore_field": target,
        "type": element_type,
        "language": language,
        "required": bool(raw.get("required")),
        "default": _text(raw.get("default")),
        "parser": parser,
    }


def field_mapping_issues(raw_mappings: object) -> list[str]:
    if not isinstance(raw_mappings, list):
        return ["Mapowanie pol musi byc lista."]
    parser_types = {
        "text": {"input", "textarea", "select"},
        "integer": {"numeric"},
        "decimal_comma": {"numeric"},
        "boolean": {"checkbox"},
        "empty_to_null": {"input", "textarea", "numeric", "select"},
    }
    issues: list[str] = []
    sources: set[str] = set()
    targets: set[str] = set()
    for index, raw in enumerate(raw_mappings, start=1):
        if not isinstance(raw, dict):
            issues.append(f"Mapowanie {index}: niepoprawny format wiersza.")
            continue
        source = _text(raw.get("source"))
        target = _text(raw.get("pimcore_field"))
        element_type = _text(raw.get("type")).lower() or "input"
        parser = _text(raw.get("parser")).lower() or "text"
        if not source:
            issues.append(f"Mapowanie {index}: brak kolumny zrodlowej.")
        elif source in sources:
            issues.append(f"Mapowanie {index}: zduplikowana kolumna zrodlowa {source}.")
        if not PIMCORE_FIELD_NAME.fullmatch(target):
            issues.append(f"Mapowanie {index}: niepoprawne pole Pimcore {target or '[puste]'}.")
        elif target in targets:
            issues.append(f"Mapowanie {index}: zduplikowane pole Pimcore {target}.")
        if element_type not in SUPPORTED_ELEMENT_TYPES:
            issues.append(f"Mapowanie {index}: nieobslugiwany typ {element_type}.")
        if parser not in SUPPORTED_PARSERS:
            issues.append(f"Mapowanie {index}: nieobslugiwany parser {parser}.")
        elif element_type in SUPPORTED_ELEMENT_TYPES and element_type not in parser_types[parser]:
            issues.append(f"Mapowanie {index}: parser {parser} nie pasuje do typu {element_type}.")
        if source:
            sources.add(source)
        if PIMCORE_FIELD_NAME.fullmatch(target):
            targets.add(target)
    return issues


def normalize_pimcore_settings(raw: object) -> dict[str, Any]:
    settings = default_pimcore_settings()
    source = raw if isinstance(raw, dict) else {}
    settings["enabled"] = bool(source.get("enabled", settings["enabled"]))
    settings["base_url"] = _text(source.get("base_url", settings["base_url"])).rstrip("/")
    settings[PIMCORE_API_KEY] = _text(source.get(PIMCORE_API_KEY))
    settings["class_name"] = _text(source.get("class_name", settings["class_name"])) or "Product"
    settings["parent_id"] = _text(source.get("parent_id"))
    settings["published"] = bool(source.get("published", settings["published"]))
    settings["object_key_template"] = _text(
        source.get("object_key_template", settings["object_key_template"])
    ) or "{EAN}"
    fields: list[str] = []
    raw_fields = source.get("existence_fields", settings["existence_fields"])
    if isinstance(raw_fields, str):
        raw_fields = raw_fields.split(",")
    if not isinstance(raw_fields, list):
        raw_fields = settings["existence_fields"]
    for item in raw_fields:
        name = _text(item)
        if PIMCORE_FIELD_NAME.fullmatch(name) and name not in fields:
            fields.append(name)
    settings["existence_fields"] = fields or ["EAN"]
    try:
        timeout = int(source.get("timeout_seconds", settings["timeout_seconds"]))
    except (TypeError, ValueError):
        timeout = 10
    settings["timeout_seconds"] = max(1, min(120, timeout))
    settings["verify_tls"] = bool(source.get("verify_tls", settings["verify_tls"]))
    mappings: list[dict[str, Any]] = []
    for item in source.get("field_mappings", []):
        normalized = normalize_field_mapping(item)
        if normalized:
            mappings.append(normalized)
    settings["field_mappings"] = mappings
    return settings


def parse_mapping_value(value: object, parser: str) -> object:
    text = _text(value)
    if parser == "integer":
        return int(text)
    if parser == "decimal_comma":
        return float(text.replace(" ", "").replace(",", "."))
    if parser == "boolean":
        lowered = text.casefold()
        if lowered in {"1", "true", "yes", "tak"}:
            return True
        if lowered in {"0", "false", "no", "nie"}:
            return False
        raise ValueError(f"Niepoprawna wartosc logiczna: {text}")
    if parser == "empty_to_null":
        return text or None
    return text
```

- [ ] **Step 4: Wire normalized defaults and encrypted persistence into existing config**

Add these imports and entries without changing existing FTP/SQL/translation behavior:

```python
# picorgftp_sql/common.py
from .pimcore_config import PIMCORE_SETTINGS_KEY, default_pimcore_settings

DEFAULT_CONFIG.setdefault(PIMCORE_SETTINGS_KEY, default_pimcore_settings())
```

```python
# picorgftp_sql/config.py
from .pimcore_config import (
    PIMCORE_API_KEY,
    PIMCORE_SETTINGS_KEY,
    field_mapping_issues,
    normalize_pimcore_settings,
)

# In _merge_raw_config and the legacy JSON load branch:
raw_pimcore = raw_config.get(PIMCORE_SETTINGS_KEY, {})
pimcore_settings = normalize_pimcore_settings(raw_pimcore)
pimcore_settings[PIMCORE_API_KEY] = decrypt(
    raw_pimcore.get(PIMCORE_API_KEY, encrypt(""))
    if isinstance(raw_pimcore, dict)
    else encrypt("")
)
config_copy[PIMCORE_SETTINGS_KEY] = pimcore_settings

# In initial config creation:
pimcore_initial = normalize_pimcore_settings(config_copy.get(PIMCORE_SETTINGS_KEY))
pimcore_initial[PIMCORE_API_KEY] = encrypt(pimcore_initial[PIMCORE_API_KEY])
initial[PIMCORE_SETTINGS_KEY] = pimcore_initial

# In save_config payload construction, after _pick_secret is defined:
pimcore_settings = normalize_pimcore_settings(config.get(PIMCORE_SETTINGS_KEY))
pimcore_payload = dict(pimcore_settings)
pimcore_payload[PIMCORE_API_KEY] = _pick_secret(
    PIMCORE_SETTINGS_KEY,
    PIMCORE_API_KEY,
    pimcore_settings[PIMCORE_API_KEY],
)
payload[PIMCORE_SETTINGS_KEY] = pimcore_payload

# Include this section in load-time secret preservation:
preserve_secrets[PIMCORE_SETTINGS_KEY] = {PIMCORE_API_KEY}
```

```python
# picorgftp_sql/web_data.py
from .pimcore_config import PIMCORE_API_KEY, PIMCORE_SETTINGS_KEY

_CONFIG_SECRET_FIELDS[PIMCORE_SETTINGS_KEY] = {PIMCORE_API_KEY}

# In _preserve_unsubmitted_config_secrets:
pimcore_payload = payload.get(PIMCORE_SETTINGS_KEY)
if isinstance(pimcore_payload, dict) and _text(pimcore_payload.get(PIMCORE_API_KEY)):
    preserve[PIMCORE_SETTINGS_KEY].discard(PIMCORE_API_KEY)
```

- [ ] **Step 5: Add a regression test proving the raw persisted API key is encrypted**

```python
# tests/test_config.py
def test_save_config_encrypts_pimcore_api_key(self) -> None:
    payload = json.loads(json.dumps(config.DEFAULT_CONFIG))
    payload["pimcore"] = {
        **payload["pimcore"],
        "enabled": True,
        "api_key": "pimcore-secret",
    }
    with (
        patch.object(config, "_active_sqlite_store", return_value=None),
        patch.object(config, "_write_json_atomic") as write_atomic,
    ):
        config.save_config(payload)

    raw = write_atomic.call_args.args[1]
    self.assertNotEqual(raw["pimcore"]["api_key"], "pimcore-secret")
    self.assertEqual(config.decrypt(raw["pimcore"]["api_key"]), "pimcore-secret")
```

- [ ] **Step 6: Run focused config tests**

Run: `pytest tests/test_pimcore_config.py tests/test_config.py -v`

Expected: PASS with zero failures.

- [ ] **Step 7: Commit the configuration layer**

```bash
git add picorgftp_sql/pimcore_config.py picorgftp_sql/common.py picorgftp_sql/config.py picorgftp_sql/web_data.py tests/test_pimcore_config.py tests/test_config.py
git commit -m "feat: add pimcore configuration model"
```

### Task 2: REST Client, Payload Builders, And EAN Filters

**Files:**
- Create: `picorgftp_sql/services/pimcore_service.py`
- Create: `tests/test_pimcore_service.py`

- [ ] **Step 1: Write failing transport and payload tests**

```python
# tests/test_pimcore_service.py
import json
from unittest.mock import Mock

import pytest

from picorgftp_sql.services.pimcore_service import (
    PimcoreApiError,
    PimcoreClient,
    build_create_payload,
    build_ean_condition,
    extract_object_id,
)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_client_uses_api_header_and_never_query_string():
    captured = {}

    def opener(request, timeout, context):
        captured["url"] = request.full_url
        captured["api_key"] = request.get_header("X-api-key")
        captured["timeout"] = timeout
        return FakeResponse({"success": True, "data": {"version": "6.6.11"}})

    client = PimcoreClient(
        {"base_url": "http://10.10.0.5", "api_key": "secret", "timeout_seconds": 7},
        opener=opener,
    )
    result = client.server_info()

    assert result["success"] is True
    assert captured == {
        "url": "http://10.10.0.5/webservice/rest/server-info",
        "api_key": "secret",
        "timeout": 7,
    }
    assert "secret" not in captured["url"]


def test_build_create_payload_parses_values_and_renders_key():
    config = {
        "class_name": "Product",
        "parent_id": "123",
        "published": True,
        "object_key_template": "{SKU}",
        "field_mappings": [
            {"source": "SKU", "pimcore_field": "SKU", "type": "input", "language": None, "required": True, "default": "", "parser": "text"},
            {"source": "TOTAL WEIGHT", "pimcore_field": "TOTAL_WEIGHT", "type": "numeric", "language": None, "required": False, "default": "", "parser": "decimal_comma"},
        ],
    }
    payload = build_create_payload(config, {"SKU": "ABC-1", "TOTAL WEIGHT": "62,5"})
    assert payload == {
        "className": "Product",
        "parentId": 123,
        "key": "ABC-1",
        "published": True,
        "elements": [
            {"type": "input", "name": "SKU", "value": "ABC-1", "language": None},
            {"type": "numeric", "name": "TOTAL_WEIGHT", "value": 62.5, "language": None},
        ],
    }


def test_ean_condition_rejects_unsafe_field_names():
    assert build_ean_condition("5904804578169", ["EAN", "Towar_powiazany_z_SKU"]) == (
        "(EAN = '5904804578169' OR Towar_powiazany_z_SKU = '5904804578169')"
    )
    with pytest.raises(ValueError, match="Niepoprawna nazwa pola"):
        build_ean_condition("5904804578169", ["EAN OR 1=1"])


def test_extract_object_id_accepts_pimcore_response_variants():
    assert extract_object_id({"id": 44}) == 44
    assert extract_object_id({"data": {"id": "45"}}) == 45
    assert extract_object_id({"object": {"id": 46}}) == 46
```

- [ ] **Step 2: Run the service tests and verify they fail**

Run: `pytest tests/test_pimcore_service.py -v`

Expected: FAIL during collection because `pimcore_service.py` does not exist.

- [ ] **Step 3: Implement the transport and public client methods**

```python
# picorgftp_sql/services/pimcore_service.py
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import ssl
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from ..common import SSL_CONTEXT
from ..pimcore_config import (
    PIMCORE_FIELD_NAME,
    field_mapping_issues,
    normalize_pimcore_settings,
    parse_mapping_value,
)


@dataclass
class PimcoreApiError(Exception):
    message: str
    endpoint: str
    status_code: int | None = None
    response_excerpt: str = ""
    kind: str = "request"

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict[str, object]:
        return {
            "message": self.message,
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "response_excerpt": self.response_excerpt,
            "kind": self.kind,
        }


def _response_excerpt(value: object, limit: int = 2000) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ")[:limit]


def _default_opener(request: Request, timeout: int, context: ssl.SSLContext | None):
    return urlopen(request, timeout=timeout, context=context)


class PimcoreClient:
    def __init__(
        self,
        settings: object,
        *,
        opener: Callable[[Request, int, ssl.SSLContext | None], object] = _default_opener,
    ) -> None:
        self.settings = normalize_pimcore_settings(settings)
        self.base_url = self.settings["base_url"].rstrip("/")
        self.opener = opener
        self.last_response: dict[str, object] = {}

    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, object] | None = None,
        body: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        endpoint = f"{self.base_url}{path}"
        if query:
            endpoint = f"{endpoint}?{urlencode(query)}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            endpoint,
            data=data,
            method=method.upper(),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-API-Key": self.settings["api_key"],
            },
        )
        context = None
        if endpoint.lower().startswith("https://"):
            context = SSL_CONTEXT if self.settings["verify_tls"] else ssl._create_unverified_context()
        try:
            with self.opener(request, self.settings["timeout_seconds"], context) as response:
                raw = response.read().decode("utf-8", errors="replace")
                status = int(getattr(response, "status", 200) or 200)
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            self.last_response = {"method": method.upper(), "endpoint": path, "status_code": int(exc.code)}
            raise PimcoreApiError(
                f"Pimcore zwrocil HTTP {exc.code}.",
                path,
                status_code=int(exc.code),
                response_excerpt=_response_excerpt(raw),
                kind="http",
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise PimcoreApiError(
                f"Nie mozna polaczyc sie z Pimcore: {exc}",
                path,
                response_excerpt=_response_excerpt(exc),
                kind="network",
            ) from exc
        if status < 200 or status >= 300:
            raise PimcoreApiError(
                f"Pimcore zwrocil HTTP {status}.",
                path,
                status_code=status,
                response_excerpt=_response_excerpt(raw),
                kind="http",
            )
        self.last_response = {"method": method.upper(), "endpoint": path, "status_code": status}
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise PimcoreApiError(
                "Pimcore zwrocil niepoprawny JSON.",
                path,
                status_code=status,
                response_excerpt=_response_excerpt(raw),
                kind="json",
            ) from exc
        if not isinstance(payload, dict):
            raise PimcoreApiError("Pimcore zwrocil niepoprawny format danych.", path, status_code=status)
        return payload

    def server_info(self) -> dict[str, Any]:
        return self.request_json("GET", "/webservice/rest/server-info")

    def classes(self) -> dict[str, Any]:
        return self.request_json("GET", "/webservice/rest/classes")

    def class_definition(self, class_id: object) -> dict[str, Any]:
        return self.request_json("GET", f"/webservice/rest/class/id/{quote(str(class_id))}")

    def object_by_id(self, object_id: object) -> dict[str, Any]:
        return self.request_json("GET", f"/webservice/rest/object/id/{quote(str(object_id))}")

    def object_list(self, class_name: str, condition: str, limit: int = 2) -> dict[str, Any]:
        return self.request_json(
            "GET",
            "/webservice/rest/object-list",
            query={"className": class_name, "condition": condition, "limit": limit},
        )

    def create_object(self, payload: dict[str, object]) -> dict[str, Any]:
        return self.request_json("POST", "/webservice/rest/object", body=payload)

    def delete_object(self, object_id: object) -> dict[str, Any]:
        return self.request_json("DELETE", f"/webservice/rest/object/id/{quote(str(object_id))}")
```

- [ ] **Step 4: Implement safe filters and payload conversion**

```python
# Append to picorgftp_sql/services/pimcore_service.py
def validate_ean(ean: object) -> str:
    value = str(ean or "").strip()
    if not re.fullmatch(r"\d{13}", value):
        raise ValueError("EAN musi zawierac dokladnie 13 cyfr.")
    return value


def build_ean_condition(ean: object, field_names: list[str]) -> str:
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
    return "(" + " OR ".join(f"{field} = '{value}'" for field in fields) + ")"


def _safe_object_key(value: object) -> str:
    key = re.sub(r"[^0-9A-Za-z_.-]+", "-", str(value or "").strip()).strip(".-")
    if not key:
        raise ValueError("Nie mozna zbudowac klucza obiektu Pimcore.")
    return key[:190]


def render_object_key(template: str, values: dict[str, object]) -> str:
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        source = match.group(1)
        value = str(values.get(source) or "").strip()
        if not value:
            missing.append(source)
        return value

    rendered = re.sub(r"\{([^{}]+)\}", replace, str(template or "{EAN}"))
    if missing:
        raise ValueError("Brak wartosci dla klucza: " + ", ".join(sorted(set(missing))))
    return _safe_object_key(rendered)


def build_create_payload(
    settings: object,
    values: dict[str, object],
    *,
    published: bool | None = None,
    use_defaults: bool = True,
) -> dict[str, object]:
    config = normalize_pimcore_settings(settings)
    errors: list[str] = []
    elements: list[dict[str, object]] = []
    effective_values = dict(values or {})
    for mapping in config["field_mappings"]:
        source = mapping["source"]
        raw = effective_values.get(source)
        if (raw is None or str(raw).strip() == "") and use_defaults:
            raw = mapping["default"]
        if mapping["required"] and (raw is None or str(raw).strip() == ""):
            errors.append(f"Pole {mapping['label']} jest wymagane.")
            continue
        if (raw is None or str(raw).strip() == "") and mapping["parser"] != "empty_to_null":
            continue
        try:
            parsed = parse_mapping_value(raw, mapping["parser"])
        except (TypeError, ValueError) as exc:
            errors.append(f"Pole {mapping['label']}: {exc}")
            continue
        effective_values[source] = raw
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
    try:
        parent_id = int(config["parent_id"])
    except (TypeError, ValueError) as exc:
        raise ValueError("parent_id musi byc liczba.") from exc
    return {
        "className": config["class_name"],
        "parentId": parent_id,
        "key": render_object_key(config["object_key_template"], effective_values),
        "published": config["published"] if published is None else bool(published),
        "elements": elements,
    }


def extract_object_id(payload: object) -> int:
    candidates = [payload]
    if isinstance(payload, dict):
        candidates.extend([payload.get("data"), payload.get("object")])
    for candidate in candidates:
        if isinstance(candidate, dict):
            try:
                return int(candidate.get("id"))
            except (TypeError, ValueError):
                pass
    raise ValueError("Odpowiedz Pimcore nie zawiera ID obiektu.")
```

- [ ] **Step 5: Add explicit HTTP failure tests**

```python
# tests/test_pimcore_service.py
from io import BytesIO
from urllib.error import HTTPError


def test_client_reports_status_endpoint_and_response_without_api_key():
    def opener(request, timeout, context):
        raise HTTPError(
            request.full_url,
            403,
            "Forbidden",
            {},
            BytesIO(b'{"message":"denied"}'),
        )

    client = PimcoreClient(
        {"base_url": "http://10.10.0.5", "api_key": "secret-key"},
        opener=opener,
    )
    with pytest.raises(PimcoreApiError) as raised:
        client.server_info()

    assert raised.value.status_code == 403
    assert raised.value.endpoint == "/webservice/rest/server-info"
    assert "denied" in raised.value.response_excerpt
    assert "secret-key" not in str(raised.value.as_dict())
```

- [ ] **Step 6: Run the REST service tests**

Run: `pytest tests/test_pimcore_service.py -v`

Expected: PASS with zero failures.

- [ ] **Step 7: Commit the REST client**

```bash
git add picorgftp_sql/services/pimcore_service.py tests/test_pimcore_service.py
git commit -m "feat: add pimcore rest client"
```

### Task 3: Full Read-Only Settings Diagnostic

**Files:**
- Modify: `picorgftp_sql/services/pimcore_service.py`
- Modify: `tests/test_pimcore_service.py`

- [ ] **Step 1: Write a failing diagnostic checklist test**

```python
# tests/test_pimcore_service.py
from picorgftp_sql.services.pimcore_service import run_settings_test


class DiagnosticClient:
    def server_info(self):
        return {"success": True, "data": {"version": "6.6.11"}}

    def classes(self):
        return {"data": [{"id": 1, "name": "Product"}]}

    def class_definition(self, class_id):
        assert class_id == 1
        return {
            "data": {
                "layoutDefinitions": {
                    "children": [
                        {"fieldtype": "input", "name": "SKU"},
                        {"fieldtype": "input", "name": "EAN"},
                    ]
                }
            }
        }

    def object_by_id(self, object_id):
        assert str(object_id) == "123"
        return {"success": True, "data": {"id": 123, "type": "folder"}}

    def object_list(self, class_name, condition, limit=2):
        assert class_name == "Product"
        assert "EAN" in condition
        return {"data": []}


def test_settings_test_returns_individual_checks_and_missing_field_error():
    config = {
        "enabled": True,
        "base_url": "http://10.10.0.5",
        "api_key": "secret",
        "class_name": "Product",
        "parent_id": "123",
        "object_key_template": "{SKU}",
        "existence_fields": ["EAN"],
        "field_mappings": [
            {"source": "SKU", "pimcore_field": "SKU", "type": "input", "required": True, "parser": "text"},
            {"source": "WEIGHT", "pimcore_field": "MISSING_WEIGHT", "type": "numeric", "required": False, "parser": "decimal_comma"},
        ],
    }
    report = run_settings_test(config, client=DiagnosticClient())
    checks = {item["key"]: item for item in report["checks"]}

    assert report["ok"] is False
    assert checks["server_info"]["status"] == "ok"
    assert checks["class_exists"]["status"] == "ok"
    assert checks["mapping_fields"]["status"] == "error"
    assert "MISSING_WEIGHT" in checks["mapping_fields"]["message"]
    assert checks["create_permission"]["status"] == "info"
    assert report["total_ms"] >= 0
```

- [ ] **Step 2: Run the diagnostic test and verify the missing function failure**

Run: `pytest tests/test_pimcore_service.py::test_settings_test_returns_individual_checks_and_missing_field_error -v`

Expected: FAIL during import with `cannot import name 'run_settings_test'`.

- [ ] **Step 3: Implement tolerant class extraction and structured checks**

```python
# Append to picorgftp_sql/services/pimcore_service.py
def _list_records(payload: object, keys: tuple[str, ...]) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _list_records(value, keys)
            if nested:
                return nested
    return []


def extract_class_fields(payload: object) -> dict[str, str]:
    fields: dict[str, str] = {}

    def visit(node: object) -> None:
        if isinstance(node, dict):
            name = str(node.get("name") or "").strip()
            field_type = str(node.get("fieldtype") or node.get("datatype") or "").strip()
            if name and field_type:
                fields[name] = field_type
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    return fields


def mapping_compatibility_issues(
    mappings: list[dict[str, object]],
    class_fields: dict[str, str],
) -> list[str]:
    parser_types = {
        "text": {"input", "textarea", "select"},
        "integer": {"numeric"},
        "decimal_comma": {"numeric"},
        "boolean": {"checkbox"},
        "empty_to_null": {"input", "textarea", "numeric", "select"},
    }
    issues: list[str] = []
    for mapping in mappings:
        target = str(mapping["pimcore_field"])
        actual_type = str(class_fields.get(target) or "")
        configured_type = str(mapping["type"])
        parser = str(mapping["parser"])
        if actual_type and actual_type != configured_type:
            issues.append(f"{target}: typ klasy {actual_type}, mapowanie {configured_type}")
        if configured_type not in parser_types.get(parser, set()):
            issues.append(f"{target}: parser {parser} nie pasuje do typu {configured_type}")
    return issues


def _check(
    key: str,
    status: str,
    message: str,
    *,
    endpoint: str = "local",
    status_code: int | None = None,
    response_excerpt: str = "",
    suggested_fix: str = "",
    elapsed_ms: int = 0,
) -> dict[str, object]:
    return {
        "key": key,
        "status": status,
        "message": message,
        "endpoint": endpoint,
        "status_code": status_code,
        "response_excerpt": response_excerpt,
        "suggested_fix": suggested_fix,
        "elapsed_ms": elapsed_ms,
    }


def run_settings_test(
    settings: object,
    *,
    client: PimcoreClient | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    raw_settings = settings if isinstance(settings, dict) else {}
    config = normalize_pimcore_settings(settings)
    checks: list[dict[str, object]] = []

    def timed(key: str, endpoint: str, callback: Callable[[], object]) -> object | None:
        check_started = time.perf_counter()
        try:
            result = callback()
            checks.append(
                _check(
                    key,
                    "ok",
                    "Test zakonczony poprawnie.",
                    endpoint=endpoint,
                    status_code=getattr(api, "last_response", {}).get("status_code"),
                    elapsed_ms=int((time.perf_counter() - check_started) * 1000),
                )
            )
            return result
        except PimcoreApiError as exc:
            checks.append(
                _check(
                    key,
                    "error",
                    str(exc),
                    endpoint=exc.endpoint,
                    status_code=exc.status_code,
                    response_excerpt=exc.response_excerpt,
                    suggested_fix="Sprawdz adres, klucz API, Webservice API i uprawnienia uzytkownika Pimcore.",
                    elapsed_ms=int((time.perf_counter() - check_started) * 1000),
                )
            )
            return None

    base_ok = bool(re.fullmatch(r"https?://[^\s/]+(?::\d+)?(?:/.*)?", config["base_url"]))
    checks.append(_check("base_url", "ok" if base_ok else "error", "Adres bazowy jest poprawny." if base_ok else "Adres Pimcore musi zaczynac sie od http:// albo https://.", suggested_fix="Wpisz pelny adres panelu Pimcore, np. http://10.10.0.5." if not base_ok else ""))
    key_ok = bool(config["api_key"])
    checks.append(_check("api_key", "ok" if key_ok else "error", "Klucz API jest ustawiony." if key_ok else "Brak klucza API.", suggested_fix="Wklej klucz API dedykowanego uzytkownika Pimcore i zapisz ustawienia." if not key_ok else ""))
    definition_issues = field_mapping_issues(raw_settings.get("field_mappings", []))
    checks.append(_check("mapping_definitions", "error" if definition_issues else "ok", " | ".join(definition_issues) if definition_issues else "Definicje mapowania sa poprawne.", suggested_fix="Popraw wskazane wiersze tabeli mapowania." if definition_issues else ""))
    if not base_ok or not key_ok:
        checks.append(_check("create_permission", "info", "Uprawnienie tworzenia nie zostalo sprawdzone."))
        return {"ok": False, "checks": checks, "total_ms": int((time.perf_counter() - started) * 1000)}

    api = client or PimcoreClient(config)
    server_info = timed("server_info", "/webservice/rest/server-info", api.server_info)
    if server_info is not None:
        version_text = json.dumps(server_info, ensure_ascii=True)
        compatible = "6." in version_text or "version" not in version_text.lower()
        checks.append(_check("version", "ok" if compatible else "warning", "Wersja Pimcore jest zgodna." if compatible else "Serwer nie zglosil wersji Pimcore 6.x."))
    classes_payload = timed("classes", "/webservice/rest/classes", api.classes)
    class_records = _list_records(classes_payload, ("data", "classes", "items"))
    class_record = next((item for item in class_records if str(item.get("name") or "") == config["class_name"]), None)
    checks.append(_check("class_exists", "ok" if class_record else "error", f"Znaleziono klase {config['class_name']}." if class_record else f"Nie znaleziono klasy {config['class_name']}.", suggested_fix="Wpisz dokladna systemowa nazwe klasy z Pimcore." if not class_record else ""))
    fields: dict[str, str] = {}
    if class_record:
        class_id = class_record.get("id") or class_record.get("classId")
        class_payload = timed("class_definition", f"/webservice/rest/class/id/{class_id}", lambda: api.class_definition(class_id))
        fields = extract_class_fields(class_payload)
    targets = [item["pimcore_field"] for item in config["field_mappings"]]
    missing = [name for name in targets if name not in fields]
    incompatible = mapping_compatibility_issues(config["field_mappings"], fields)
    mapping_errors = (["Brak pol w klasie: " + ", ".join(missing)] if missing else []) + incompatible
    checks.append(_check("mapping_fields", "error" if mapping_errors else "ok", " | ".join(mapping_errors) if mapping_errors else "Wszystkie mapowane pola istnieja i maja zgodne typy.", suggested_fix="Zmien nazwy pol lub typy/parsery w mapowaniu zgodnie z definicja klasy Pimcore." if mapping_errors else ""))
    required_sources = {item["source"] for item in config["field_mappings"] if item["required"]}
    key_sources = set(re.findall(r"\{([^{}]+)\}", config["object_key_template"]))
    local_ok = "EAN" in required_sources and bool(key_sources & {item["source"] for item in config["field_mappings"]})
    checks.append(_check("mapping_local", "ok" if local_ok else "error", "Mapowanie zawiera EAN i zrodlo klucza." if local_ok else "EAN musi byc wymagany, a szablon klucza musi wskazywac mapowane pole.", suggested_fix="Oznacz EAN jako wymagany i ustaw szablon np. {SKU} albo {EAN}." if not local_ok else ""))
    if config["parent_id"]:
        timed("parent", f"/webservice/rest/object/id/{config['parent_id']}", lambda: api.object_by_id(config["parent_id"]))
    else:
        checks.append(_check("parent", "error", "Brak parent_id folderu Produkty.", suggested_fix="Wpisz numeryczne ID folderu Produkty z Pimcore."))
    timed("object_list", "/webservice/rest/object-list", lambda: api.object_list(config["class_name"], build_ean_condition("0000000000000", config["existence_fields"])))
    checks.append(_check("test_form_schema", "ok" if config["field_mappings"] else "error", "Formularz testowy moze zostac zbudowany." if config["field_mappings"] else "Brak mapowania pol.", suggested_fix="Dodaj co najmniej mapowania EAN i pola uzywanego przez szablon klucza." if not config["field_mappings"] else ""))
    checks.append(_check("create_permission", "info", "Uprawnienie tworzenia nie zostalo sprawdzone. Uruchom testowe dodanie obiektu."))
    return {
        "ok": not any(item["status"] == "error" for item in checks),
        "checks": checks,
        "total_ms": int((time.perf_counter() - started) * 1000),
    }
```

- [ ] **Step 4: Add 401, timeout, missing class, bad parent, and invalid JSON cases**

```python
VALID_DIAGNOSTIC_CONFIG = {
    "enabled": True,
    "base_url": "http://10.10.0.5",
    "api_key": "secret",
    "class_name": "Product",
    "parent_id": "123",
    "object_key_template": "{EAN}",
    "existence_fields": ["EAN"],
    "field_mappings": [
        {"source": "EAN", "pimcore_field": "EAN", "type": "input", "required": True, "parser": "text"}
    ],
}


@pytest.mark.parametrize(
    ("status_code", "expected_key"),
    [(401, "server_info"), (403, "server_info")],
)
def test_settings_test_preserves_auth_http_status(status_code, expected_key):
    error = PimcoreApiError("Klucz API zostal odrzucony.", "/webservice/rest/server-info", status_code=status_code, kind="http")
    client = Mock()
    client.server_info.side_effect = error
    report = run_settings_test(
        {"enabled": True, "base_url": "http://10.10.0.5", "api_key": "secret"},
        client=client,
    )
    item = next(check for check in report["checks"] if check["key"] == expected_key)
    assert item["status"] == "error"
    assert item["status_code"] == status_code
    assert item["endpoint"] == "/webservice/rest/server-info"


def test_settings_test_reports_network_timeout():
    client = DiagnosticClient()
    client.server_info = Mock(
        side_effect=PimcoreApiError(
            "Przekroczono czas polaczenia.",
            "/webservice/rest/server-info",
            kind="network",
        )
    )
    report = run_settings_test(VALID_DIAGNOSTIC_CONFIG, client=client)
    item = next(check for check in report["checks"] if check["key"] == "server_info")
    assert item["status"] == "error"
    assert "czas" in item["message"]


def test_settings_test_reports_missing_class():
    class MissingClassClient(DiagnosticClient):
        def classes(self):
            return {"data": [{"id": 2, "name": "Other"}]}

    report = run_settings_test(VALID_DIAGNOSTIC_CONFIG, client=MissingClassClient())
    item = next(check for check in report["checks"] if check["key"] == "class_exists")
    assert item["status"] == "error"
    assert "Product" in item["message"]


def test_settings_test_reports_bad_parent_with_endpoint():
    class BadParentClient(DiagnosticClient):
        def object_by_id(self, object_id):
            raise PimcoreApiError(
                "Nie znaleziono parent_id.",
                f"/webservice/rest/object/id/{object_id}",
                status_code=404,
                kind="http",
            )

    report = run_settings_test(VALID_DIAGNOSTIC_CONFIG, client=BadParentClient())
    item = next(check for check in report["checks"] if check["key"] == "parent")
    assert item["status"] == "error"
    assert item["status_code"] == 404
    assert item["endpoint"].endswith("/123")


def test_client_reports_invalid_json_body():
    class RawResponse(FakeResponse):
        def __init__(self):
            self.status = 200
            self._body = b"not-json"

    client = PimcoreClient(
        {"base_url": "http://10.10.0.5", "api_key": "secret"},
        opener=lambda request, timeout, context: RawResponse(),
    )
    with pytest.raises(PimcoreApiError) as raised:
        client.server_info()
    assert raised.value.kind == "json"
    assert raised.value.status_code == 200
    assert raised.value.response_excerpt == "not-json"
```

- [ ] **Step 5: Run the diagnostic suite**

Run: `pytest tests/test_pimcore_service.py -v`

Expected: PASS with zero failures.

- [ ] **Step 6: Commit read-only diagnostics**

```bash
git add picorgftp_sql/services/pimcore_service.py tests/test_pimcore_service.py
git commit -m "feat: validate pimcore settings"
```

### Task 4: Settings Adapter, Safe Snapshot, CSV Headers, And Diagnostic Routes

**Files:**
- Modify: `picorgftp_sql/web_data.py:1470-1760`
- Modify: `picorgftp_sql/web/app.py:70-115,4128-4358`
- Create: `tests/test_pimcore_web.py`
- Modify: `tests/test_web_data_users.py`

- [ ] **Step 1: Write failing settings adapter tests**

```python
# tests/test_pimcore_web.py
import json
from unittest.mock import patch

from picorgftp_sql import web_data


def test_settings_snapshot_hides_pimcore_api_key():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"]["enabled"] = True
    cfg["pimcore"]["api_key"] = "secret"
    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "load_users", return_value=[]),
    ):
        snapshot = web_data.settings_snapshot()

    assert snapshot["pimcore"]["api_key_set"] is True
    assert "api_key" not in snapshot["pimcore"]


def test_update_settings_preserves_blank_pimcore_api_key_and_saves_mapping():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"]["api_key"] = "saved-secret"
    saved = []
    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "save_config", side_effect=lambda payload, **kwargs: saved.append(json.loads(json.dumps(payload)))),
        patch.object(web_data.config, "initialize_config", return_value=cfg),
        patch.object(web_data, "settings_snapshot", return_value={}),
    ):
        web_data.update_settings(
            {
                "pimcore": {
                    "enabled": True,
                    "api_key": "",
                    "base_url": "http://10.10.0.5",
                    "field_mappings": [
                        {"source": "EAN", "pimcore_field": "EAN", "type": "input", "required": True, "parser": "text"}
                    ],
                }
            }
        )

    assert saved[0]["pimcore"]["api_key"] == "saved-secret"
    assert saved[0]["pimcore"]["field_mappings"][0]["source"] == "EAN"


def test_parse_csv_headers_supports_semicolon_and_quoted_labels():
    raw = b'SKU;EAN;"TOTAL WEIGHT";"TOTAL VOLUME [m2]"\r\nABC;5904804578169;62,5;1,2\r\n'
    assert web_data.parse_pimcore_csv_headers(raw) == [
        "SKU",
        "EAN",
        "TOTAL WEIGHT",
        "TOTAL VOLUME [m2]",
    ]
```

- [ ] **Step 2: Run the new tests and verify missing snapshot/parser behavior**

Run: `pytest tests/test_pimcore_web.py -v`

Expected: FAIL because `settings_snapshot()` has no `pimcore` object and `parse_pimcore_csv_headers` is undefined.

- [ ] **Step 3: Implement settings merge, safe snapshot, and CSV parsing**

```python
# Add imports in picorgftp_sql/web_data.py
import csv
import io

from .pimcore_config import (
    PIMCORE_API_KEY,
    PIMCORE_SETTINGS_KEY,
    normalize_pimcore_settings,
)
from .services.pimcore_service import PimcoreClient, run_settings_test


def parse_pimcore_csv_headers(content: bytes) -> list[str]:
    if not content:
        raise ValueError("Plik CSV jest pusty.")
    text = ""
    for encoding in ("utf-8-sig", "cp1250"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        raise ValueError("Nie mozna odczytac kodowania pliku CSV.")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        reader = csv.reader(io.StringIO(text), dialect)
    except csv.Error:
        reader = csv.reader(io.StringIO(text), delimiter=";")
    row = next(reader, [])
    headers: list[str] = []
    for value in row:
        header = str(value or "").strip()
        if header and header not in headers:
            headers.append(header)
    if not headers:
        raise ValueError("Plik CSV nie zawiera naglowkow.")
    return headers


def test_pimcore_settings(overrides: object = None, username: str = "admin") -> dict[str, object]:
    saved = normalize_pimcore_settings(config.CONFIG.get(PIMCORE_SETTINGS_KEY))
    merged = dict(saved)
    if isinstance(overrides, dict):
        merged.update(overrides)
        if not _text(overrides.get(PIMCORE_API_KEY)):
            merged[PIMCORE_API_KEY] = saved[PIMCORE_API_KEY]
    report = run_settings_test(merged, client=PimcoreClient(merged))
    record_history(
        username=username,
        action="pimcore_settings_test",
        summary="Test ustawien Pimcore zakonczony poprawnie." if report["ok"] else "Test ustawien Pimcore wykryl bledy.",
        details={"pimcore_settings_test": report},
    )
    return report
```

In `update_settings()`, merge only submitted Pimcore keys and retain the in-memory API key when the submitted value is blank:

```python
pimcore_payload = payload.get(PIMCORE_SETTINGS_KEY)
if isinstance(pimcore_payload, dict):
    if "field_mappings" in pimcore_payload:
        issues = field_mapping_issues(pimcore_payload.get("field_mappings"))
        if issues:
            raise ValueError(" ".join(issues))
    current = normalize_pimcore_settings(cfg.get(PIMCORE_SETTINGS_KEY))
    merged = dict(current)
    merged.update(pimcore_payload)
    if not _text(pimcore_payload.get(PIMCORE_API_KEY)):
        merged[PIMCORE_API_KEY] = current[PIMCORE_API_KEY]
    cfg[PIMCORE_SETTINGS_KEY] = normalize_pimcore_settings(merged)
```

In `settings_snapshot()`, expose the normalized section without the key:

```python
pimcore = normalize_pimcore_settings(cfg.get(PIMCORE_SETTINGS_KEY))
pimcore_public = {key: value for key, value in pimcore.items() if key != PIMCORE_API_KEY}
pimcore_public["api_key_set"] = bool(_text(pimcore[PIMCORE_API_KEY]))

# Add to the returned snapshot:
"pimcore": pimcore_public,
```

- [ ] **Step 4: Write failing admin route tests**

```python
# tests/test_pimcore_web.py
from fastapi.testclient import TestClient

from picorgftp_sql.web import app as web_app


def test_pimcore_settings_test_route_returns_structured_report():
    client = TestClient(web_app.app)
    report = {"ok": False, "checks": [{"key": "mapping_fields", "status": "error"}], "total_ms": 4}
    with (
        patch.object(web_app, "_require_admin", return_value={"username": "admin", "role": "admin"}),
        patch.object(web_app, "test_pimcore_settings", return_value=report),
    ):
        response = client.post("/api/settings/pimcore/test")
    assert response.status_code == 200
    assert response.json() == report


def test_pimcore_csv_headers_route_parses_uploaded_file():
    client = TestClient(web_app.app)
    with patch.object(web_app, "_require_admin", return_value={"username": "admin", "role": "admin"}):
        response = client.post(
            "/api/settings/pimcore/import-csv-headers",
            files={"file": ("products.csv", b"SKU;EAN\r\nABC;5904804578169\r\n", "text/csv")},
        )
    assert response.status_code == 200
    assert response.json() == {"headers": ["SKU", "EAN"]}
```

- [ ] **Step 5: Add thin admin-only FastAPI routes**

Import `parse_pimcore_csv_headers` and `test_pimcore_settings` from `web_data`, then add:

```python
# picorgftp_sql/web/app.py inside create_app()
@app.post("/api/settings/pimcore/test")
async def pimcore_settings_test_api(request: Request) -> JSONResponse:
    user = _require_admin(request)
    raw = await request.body()
    payload = json.loads(raw.decode("utf-8")) if raw else {}
    overrides = payload.get("settings") if isinstance(payload, dict) else None
    report = await run_in_threadpool(test_pimcore_settings, overrides, str(user.get("username") or "admin"))
    return JSONResponse(report)


@app.post("/api/settings/pimcore/import-csv-headers")
async def pimcore_csv_headers_api(request: Request) -> JSONResponse:
    _require_admin(request)
    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile) or not upload.filename:
        raise HTTPException(status_code=400, detail="Brak pliku CSV.")
    content = await upload.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Plik CSV jest za duzy.")
    try:
        headers = parse_pimcore_csv_headers(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"headers": headers})
```

- [ ] **Step 6: Run settings and route tests**

Run: `pytest tests/test_pimcore_web.py tests/test_web_data_users.py -v`

Expected: PASS with zero failures.

- [ ] **Step 7: Commit the settings adapter and routes**

```bash
git add picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_pimcore_web.py tests/test_web_data_users.py
git commit -m "feat: expose pimcore settings diagnostics"
```

### Task 5: Live Test Operation Registry And Persistent Audit

**Files:**
- Create: `picorgftp_sql/pimcore_operations.py`
- Modify: `picorgftp_sql/services/pimcore_service.py`
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/app.py`
- Create: `tests/test_pimcore_operations.py`
- Modify: `tests/test_pimcore_web.py`

- [ ] **Step 1: Write failing operation sequencing and retention tests**

```python
# tests/test_pimcore_operations.py
from concurrent.futures import Future

from picorgftp_sql.pimcore_operations import PimcoreOperationRegistry


class ImmediateExecutor:
    def submit(self, callback, *args, **kwargs):
        future = Future()
        try:
            future.set_result(callback(*args, **kwargs))
        except BaseException as exc:
            future.set_exception(exc)
        return future


def test_registry_numbers_events_and_returns_only_new_entries():
    persisted = []
    registry = PimcoreOperationRegistry(executor=ImmediateExecutor())

    def worker(emit):
        emit("validate", "info", "Walidacja")
        emit("create", "success", "Utworzono", object_id=42, elapsed_ms=11)
        return {"status": "completed", "object_id": 42}

    started = registry.start(
        operation_type="test",
        username="admin",
        values={"EAN": "5904804578169"},
        cleanup_policy="keep",
        worker=worker,
        persist=persisted.append,
    )
    first = registry.status(started["operation_id"], after_sequence=0)
    second = registry.status(started["operation_id"], after_sequence=1)

    assert [item["sequence"] for item in first["events"]] == [1, 2, 3, 4]
    assert [item["sequence"] for item in second["events"]] == [2, 3, 4]
    assert first["status"] == "completed"
    assert first["total_ms"] >= 0
    assert persisted[0]["operation_id"] == started["operation_id"]


def test_registry_redacts_secrets_from_values_events_and_results():
    persisted = []
    registry = PimcoreOperationRegistry(executor=ImmediateExecutor())
    started = registry.start(
        operation_type="test",
        username="admin",
        values={"EAN": "5904804578169", "api_key": "never-store"},
        cleanup_policy="keep",
        worker=lambda emit: (
            emit("request", "info", "Wysylanie", authorization="Bearer never-store")
            or {"status": "completed", "cookie": "never-store"}
        ),
        persist=persisted.append,
    )
    report = registry.status(started["operation_id"])
    assert report["values"]["api_key"] == "[REDACTED]"
    assert report["events"][1]["authorization"] == "[REDACTED]"
    assert report["result"]["cookie"] == "[REDACTED]"
```

- [ ] **Step 2: Run the registry test and verify the missing module failure**

Run: `pytest tests/test_pimcore_operations.py -v`

Expected: FAIL during collection because `pimcore_operations.py` does not exist.

- [ ] **Step 3: Implement the thread-safe generic operation registry**

```python
# picorgftp_sql/pimcore_operations.py
from __future__ import annotations

from concurrent.futures import Executor, ThreadPoolExecutor
import secrets
import threading
import time
from typing import Callable

TERMINAL_STATUSES = {"completed", "partial", "failed"}
SENSITIVE_LOG_KEYS = {"api_key", "x-api-key", "authorization", "cookie", "set-cookie"}


def redact_pimcore_log_value(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).casefold() in SENSITIVE_LOG_KEYS else redact_pimcore_log_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_pimcore_log_value(item) for item in value]
    return value


class PimcoreOperationRegistry:
    def __init__(
        self,
        *,
        executor: Executor | None = None,
        retention_seconds: int = 6 * 60 * 60,
    ) -> None:
        self._executor = executor or ThreadPoolExecutor(max_workers=2, thread_name_prefix="pimcore")
        self._retention_seconds = retention_seconds
        self._items: dict[str, dict[str, object]] = {}
        self._lock = threading.RLock()

    def _event(self, operation_id: str, stage: str, severity: str, message: str, **details: object) -> None:
        with self._lock:
            operation = self._items.get(operation_id)
            if not operation:
                return
            sequence = len(operation["events"]) + 1
            now = time.time()
            event = {
                "sequence": sequence,
                "timestamp": now,
                "elapsed_ms": int(max(0, now - float(operation["started_at"] or now)) * 1000),
                "stage": stage,
                "severity": severity,
                "message": str(message or ""),
            }
            event.update(redact_pimcore_log_value(details))
            operation["events"].append(event)

    def start(
        self,
        *,
        operation_type: str,
        username: str,
        values: dict[str, object],
        cleanup_policy: str,
        worker: Callable[[Callable[..., None]], dict[str, object]],
        persist: Callable[[dict[str, object]], object],
    ) -> dict[str, object]:
        self.cleanup()
        operation_id = secrets.token_hex(12)
        created_at = time.time()
        operation = {
            "operation_id": operation_id,
            "operation_type": operation_type,
            "username": username,
            "values": redact_pimcore_log_value(dict(values)),
            "cleanup_policy": cleanup_policy,
            "status": "queued",
            "created_at": created_at,
            "started_at": 0.0,
            "finished_at": 0.0,
            "total_ms": 0,
            "events": [],
            "result": {},
            "error": "",
        }
        with self._lock:
            self._items[operation_id] = operation
        self._executor.submit(self._run, operation_id, worker, persist)
        return {"operation_id": operation_id, "status": "queued"}

    def _run(self, operation_id, worker, persist) -> None:
        with self._lock:
            operation = self._items[operation_id]
            operation["status"] = "running"
            operation["started_at"] = time.time()
        self._event(operation_id, "start", "info", "Rozpoczeto operacje Pimcore.")
        try:
            result = worker(lambda stage, severity, message, **details: self._event(operation_id, stage, severity, message, **details))
            status = str(result.get("status") or "completed")
            if status not in {"completed", "partial"}:
                status = "completed"
            with self._lock:
                operation = self._items[operation_id]
                operation["status"] = status
                operation["result"] = redact_pimcore_log_value(dict(result))
            self._event(operation_id, "finish", "warning" if status == "partial" else "success", "Zakonczono operacje Pimcore.")
        except Exception as exc:
            with self._lock:
                operation = self._items[operation_id]
                operation["status"] = "failed"
                operation["error"] = str(exc) or exc.__class__.__name__
            self._event(operation_id, "finish", "error", str(exc) or exc.__class__.__name__)
        finally:
            with self._lock:
                operation = self._items[operation_id]
                operation["finished_at"] = time.time()
                operation["total_ms"] = int(max(0, operation["finished_at"] - operation["started_at"]) * 1000)
                snapshot = self._snapshot(operation, after_sequence=0)
            persist(snapshot)

    def _snapshot(self, operation: dict[str, object], after_sequence: int) -> dict[str, object]:
        return {
            key: value
            for key, value in operation.items()
            if key != "events"
        } | {
            "events": [dict(item) for item in operation["events"] if int(item["sequence"]) > after_sequence]
        }

    def status(self, operation_id: str, *, after_sequence: int = 0) -> dict[str, object] | None:
        self.cleanup()
        with self._lock:
            operation = self._items.get(operation_id)
            return self._snapshot(operation, max(0, int(after_sequence))) if operation else None

    def cleanup(self, now: float | None = None) -> None:
        cutoff = (time.time() if now is None else now) - self._retention_seconds
        with self._lock:
            for operation_id, item in list(self._items.items()):
                if item["status"] in TERMINAL_STATUSES and float(item["finished_at"] or 0) < cutoff:
                    self._items.pop(operation_id, None)
```

- [ ] **Step 4: Write failing create/fetch/delete workflow tests**

```python
# tests/test_pimcore_operations.py
from picorgftp_sql.services.pimcore_service import PimcoreApiError, run_test_create


class TestClient:
    def __init__(self, *, delete_error=None):
        self.deleted = []
        self.delete_error = delete_error

    def server_info(self):
        return {"data": {"version": "6.6.11"}}

    def classes(self):
        return {"data": [{"id": 1, "name": "Product"}]}

    def class_definition(self, class_id):
        return {"data": {"children": [{"fieldtype": "input", "name": "EAN"}]}}

    def object_list(self, class_name, condition, limit=2):
        return {"data": []}

    def create_object(self, payload):
        assert payload["published"] is False
        return {"data": {"id": 77}}

    def object_by_id(self, object_id):
        return {"data": {"id": object_id, "fullPath": "/Produkty/test-77", "elements": [{"name": "EAN", "value": "5904804578169"}]}}

    def delete_object(self, object_id):
        if self.delete_error:
            raise self.delete_error
        self.deleted.append(object_id)
        return {"success": True}


def test_delete_cleanup_creates_verifies_and_deletes():
    events = []
    result = run_test_create(
        {
            "api_key": "test-key",
            "class_name": "Product",
            "parent_id": "123",
            "object_key_template": "{EAN}",
            "field_mappings": [
                {"source": "EAN", "pimcore_field": "EAN", "type": "input", "required": True, "parser": "text"}
            ],
        },
        {"EAN": "5904804578169"},
        "delete",
        client=TestClient(),
        emit=lambda stage, severity, message, **details: events.append({"stage": stage, **details}),
    )
    assert result["status"] == "completed"
    assert result["object_id"] == 77
    assert result["object_path"] == "/Produkty/test-77"
    assert result["cleanup_result"] == "deleted"
    stages = [event["stage"] for event in events]
    assert "preflight" in stages
    assert stages[-6:] == ["validate", "payload", "duplicate_check", "create", "verify", "delete"]


def test_delete_failure_is_partial_and_keeps_manual_cleanup_identity():
    error = PimcoreApiError(
        "Brak uprawnienia delete.",
        "/webservice/rest/object/id/77",
        status_code=403,
        kind="http",
    )
    result = run_test_create(
        {
            "api_key": "test-key",
            "class_name": "Product",
            "parent_id": "123",
            "object_key_template": "{EAN}",
            "field_mappings": [
                {"source": "EAN", "pimcore_field": "EAN", "type": "input", "required": True, "parser": "text"}
            ],
        },
        {"EAN": "5904804578169"},
        "delete",
        client=TestClient(delete_error=error),
        emit=lambda *args, **kwargs: None,
    )
    assert result["status"] == "partial"
    assert result["cleanup_result"] == "delete_failed"
    assert result["object_id"] == 77
    assert result["object_key"] == "5904804578169"
    assert result["object_path"] == "/Produkty/test-77"


def test_fetch_failure_is_partial_but_still_runs_selected_delete():
    class FetchFailureClient(TestClient):
        def object_by_id(self, object_id):
            raise PimcoreApiError(
                "Odczyt kontrolny nie powiodl sie.",
                f"/webservice/rest/object/id/{object_id}",
                status_code=500,
                kind="http",
            )

    client = FetchFailureClient()
    result = run_test_create(
        {
            "api_key": "test-key",
            "class_name": "Product",
            "parent_id": "123",
            "object_key_template": "{EAN}",
            "field_mappings": [
                {"source": "EAN", "pimcore_field": "EAN", "type": "input", "required": True, "parser": "text"}
            ],
        },
        {"EAN": "5904804578169"},
        "delete",
        client=client,
        emit=lambda *args, **kwargs: None,
    )
    assert result["status"] == "partial"
    assert result["cleanup_result"] == "deleted"
    assert client.deleted == [77]


def test_keep_cleanup_retains_unpublished_object():
    client = TestClient()
    result = run_test_create(
        {
            "api_key": "test-key",
            "class_name": "Product",
            "parent_id": "123",
            "object_key_template": "{EAN}",
            "field_mappings": [
                {"source": "EAN", "pimcore_field": "EAN", "type": "input", "required": True, "parser": "text"}
            ],
        },
        {"EAN": "5904804578169"},
        "keep",
        client=client,
        emit=lambda *args, **kwargs: None,
    )
    assert result["status"] == "completed"
    assert result["cleanup_result"] == "kept"
    assert client.deleted == []
```

- [ ] **Step 5: Implement the real test-create workflow with partial failure reporting**

```python
# Append to picorgftp_sql/services/pimcore_service.py
def extract_object_values(payload: object) -> dict[str, object]:
    values: dict[str, object] = {}

    def visit(node: object) -> None:
        if isinstance(node, dict):
            name = str(node.get("name") or "").strip()
            if name and "value" in node:
                values[name] = node.get("value")
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    return values


def extract_object_path(payload: object) -> str:
    if isinstance(payload, dict):
        for key in ("fullPath", "path"):
            if payload.get(key):
                return str(payload[key])
        for key in ("data", "object"):
            path = extract_object_path(payload.get(key))
            if path:
                return path
    return ""


def run_test_create(
    settings: object,
    values: dict[str, object],
    cleanup_policy: str,
    *,
    client: PimcoreClient | None = None,
    emit: Callable[..., None],
) -> dict[str, object]:
    if cleanup_policy not in {"delete", "keep"}:
        raise ValueError("Wybierz usuniecie albo pozostawienie obiektu testowego.")
    config = normalize_pimcore_settings(settings)
    api = client or PimcoreClient(config)
    preflight = run_settings_test(config, client=api)
    for check in preflight["checks"]:
        severity = {
            "ok": "success",
            "warning": "warning",
            "error": "error",
            "info": "info",
        }.get(str(check.get("status")), "info")
        emit(
            "preflight",
            severity,
            f"{check.get('key')}: {check.get('message')}",
            endpoint=check.get("endpoint"),
            status_code=check.get("status_code"),
            response_excerpt=check.get("response_excerpt"),
            suggested_fix=check.get("suggested_fix"),
            stage_elapsed_ms=check.get("elapsed_ms", 0),
        )
    if not preflight["ok"]:
        failed = [str(item.get("message")) for item in preflight["checks"] if item.get("status") == "error"]
        raise ValueError("Test konfiguracji blokuje zapis: " + " | ".join(failed))
    stage_started = time.perf_counter()
    try:
        payload = build_create_payload(config, values, published=False, use_defaults=False)
    except ValueError as exc:
        emit("validate", "error", str(exc), stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
        raise
    emit("validate", "success", "Walidacja konfiguracji i pol zakonczona.", stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
    safe_payload = {**payload, "elements": [dict(item) for item in payload["elements"]]}
    emit("payload", "info", "Zbudowano dane obiektu.", payload=safe_payload, stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
    stage_started = time.perf_counter()
    ean = validate_ean(values.get("EAN"))
    duplicates = api.object_list(config["class_name"], build_ean_condition(ean, config["existence_fields"]), limit=2)
    duplicate_records = _list_records(duplicates, ("data", "objects", "items"))
    if duplicate_records:
        duplicate = duplicate_records[0]
        emit("duplicate_check", "error", "Testowy EAN juz istnieje w Pimcore.", object_id=duplicate.get("id"), object_path=duplicate.get("fullPath") or duplicate.get("path"), stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
        raise ValueError("Testowy EAN juz istnieje w Pimcore; podaj izolowana wartosc.")
    emit("duplicate_check", "success", "Testowy EAN nie istnieje w Pimcore.", stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
    stage_started = time.perf_counter()
    try:
        created = api.create_object(payload)
        object_id = extract_object_id(created)
    except PimcoreApiError as exc:
        emit("create", "error", str(exc), method="POST", endpoint="/webservice/rest/object", error=exc.as_dict(), stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
        raise
    except ValueError as exc:
        emit("create", "error", str(exc), method="POST", endpoint="/webservice/rest/object", response_excerpt=_response_excerpt(json.dumps(created, ensure_ascii=True)), stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
        raise
    emit("create", "success", "Utworzono obiekt.", object_id=object_id, method="POST", endpoint="/webservice/rest/object", status_code=getattr(api, "last_response", {}).get("status_code"), response_excerpt=_response_excerpt(json.dumps(created, ensure_ascii=True)), stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
    status = "completed"
    cleanup_result = "kept"
    error = ""
    object_path = ""
    try:
        stage_started = time.perf_counter()
        fetched = api.object_by_id(object_id)
        object_path = extract_object_path(fetched)
        actual = extract_object_values(fetched)
        expected = {item["name"]: item["value"] for item in payload["elements"]}
        mismatched = [name for name, value in expected.items() if actual.get(name) != value]
        if mismatched:
            status = "partial"
            error = "Nie potwierdzono pol: " + ", ".join(mismatched)
            emit("verify", "warning", error, object_id=object_id, endpoint=f"/webservice/rest/object/id/{object_id}", status_code=getattr(api, "last_response", {}).get("status_code"), response_excerpt=_response_excerpt(json.dumps(fetched, ensure_ascii=True)), stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
        else:
            emit("verify", "success", "Odczyt kontrolny potwierdzil dane.", object_id=object_id, endpoint=f"/webservice/rest/object/id/{object_id}", status_code=getattr(api, "last_response", {}).get("status_code"), response_excerpt=_response_excerpt(json.dumps(fetched, ensure_ascii=True)), stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
    except PimcoreApiError as exc:
        status = "partial"
        error = str(exc)
        emit("verify", "error", str(exc), object_id=object_id, error=exc.as_dict(), stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
    if cleanup_policy == "delete":
        try:
            stage_started = time.perf_counter()
            deleted = api.delete_object(object_id)
            cleanup_result = "deleted"
            emit("delete", "success", "Usunieto obiekt testowy.", object_id=object_id, method="DELETE", endpoint=f"/webservice/rest/object/id/{object_id}", status_code=getattr(api, "last_response", {}).get("status_code"), response_excerpt=_response_excerpt(json.dumps(deleted, ensure_ascii=True)), stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
        except PimcoreApiError as exc:
            status = "partial"
            cleanup_result = "delete_failed"
            error = str(exc)
            emit("delete", "error", str(exc), object_id=object_id, error=exc.as_dict(), stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
    return {
        "status": status,
        "object_id": object_id,
        "object_key": payload["key"],
        "object_path": object_path,
        "cleanup_policy": cleanup_policy,
        "cleanup_result": cleanup_result,
        "error": error,
        "payload": safe_payload,
    }
```

- [ ] **Step 6: Bridge the registry to config, history, and filtered audit queries**

```python
# picorgftp_sql/web_data.py
from .pimcore_operations import PimcoreOperationRegistry, redact_pimcore_log_value
from .services.pimcore_service import run_test_create

_PIMCORE_OPERATIONS = PimcoreOperationRegistry()


def _persist_pimcore_operation(report: dict[str, object]) -> dict[str, object]:
    values = report.get("values") if isinstance(report.get("values"), dict) else {}
    result = report.get("result") if isinstance(report.get("result"), dict) else {}
    result_object = result.get("object") if isinstance(result.get("object"), dict) else {}
    if report.get("operation_type") == "test":
        action = "pimcore_test_create"
    elif report.get("status") in {"duplicate", "failed"}:
        action = "pimcore_product_create_rejected"
    else:
        action = "pimcore_product_create"
    return record_history(
        username=_text(report.get("username")),
        action=action,
        ean=values.get("EAN", ""),
        product_id=result.get("object_id") or result_object.get("id", ""),
        summary=f"Pimcore: {report.get('status', 'unknown')}.",
        details={"pimcore_operation": report},
    )


def start_pimcore_test_create(values: object, cleanup_policy: object, username: str) -> dict[str, object]:
    submitted = dict(values) if isinstance(values, dict) else {}
    policy = _text(cleanup_policy)
    settings = normalize_pimcore_settings(config.CONFIG.get(PIMCORE_SETTINGS_KEY))
    return _PIMCORE_OPERATIONS.start(
        operation_type="test",
        username=username,
        values=submitted,
        cleanup_policy=policy,
        worker=lambda emit: run_test_create(settings, submitted, policy, emit=emit),
        persist=_persist_pimcore_operation,
    )


def pimcore_operation_status(operation_id: str, after_sequence: int = 0) -> dict[str, object] | None:
    return _PIMCORE_OPERATIONS.status(operation_id, after_sequence=after_sequence)


def pimcore_operation_history(
    *,
    operation_type: str = "",
    result: str = "",
    user: str = "",
    query: str = "",
    date_from: float = 0,
    date_to: float = 0,
    limit: int = 200,
) -> dict[str, object]:
    records = []
    for item in reversed(_load_history_records()):
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        operation = details.get("pimcore_operation") if isinstance(details.get("pimcore_operation"), dict) else None
        if not operation:
            continue
        if operation_type and _text(operation.get("operation_type")) != _text(operation_type):
            continue
        if result and _text(operation.get("status")) != _text(result):
            continue
        if user and _text(operation.get("username")).casefold() != _text(user).casefold():
            continue
        started_at = float(operation.get("started_at") or operation.get("created_at") or 0)
        if date_from and started_at < float(date_from):
            continue
        if date_to and started_at > float(date_to):
            continue
        searchable = json.dumps(operation, ensure_ascii=False).casefold()
        if query and _text(query).casefold() not in searchable:
            continue
        records.append(operation)
        if len(records) >= max(1, min(1000, int(limit or 200))):
            break
    return {"items": records, "count": len(records)}
```

Add a persistence-query regression test:

```python
# tests/test_pimcore_web.py
def test_pimcore_operation_history_reads_persisted_audit_records():
    operation = {
        "operation_id": "op-1",
        "operation_type": "test",
        "username": "admin",
        "status": "partial",
        "started_at": 15.0,
        "events": [{"sequence": 1, "stage": "delete", "message": "HTTP 403"}],
    }
    records = [
        {"action": "entry_save", "details": {}},
        {"action": "pimcore_test_create", "details": {"pimcore_operation": operation}},
    ]
    with patch.object(web_data, "_load_history_records", return_value=records):
        result = web_data.pimcore_operation_history(
            operation_type="test",
            result="partial",
            user="admin",
            query="HTTP 403",
            date_from=10,
            date_to=20,
        )
    assert result == {"items": [operation], "count": 1}
```

- [ ] **Step 7: Add admin-only start/status/history routes and tests**

```python
# tests/test_pimcore_web.py
def test_pimcore_test_run_routes_forward_admin_and_sequence():
    client = TestClient(web_app.app)
    user = {"username": "admin", "role": "admin"}
    with (
        patch.object(web_app, "_require_admin", return_value=user),
        patch.object(web_app, "start_pimcore_test_create", return_value={"operation_id": "op-1", "status": "queued"}),
        patch.object(web_app, "pimcore_operation_status", return_value={"operation_id": "op-1", "events": [], "status": "running"}) as status,
    ):
        started = client.post(
            "/api/settings/pimcore/test-create-runs",
            json={"values": {"EAN": "5904804578169"}, "cleanup_policy": "delete"},
        )
        polled = client.get("/api/settings/pimcore/test-create-runs/op-1?after_sequence=4")
    assert started.status_code == 200
    assert started.json()["operation"]["operation_id"] == "op-1"
    assert polled.status_code == 200
    status.assert_called_once_with("op-1", 4)


def test_missing_pimcore_operation_returns_404():
    client = TestClient(web_app.app)
    with (
        patch.object(web_app, "_require_admin", return_value={"username": "admin", "role": "admin"}),
        patch.object(web_app, "pimcore_operation_status", return_value=None),
    ):
        response = client.get("/api/settings/pimcore/test-create-runs/missing")
    assert response.status_code == 404


def test_pimcore_history_route_forwards_all_filters():
    client = TestClient(web_app.app)
    with (
        patch.object(web_app, "_require_admin", return_value={"username": "admin", "role": "admin"}),
        patch.object(web_app, "pimcore_operation_history", return_value={"items": [], "count": 0}) as history,
    ):
        response = client.get(
            "/api/settings/pimcore/operations?operation_type=test&result=partial&user=admin&query=5904&date_from=10&date_to=20&limit=25"
        )
    assert response.status_code == 200
    history.assert_called_once_with(
        operation_type="test",
        result="partial",
        user="admin",
        query="5904",
        date_from=10.0,
        date_to=20.0,
        limit=25,
    )


# picorgftp_sql/web/app.py
@app.post("/api/settings/pimcore/test-create-runs")
async def pimcore_test_create_start_api(request: Request) -> JSONResponse:
    user = _require_admin(request)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Niepoprawne dane testu Pimcore.")
    try:
        operation = start_pimcore_test_create(
            payload.get("values"),
            payload.get("cleanup_policy"),
            str(user.get("username") or "admin"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"operation": operation})


@app.get("/api/settings/pimcore/test-create-runs/{operation_id}")
def pimcore_test_create_status_api(request: Request, operation_id: str, after_sequence: int = 0) -> Dict[str, Any]:
    _require_admin(request)
    operation = pimcore_operation_status(operation_id, after_sequence)
    if not operation:
        raise HTTPException(status_code=404, detail="Nie znaleziono operacji Pimcore.")
    return operation


@app.get("/api/settings/pimcore/operations")
def pimcore_operations_api(
    request: Request,
    operation_type: str = "",
    result: str = "",
    user: str = "",
    query: str = "",
    date_from: float = 0,
    date_to: float = 0,
    limit: int = 200,
) -> Dict[str, Any]:
    _require_admin(request)
    return pimcore_operation_history(
        operation_type=operation_type,
        result=result,
        user=user,
        query=query,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
```

- [ ] **Step 8: Run operation and route tests**

Run: `pytest tests/test_pimcore_operations.py tests/test_pimcore_web.py -v`

Expected: PASS with zero failures.

- [ ] **Step 9: Commit live operation backend support**

```bash
git add picorgftp_sql/pimcore_operations.py picorgftp_sql/services/pimcore_service.py picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_pimcore_operations.py tests/test_pimcore_web.py
git commit -m "feat: add pimcore live test operations"
```

### Task 6: Pimcore Settings Tab, Mapping Editor, And Read-Only Checklist

**Files:**
- Modify: `picorgftp_sql/web/static/index.html:350-365`
- Modify: `picorgftp_sql/web/static/app.js:1-35,170-205,5299-5318,5691-6452,6555-6562`
- Modify: `picorgftp_sql/web/static/app.css:850-1130,1510-1620`
- Modify: `tests/test_web_ui_integrity.py`
- Modify: `tests/test_source_integrity.py`

- [ ] **Step 1: Write failing UI structure tests**

```python
# tests/test_web_ui_integrity.py
def test_settings_include_pimcore_tab(self) -> None:
    html = _parse(INDEX_HTML)
    self.assertTrue(html.has_tag("button", **{"data-settings-tab": "pimcore"}))


# tests/test_source_integrity.py
def test_pimcore_settings_wires_save_test_and_csv_import(self) -> None:
    source = APP_JS.read_text(encoding="utf-8")
    self.assertIn('function renderSettingsPimcore()', source)
    self.assertIn('requestJson("/api/settings/pimcore/test"', source)
    self.assertIn('requestJson("/api/settings/pimcore/import-csv-headers"', source)
    self.assertIn('field_mappings: collectPimcoreMappings(form)', source)
```

- [ ] **Step 2: Run UI integrity tests and verify they fail**

Run: `pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py -v`

Expected: FAIL because the Pimcore tab, modals, and JavaScript functions are absent.

- [ ] **Step 3: Add the settings tab and checklist container**

```html
<!-- picorgftp_sql/web/static/index.html inside .settings-tabs -->
<button type="button" class="settings-tab" data-settings-tab="pimcore">Pimcore</button>
```

Use the existing DOM helper style in `app.js`. Add `renderSettingsPimcore()` with these exact controls and names:

```javascript
function pimcoreMappingRow(mapping = {}) {
  const row = document.createElement("div");
  row.className = "pimcore-mapping-row";
  const textInput = (name, value, label) => {
    const input = document.createElement("input");
    input.name = name;
    input.value = value || "";
    input.placeholder = label;
    input.setAttribute("aria-label", label);
    return input;
  };
  const choice = (name, value, values, label) => {
    const select = document.createElement("select");
    select.name = name;
    select.setAttribute("aria-label", label);
    for (const item of values) {
      const option = document.createElement("option");
      option.value = item;
      option.textContent = item;
      option.selected = item === value;
      select.appendChild(option);
    }
    return select;
  };
  const required = document.createElement("input");
  required.type = "checkbox";
  required.name = "mapping_required";
  required.checked = Boolean(mapping.required);
  required.setAttribute("aria-label", "Pole wymagane");
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "ghost-button";
  remove.textContent = "Usun";
  remove.title = "Usun mapowanie";
  remove.addEventListener("click", () => row.remove());
  row.append(
    textInput("mapping_source", mapping.source, "Kolumna CSV"),
    textInput("mapping_label", mapping.label, "Etykieta"),
    textInput("mapping_target", mapping.pimcore_field, "Pole Pimcore"),
    choice("mapping_type", mapping.type || "input", ["input", "textarea", "numeric", "checkbox", "select"], "Typ Pimcore"),
    textInput("mapping_language", mapping.language, "Jezyk"),
    required,
    textInput("mapping_default", mapping.default, "Wartosc domyslna"),
    choice("mapping_parser", mapping.parser || "text", ["text", "integer", "decimal_comma", "boolean", "empty_to_null"], "Parser"),
    remove
  );
  return row;
}


function collectPimcoreMappings(form) {
  return [...form.querySelectorAll(".pimcore-mapping-row")].map((row) => ({
    source: row.querySelector('[name="mapping_source"]').value.trim(),
    label: row.querySelector('[name="mapping_label"]').value.trim(),
    pimcore_field: row.querySelector('[name="mapping_target"]').value.trim(),
    type: row.querySelector('[name="mapping_type"]').value,
    language: row.querySelector('[name="mapping_language"]').value.trim() || null,
    required: row.querySelector('[name="mapping_required"]').checked,
    default: row.querySelector('[name="mapping_default"]').value,
    parser: row.querySelector('[name="mapping_parser"]').value,
  }));
}


function collectPimcoreSettings(form) {
  const data = new FormData(form);
  return {
    enabled: data.has("enabled"),
    base_url: data.get("base_url"),
    api_key: data.get("api_key"),
    class_name: data.get("class_name"),
    parent_id: data.get("parent_id"),
    published: data.has("published"),
    object_key_template: data.get("object_key_template"),
    existence_fields: String(data.get("existence_fields") || "").split(",").map((item) => item.trim()).filter(Boolean),
    timeout_seconds: Number(data.get("timeout_seconds") || 10),
    verify_tls: data.has("verify_tls"),
    field_mappings: collectPimcoreMappings(form),
  };
}


function pimcoreChecklistElement() {
  const output = document.createElement("div");
  output.id = "pimcoreSettingsChecklist";
  output.className = "pimcore-checklist empty-state";
  output.textContent = "Test nie zostal uruchomiony.";
  return output;
}


function renderSettingsPimcore() {
  const pimcore = state.settings.pimcore || {};
  const form = document.createElement("form");
  form.className = "settings-form";
  const mappings = document.createElement("div");
  mappings.className = "pimcore-mapping-list wide-field";
  for (const mapping of pimcore.field_mappings || []) {
    mappings.appendChild(pimcoreMappingRow(mapping));
  }
  const addMapping = document.createElement("button");
  addMapping.type = "button";
  addMapping.className = "secondary-button";
  addMapping.textContent = "Dodaj mapowanie";
  addMapping.addEventListener("click", () => mappings.appendChild(pimcoreMappingRow({})));
  form.append(
    settingsFieldGroup(
      "Polaczenie Pimcore",
      checkField("enabled", "Integracja wlaczona", pimcore.enabled),
      inputField("base_url", "Adres Pimcore", pimcore.base_url || "http://10.10.0.5"),
      credentialField("api_key", "Klucz API", pimcore.api_key_set),
      inputField("class_name", "Klasa", pimcore.class_name || "Product"),
      inputField("parent_id", "ID folderu Produkty", pimcore.parent_id || ""),
      checkField("published", "Publikuj nowe produkty", pimcore.published),
      inputField("object_key_template", "Szablon klucza", pimcore.object_key_template || "{SKU}"),
      inputField("existence_fields", "Pola sprawdzania EAN", (pimcore.existence_fields || []).join(", ")),
      inputField("timeout_seconds", "Timeout [s]", pimcore.timeout_seconds || 10, { type: "number", min: "1", max: "120" }),
      checkField("verify_tls", "Weryfikuj certyfikat TLS", pimcore.verify_tls !== false)
    ),
    settingsFieldGroup(
      "Mapowanie CSV do Pimcore",
      mappings,
      actionRow(addMapping, pimcoreCsvImportButton(mappings))
    ),
    settingsFieldGroup(
      "Testy integracji",
      actionRow(pimcoreReadOnlyTestButton(() => collectPimcoreSettings(form))),
      pimcoreChecklistElement()
    )
  );
  settingsSaveButton(form, () => ({ pimcore: collectPimcoreSettings(form) }));
  settingsOutput.appendChild(form);
}
```

The mapping row and collector above keep source/target/type/parser names consistent with the backend model and give every compact control an accessible label.

- [ ] **Step 4: Implement CSV header import and checklist rendering**

```javascript
function pimcoreCsvImportButton(mappingList) {
  const input = document.createElement("input");
  const button = document.createElement("button");
  input.type = "file";
  input.accept = ".csv,text/csv";
  input.hidden = true;
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Wczytaj naglowki CSV";
  button.addEventListener("click", () => input.click());
  input.addEventListener("change", async () => {
    const file = input.files?.[0];
    if (!file) return;
    try {
      const body = new FormData();
      body.set("file", file, file.name);
      const payload = await requestJson("/api/settings/pimcore/import-csv-headers", { method: "POST", body });
      const existing = new Set(
        [...mappingList.querySelectorAll('[name="mapping_source"]')].map((item) => item.value)
      );
      for (const header of payload.headers || []) {
        if (!existing.has(header)) mappingList.appendChild(pimcoreMappingRow({ source: header, label: header }));
      }
      settingsStatus.textContent = `Wczytano ${payload.headers?.length || 0} naglowkow CSV.`;
    } catch (error) {
      settingsStatus.textContent = error.message;
    } finally {
      input.value = "";
    }
  });
  const wrapper = document.createElement("span");
  wrapper.append(button, input);
  return wrapper;
}


function renderPimcoreChecklist(report) {
  const output = document.querySelector("#pimcoreSettingsChecklist");
  if (!output) return;
  output.textContent = "";
  output.className = "pimcore-checklist";
  for (const check of report.checks || []) {
    const row = document.createElement("div");
    const title = document.createElement("strong");
    const detail = document.createElement("span");
    row.className = `pimcore-check-row ${check.status || "info"}`;
    title.textContent = `${check.status || "info"}: ${check.message || check.key}`;
    detail.textContent = [
      check.endpoint,
      check.status_code ? `HTTP ${check.status_code}` : "",
      `${Number(check.elapsed_ms || 0)} ms`,
      check.response_excerpt,
      check.suggested_fix,
    ].filter(Boolean).join(" | ");
    row.append(title, detail);
    output.appendChild(row);
  }
}


function pimcoreReadOnlyTestButton(getSettings) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Sprawdz konfiguracje";
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      renderPimcoreChecklist(await requestJson("/api/settings/pimcore/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: getSettings() }),
        timeoutMs: 120000,
      }));
    } catch (error) {
      settingsStatus.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  return button;
}
```

Render each check as one row containing status icon/text, message, endpoint, HTTP status, elapsed time, response excerpt, and suggested fix. Never render or interpolate `api_key`.

- [ ] **Step 5: Add dense responsive styles and settings dispatch**

Add `.pimcore-mapping-list`, `.pimcore-mapping-row`, `.pimcore-checklist`, `.pimcore-check-row`, and status modifier classes. Use a fixed mapping grid on desktop and one column below `900px`; keep border radius at `8px` or less and use existing color variables. Add:

```css
.pimcore-mapping-list,
.pimcore-checklist {
  display: grid;
  gap: 8px;
}

.pimcore-mapping-row {
  display: grid;
  grid-template-columns: 1.2fr 1.2fr 1.2fr 110px 90px 36px 1fr 130px auto;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid var(--line);
  padding: 8px 0;
}

.pimcore-check-row {
  display: grid;
  gap: 4px;
  border-left: 4px solid var(--line);
  padding: 8px 10px;
}

.pimcore-check-row.ok { border-left-color: var(--accent); }
.pimcore-check-row.warning { border-left-color: var(--warn); }
.pimcore-check-row.error { border-left-color: var(--danger); }

@media (max-width: 900px) {
  .pimcore-mapping-row {
    grid-template-columns: 1fr;
  }
}
```

```javascript
if (state.activeSettingsTab === "pimcore") renderSettingsPimcore();
```

In `index.html`, change both static asset query strings to `v=20260701-pimcore` so deployed browsers do not reuse the pre-Pimcore JavaScript or CSS.

- [ ] **Step 6: Run UI integrity and all settings tests**

Run: `pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py tests/test_pimcore_web.py tests/test_web_data_users.py -v`

Expected: PASS with zero failures.

- [ ] **Step 7: Commit the settings UI**

```bash
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py tests/test_source_integrity.py
git commit -m "feat: add pimcore settings interface"
```

### Task 7: Two-Pane Test Modal, Live Logs, And Pimcore History

**Files:**
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_web_ui_integrity.py`
- Modify: `tests/test_source_integrity.py`

- [ ] **Step 1: Add failing tests for non-closing live test behavior**

```python
# tests/test_web_ui_integrity.py
def test_pimcore_test_and_history_modals_exist(self) -> None:
    html = _parse(INDEX_HTML)
    self.assertIn("pimcoreTestModal", html.ids)
    self.assertIn("pimcoreHistoryModal", html.ids)
    self.assertIn("pimcoreTestForm", html.ids)
    self.assertIn("pimcoreLiveLog", html.ids)


# tests/test_source_integrity.py
def test_pimcore_write_test_keeps_modal_open_and_polls_incrementally(self) -> None:
    source = APP_JS.read_text(encoding="utf-8")
    self.assertIn("function openPimcoreWriteTest()", source)
    self.assertIn("after_sequence", source)
    self.assertIn("500", source)
    self.assertIn("pimcoreTestForm.reset()", source)
    self.assertNotIn('pimcoreTestModal.classList.remove("active"); // submit', source)
    self.assertIn("cleanup_policy", source)


def test_pimcore_live_log_history_uses_dedicated_endpoint(self) -> None:
    source = APP_JS.read_text(encoding="utf-8")
    self.assertIn("/api/settings/pimcore/test-create-runs", source)
    self.assertIn("/api/settings/pimcore/operations", source)
    self.assertIn("function appendPimcoreLiveEvents", source)
```

- [ ] **Step 2: Run focused integrity tests and verify failure**

Run: `pytest tests/test_source_integrity.py tests/test_web_ui_integrity.py -v`

Expected: FAIL because live test functions and modal IDs are absent.

- [ ] **Step 3: Add the dedicated nested modals**

```html
<!-- picorgftp_sql/web/static/index.html, after settingsView -->
<div id="pimcoreTestModal" class="modal-view nested-modal">
  <section class="manager-panel pimcore-test-panel">
    <div class="section-heading">
      <h1>Testowe dodanie obiektu Pimcore</h1>
      <button id="pimcoreTestCloseButton" type="button" class="ghost-button modal-close">Zamknij</button>
    </div>
    <div class="pimcore-test-layout">
      <form id="pimcoreTestForm" class="pimcore-test-fields"></form>
      <section class="pimcore-live-log-panel" aria-labelledby="pimcoreLiveLogTitle">
        <div class="section-heading">
          <h2 id="pimcoreLiveLogTitle">Log operacji</h2>
          <span id="pimcoreTestElapsed">0 ms</span>
        </div>
        <div id="pimcoreLiveLog" class="pimcore-live-log empty-state" aria-live="polite">Brak operacji.</div>
      </section>
    </div>
    <div class="pimcore-test-actions">
      <label><input type="radio" name="pimcore_cleanup_policy" value="delete"> Usun po tescie</label>
      <label><input type="radio" name="pimcore_cleanup_policy" value="keep"> Pozostaw w Pimcore</label>
      <button id="pimcoreTestSubmitButton" type="button">Wyslij</button>
      <button id="pimcoreTestClearButton" type="button" class="secondary-button">Wyczysc formularz</button>
      <span id="pimcoreTestStatus" role="status"></span>
    </div>
  </section>
</div>

<div id="pimcoreHistoryModal" class="modal-view nested-modal">
  <section class="manager-panel">
    <div class="section-heading">
      <h1>Historia operacji Pimcore</h1>
      <button id="pimcoreHistoryCloseButton" type="button" class="ghost-button modal-close">Zamknij</button>
    </div>
    <form id="pimcoreHistoryFilters" class="pimcore-history-filters">
      <select name="operation_type" aria-label="Typ operacji">
        <option value="">Wszystkie typy</option>
        <option value="manual">Dodanie reczne</option>
        <option value="test">Dodanie testowe</option>
      </select>
      <select name="result" aria-label="Wynik operacji">
        <option value="">Wszystkie wyniki</option>
        <option value="completed">Sukces</option>
        <option value="duplicate">Duplikat</option>
        <option value="partial">Czesciowy blad</option>
        <option value="failed">Blad</option>
      </select>
      <input name="user" aria-label="Uzytkownik" placeholder="Uzytkownik">
      <input name="query" aria-label="EAN, SKU lub klucz" placeholder="EAN, SKU lub klucz">
      <input name="date_from" type="date" aria-label="Data od">
      <input name="date_to" type="date" aria-label="Data do">
      <button type="submit" class="secondary-button">Filtruj</button>
    </form>
    <div id="pimcoreHistoryOutput" class="history-output empty-state">Brak operacji.</div>
  </section>
</div>
```

Do not attach these modals to the generic `[data-close-modal]` backdrop behavior. Only the named close buttons remove `active`.

- [ ] **Step 4: Render an empty independent form and explicit cleanup selection**

```javascript
// Add `pimcoreTestOperation: null` to the top-level state object, then cache:
const pimcoreTestModal = document.querySelector("#pimcoreTestModal");
const pimcoreTestForm = document.querySelector("#pimcoreTestForm");
const pimcoreLiveLog = document.querySelector("#pimcoreLiveLog");
const pimcoreTestElapsed = document.querySelector("#pimcoreTestElapsed");
const pimcoreTestStatus = document.querySelector("#pimcoreTestStatus");
const pimcoreTestSubmitButton = document.querySelector("#pimcoreTestSubmitButton");
const pimcoreTestClearButton = document.querySelector("#pimcoreTestClearButton");
const pimcoreTestCloseButton = document.querySelector("#pimcoreTestCloseButton");
const pimcoreHistoryModal = document.querySelector("#pimcoreHistoryModal");
const pimcoreHistoryFilters = document.querySelector("#pimcoreHistoryFilters");
const pimcoreHistoryOutput = document.querySelector("#pimcoreHistoryOutput");
const pimcoreHistoryCloseButton = document.querySelector("#pimcoreHistoryCloseButton");


function pimcoreOpenWriteTestButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Testowo dodaj obiekt";
  button.addEventListener("click", openPimcoreWriteTest);
  return button;
}


function pimcoreHistoryButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Historia Pimcore";
  button.addEventListener("click", openPimcoreHistory);
  return button;
}


function openPimcoreWriteTest() {
  pimcoreTestForm.textContent = "";
  for (const mapping of state.settings?.pimcore?.field_mappings || []) {
    const label = document.createElement("label");
    const title = document.createElement("span");
    const input = document.createElement("input");
    title.textContent = `${mapping.label || mapping.source}${mapping.required ? " *" : ""}`;
    input.name = mapping.source;
    input.value = "";
    input.required = Boolean(mapping.required);
    input.autocomplete = "off";
    label.append(title, input);
    pimcoreTestForm.appendChild(label);
  }
  pimcoreTestModal.querySelectorAll('[name="pimcore_cleanup_policy"]').forEach((item) => {
    item.checked = false;
  });
  clearPimcoreLiveLog();
  pimcoreTestModal.classList.add("active");
}


function collectPimcoreTestValues() {
  return Object.fromEntries(
    [...pimcoreTestForm.querySelectorAll("input[name]")].map((input) => [input.name, input.value])
  );
}
```

Keep cleanup controls outside `pimcoreTestForm` and query them from the modal. In `renderSettingsPimcore()`, change the test action row to `actionRow(pimcoreReadOnlyTestButton(() => collectPimcoreSettings(form)), pimcoreOpenWriteTestButton(), pimcoreHistoryButton())`.

- [ ] **Step 5: Start the run and poll numbered events every 500 ms**

```javascript
function clearPimcoreLiveLog() {
  pimcoreLiveLog.textContent = "Brak operacji.";
  pimcoreLiveLog.className = "pimcore-live-log empty-state";
  pimcoreTestElapsed.textContent = "0 ms";
  pimcoreTestStatus.textContent = "";
}


function appendPimcoreLiveEvents(events) {
  const wasAtBottom =
    pimcoreLiveLog.scrollHeight - pimcoreLiveLog.scrollTop - pimcoreLiveLog.clientHeight < 24;
  if (pimcoreLiveLog.classList.contains("empty-state")) {
    pimcoreLiveLog.textContent = "";
    pimcoreLiveLog.className = "pimcore-live-log";
  }
  for (const event of events) {
    const row = document.createElement("div");
    const heading = document.createElement("strong");
    const detail = document.createElement("span");
    const diagnostic = document.createElement("pre");
    row.className = `pimcore-live-event ${event.severity || "info"}`;
    const eventTime = Number(event.timestamp || 0) * 1000 || Date.now();
    heading.textContent = `[${new Date(eventTime).toLocaleTimeString()}] ${event.stage || "etap"}: ${event.message || ""}`;
    detail.textContent = [
      event.method,
      event.endpoint,
      event.status_code ? `HTTP ${event.status_code}` : "",
      `od startu ${Number(event.elapsed_ms || 0)} ms`,
      event.stage_elapsed_ms !== undefined ? `etap ${Number(event.stage_elapsed_ms || 0)} ms` : "",
    ].filter(Boolean).join(" | ");
    diagnostic.textContent = [
      event.response_excerpt,
      event.suggested_fix,
      event.error ? JSON.stringify(event.error, null, 2) : "",
    ].filter(Boolean).join("\n");
    row.append(heading, detail);
    if (diagnostic.textContent) row.appendChild(diagnostic);
    pimcoreLiveLog.appendChild(row);
  }
  if (wasAtBottom) pimcoreLiveLog.scrollTop = pimcoreLiveLog.scrollHeight;
}


function pimcoreTestObjectKey(template, values) {
  const missing = [];
  const rendered = String(template || "{EAN}").replace(/\{([^{}]+)\}/g, (_match, source) => {
    const value = String(values[source] || "").trim();
    if (!value) missing.push(source);
    return value;
  });
  if (missing.length) throw new Error(`Brak wartosci dla klucza: ${[...new Set(missing)].join(", ")}`);
  const key = rendered.replace(/[^0-9A-Za-z_.-]+/g, "-").replace(/^[.-]+|[.-]+$/g, "");
  if (!key) throw new Error("Nie mozna zbudowac klucza obiektu Pimcore.");
  return key.slice(0, 190);
}


async function submitPimcoreWriteTest() {
  if (!pimcoreTestForm.reportValidity()) return;
  const cleanup = pimcoreTestModal.querySelector('[name="pimcore_cleanup_policy"]:checked')?.value || "";
  if (!cleanup) throw new Error("Wybierz, czy obiekt ma zostac usuniety po tescie.");
  const values = collectPimcoreTestValues();
  const target = state.settings?.pimcore || {};
  const objectKey = pimcoreTestObjectKey(target.object_key_template, values);
  if (!window.confirm(`Wyslac obiekt do ${target.base_url}, klasa ${target.class_name}, parent ${target.parent_id}, klucz ${objectKey}, tryb ${cleanup}?`)) return;
  pimcoreTestSubmitButton.disabled = true;
  pimcoreTestClearButton.disabled = true;
  clearPimcoreLiveLog();
  const payload = await requestJson("/api/settings/pimcore/test-create-runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ values, cleanup_policy: cleanup }),
  });
  state.pimcoreTestOperation = {
    operationId: payload.operation.operation_id,
    lastSequence: 0,
    active: true,
  };
  await pollPimcoreTestOperation();
}


async function pollPimcoreTestOperation() {
  const tracked = state.pimcoreTestOperation;
  if (!tracked?.active) return;
  try {
    const params = new URLSearchParams({ after_sequence: String(tracked.lastSequence || 0) });
    const payload = await requestJson(
      `/api/settings/pimcore/test-create-runs/${encodeURIComponent(tracked.operationId)}?${params.toString()}`
    );
    appendPimcoreLiveEvents(payload.events || []);
    for (const event of payload.events || []) tracked.lastSequence = Math.max(tracked.lastSequence, Number(event.sequence || 0));
    pimcoreTestElapsed.textContent = formatDuration(payload.total_ms || 0);
    if (["completed", "partial", "failed"].includes(payload.status)) {
      tracked.active = false;
      pimcoreTestSubmitButton.disabled = false;
      pimcoreTestClearButton.disabled = false;
      pimcoreTestStatus.textContent = `Wynik: ${payload.status}. Operacja ${payload.operation_id}.`;
      return;
    }
  } catch (error) {
    appendPimcoreLiveEvents([{ sequence: tracked.lastSequence, severity: "warning", stage: "poll", message: `Utrata polaczenia z logiem: ${error.message}` }]);
  }
  window.setTimeout(pollPimcoreTestOperation, 500);
}
```

The two helpers append one stable row per event and preserve scroll position unless the user was already at the bottom.

- [ ] **Step 6: Implement explicit clear, close, and history behavior**

```javascript
pimcoreTestSubmitButton.addEventListener("click", () => {
  submitPimcoreWriteTest().catch((error) => {
    pimcoreTestStatus.textContent = error.message;
    pimcoreTestSubmitButton.disabled = false;
    pimcoreTestClearButton.disabled = false;
  });
});

pimcoreTestClearButton.addEventListener("click", () => {
  if (state.pimcoreTestOperation?.active) return;
  pimcoreTestForm.reset();
  pimcoreTestModal.querySelectorAll('[name="pimcore_cleanup_policy"]').forEach((item) => {
    item.checked = false;
  });
  clearPimcoreLiveLog();
});

pimcoreTestCloseButton.addEventListener("click", () => {
  pimcoreTestModal.classList.remove("active");
});

pimcoreHistoryCloseButton.addEventListener("click", () => {
  pimcoreHistoryModal.classList.remove("active");
});


function renderPimcoreHistory(items) {
  pimcoreHistoryOutput.textContent = "";
  pimcoreHistoryOutput.className = items.length ? "history-output" : "history-output empty-state";
  if (!items.length) {
    pimcoreHistoryOutput.textContent = "Brak operacji Pimcore dla wybranego filtra.";
    return;
  }
  for (const item of items) {
    const row = document.createElement("div");
    const toggle = document.createElement("button");
    const title = document.createElement("strong");
    const meta = document.createElement("span");
    const details = document.createElement("div");
    row.className = "pimcore-history-row";
    toggle.type = "button";
    toggle.className = "history-summary-row";
    title.textContent = `${item.operation_type || "operacja"} | ${item.status || "unknown"} | ${item.operation_id || ""}`;
    const resultPayload = item.result?.payload || {};
    meta.textContent = [
      item.started_at ? new Date(Number(item.started_at) * 1000).toLocaleString() : "",
      item.username,
      `${Number(item.total_ms || 0)} ms`,
      `klasa ${resultPayload.className || "brak"}`,
      `parent ${resultPayload.parentId || "brak"}`,
      `obiekt ${item.result?.object_id || item.result?.object?.id || "brak"}`,
      item.result?.object_path || item.result?.object?.path || "",
    ].filter(Boolean).join(" | ");
    details.className = "pimcore-history-event-details";
    details.hidden = true;
    for (const event of item.events || []) {
      const line = document.createElement("div");
      line.textContent = [
        `${event.sequence}. ${event.stage}: ${event.message}`,
        event.method,
        event.endpoint,
        event.status_code ? `HTTP ${event.status_code}` : "",
        `od startu ${Number(event.elapsed_ms || 0)} ms`,
        event.stage_elapsed_ms !== undefined ? `etap ${Number(event.stage_elapsed_ms || 0)} ms` : "",
        event.response_excerpt,
        event.suggested_fix,
      ].filter(Boolean).join(" | ");
      details.appendChild(line);
    }
    toggle.addEventListener("click", () => {
      details.hidden = !details.hidden;
    });
    toggle.append(title, meta);
    row.append(toggle, details);
    pimcoreHistoryOutput.appendChild(row);
  }
}


async function loadPimcoreHistory() {
  const data = new FormData(pimcoreHistoryFilters);
  const params = new URLSearchParams();
  for (const key of ["operation_type", "result", "user", "query"]) {
    const value = String(data.get(key) || "").trim();
    if (value) params.set(key, value);
  }
  const from = String(data.get("date_from") || "");
  const to = String(data.get("date_to") || "");
  if (from) params.set("date_from", String(new Date(`${from}T00:00:00`).getTime() / 1000));
  if (to) params.set("date_to", String(new Date(`${to}T23:59:59`).getTime() / 1000));
  const payload = await requestJson(`/api/settings/pimcore/operations?${params.toString()}`);
  renderPimcoreHistory(payload.items || []);
}


async function openPimcoreHistory() {
  pimcoreHistoryModal.classList.add("active");
  await loadPimcoreHistory();
}

pimcoreHistoryFilters.addEventListener("submit", (event) => {
  event.preventDefault();
  loadPimcoreHistory().catch((error) => {
    pimcoreHistoryOutput.className = "history-output empty-state";
    pimcoreHistoryOutput.textContent = error.message;
  });
});
```

The submit handler never resets the form and never removes `active`. History filtering covers type, result, user, query, and date range; clicking a row expands its complete numbered events without another backend call.

- [ ] **Step 7: Add responsive two-pane and log styles**

Use:

```css
.pimcore-test-layout {
  display: grid;
  grid-template-columns: minmax(320px, 1fr) minmax(380px, 1.1fr);
  min-height: 0;
  gap: 16px;
}

.pimcore-test-fields,
.pimcore-live-log {
  min-width: 0;
  max-height: min(68vh, 760px);
  overflow: auto;
}

.pimcore-live-log {
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
}

@media (max-width: 900px) {
  .pimcore-test-layout {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 8: Run UI and backend operation tests**

Run: `pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py tests/test_pimcore_operations.py tests/test_pimcore_web.py -v`

Expected: PASS with zero failures.

- [ ] **Step 9: Commit live test UI and audit history**

```bash
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py tests/test_source_integrity.py
git commit -m "feat: add pimcore live write test ui"
```

### Task 8: Runtime EAN Lookup And Product Creation Backend

**Files:**
- Modify: `picorgftp_sql/services/pimcore_service.py`
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/app.py`
- Modify: `tests/test_pimcore_service.py`
- Modify: `tests/test_pimcore_web.py`

- [ ] **Step 1: Write failing duplicate lookup and create tests**

```python
# tests/test_pimcore_service.py
from picorgftp_sql.services.pimcore_service import create_product, find_product_by_ean


class ProductClient:
    def __init__(self, existing=None):
        self.existing = existing or []
        self.created = []

    def object_list(self, class_name, condition, limit=2):
        return {"data": self.existing}

    def create_object(self, payload):
        self.created.append(payload)
        return {"data": {"id": 91}}

    def object_by_id(self, object_id):
        return {"data": {"id": object_id, "key": "ABC-1", "fullPath": "/Produkty/ABC-1"}}


PRODUCT_CONFIG = {
    "enabled": True,
    "class_name": "Product",
    "parent_id": "123",
    "published": True,
    "object_key_template": "{SKU}",
    "existence_fields": ["EAN", "Towar_powiazany_z_SKU"],
    "field_mappings": [
        {"source": "SKU", "pimcore_field": "SKU", "type": "input", "required": True, "parser": "text"},
        {"source": "EAN", "pimcore_field": "EAN", "type": "input", "required": True, "parser": "text"},
    ],
}


def test_find_product_by_ean_returns_normalized_identity():
    client = ProductClient(existing=[{"id": 51, "key": "ABC", "fullPath": "/Produkty/ABC"}])
    result = find_product_by_ean(PRODUCT_CONFIG, "5904804578169", client=client)
    assert result == {"id": 51, "key": "ABC", "path": "/Produkty/ABC"}


def test_create_product_rechecks_duplicate_before_post():
    client = ProductClient(existing=[{"id": 51, "key": "ABC", "fullPath": "/Produkty/ABC"}])
    result = create_product(
        PRODUCT_CONFIG,
        {"SKU": "ABC-1", "EAN": "5904804578169"},
        client=client,
        emit=lambda *args, **kwargs: None,
    )
    assert result["duplicate"] is True
    assert result["object"]["id"] == 51
    assert client.created == []


def test_create_product_posts_when_ean_is_missing():
    client = ProductClient()
    result = create_product(
        PRODUCT_CONFIG,
        {"SKU": "ABC-1", "EAN": "5904804578169"},
        client=client,
        emit=lambda *args, **kwargs: None,
    )
    assert result["created"] is True
    assert result["object"] == {"id": 91, "key": "ABC-1", "path": "/Produkty/ABC-1"}
    assert client.created[0]["published"] is True
```

- [ ] **Step 2: Run focused service tests and verify missing functions**

Run: `pytest tests/test_pimcore_service.py -v`

Expected: FAIL during import because `find_product_by_ean` and `create_product` are undefined.

- [ ] **Step 3: Implement tolerant object-list normalization and duplicate-safe create**

```python
# Append to picorgftp_sql/services/pimcore_service.py
def normalize_object_identity(record: object) -> dict[str, object]:
    source = record if isinstance(record, dict) else {}
    try:
        object_id = int(source.get("id"))
    except (TypeError, ValueError):
        object_id = 0
    return {
        "id": object_id,
        "key": str(source.get("key") or ""),
        "path": str(source.get("fullPath") or source.get("path") or ""),
    }


def find_product_by_ean(
    settings: object,
    ean: object,
    *,
    client: PimcoreClient | None = None,
) -> dict[str, object] | None:
    config = normalize_pimcore_settings(settings)
    api = client or PimcoreClient(config)
    payload = api.object_list(
        config["class_name"],
        build_ean_condition(ean, config["existence_fields"]),
        limit=2,
    )
    records = _list_records(payload, ("data", "objects", "items"))
    return normalize_object_identity(records[0]) if records else None


def create_product(
    settings: object,
    values: dict[str, object],
    *,
    client: PimcoreClient | None = None,
    emit: Callable[..., None],
) -> dict[str, object]:
    config = normalize_pimcore_settings(settings)
    api = client or PimcoreClient(config)
    ean = validate_ean(values.get("EAN"))
    stage_started = time.perf_counter()
    duplicate = find_product_by_ean(config, ean, client=api)
    if duplicate:
        emit("duplicate_check", "warning", "EAN juz istnieje w Pimcore.", object_id=duplicate["id"], stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
        return {"created": False, "duplicate": True, "object": duplicate}
    emit("duplicate_check", "success", "EAN nie istnieje; mozna utworzyc produkt.", stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
    stage_started = time.perf_counter()
    payload = build_create_payload(config, values, published=config["published"], use_defaults=True)
    emit("payload", "success", "Zbudowano dane produktu.", stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
    stage_started = time.perf_counter()
    try:
        response = api.create_object(payload)
        object_id = extract_object_id(response)
    except PimcoreApiError as exc:
        emit("create", "error", str(exc), method="POST", endpoint="/webservice/rest/object", error=exc.as_dict(), stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
        raise
    except ValueError as exc:
        emit("create", "error", str(exc), method="POST", endpoint="/webservice/rest/object", response_excerpt=_response_excerpt(json.dumps(response, ensure_ascii=True)), stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
        raise
    emit("create", "success", "Utworzono produkt Pimcore.", object_id=object_id, method="POST", endpoint="/webservice/rest/object", status_code=getattr(api, "last_response", {}).get("status_code"), response_excerpt=_response_excerpt(json.dumps(response, ensure_ascii=True)), stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
    stage_started = time.perf_counter()
    fetched = api.object_by_id(object_id)
    identity = normalize_object_identity(
        fetched.get("data") if isinstance(fetched.get("data"), dict) else fetched
    )
    if not identity["id"]:
        identity["id"] = object_id
    emit("verify", "success", "Potwierdzono produkt w Pimcore.", object_id=object_id, endpoint=f"/webservice/rest/object/id/{object_id}", status_code=getattr(api, "last_response", {}).get("status_code"), response_excerpt=_response_excerpt(json.dumps(fetched, ensure_ascii=True)), stage_elapsed_ms=int((time.perf_counter() - stage_started) * 1000))
    return {
        "created": True,
        "duplicate": False,
        "object": identity,
        "payload": payload,
    }
```

- [ ] **Step 4: Write failing web adapter and route tests**

```python
# tests/test_pimcore_web.py
def test_product_status_returns_disabled_without_network_call():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"]["enabled"] = False
    with patch.object(web_data.config, "CONFIG", cfg):
        assert web_data.find_pimcore_product_by_ean("5904804578169") == {
            "enabled": False,
            "exists": False,
            "object": None,
            "form_schema": [],
        }


def test_runtime_create_route_allows_logged_in_user_and_returns_created_object():
    client = TestClient(web_app.app)
    expected = {"created": True, "duplicate": False, "object": {"id": 91, "key": "ABC", "path": "/Produkty/ABC"}}
    with (
        patch.object(web_app, "_require_user", return_value="operator"),
        patch.object(web_app, "create_pimcore_product", return_value=expected) as create,
    ):
        response = client.post(
            "/api/pimcore/products",
            json={"values": {"SKU": "ABC", "EAN": "5904804578169"}},
        )
    assert response.status_code == 200
    assert response.json() == expected
    create.assert_called_once_with({"SKU": "ABC", "EAN": "5904804578169"}, "operator")
```

- [ ] **Step 5: Add web-data wrappers with complete manual audit timing**

```python
# picorgftp_sql/web_data.py
import secrets

from .services.pimcore_service import create_product, find_product_by_ean


def _pimcore_runtime_form_schema(settings: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            "source": item["source"],
            "label": item["label"],
            "required": item["required"],
            "default": item["default"],
            "parser": item["parser"],
        }
        for item in settings["field_mappings"]
    ]


def find_pimcore_product_by_ean(ean: object) -> dict[str, object]:
    settings = normalize_pimcore_settings(config.CONFIG.get(PIMCORE_SETTINGS_KEY))
    if not settings["enabled"]:
        return {"enabled": False, "exists": False, "object": None, "form_schema": []}
    found = find_product_by_ean(settings, ean)
    return {
        "enabled": True,
        "exists": bool(found),
        "object": found,
        "form_schema": _pimcore_runtime_form_schema(settings),
    }


def create_pimcore_product(values: object, username: str) -> dict[str, object]:
    submitted = dict(values) if isinstance(values, dict) else {}
    settings = normalize_pimcore_settings(config.CONFIG.get(PIMCORE_SETTINGS_KEY))
    if not settings["enabled"]:
        raise ValueError("Integracja Pimcore jest wylaczona.")
    operation_id = secrets.token_hex(12)
    started = time.time()
    events: list[dict[str, object]] = []
    result: dict[str, object] = {}

    def emit(stage: str, severity: str, message: str, **details: object) -> None:
        event = {
            "sequence": len(events) + 1,
            "timestamp": time.time(),
            "elapsed_ms": int(max(0, time.time() - started) * 1000),
            "stage": stage,
            "severity": severity,
            "message": message,
        }
        event.update(details)
        events.append(event)

    try:
        result = create_product(settings, submitted, emit=emit)
        status = "duplicate" if result.get("duplicate") else "completed"
        return result
    except Exception as exc:
        status = "failed"
        emit("finish", "error", str(exc) or exc.__class__.__name__)
        raise
    finally:
        finished = time.time()
        report = redact_pimcore_log_value({
            "operation_id": operation_id,
            "operation_type": "manual",
            "username": username,
            "values": submitted,
            "status": status,
            "started_at": started,
            "finished_at": finished,
            "total_ms": int(max(0, finished - started) * 1000),
            "events": events,
            "result": result,
        })
        _persist_pimcore_operation(report)
```

- [ ] **Step 6: Add authenticated status and create routes with structured errors**

```python
# picorgftp_sql/web/app.py
from ..services.pimcore_service import PimcoreApiError


@app.get("/api/pimcore/product-status")
async def pimcore_product_status_api(request: Request, ean: str) -> JSONResponse:
    username = _require_user(request)
    try:
        result = await run_in_threadpool(find_pimcore_product_by_ean, ean)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PimcoreApiError as exc:
        _write_web_event(level="warning", event="PIMCORE_PRODUCT_LOOKUP", username=username, message=str(exc), details={"ean": ean, "error": exc.as_dict()})
        return JSONResponse(
            {"enabled": True, "available": False, "exists": False, "object": None, "error": exc.as_dict()}
        )
    result["available"] = True
    _write_web_event(level="info", event="PIMCORE_PRODUCT_LOOKUP", username=username, message=f"EAN {ean}: {'istnieje' if result.get('exists') else 'brak'}.", details={"ean": ean, "exists": bool(result.get("exists")), "object": result.get("object")})
    return JSONResponse(result)


@app.post("/api/pimcore/products")
async def pimcore_product_create_api(request: Request) -> JSONResponse:
    username = _require_user(request)
    payload = await request.json()
    values = payload.get("values") if isinstance(payload, dict) else None
    if not isinstance(values, dict):
        raise HTTPException(status_code=400, detail="Brak danych produktu Pimcore.")
    try:
        result = await run_in_threadpool(create_pimcore_product, values, username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PimcoreApiError as exc:
        raise HTTPException(status_code=502, detail=exc.as_dict()) from exc
    return JSONResponse(result)
```

- [ ] **Step 7: Run runtime service and web tests**

Run: `pytest tests/test_pimcore_service.py tests/test_pimcore_web.py -v`

Expected: PASS with zero failures.

- [ ] **Step 8: Commit runtime backend integration**

```bash
git add picorgftp_sql/services/pimcore_service.py picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_pimcore_service.py tests/test_pimcore_web.py
git commit -m "feat: create missing pimcore products"
```

### Task 9: Main EAN Workflow Prompt And Runtime Create Modal

**Files:**
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_web_ui_integrity.py`
- Modify: `tests/test_source_integrity.py`

- [ ] **Step 1: Write failing runtime UI tests**

```python
# tests/test_web_ui_integrity.py
def test_runtime_pimcore_prompt_and_create_modals_exist(self) -> None:
    html = _parse(INDEX_HTML)
    self.assertIn("pimcoreMissingModal", html.ids)
    self.assertIn("pimcoreCreateModal", html.ids)
    self.assertIn("pimcoreCreateForm", html.ids)
    self.assertIn("pimcoreMissingCreateButton", html.ids)


# tests/test_source_integrity.py
def test_ean_input_debounces_pimcore_lookup_and_rechecks_on_create(self) -> None:
    source = APP_JS.read_text(encoding="utf-8")
    self.assertIn("function schedulePimcoreStatusLookup()", source)
    self.assertIn("/api/pimcore/product-status", source)
    self.assertIn('requestJson("/api/pimcore/products"', source)
    self.assertIn("500", source)
    self.assertIn("pimcoreCreateEan.readOnly = true", source)
```

- [ ] **Step 2: Run UI tests and verify failure**

Run: `pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py -v`

Expected: FAIL because runtime Pimcore modals and handlers are absent.

- [ ] **Step 3: Add the missing-product prompt and mapped create modal**

```html
<!-- picorgftp_sql/web/static/index.html -->
<div id="pimcoreMissingModal" class="modal-view">
  <section class="modal-panel compact-modal">
    <div class="section-heading">
      <h1>Brak produktu w Pimcore</h1>
      <button id="pimcoreMissingCancelButton" type="button" class="ghost-button modal-close">Anuluj</button>
    </div>
    <p id="pimcoreMissingMessage"></p>
    <div class="heading-actions">
      <button id="pimcoreMissingCreateButton" type="button">Dodaj produkt</button>
      <button id="pimcoreMissingContinueButton" type="button" class="secondary-button">Kontynuuj bez dodawania</button>
    </div>
  </section>
</div>

<div id="pimcoreCreateModal" class="modal-view">
  <section class="manager-panel pimcore-create-panel">
    <div class="section-heading">
      <h1>Nowy produkt Pimcore</h1>
      <button id="pimcoreCreateCancelButton" type="button" class="ghost-button modal-close">Anuluj</button>
    </div>
    <form id="pimcoreCreateForm" class="pimcore-runtime-fields"></form>
    <div class="heading-actions">
      <button id="pimcoreCreateSubmitButton" type="submit" form="pimcoreCreateForm">Zapisz</button>
      <span id="pimcoreCreateStatus" role="status"></span>
    </div>
  </section>
</div>
```

- [ ] **Step 4: Debounce valid EAN-13 lookups and ignore stale responses**

Add state fields `pimcoreLookupTimer`, `pimcoreLookupRequestId`, `pimcoreLastCheckedEan`, `pimcoreMissingEan`, and `pimcoreCreateSchema`. Then implement:

```javascript
Object.assign(state, {
  pimcoreLookupTimer: 0,
  pimcoreLookupRequestId: 0,
  pimcoreLastCheckedEan: "",
  pimcoreMissingEan: "",
  pimcoreCreateSchema: [],
});

const pimcoreMissingModal = document.querySelector("#pimcoreMissingModal");
const pimcoreMissingMessage = document.querySelector("#pimcoreMissingMessage");
const pimcoreMissingCreateButton = document.querySelector("#pimcoreMissingCreateButton");
const pimcoreMissingContinueButton = document.querySelector("#pimcoreMissingContinueButton");
const pimcoreMissingCancelButton = document.querySelector("#pimcoreMissingCancelButton");
const pimcoreCreateModal = document.querySelector("#pimcoreCreateModal");
const pimcoreCreateForm = document.querySelector("#pimcoreCreateForm");
const pimcoreCreateSubmitButton = document.querySelector("#pimcoreCreateSubmitButton");
const pimcoreCreateCancelButton = document.querySelector("#pimcoreCreateCancelButton");
const pimcoreCreateStatus = document.querySelector("#pimcoreCreateStatus");


function schedulePimcoreStatusLookup() {
  window.clearTimeout(state.pimcoreLookupTimer);
  const ean = productForm.elements.ean.value.trim();
  if (!/^\d{13}$/.test(ean) || ean === state.pimcoreLastCheckedEan) return;
  state.pimcoreLookupTimer = window.setTimeout(() => {
    checkPimcoreProductStatus(ean).catch((error) => {
      formStatus.textContent = `Nie mozna sprawdzic Pimcore: ${error.message}. Mozesz kontynuowac prace.`;
    });
  }, 500);
}


async function checkPimcoreProductStatus(ean) {
  const requestId = ++state.pimcoreLookupRequestId;
  const payload = await requestJson(`/api/pimcore/product-status?ean=${encodeURIComponent(ean)}`);
  if (requestId !== state.pimcoreLookupRequestId || productForm.elements.ean.value.trim() !== ean) return;
  state.pimcoreLastCheckedEan = ean;
  if (!payload.enabled || payload.exists) return;
  if (payload.available === false) {
    formStatus.textContent = `Pimcore niedostepny: ${payload.error?.message || "blad polaczenia"}`;
    return;
  }
  state.pimcoreCreateSchema = Array.isArray(payload.form_schema) ? payload.form_schema : [];
  state.pimcoreMissingEan = ean;
  pimcoreMissingMessage.textContent = `EAN ${ean} nie istnieje w Pimcore. Czy dodac produkt?`;
  pimcoreMissingModal.classList.add("active");
}

productForm.elements.ean.addEventListener("input", schedulePimcoreStatusLookup);
```

- [ ] **Step 5: Render mapped runtime fields with locked EAN and defaults**

```javascript
function openPimcoreCreateModal(ean) {
  pimcoreCreateForm.textContent = "";
  for (const mapping of state.pimcoreCreateSchema || []) {
    const label = document.createElement("label");
    const title = document.createElement("span");
    const input = document.createElement("input");
    title.textContent = `${mapping.label || mapping.source}${mapping.required ? " *" : ""}`;
    input.name = mapping.source;
    input.value = mapping.source === "EAN" ? ean : mapping.default || "";
    input.required = Boolean(mapping.required);
    if (mapping.source === "EAN") {
      input.readOnly = true;
      input.id = "pimcoreCreateEan";
    }
    label.append(title, input);
    pimcoreCreateForm.appendChild(label);
  }
  const pimcoreCreateEan = pimcoreCreateForm.querySelector("#pimcoreCreateEan");
  if (pimcoreCreateEan) pimcoreCreateEan.readOnly = true;
  pimcoreMissingModal.classList.remove("active");
  pimcoreCreateModal.classList.add("active");
}
```

- [ ] **Step 6: Submit without blocking the existing photo workflow**

```javascript
pimcoreCreateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  pimcoreCreateSubmitButton.disabled = true;
  pimcoreCreateStatus.textContent = "Zapisywanie w Pimcore...";
  try {
    const values = Object.fromEntries(new FormData(pimcoreCreateForm).entries());
    const payload = await requestJson("/api/pimcore/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
      timeoutMs: 120000,
    });
    const object = payload.object || {};
    pimcoreCreateModal.classList.remove("active");
    formStatus.textContent = payload.duplicate
      ? `EAN juz istnieje w Pimcore: ${object.path || object.id}.`
      : `Utworzono produkt Pimcore: ${object.path || object.id}. Mozesz kontynuowac dodawanie zdjec.`;
  } catch (error) {
    pimcoreCreateStatus.textContent = error.message;
  } finally {
    pimcoreCreateSubmitButton.disabled = false;
  }
});

pimcoreMissingCreateButton.addEventListener("click", () => {
  openPimcoreCreateModal(state.pimcoreMissingEan);
});

pimcoreMissingContinueButton.addEventListener("click", () => {
  pimcoreMissingModal.classList.remove("active");
});

pimcoreMissingCancelButton.addEventListener("click", () => {
  pimcoreMissingModal.classList.remove("active");
});

pimcoreCreateCancelButton.addEventListener("click", () => {
  pimcoreCreateModal.classList.remove("active");
});
```

Add these lines inside the existing `resetCurrentDraft()` after the product form reset so a future identical EAN is checked again:

```javascript
window.clearTimeout(state.pimcoreLookupTimer);
state.pimcoreLookupRequestId += 1;
state.pimcoreLastCheckedEan = "";
state.pimcoreMissingEan = "";
state.pimcoreCreateSchema = [];
pimcoreMissingModal.classList.remove("active");
pimcoreCreateModal.classList.remove("active");
```

- [ ] **Step 7: Add compact responsive runtime modal styles**

```css
.pimcore-create-panel {
  width: min(960px, calc(100vw - 32px));
}

.pimcore-runtime-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  max-height: min(68vh, 720px);
  overflow: auto;
}

.pimcore-runtime-fields label {
  display: grid;
  gap: 6px;
  min-width: 0;
}

@media (max-width: 700px) {
  .pimcore-runtime-fields {
    grid-template-columns: 1fr;
  }
}
```

Use existing input styles and do not add cards inside these modal panels.

- [ ] **Step 8: Run runtime UI and API tests**

Run: `pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py tests/test_pimcore_web.py tests/test_pimcore_service.py -v`

Expected: PASS with zero failures.

- [ ] **Step 9: Commit the EAN workflow UI**

```bash
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py tests/test_source_integrity.py
git commit -m "feat: prompt to create missing pimcore products"
```

### Task 10: Documentation, Full Regression, And Manual Verification

**Files:**
- Modify: `README.md`
- Verify: all changed source and test files

- [ ] **Step 1: Document setup and operational safety**

Add a `Pimcore 6.6 REST` section to `README.md` containing these concrete requirements:

```markdown
## Pimcore 6.6 REST

1. In Pimcore enable `Settings > System Settings > Web Service API`.
2. Create or select a dedicated Pimcore user and copy its API key.
3. Grant that user read access to server info, classes, the Product class and the target `Produkty` folder.
4. Grant create/read/delete object permissions when the settings write test will use `Usun po tescie`.
5. In PicOrgFTP-SQL open `Ustawienia > Pimcore`, set the base URL, API key, class name and parent ID, then map CSV headers to Pimcore fields.
6. Run `Sprawdz konfiguracje`. Correct every error row before enabling runtime creation.
7. Run `Testowo dodaj obiekt`, enter isolated test data, choose the cleanup policy and inspect the live log.

The API key is stored encrypted and is never returned by the normal settings endpoint or written to Pimcore operation logs. A test object left in Pimcore is unpublished. If cleanup fails, use the object ID/key/path from the operation report to remove it manually.
```

- [ ] **Step 2: Run formatting and placeholder checks**

Run: `git diff --check`

Expected: exit code 0 with no whitespace errors.

Run: `rg -n "T[B]D|T[O]DO|F[I]XME|X-API-Key.*api_key.*query" picorgftp_sql tests README.md`

Expected: no new Pimcore implementation placeholders and no query-string API-key usage.

- [ ] **Step 3: Run focused Pimcore regression tests**

Run: `pytest tests/test_pimcore_config.py tests/test_pimcore_service.py tests/test_pimcore_operations.py tests/test_pimcore_web.py tests/test_web_ui_integrity.py tests/test_source_integrity.py -v`

Expected: PASS with zero failures.

- [ ] **Step 4: Run the complete repository test suite**

Run: `pytest -q`

Expected: exit code 0 and zero failed tests.

- [ ] **Step 5: Start the local web server and verify the static experience**

Run: `python -m uvicorn picorgftp_sql.web.app:app --host 127.0.0.1 --port 8000`

Expected: Uvicorn reports the application running at `http://127.0.0.1:8000`.

In a browser at `http://127.0.0.1:8000` verify desktop and narrow mobile widths:

1. The Pimcore settings tab has no overlapping labels, controls, or mapping rows.
2. The test modal is two columns on desktop and one column on mobile.
3. All mapped test inputs start empty.
4. `Wyslij` leaves the modal open and values intact.
5. `Wyczysc formularz` clears fields and current visible logs only.
6. Only the close button/icon dismisses the test modal.
7. Live events append in order and keep endpoint, status, and timing readable.

- [ ] **Step 6: Run the real read-only Pimcore test when network access and credentials are available**

Use the saved URL `http://10.10.0.5`, API key, exact class name, exact `Produkty` parent ID, and actual field mappings. Confirm every checklist row is `ok` except `create_permission`, which remains informational until the write test.

- [ ] **Step 7: Run both real write-test cleanup policies with isolated values**

First choose `Usun po tescie` and confirm create, fetch, value verification, delete, final status, object ID, and stage timings. Then choose `Pozostaw w Pimcore`, confirm the retained object is unpublished, inspect it in Pimcore, and remove it manually after verification.

- [ ] **Step 8: Verify the main EAN workflow against Pimcore**

Enter an existing EAN and confirm no prompt appears. Enter a missing EAN, fill mapped fields, save, confirm the returned Pimcore ID/path, then continue the existing image upload and SQL URL-update workflow.

- [ ] **Step 9: Commit documentation**

```bash
git add README.md
git commit -m "docs: document pimcore integration"
```

- [ ] **Step 10: Inspect final branch state**

Run: `git status --short --branch`

Expected: clean `dev` worktree with implementation commits ahead of or synchronized with `origin/dev`.

Run: `git log --oneline --decorate -10`

Expected: the Pimcore commits from Tasks 1-10 appear in task order.
