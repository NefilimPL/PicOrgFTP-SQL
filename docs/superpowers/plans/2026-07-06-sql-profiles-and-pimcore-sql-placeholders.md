# SQL Profiles And Pimcore SQL Placeholders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SQL connection profiles, SQL-backed Pimcore field mappings, SQLite Pimcore submission storage/export, and runtime recalculation difference UI.

**Architecture:** Keep existing slot SQL behavior on the current default SQL settings and add a profile layer for Pimcore SQL mappings. Backend modules own normalization, validation, connection selection, SQL execution, rendering, redaction, persistence, and export; browser code only edits settings and displays calculation state returned by the backend.

**Tech Stack:** Python 3, FastAPI, SQLite, MySQL connector, pyodbc, pytest, vanilla JavaScript, CSS.

---

## File Structure

- Create `picorgftp_sql/sql_profiles.py`: normalize SQL profiles, derive the default slot-owned profile from existing config, expose public redacted profile views, and resolve connection dictionaries.
- Create `picorgftp_sql/services/pimcore_sql_service.py`: validate read-only SQL, bind supported placeholders, execute one-row SQL values through selected profiles, and return calculated values with warnings.
- Modify `picorgftp_sql/common.py`: add `SQL_PROFILES_KEY = "sql_profiles"` and default config entry.
- Modify `picorgftp_sql/config.py`: load/save `sql_profiles`, encrypt profile passwords, preserve submitted profile secrets, and keep default SQL keys intact for slots.
- Modify `picorgftp_sql/pimcore_config.py`: normalize `sql_query` and `sql_profile_id`; validate SQL mode with profile context; skip template parsing when `value_template` is `SQL`.
- Modify `picorgftp_sql/web_data.py`: expose profile settings, save profile settings, include SQL metadata in Pimcore schemas, render SQL-mode mappings, persist Pimcore submissions, and export SQLite submission records.
- Modify `picorgftp_sql/sqlite_store.py`: create `pimcore_submissions`, add append/query methods, and keep schema migration idempotent.
- Modify `picorgftp_sql/web/app.py`: add SQL profile diagnostic route, extend render routes, add Pimcore submission export route, and pass new data through existing endpoints.
- Modify `picorgftp_sql/web/static/app.js`: render SQL profile management, SQL-mode mapping controls, calculated difference UI, apply-calculated buttons, and export actions.
- Modify `picorgftp_sql/web/static/app.css`: style profile rows/cards and yellow calculated-difference state.
- Modify `picorgftp_sql/web/static/index.html`: bump static asset query strings.
- Add and modify tests:
  - `tests/test_sql_profiles.py`
  - `tests/test_pimcore_sql_service.py`
  - `tests/test_config.py`
  - `tests/test_pimcore_config.py`
  - `tests/test_pimcore_web.py`
  - `tests/test_sqlite_store.py`
  - `tests/test_web_data_users.py`
  - `tests/test_web_ui_integrity.py`
  - `tests/test_source_integrity.py`

## Task 1: SQL Profile Model And Config Persistence

**Files:**
- Create: `picorgftp_sql/sql_profiles.py`
- Modify: `picorgftp_sql/common.py`
- Modify: `picorgftp_sql/config.py`
- Test: `tests/test_sql_profiles.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing profile normalization tests**

Create `tests/test_sql_profiles.py`:

```python
from copy import deepcopy

from picorgftp_sql import common
from picorgftp_sql.sql_profiles import (
    DEFAULT_SQL_PROFILE_ID,
    SQL_PROFILES_KEY,
    normalize_sql_profiles,
    public_sql_profiles,
    resolve_sql_profile,
)


def test_default_profile_is_derived_from_existing_sql_config():
    cfg = deepcopy(common.DEFAULT_CONFIG)
    cfg[common.p] = common.K
    cfg[common.K][common.c] = "mysql.local"
    cfg[common.K][common.b] = "catalog"
    cfg[common.K][common.N] = "writer"
    cfg[common.K][common.M] = "secret"

    profiles = normalize_sql_profiles(cfg)
    default = profiles[0]

    assert default["id"] == DEFAULT_SQL_PROFILE_ID
    assert default["label"] == "Domyslny"
    assert default["usage"] == "slots"
    assert default["locked"] is True
    assert default["type"] == "mysql"
    assert default["host"] == "mysql.local"
    assert default["database"] == "catalog"
    assert default["user"] == "writer"
    assert default["password"] == "secret"


def test_additional_profiles_are_cleaned_and_public_view_hides_passwords():
    cfg = deepcopy(common.DEFAULT_CONFIG)
    cfg[SQL_PROFILES_KEY] = [
        {
            "id": " Stock DB ",
            "label": " Stock ",
            "type": "mssql",
            "host": "sql.local",
            "database": "erp",
            "user": "reader",
            "password": "secret",
            "enabled": True,
        },
        {"id": "default", "label": "bad", "host": "ignored"},
        {"id": "", "label": "empty"},
    ]

    profiles = normalize_sql_profiles(cfg)
    stock = resolve_sql_profile(profiles, "stock-db")
    public = public_sql_profiles(profiles)

    assert stock["usage"] == "pimcore_sql"
    assert stock["locked"] is False
    assert stock["enabled"] is True
    assert public[1]["id"] == "stock-db"
    assert public[1]["password_set"] is True
    assert "password" not in public[1]
```

Add to `tests/test_config.py`:

```python
    def test_save_config_encrypts_additional_sql_profile_passwords(self) -> None:
        payload = deepcopy(common.DEFAULT_CONFIG)
        payload["sql_profiles"] = [
            {
                "id": "stock",
                "label": "Stock",
                "type": "mysql",
                "host": "mysql.local",
                "database": "catalog",
                "user": "reader",
                "password": "profile-secret",
                "enabled": True,
            }
        ]

        with (
            patch.object(config, "_active_sqlite_store", return_value=None),
            patch.object(config, "_write_json_atomic") as write_atomic,
        ):
            config.save_config(payload)

        raw_profiles = write_atomic.call_args.args[1]["sql_profiles"]
        self.assertNotEqual(raw_profiles[0]["password"], "profile-secret")
        self.assertEqual(config.decrypt(raw_profiles[0]["password"]), "profile-secret")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_sql_profiles.py tests/test_config.py::ConfigTests::test_save_config_encrypts_additional_sql_profile_passwords -q
```

Expected: FAIL because `picorgftp_sql.sql_profiles` and `sql_profiles` config persistence do not exist yet.

- [ ] **Step 3: Implement SQL profile normalization**

Create `picorgftp_sql/sql_profiles.py` with these public functions and constants:

```python
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .common import K, M, N, P, b, c, p

SQL_PROFILES_KEY = "sql_profiles"
DEFAULT_SQL_PROFILE_ID = "default"
PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _text(value: object) -> str:
    return str(value or "").strip()


def _slug(value: object) -> str:
    text = _text(value).casefold()
    text = re.sub(r"[^a-z0-9_-]+", "-", text).strip("-_")
    return text[:64]


def _db_type(value: object) -> str:
    return K if _text(value).casefold() == K else "mssql"


def default_sql_profile(config_dict: dict[str, Any]) -> dict[str, Any]:
    db_type = _db_type(config_dict.get(p, K))
    section = config_dict.get(K if db_type == K else P, {})
    if not isinstance(section, dict):
        section = {}
    return {
        "id": DEFAULT_SQL_PROFILE_ID,
        "label": "Domyslny",
        "type": db_type,
        "host": _text(section.get(c)),
        "database": _text(section.get(b)),
        "user": _text(section.get(N)),
        "password": _text(section.get(M)),
        "enabled": True,
        "usage": "slots",
        "locked": True,
    }


def normalize_additional_sql_profile(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    raw_id = _slug(raw.get("id") or raw.get("label"))
    if not raw_id or raw_id == DEFAULT_SQL_PROFILE_ID or not PROFILE_ID_RE.fullmatch(raw_id):
        return None
    label = _text(raw.get("label")) or raw_id
    profile_type = _db_type(raw.get("type", K))
    return {
        "id": raw_id,
        "label": label,
        "type": profile_type,
        "host": _text(raw.get("host") or raw.get("server")),
        "database": _text(raw.get("database")),
        "user": _text(raw.get("user")),
        "password": _text(raw.get("password")),
        "enabled": bool(raw.get("enabled", True)),
        "usage": "pimcore_sql",
        "locked": False,
    }


def normalize_sql_profiles(config_dict: object) -> list[dict[str, Any]]:
    source = config_dict if isinstance(config_dict, dict) else {}
    profiles = [default_sql_profile(source)]
    seen = {DEFAULT_SQL_PROFILE_ID}
    for raw in source.get(SQL_PROFILES_KEY, []) if isinstance(source.get(SQL_PROFILES_KEY), list) else []:
        profile = normalize_additional_sql_profile(raw)
        if not profile or profile["id"] in seen:
            continue
        profiles.append(profile)
        seen.add(profile["id"])
    return profiles


def additional_sql_profiles(config_dict: object) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in normalize_sql_profiles(config_dict)[1:]]


def resolve_sql_profile(profiles: list[dict[str, Any]], profile_id: object) -> dict[str, Any]:
    wanted = _text(profile_id) or DEFAULT_SQL_PROFILE_ID
    for profile in profiles:
        if profile.get("id") == wanted:
            return dict(profile)
    raise ValueError(f"Nie znaleziono profilu SQL: {wanted}.")


def public_sql_profiles(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for profile in profiles:
        item = {key: value for key, value in profile.items() if key != "password"}
        item["user_set"] = bool(_text(profile.get("user")))
        item["password_set"] = bool(_text(profile.get("password")))
        result.append(item)
    return result
```

- [ ] **Step 4: Wire config defaults and encrypted persistence**

Modify `picorgftp_sql/common.py` near the other config key constants:

```python
SQL_PROFILES_KEY = "sql_profiles"
```

Add after `DEFAULT_CONFIG.setdefault(PIMCORE_SETTINGS_KEY, default_pimcore_settings())`:

```python
DEFAULT_CONFIG.setdefault(SQL_PROFILES_KEY, [])
```

Modify `picorgftp_sql/config.py`:

```python
from .sql_profiles import SQL_PROFILES_KEY, additional_sql_profiles
```

In `_merge_raw_config`, after SQL available columns are normalized:

```python
    raw_profiles = raw_config.get(SQL_PROFILES_KEY, [])
    config_copy[SQL_PROFILES_KEY] = additional_sql_profiles({SQL_PROFILES_KEY: raw_profiles})
    raw_profile_by_id = {
        str(item.get("id") or ""): item
        for item in raw_profiles
        if Aq(item, dict)
    }
    for profile in config_copy[SQL_PROFILES_KEY]:
        raw_profile = raw_profile_by_id.get(profile["id"], {})
        if Aq(raw_profile, dict):
            profile["password"] = decrypt(raw_profile.get("password", encrypt(B)))
```

Add `SQL_PROFILES_KEY: config_copy.get(SQL_PROFILES_KEY, [])` to the initial payload in `load_config`.

In `save_config`, before building `payload`, compute:

```python
    sql_profiles_payload = []
    raw_profiles = raw_config.get(SQL_PROFILES_KEY, []) if Aq(raw_config.get(SQL_PROFILES_KEY), list) else []
    raw_profile_by_id = {
        str(item.get("id") or ""): item
        for item in raw_profiles
        if Aq(item, dict)
    }
    for profile in additional_sql_profiles(config):
        raw_profile = raw_profile_by_id.get(profile["id"], {})
        password = profile.get("password", B)
        if (
            preserve_secrets.get(SQL_PROFILES_KEY)
            and profile["id"] in preserve_secrets.get(SQL_PROFILES_KEY, set())
            and Aq(raw_profile, dict)
            and raw_profile.get("password") is not None
        ):
            encrypted_password = raw_profile.get("password")
        else:
            encrypted_password = encrypt(password)
        sql_profiles_payload.append({**profile, "password": encrypted_password})
```

Add to `payload`:

```python
        SQL_PROFILES_KEY: sql_profiles_payload,
```

- [ ] **Step 5: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_sql_profiles.py tests/test_config.py::ConfigTests::test_save_config_encrypts_additional_sql_profile_passwords -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add picorgftp_sql/common.py picorgftp_sql/config.py picorgftp_sql/sql_profiles.py tests/test_sql_profiles.py tests/test_config.py
git commit -m "feat: add sql profile configuration model"
```

## Task 2: SQL Value Execution Service

**Files:**
- Create: `picorgftp_sql/services/pimcore_sql_service.py`
- Test: `tests/test_pimcore_sql_service.py`

- [ ] **Step 1: Write failing SQL execution tests**

Create `tests/test_pimcore_sql_service.py`:

```python
import pytest

from picorgftp_sql.services.pimcore_sql_service import (
    SqlValueError,
    bind_sql_value_query,
    execute_sql_value_query,
    validate_sql_value_query,
)


def test_validate_sql_value_query_accepts_single_select():
    assert validate_sql_value_query("SELECT stock FROM product WHERE ean = {ean}") == ""


@pytest.mark.parametrize(
    "query",
    [
        "",
        "UPDATE product SET stock = 1",
        "SELECT stock FROM product; SELECT 1",
        "DELETE FROM product",
        "EXEC dbo.read_stock",
    ],
)
def test_validate_sql_value_query_rejects_unsafe_sql(query):
    with pytest.raises(SqlValueError):
        validate_sql_value_query(query)


def test_bind_sql_value_query_uses_mysql_parameters():
    query, params = bind_sql_value_query(
        "SELECT stock FROM product WHERE ean = {ean} AND sku = {pimcore:SKU}",
        {"ean": "5901234567890"},
        {"SKU": "ABC"},
        "mysql",
    )

    assert query == "SELECT stock FROM product WHERE ean = %s AND sku = %s"
    assert params == ("5901234567890", "ABC")


def test_bind_sql_value_query_uses_mssql_parameters_and_empty_missing_values():
    query, params = bind_sql_value_query(
        "SELECT TOP 1 stock FROM product WHERE ean = {EAN} AND model = {model}",
        {"ean": "5901234567890"},
        {},
        "mssql",
    )

    assert query == "SELECT TOP 1 stock FROM product WHERE ean = ? AND model = ?"
    assert params == ("5901234567890", "")


def test_execute_sql_value_query_returns_first_value_and_multiple_row_warning():
    class Cursor:
        def execute(self, query, params):
            self.query = query
            self.params = params

        def fetchmany(self, count):
            return [("12",), ("13",)]

        def close(self):
            return None

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            return None

    result = execute_sql_value_query(
        {"id": "stock", "type": "mysql"},
        "SELECT stock FROM product WHERE ean = {ean}",
        {"ean": "5901234567890"},
        {},
        connector=lambda profile: Connection(),
    )

    assert result.value == "12"
    assert result.warnings[0]["code"] == "multiple_rows"


def test_execute_sql_value_query_returns_empty_with_warning_when_no_row():
    class Cursor:
        def execute(self, query, params):
            return None

        def fetchmany(self, count):
            return []

        def close(self):
            return None

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            return None

    result = execute_sql_value_query(
        {"id": "stock", "type": "mysql"},
        "SELECT stock FROM product WHERE ean = {ean}",
        {"ean": "5901234567890"},
        {},
        connector=lambda profile: Connection(),
    )

    assert result.value == ""
    assert result.warnings[0]["code"] == "no_rows"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_pimcore_sql_service.py -q
```

Expected: FAIL because `picorgftp_sql.services.pimcore_sql_service` does not exist.

- [ ] **Step 3: Implement SQL value service**

Create `picorgftp_sql/services/pimcore_sql_service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Callable, Sequence

from ..common import E, K, M, N, b, c, mysql, pyodbc
from ..workflow_utils import normalize_sql_value

MAX_SQL_VALUE_QUERY_LENGTH = 8000
UNSAFE_SQL_RE = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|truncate|exec|execute|call|create|grant|revoke)\b",
    re.I,
)
PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


class SqlValueError(ValueError):
    pass


@dataclass(frozen=True)
class SqlValueResult:
    value: str
    warnings: list[dict[str, str]]


def _text(value: object) -> str:
    return str(value or "").strip()


def _strip_sql_comments(query: str) -> str:
    query = re.sub(r"/\*.*?\*/", " ", query, flags=re.S)
    return re.sub(r"--[^\r\n]*", " ", query)


def validate_sql_value_query(query: object) -> str:
    text = str(query or "").strip()
    if not text:
        raise SqlValueError("Zapytanie SQL jest wymagane.")
    if len(text) > MAX_SQL_VALUE_QUERY_LENGTH:
        raise SqlValueError("Zapytanie SQL jest za dlugie.")
    without_comments = _strip_sql_comments(text).strip()
    if not re.match(r"(?is)^\s*select\b", without_comments):
        raise SqlValueError("Zapytanie SQL dla Pimcore musi zaczynac sie od SELECT.")
    if ";" in without_comments.rstrip(";"):
        raise SqlValueError("Zapytanie SQL dla Pimcore musi byc pojedynczym SELECT.")
    if UNSAFE_SQL_RE.search(without_comments):
        raise SqlValueError("Zapytanie SQL zawiera niedozwolona instrukcje.")
    return without_comments.rstrip("; \r\n\t")


def _placeholder_value(token: str, product_values: dict[str, object], pimcore_values: dict[str, object]) -> str:
    key = _text(token)
    folded = key.casefold()
    if folded.startswith("pimcore:"):
        return _text(pimcore_values.get(key.split(":", 1)[1]))
    if folded == "ean":
        return _text(product_values.get("ean") or product_values.get("EAN") or pimcore_values.get("EAN"))
    return _text(product_values.get(folded) or product_values.get(key) or pimcore_values.get(key))


def bind_sql_value_query(
    query: object,
    product_values: dict[str, object],
    pimcore_values: dict[str, object],
    db_type: str,
) -> tuple[str, Sequence[str]]:
    safe_query = validate_sql_value_query(query)
    marker = "%s" if str(db_type or K).casefold() == K else "?"
    params: list[str] = []

    def replace(match: re.Match[str]) -> str:
        params.append(_placeholder_value(match.group(1), product_values, pimcore_values))
        return marker

    return PLACEHOLDER_RE.sub(replace, safe_query), tuple(params)


def connect_profile(profile: dict[str, object]):
    db_type = str(profile.get("type") or K).casefold()
    if db_type == K:
        return mysql.connector.connect(
            host=_text(profile.get("host")),
            user=_text(profile.get("user")),
            password=_text(profile.get("password")),
            database=_text(profile.get("database")),
            connection_timeout=5,
            use_pure=True,
        )
    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={_text(profile.get('host'))};"
        f"DATABASE={_text(profile.get('database'))};"
        f"UID={_text(profile.get('user'))};"
        f"PWD={_text(profile.get('password'))};"
        "Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=5"
    )
    return pyodbc.connect(conn_str)


def execute_sql_value_query(
    profile: dict[str, object],
    query: object,
    product_values: dict[str, object],
    pimcore_values: dict[str, object],
    *,
    connector: Callable[[dict[str, object]], object] = connect_profile,
) -> SqlValueResult:
    bound_query, params = bind_sql_value_query(
        query,
        product_values,
        pimcore_values,
        str(profile.get("type") or K),
    )
    conn = None
    cursor = None
    try:
        conn = connector(profile)
        cursor = conn.cursor()
        cursor.execute(bound_query, params)
        rows = cursor.fetchmany(2)
    except E as exc:
        raise SqlValueError(f"Nie mozna wykonac SQL: {exc}") from exc
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except E:
                pass
        if conn is not None:
            try:
                conn.close()
            except E:
                pass
    if not rows:
        return SqlValueResult("", [{"code": "no_rows", "message": "SQL nie zwrocil wiersza."}])
    first = rows[0]
    try:
        raw_value = first[0]
    except E:
        raw_value = first
    warnings = []
    if len(rows) > 1:
        warnings.append(
            {
                "code": "multiple_rows",
                "message": "SQL zwrocil wiele wierszy; uzyto pierwszego.",
            }
        )
    return SqlValueResult(normalize_sql_value(raw_value), warnings)
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_pimcore_sql_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add picorgftp_sql/services/pimcore_sql_service.py tests/test_pimcore_sql_service.py
git commit -m "feat: execute pimcore sql value queries"
```

## Task 3: Pimcore Mapping SQL Mode

**Files:**
- Modify: `picorgftp_sql/pimcore_config.py`
- Modify: `picorgftp_sql/web_data.py`
- Test: `tests/test_pimcore_config.py`
- Test: `tests/test_pimcore_web.py`

- [ ] **Step 1: Write failing mapping normalization and schema tests**

Add to `tests/test_pimcore_config.py`:

```python
def test_normalize_field_mapping_keeps_sql_query_and_profile_id():
    result = normalize_pimcore_settings(
        {
            "field_mappings": [
                {
                    "source": "STOCK",
                    "label": "Stan",
                    "pimcore_field": "stockText",
                    "type": "input",
                    "parser": "text",
                    "value_template": "SQL",
                    "sql_query": "SELECT stock FROM product WHERE ean = {ean}",
                    "sql_profile_id": "stock-db",
                }
            ]
        }
    )

    mapping = result["field_mappings"][0]
    assert mapping["value_template"] == "SQL"
    assert mapping["sql_query"] == "SELECT stock FROM product WHERE ean = {ean}"
    assert mapping["sql_profile_id"] == "stock-db"


def test_field_mapping_issues_require_sql_query_and_profile_for_sql_mode():
    issues = field_mapping_issues(
        [
            {
                "source": "STOCK",
                "label": "Stan",
                "pimcore_field": "stockText",
                "type": "input",
                "parser": "text",
                "value_template": "SQL",
            }
        ],
        sql_profiles=[],
    )

    assert "Mapowanie 1: SQL wymaga zapytania." in issues
    assert "Mapowanie 1: SQL wymaga profilu polaczenia." in issues
```

Add to `tests/test_pimcore_web.py`:

```python
def test_runtime_schema_exposes_sql_mapping_metadata_without_secrets():
    settings_payload = {
        "field_mappings": [
            {
                "source": "STOCK",
                "label": "Stan",
                "pimcore_field": "stockText",
                "type": "input",
                "parser": "text",
                "value_template": "SQL",
                "sql_query": "SELECT stock FROM product WHERE ean = {ean}",
                "sql_profile_id": "stock-db",
            }
        ]
    }

    schema = web_data._pimcore_runtime_form_schema(
        web_data.normalize_pimcore_settings(settings_payload)
    )

    assert schema[0]["value_template"] == "SQL"
    assert schema[0]["sql_query"] == "SELECT stock FROM product WHERE ean = {ean}"
    assert schema[0]["sql_profile_id"] == "stock-db"
    assert "password" not in json.dumps(schema).casefold()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_pimcore_config.py::test_normalize_field_mapping_keeps_sql_query_and_profile_id tests/test_pimcore_config.py::test_field_mapping_issues_require_sql_query_and_profile_for_sql_mode tests/test_pimcore_web.py::test_runtime_schema_exposes_sql_mapping_metadata_without_secrets -q
```

Expected: FAIL because mappings do not normalize SQL metadata and `field_mapping_issues` does not accept profile context.

- [ ] **Step 3: Implement mapping normalization and validation**

Modify `normalize_field_mapping` return value in `picorgftp_sql/pimcore_config.py`:

```python
        "sql_query": _text(raw.get("sql_query")),
        "sql_profile_id": _text(raw.get("sql_profile_id")),
```

Modify `infer_field_mapping` return value:

```python
        "sql_query": "",
        "sql_profile_id": "",
```

Change the `field_mapping_issues` signature:

```python
def field_mapping_issues(
    raw_mappings: object,
    *,
    sql_profiles: list[dict[str, object]] | None = None,
) -> list[str]:
```

Inside the loop, after `template = _text(raw.get("value_template"))`, add:

```python
        sql_query = _text(raw.get("sql_query"))
        sql_profile_id = _text(raw.get("sql_profile_id"))
        is_sql_mode = template.casefold() == "sql"
        available_profile_ids = {
            _text(item.get("id"))
            for item in (sql_profiles or [])
            if isinstance(item, dict) and bool(item.get("enabled", True))
        }
        if is_sql_mode:
            if not sql_query:
                issues.append(f"Mapowanie {index}: SQL wymaga zapytania.")
            if not sql_profile_id:
                issues.append(f"Mapowanie {index}: SQL wymaga profilu polaczenia.")
            elif available_profile_ids and sql_profile_id not in available_profile_ids:
                issues.append(
                    f"Mapowanie {index}: profil SQL {sql_profile_id} jest niedostepny."
                )
```

Before parsing templates in the second pass, skip SQL mode:

```python
            if template.casefold() == "sql":
                continue
```

- [ ] **Step 4: Expose SQL metadata in runtime schema**

Modify `_pimcore_runtime_form_schema` in `picorgftp_sql/web_data.py`:

```python
            "sql_query": item.get("sql_query", ""),
            "sql_profile_id": item.get("sql_profile_id", ""),
```

- [ ] **Step 5: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_pimcore_config.py::test_normalize_field_mapping_keeps_sql_query_and_profile_id tests/test_pimcore_config.py::test_field_mapping_issues_require_sql_query_and_profile_for_sql_mode tests/test_pimcore_web.py::test_runtime_schema_exposes_sql_mapping_metadata_without_secrets -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add picorgftp_sql/pimcore_config.py picorgftp_sql/web_data.py tests/test_pimcore_config.py tests/test_pimcore_web.py
git commit -m "feat: add sql mode to pimcore mappings"
```

## Task 4: Settings Snapshot, Save, And Profile Diagnostics

**Files:**
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/app.py`
- Modify: `picorgftp_sql/services/pimcore_sql_service.py`
- Test: `tests/test_web_data_users.py`
- Test: `tests/test_pimcore_web.py`

- [ ] **Step 1: Write failing settings and route tests**

Add to `tests/test_web_data_users.py`:

```python
    def test_settings_snapshot_exposes_public_sql_profiles(self) -> None:
        cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
        cfg["sql_profiles"] = [
            {
                "id": "stock",
                "label": "Stock",
                "type": "mysql",
                "host": "mysql.local",
                "database": "catalog",
                "user": "reader",
                "password": "secret",
                "enabled": True,
            }
        ]

        with (
            patch.object(web_data.config, "CONFIG", cfg),
            patch.object(web_data, "load_users", return_value=[]),
        ):
            snapshot = web_data.settings_snapshot()

        assert snapshot["database"]["profiles"][0]["id"] == "default"
        assert snapshot["database"]["profiles"][0]["usage"] == "slots"
        assert snapshot["database"]["profiles"][1]["id"] == "stock"
        assert snapshot["database"]["profiles"][1]["password_set"] is True
        assert "secret" not in json.dumps(snapshot)

    def test_update_settings_saves_additional_sql_profiles_and_preserves_blank_password(self) -> None:
        cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
        cfg["sql_profiles"] = [
            {
                "id": "stock",
                "label": "Stock",
                "type": "mysql",
                "host": "old.local",
                "database": "catalog",
                "user": "reader",
                "password": "saved-secret",
                "enabled": True,
            }
        ]
        saved = []

        with (
            patch.object(web_data.config, "CONFIG", cfg),
            patch.object(web_data, "save_config", side_effect=lambda payload, **kwargs: saved.append(json.loads(json.dumps(payload)))),
            patch.object(web_data.config, "initialize_config", return_value=cfg),
            patch.object(web_data, "settings_snapshot", return_value={}),
        ):
            web_data.update_settings(
                {
                    "database": {
                        "profiles": [
                            {
                                "id": "stock",
                                "label": "Stock",
                                "type": "mysql",
                                "host": "new.local",
                                "database": "catalog",
                                "user": "reader",
                                "password": "",
                                "enabled": True,
                            }
                        ]
                    }
                }
            )

        assert saved[0]["sql_profiles"][0]["host"] == "new.local"
        assert saved[0]["sql_profiles"][0]["password"] == "saved-secret"
```

Add to `tests/test_pimcore_web.py`:

```python
def test_admin_can_test_sql_profile_route():
    client = TestClient(web_app.app)
    expected = {"ok": True, "message": "Polaczenie SQL dziala."}
    with (
        patch.object(web_app, "_require_admin", return_value={"username": "admin", "role": "admin"}),
        patch.object(web_app, "test_sql_profile_connection", return_value=expected) as test_profile,
    ):
        response = client.post("/api/settings/sql-profiles/stock/test")

    assert response.status_code == 200
    assert response.json() == expected
    test_profile.assert_called_once_with("stock")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_web_data_users.py::WebDataUsersTests::test_settings_snapshot_exposes_public_sql_profiles tests/test_web_data_users.py::WebDataUsersTests::test_update_settings_saves_additional_sql_profiles_and_preserves_blank_password tests/test_pimcore_web.py::test_admin_can_test_sql_profile_route -q
```

Expected: FAIL because snapshots, saving, and route do not support profiles.

- [ ] **Step 3: Implement web settings profile handling**

Modify imports in `web_data.py`:

```python
from .sql_profiles import (
    SQL_PROFILES_KEY,
    additional_sql_profiles,
    normalize_sql_profiles,
    public_sql_profiles,
    resolve_sql_profile,
)
from .services.pimcore_sql_service import connect_profile
```

In `_preserve_unsubmitted_config_secrets`, add:

```python
    profile_preserve = set()
    submitted_profiles = db_payload.get("profiles") if isinstance(db_payload.get("profiles"), list) else []
    existing_profiles = {
        _text(item.get("id")): item
        for item in config.CONFIG.get(SQL_PROFILES_KEY, [])
        if isinstance(item, dict)
    }
    for item in submitted_profiles:
        if not isinstance(item, dict):
            continue
        profile_id = _text(item.get("id"))
        if profile_id in existing_profiles and not _text(item.get("password")):
            profile_preserve.add(profile_id)
    if profile_preserve:
        preserve[SQL_PROFILES_KEY] = profile_preserve
```

In `update_settings`, inside `if db_payload:`, add:

```python
        if isinstance(db_payload.get("profiles"), list):
            current_profiles = {
                _text(item.get("id")): item
                for item in cfg.get(SQL_PROFILES_KEY, [])
                if isinstance(item, dict)
            }
            merged_profiles = []
            for item in db_payload["profiles"]:
                if not isinstance(item, dict):
                    continue
                profile = dict(item)
                profile_id = _text(profile.get("id"))
                if profile_id and not _text(profile.get("password")) and profile_id in current_profiles:
                    profile["password"] = current_profiles[profile_id].get("password", "")
                merged_profiles.append(profile)
            cfg[SQL_PROFILES_KEY] = additional_sql_profiles({SQL_PROFILES_KEY: merged_profiles})
```

In `settings_snapshot`, add to `"database"`:

```python
            "profiles": public_sql_profiles(normalize_sql_profiles(cfg)),
```

Add function in `web_data.py`:

```python
def test_sql_profile_connection(profile_id: object) -> dict[str, object]:
    profiles = normalize_sql_profiles(config.CONFIG)
    profile = resolve_sql_profile(profiles, profile_id)
    if profile.get("id") == "default":
        return test_sql_connection()
    conn = None
    cursor = None
    try:
        conn = connect_profile(profile)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        return {"ok": True, "message": "Polaczenie SQL dziala."}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
```

- [ ] **Step 4: Add profile diagnostic route**

Modify imports in `web/app.py` to import `test_sql_profile_connection`. Add route near SQL settings routes:

```python
    @app.post("/api/settings/sql-profiles/{profile_id}/test")
    async def settings_sql_profile_test(request: Request, profile_id: str) -> JSONResponse:
        _require_admin(request)
        result = await run_in_threadpool(test_sql_profile_connection, profile_id)
        return JSONResponse(result)
```

- [ ] **Step 5: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_web_data_users.py::WebDataUsersTests::test_settings_snapshot_exposes_public_sql_profiles tests/test_web_data_users.py::WebDataUsersTests::test_update_settings_saves_additional_sql_profiles_and_preserves_blank_password tests/test_pimcore_web.py::test_admin_can_test_sql_profile_route -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_web_data_users.py tests/test_pimcore_web.py
git commit -m "feat: expose and test sql profiles in settings"
```

## Task 5: SQL Mode Rendering For Pimcore Runtime

**Files:**
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/pimcore_config.py`
- Test: `tests/test_pimcore_web.py`

- [ ] **Step 1: Write failing render behavior tests**

Add to `tests/test_pimcore_web.py`:

```python
def test_render_saved_pimcore_templates_auto_applies_sql_only_when_empty():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update(
        {
            "enabled": True,
            "setup_complete": True,
            "field_mappings": [
                {
                    "source": "STOCK",
                    "label": "Stan",
                    "pimcore_field": "stockText",
                    "type": "input",
                    "parser": "text",
                    "value_template": "SQL",
                    "sql_query": "SELECT stock FROM product WHERE ean = {ean}",
                    "sql_profile_id": "stock",
                }
            ],
        }
    )
    cfg["sql_profiles"] = [
        {
            "id": "stock",
            "label": "Stock",
            "type": "mysql",
            "host": "mysql.local",
            "database": "catalog",
            "user": "reader",
            "password": "secret",
            "enabled": True,
        }
    ]

    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "execute_sql_value_query", return_value=web_data.SqlValueResult("12", [])),
    ):
        empty = web_data.render_saved_pimcore_templates({"ean": "5901234567890"}, {"STOCK": ""}, ["STOCK"])
        manual = web_data.render_saved_pimcore_templates({"ean": "5901234567890"}, {"STOCK": "manual"}, ["STOCK"])

    assert empty["values"]["STOCK"] == "12"
    assert empty["calculated_values"]["STOCK"] == "12"
    assert empty["changed"]["STOCK"] is False
    assert manual["values"]["STOCK"] == "manual"
    assert manual["calculated_values"]["STOCK"] == "12"
    assert manual["changed"]["STOCK"] is True


def test_render_saved_pimcore_templates_for_edit_does_not_auto_apply_sql():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update(
        {
            "enabled": True,
            "setup_complete": True,
            "field_mappings": [
                {
                    "source": "STOCK",
                    "label": "Stan",
                    "pimcore_field": "stockText",
                    "type": "input",
                    "parser": "text",
                    "value_template": "SQL",
                    "sql_query": "SELECT stock FROM product WHERE ean = {ean}",
                    "sql_profile_id": "stock",
                }
            ],
        }
    )
    cfg["sql_profiles"] = [
        {
            "id": "stock",
            "label": "Stock",
            "type": "mysql",
            "host": "mysql.local",
            "database": "catalog",
            "user": "reader",
            "password": "secret",
            "enabled": True,
        }
    ]

    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "execute_sql_value_query", return_value=web_data.SqlValueResult("12", [])),
    ):
        result = web_data.render_saved_pimcore_templates(
            {"ean": "5901234567890"},
            {"STOCK": "existing"},
            ["STOCK"],
            mode="edit",
        )

    assert result["values"]["STOCK"] == "existing"
    assert result["calculated_values"]["STOCK"] == "12"
    assert result["changed"]["STOCK"] is True
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_pimcore_web.py::test_render_saved_pimcore_templates_auto_applies_sql_only_when_empty tests/test_pimcore_web.py::test_render_saved_pimcore_templates_for_edit_does_not_auto_apply_sql -q
```

Expected: FAIL because `_render_templates` does not execute SQL mode and `render_saved_pimcore_templates` does not accept `mode`.

- [ ] **Step 3: Implement SQL mode rendering**

Modify imports in `web_data.py`:

```python
from .services.pimcore_sql_service import SqlValueResult, execute_sql_value_query
```

Change `_render_templates` signature:

```python
def _render_templates(
    settings_payload: dict[str, object],
    product_values: object,
    values: object,
    targets: list[str] | None = None,
    *,
    fill_missing_product_values: bool = False,
    mode: str = "create",
) -> dict[str, object]:
```

Inside `_render_templates`, before calling `render_mapping_templates`, split mappings:

```python
    mappings_list = list(settings_payload["field_mappings"])
    sql_sources = {
        item["source"]
        for item in mappings_list
        if str(item.get("value_template") or "").strip().casefold() == "sql"
    }
    selected_targets = set(targets or [item["source"] for item in mappings_list])
    template_mappings = [
        {**item, "value_template": "" if item["source"] in sql_sources else item.get("value_template", "")}
        for item in mappings_list
    ]
```

Call `render_mapping_templates` with `template_mappings` as the mappings argument instead of the original mappings. Initialize response metadata:

```python
    calculated_values: dict[str, object] = {}
    changed: dict[str, bool] = {}
```

After standard template handling, execute SQL for selected SQL sources:

```python
    product_context = _product_template_values(
        product_values,
        fill_missing=fill_missing_product_values,
    )
    profiles = normalize_sql_profiles(config.CONFIG)
    for mapping in mappings_list:
        source = mapping["source"]
        if source not in selected_targets:
            continue
        if source not in sql_sources:
            if source in output:
                calculated_values[source] = output[source]
                changed[source] = False
            continue
        try:
            profile = resolve_sql_profile(profiles, mapping.get("sql_profile_id"))
            if not profile.get("enabled", True):
                raise ValueError(f"Profil SQL {profile.get('label') or profile.get('id')} jest wylaczony.")
            sql_result = execute_sql_value_query(
                profile,
                mapping.get("sql_query"),
                product_context,
                output,
            )
        except Exception as exc:
            warnings.append({"source": source, "code": "sql_error", "message": str(exc)})
            calculated = ""
        else:
            calculated = sql_result.value
            warnings.extend({"source": source, **warning} for warning in sql_result.warnings)
        calculated_values[source] = calculated
        current = str(submitted.get(source, ""))
        changed[source] = current != str(calculated)
        if (mode in {"create", "test", "preview"} and not _text(current)) or mode == "apply":
            output[source] = calculated
            changed[source] = False
```

Return:

```python
    return {
        "values": output,
        "calculated_values": calculated_values,
        "warnings": warnings,
        "changed": changed,
    }
```

Change `preview_pimcore_template`, `pimcore_test_sample`, and `render_saved_pimcore_templates` to pass `mode`. Change `render_saved_pimcore_templates` signature:

```python
def render_saved_pimcore_templates(
    product_values: object,
    values: object,
    targets: object,
    mode: str = "create",
) -> dict[str, object]:
```

- [ ] **Step 4: Extend render route to pass mode**

In `web/app.py`, update the render call:

```python
                source.get("mode", "create"),
```

and update function call ordering to match the new signature.

- [ ] **Step 5: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_pimcore_web.py::test_render_saved_pimcore_templates_auto_applies_sql_only_when_empty tests/test_pimcore_web.py::test_render_saved_pimcore_templates_for_edit_does_not_auto_apply_sql -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_pimcore_web.py
git commit -m "feat: render pimcore sql mapping values"
```

## Task 6: SQLite Pimcore Submission Storage

**Files:**
- Modify: `picorgftp_sql/sqlite_store.py`
- Modify: `picorgftp_sql/web_data.py`
- Test: `tests/test_sqlite_store.py`
- Test: `tests/test_pimcore_web.py`

- [ ] **Step 1: Write failing SQLite store tests**

Add to `tests/test_sqlite_store.py`:

```python
def test_pimcore_submissions_roundtrip_and_filter(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()

    store.append_pimcore_submission(
        {
            "operation_id": "op-1",
            "operation_type": "manual_create",
            "username": "operator",
            "ean": "5901234567890",
            "object_id": "91",
            "object_path": "/Produkty/91",
            "status": "completed",
            "values": {"EAN": "5901234567890", "STOCK": "12"},
            "payload": {"className": "Product"},
            "result": {"object_id": 91},
            "warnings": [],
        }
    )

    rows = store.query_pimcore_submissions(user="operator", query="590123", limit=20)

    assert len(rows) == 1
    assert rows[0]["operation_id"] == "op-1"
    assert rows[0]["values"]["STOCK"] == "12"
    assert rows[0]["payload"]["className"] == "Product"
    assert rows[0]["created_at"].endswith("Z")
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
python -m pytest tests/test_sqlite_store.py::test_pimcore_submissions_roundtrip_and_filter -q
```

Expected: FAIL because the table and methods do not exist.

- [ ] **Step 3: Implement SQLite table and methods**

In `picorgftp_sql/sqlite_store.py`, increment:

```python
SCHEMA_VERSION = 4
```

Add table to `initialize()`:

```sql
                CREATE TABLE IF NOT EXISTS pimcore_submissions (
                    id TEXT PRIMARY KEY,
                    operation_id TEXT NOT NULL DEFAULT '',
                    operation_type TEXT NOT NULL,
                    username TEXT NOT NULL DEFAULT '',
                    ean TEXT NOT NULL DEFAULT '',
                    object_id TEXT NOT NULL DEFAULT '',
                    object_path TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    values_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    warnings_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
```

Add indexes:

```sql
                CREATE INDEX IF NOT EXISTS idx_pimcore_submissions_created_at
                    ON pimcore_submissions(created_at);
                CREATE INDEX IF NOT EXISTS idx_pimcore_submissions_ean
                    ON pimcore_submissions(ean);
                CREATE INDEX IF NOT EXISTS idx_pimcore_submissions_user
                    ON pimcore_submissions(username);
```

Add methods to `SqliteStore`:

```python
    def append_pimcore_submission(self, record: dict[str, object]) -> dict[str, Any]:
        self.initialize()
        record_id = _text(record.get("id")) or f"pim-{uuid.uuid4().hex}"
        created_at = _iso_from_timestamp(record.get("created_at") or _now_iso())
        payload = {
            "id": record_id,
            "operation_id": _text(record.get("operation_id")),
            "operation_type": _text(record.get("operation_type")),
            "username": _text(record.get("username")),
            "ean": _text(record.get("ean")),
            "object_id": _text(record.get("object_id")),
            "object_path": _text(record.get("object_path")),
            "status": _text(record.get("status")),
            "values": record.get("values") if isinstance(record.get("values"), dict) else {},
            "payload": record.get("payload") if isinstance(record.get("payload"), dict) else {},
            "result": record.get("result") if isinstance(record.get("result"), dict) else {},
            "warnings": record.get("warnings") if isinstance(record.get("warnings"), list) else [],
            "created_at": created_at,
        }
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO pimcore_submissions (
                    id, operation_id, operation_type, username, ean, object_id,
                    object_path, status, values_json, payload_json, result_json,
                    warnings_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    operation_id = excluded.operation_id,
                    operation_type = excluded.operation_type,
                    username = excluded.username,
                    ean = excluded.ean,
                    object_id = excluded.object_id,
                    object_path = excluded.object_path,
                    status = excluded.status,
                    values_json = excluded.values_json,
                    payload_json = excluded.payload_json,
                    result_json = excluded.result_json,
                    warnings_json = excluded.warnings_json,
                    created_at = excluded.created_at
                """,
                (
                    payload["id"],
                    payload["operation_id"],
                    payload["operation_type"],
                    payload["username"],
                    payload["ean"],
                    payload["object_id"],
                    payload["object_path"],
                    payload["status"],
                    _json_dumps(payload["values"]),
                    _json_dumps(payload["payload"]),
                    _json_dumps(payload["result"]),
                    _json_dumps(payload["warnings"]),
                    payload["created_at"],
                ),
            )
        return payload

    def query_pimcore_submissions(
        self,
        *,
        operation_type: str = "",
        status: str = "",
        user: str = "",
        query: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        self.initialize()
        clauses = []
        params: list[object] = []
        if _text(operation_type):
            clauses.append("operation_type = ?")
            params.append(_text(operation_type))
        if _text(status):
            clauses.append("status = ?")
            params.append(_text(status))
        if _text(user):
            clauses.append("LOWER(username) = LOWER(?)")
            params.append(_text(user))
        if _text(date_from):
            clauses.append("created_at >= ?")
            params.append(_text(date_from))
        if _text(date_to):
            clauses.append("created_at <= ?")
            params.append(_text(date_to))
        if _text(query):
            needle = f"%{_text(query)}%"
            clauses.append(
                "(ean LIKE ? OR object_id LIKE ? OR object_path LIKE ? OR values_json LIKE ?)"
            )
            params.extend([needle, needle, needle, needle])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        bounded_limit = max(1, min(1000, int(limit or 200)))
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM pimcore_submissions
                {where}
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (*params, bounded_limit),
            ).fetchall()
        result = []
        for row in rows:
            result.append(
                {
                    "id": row["id"],
                    "operation_id": row["operation_id"],
                    "operation_type": row["operation_type"],
                    "username": row["username"],
                    "ean": row["ean"],
                    "object_id": row["object_id"],
                    "object_path": row["object_path"],
                    "status": row["status"],
                    "values": _json_loads(row["values_json"], {}),
                    "payload": _json_loads(row["payload_json"], {}),
                    "result": _json_loads(row["result_json"], {}),
                    "warnings": _json_loads(row["warnings_json"], []),
                    "created_at": row["created_at"],
                }
            )
        return result
```

- [ ] **Step 4: Run SQLite test and verify it passes**

Run:

```powershell
python -m pytest tests/test_sqlite_store.py::test_schema_creates_expected_tables tests/test_sqlite_store.py::test_pimcore_submissions_roundtrip_and_filter -q
```

Expected: PASS after adding `pimcore_submissions` to the expected table set.

- [ ] **Step 5: Add web_data persistence tests**

Add to `tests/test_pimcore_web.py`:

```python
def test_create_adapter_persists_detailed_sqlite_submission_when_store_active():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update({"enabled": True, "setup_complete": True})
    store = Mock()

    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "_active_sqlite_store", return_value=store),
        patch.object(
            web_data,
            "create_product",
            return_value={"created": True, "duplicate": False, "object": {"id": 91}, "payload": {"className": "Product"}},
        ),
        patch.object(web_data, "_persist_pimcore_operation"),
    ):
        web_data.create_pimcore_product({"EAN": "5904804578169"}, "operator")

    submitted = store.append_pimcore_submission.call_args.args[0]
    assert submitted["operation_type"] == "manual_create"
    assert submitted["username"] == "operator"
    assert submitted["values"]["EAN"] == "5904804578169"
    assert submitted["payload"]["className"] == "Product"
```

- [ ] **Step 6: Implement web_data persistence hook**

Add to `web_data.py`:

```python
def _persist_pimcore_submission(record: dict[str, object]) -> None:
    store = _active_sqlite_store()
    if store is None:
        return
    try:
        store.append_pimcore_submission(redact_pimcore_log_value(record))
    except Exception as exc:
        log_error(f"Failed to persist Pimcore submission: {exc}")
```

Call `_persist_pimcore_submission` in `create_pimcore_product` and `update_pimcore_product` `finally` blocks after building the report. Pass operation ID, operation type, username, values, status, result payload, object identity, warnings, and timestamps.

- [ ] **Step 7: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_sqlite_store.py::test_pimcore_submissions_roundtrip_and_filter tests/test_pimcore_web.py::test_create_adapter_persists_detailed_sqlite_submission_when_store_active -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```powershell
git add picorgftp_sql/sqlite_store.py picorgftp_sql/web_data.py tests/test_sqlite_store.py tests/test_pimcore_web.py
git commit -m "feat: store pimcore submissions in sqlite"
```

## Task 7: Pimcore Submission Export API

**Files:**
- Modify: `picorgftp_sql/web_data.py`
- Modify: `picorgftp_sql/web/app.py`
- Test: `tests/test_pimcore_web.py`

- [ ] **Step 1: Write failing export tests**

Add to `tests/test_pimcore_web.py`:

```python
def test_admin_can_export_pimcore_submissions_as_json():
    client = TestClient(web_app.app)
    expected = {"items": [{"operation_id": "op-1"}], "format": "json"}
    with (
        patch.object(web_app, "_require_admin", return_value={"username": "admin", "role": "admin"}),
        patch.object(web_app, "export_pimcore_submissions", return_value=expected) as export,
    ):
        response = client.get("/api/settings/pimcore/submissions/export?format=json&user=operator")

    assert response.status_code == 200
    assert response.json() == expected
    export.assert_called_once()


def test_export_pimcore_submissions_as_csv_contains_common_columns():
    store = Mock()
    store.query_pimcore_submissions.return_value = [
        {
            "operation_id": "op-1",
            "operation_type": "manual_create",
            "username": "operator",
            "ean": "5901234567890",
            "status": "completed",
            "values": {"STOCK": "12"},
            "payload": {"className": "Product"},
            "result": {"object_id": 91},
            "warnings": [],
            "created_at": "2026-07-06T12:00:00.000Z",
        }
    ]

    with patch.object(web_data, "_active_sqlite_store", return_value=store):
        exported = web_data.export_pimcore_submissions(export_format="csv")

    assert exported["format"] == "csv"
    assert "operation_id,operation_type,username,ean,status,created_at" in exported["content"]
    assert "op-1,manual_create,operator,5901234567890,completed,2026-07-06T12:00:00.000Z" in exported["content"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_pimcore_web.py::test_admin_can_export_pimcore_submissions_as_json tests/test_pimcore_web.py::test_export_pimcore_submissions_as_csv_contains_common_columns -q
```

Expected: FAIL because export function and route do not exist.

- [ ] **Step 3: Implement export helper**

Add to `web_data.py`:

```python
def export_pimcore_submissions(
    *,
    export_format: str = "json",
    operation_type: str = "",
    status: str = "",
    user: str = "",
    query: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 1000,
) -> dict[str, object]:
    store = _active_sqlite_store()
    if store is None:
        return {"format": export_format, "items": [], "content": "", "count": 0}
    rows = store.query_pimcore_submissions(
        operation_type=operation_type,
        status=status,
        user=user,
        query=query,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    fmt = _text(export_format).lower() or "json"
    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(
            [
                "operation_id",
                "operation_type",
                "username",
                "ean",
                "status",
                "created_at",
                "object_id",
                "object_path",
                "values_json",
                "payload_json",
                "result_json",
                "warnings_json",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.get("operation_id", ""),
                    row.get("operation_type", ""),
                    row.get("username", ""),
                    row.get("ean", ""),
                    row.get("status", ""),
                    row.get("created_at", ""),
                    row.get("object_id", ""),
                    row.get("object_path", ""),
                    json.dumps(row.get("values", {}), ensure_ascii=False, sort_keys=True),
                    json.dumps(row.get("payload", {}), ensure_ascii=False, sort_keys=True),
                    json.dumps(row.get("result", {}), ensure_ascii=False, sort_keys=True),
                    json.dumps(row.get("warnings", []), ensure_ascii=False, sort_keys=True),
                ]
            )
        return {"format": "csv", "content": output.getvalue(), "count": len(rows)}
    return {"format": "json", "items": rows, "count": len(rows)}
```

- [ ] **Step 4: Add route**

Import `Response` from FastAPI responses if needed. Add route in `web/app.py`:

```python
    @app.get("/api/settings/pimcore/submissions/export")
    def pimcore_submissions_export_api(
        request: Request,
        format: str = "json",
        operation_type: str = "",
        status: str = "",
        user: str = "",
        query: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 1000,
    ):
        _require_admin(request)
        result = export_pimcore_submissions(
            export_format=format,
            operation_type=operation_type,
            status=status,
            user=user,
            query=query,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
        if result.get("format") == "csv":
            return Response(
                str(result.get("content") or ""),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": "attachment; filename=pimcore-submissions.csv"},
            )
        return JSONResponse(result)
```

- [ ] **Step 5: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_pimcore_web.py::test_admin_can_export_pimcore_submissions_as_json tests/test_pimcore_web.py::test_export_pimcore_submissions_as_csv_contains_common_columns -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_pimcore_web.py
git commit -m "feat: export pimcore sqlite submissions"
```

## Task 8: Web UI For Profiles And Pimcore SQL Mapping Controls

**Files:**
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `picorgftp_sql/web/static/index.html`
- Test: `tests/test_web_ui_integrity.py`
- Test: `tests/test_source_integrity.py`

- [ ] **Step 1: Write failing UI integrity tests**

Add to `tests/test_web_ui_integrity.py`:

```python
    def test_sql_profile_ui_and_pimcore_sql_mapping_controls_exist(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        css = (ROOT / "picorgftp_sql" / "web" / "static" / "app.css").read_text(encoding="utf-8")
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("Profil domyslny jest zawsze uzywany przez Sloty", source)
        self.assertIn("function sqlProfileRow", source)
        self.assertIn("/api/settings/sql-profiles/", source)
        self.assertIn("mapping_sql_query", source)
        self.assertIn("mapping_sql_profile_id", source)
        self.assertIn("pimcore-runtime-calculated", source)
        self.assertIn("pimcore-runtime-different", css)
        self.assertIn("20260706-sql-profiles", html)
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
python -m pytest tests/test_web_ui_integrity.py::SourceIntegrityTests::test_sql_profile_ui_and_pimcore_sql_mapping_controls_exist -q
```

Expected: FAIL because UI strings and controls do not exist.

- [ ] **Step 3: Add profile rows in SQL settings UI**

In `app.js`, add helpers near `renderSettingsSql`:

```javascript
function sqlProfileRow(profile = {}) {
  const row = document.createElement("div");
  row.className = "sql-profile-row";
  row.dataset.profileId = profile.id || "";
  row.append(
    inputField("profile_label", "Nazwa profilu", profile.label || ""),
    selectField("profile_type", "Typ bazy", profile.type || "mysql", [["mysql", "MySQL"], ["mssql", "MS SQL"]]),
    inputField("profile_host", "Serwer", profile.host || ""),
    inputField("profile_database", "Baza", profile.database || ""),
    credentialField("profile_user", "Uzytkownik", profile.user_set, { secretPath: `database.profiles.${profile.id}.user` }),
    credentialField("profile_password", "Haslo", profile.password_set, { type: "password", secretPath: `database.profiles.${profile.id}.password` }),
    checkField("profile_enabled", "Aktywny", profile.enabled !== false)
  );
  const test = document.createElement("button");
  test.type = "button";
  test.className = "secondary-button";
  test.textContent = "Test profilu";
  test.addEventListener("click", async () => {
    test.disabled = true;
    try {
      const result = await requestJson(`/api/settings/sql-profiles/${encodeURIComponent(profile.id || "")}/test`, { method: "POST" });
      formStatus.textContent = result.message || "";
    } catch (error) {
      formStatus.textContent = error.message;
    } finally {
      test.disabled = false;
    }
  });
  row.appendChild(test);
  if (!profile.locked) {
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "ghost-button";
    remove.textContent = "Usun";
    remove.addEventListener("click", () => row.remove());
    row.appendChild(remove);
  }
  return row;
}

function collectSqlProfiles(form) {
  return Array.from(form.querySelectorAll(".sql-profile-row"))
    .filter((row) => row.dataset.profileId !== "default")
    .map((row) => ({
      id: row.dataset.profileId || row.querySelector('[name="profile_label"]').value,
      label: row.querySelector('[name="profile_label"]').value,
      type: row.querySelector('[name="profile_type"]').value,
      host: row.querySelector('[name="profile_host"]').value,
      database: row.querySelector('[name="profile_database"]').value,
      user: row.querySelector('[name="profile_user"]').value,
      password: row.querySelector('[name="profile_password"]').value,
      enabled: row.querySelector('[name="profile_enabled"]').checked,
    }));
}
```

In `renderSettingsSql`, add a profiles container:

```javascript
  const profiles = document.createElement("div");
  profiles.className = "sql-profile-list";
  for (const profile of db.profiles || []) {
    profiles.appendChild(sqlProfileRow(profile));
  }
  const addProfile = document.createElement("button");
  addProfile.type = "button";
  addProfile.className = "secondary-button";
  addProfile.textContent = "Dodaj profil Pimcore SQL";
  addProfile.addEventListener("click", () => {
    profiles.appendChild(sqlProfileRow({ id: `profile-${Date.now()}`, label: "Nowy profil", type: "mysql", enabled: true }));
  });
```

Add to form:

```javascript
    settingsFieldGroup(
      "Profile SQL",
      settingsNote("Profil domyslny jest zawsze uzywany przez Sloty."),
      profiles,
      actionRow(addProfile)
    )
```

Add to settings save payload:

```javascript
      profiles: collectSqlProfiles(form),
```

- [ ] **Step 4: Add Pimcore SQL mapping controls**

In `pimcoreMappingRow` and `pimcoreSimpleMappingRow`, set:

```javascript
  row.dataset.sqlQuery = mapping.sql_query || "";
  row.dataset.sqlProfileId = mapping.sql_profile_id || "";
```

Create:

```javascript
function sqlProfileOptions(selected = "") {
  return (state.settings?.database?.profiles || [])
    .filter((profile) => profile.usage === "pimcore_sql" && profile.enabled !== false)
    .map((profile) => [profile.id, profile.label || profile.id, profile.id === selected]);
}

function pimcoreSqlMappingControls(row, mapping = {}) {
  const wrapper = document.createElement("div");
  wrapper.className = "pimcore-sql-mapping-controls";
  const query = inputField("mapping_sql_query", "Zapytanie SQL", mapping.sql_query || "", { textarea: true });
  const profile = selectField(
    "mapping_sql_profile_id",
    "Profil SQL",
    mapping.sql_profile_id || "",
    [["", "Wybierz profil"]].concat(sqlProfileOptions(mapping.sql_profile_id || ""))
  );
  wrapper.append(query, profile);
  return wrapper;
}
```

Append `pimcoreSqlMappingControls(row, mapping)` to mapping rows. Extend `collectPimcoreMappings`, `collectSimplePimcoreMappings`, and setup mapping collection to include:

```javascript
    sql_query: row.querySelector('[name="mapping_sql_query"]')?.value || row.dataset.sqlQuery || "",
    sql_profile_id: row.querySelector('[name="mapping_sql_profile_id"]')?.value || row.dataset.sqlProfileId || "",
```

- [ ] **Step 5: Add CSS and cache bump**

Add to `app.css`:

```css
.sql-profile-list,
.pimcore-sql-mapping-controls {
  display: grid;
  gap: 10px;
}

.sql-profile-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr)) auto auto;
  gap: 8px;
  align-items: end;
}

.pimcore-runtime-different input {
  border-color: #d8a300;
  background: #fff8d6;
}

.pimcore-runtime-calculated {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px;
  align-items: center;
  color: #6b5300;
  font-size: 0.9rem;
}
```

In `index.html`, change asset query strings to `20260706-sql-profiles`.

- [ ] **Step 6: Run UI integrity test**

Run:

```powershell
python -m pytest tests/test_web_ui_integrity.py::SourceIntegrityTests::test_sql_profile_ui_and_pimcore_sql_mapping_controls_exist -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css picorgftp_sql/web/static/index.html tests/test_web_ui_integrity.py
git commit -m "feat: add sql profile and pimcore sql mapping ui"
```

## Task 9: Runtime Difference UI And Apply-Calculated Action

**Files:**
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Test: `tests/test_web_ui_integrity.py`

- [ ] **Step 1: Write failing source integrity test**

Add to `tests/test_web_ui_integrity.py`:

```python
    def test_pimcore_runtime_difference_ui_preserves_manual_values(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn("function updatePimcoreRuntimeCalculatedState", source)
        self.assertIn("dataset.calculatedValue", source)
        self.assertIn("pimcore-runtime-different", source)
        self.assertIn("Zastosuj wyliczone", source)
        self.assertIn('mode: form.dataset.pimcoreMode || "create"', source)
        self.assertIn("if (!input.value)", source)
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
python -m pytest tests/test_web_ui_integrity.py::SourceIntegrityTests::test_pimcore_runtime_difference_ui_preserves_manual_values -q
```

Expected: FAIL because calculated state UI does not exist.

- [ ] **Step 3: Implement calculated state helpers**

Add to `app.js` near runtime form helpers:

```javascript
function updatePimcoreRuntimeCalculatedState(form, result = {}) {
  const calculated = result.calculated_values || {};
  const changed = result.changed || {};
  for (const [source, value] of Object.entries(calculated)) {
    const input = form.elements[source];
    if (!input) continue;
    const field = input.closest(".pimcore-runtime-field");
    if (!field) continue;
    input.dataset.calculatedValue = value ?? "";
    let info = field.querySelector(".pimcore-runtime-calculated");
    if (!info) {
      info = document.createElement("span");
      info.className = "pimcore-runtime-calculated";
      const text = document.createElement("span");
      const apply = document.createElement("button");
      apply.type = "button";
      apply.className = "ghost-button";
      apply.textContent = "Zastosuj wyliczone";
      apply.addEventListener("click", () => {
        input.value = input.dataset.calculatedValue || "";
        field.classList.remove("pimcore-runtime-different");
        info.hidden = true;
      });
      info.append(text, apply);
      field.appendChild(info);
    }
    info.querySelector("span").textContent = `Wyliczone: ${value ?? ""}`;
    const isDifferent = changed[source] === true;
    field.classList.toggle("pimcore-runtime-different", isDifferent);
    info.hidden = !isDifferent;
  }
}
```

In `populatePimcoreRuntimeForm`, set mode on the form in callers:

```javascript
pimcoreCreateForm.dataset.pimcoreMode = "create";
pimcoreEditForm.dataset.pimcoreMode = "edit";
pimcoreTestForm.dataset.pimcoreMode = "test";
```

In `renderPimcoreRuntimeTemplates`, send mode and preserve non-empty values:

```javascript
    body: JSON.stringify({
      product_values: formPayload(),
      values,
      targets: selected,
      mode: form.dataset.pimcoreMode || "create",
    }),
```

Change input application loop:

```javascript
      if (!input.value || form.dataset.pimcoreMode === "apply") {
        input.value = result.values[source] ?? "";
      }
```

After the loop:

```javascript
  updatePimcoreRuntimeCalculatedState(form, result);
```

- [ ] **Step 4: Run test and verify it passes**

Run:

```powershell
python -m pytest tests/test_web_ui_integrity.py::SourceIntegrityTests::test_pimcore_runtime_difference_ui_preserves_manual_values -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py
git commit -m "feat: show pimcore calculated value differences"
```

## Task 10: UI Export Action

**Files:**
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/index.html`
- Test: `tests/test_web_ui_integrity.py`

- [ ] **Step 1: Write failing UI export test**

Add to `tests/test_web_ui_integrity.py`:

```python
    def test_pimcore_history_has_submission_export_actions(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("exportPimcoreSubmissions", source)
        self.assertIn("/api/settings/pimcore/submissions/export", source)
        self.assertIn("Eksport CSV", html)
        self.assertIn("pimcoreHistoryExportCsvButton", html)
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
python -m pytest tests/test_web_ui_integrity.py::SourceIntegrityTests::test_pimcore_history_has_submission_export_actions -q
```

Expected: FAIL because export buttons do not exist.

- [ ] **Step 3: Add export buttons and JavaScript**

In `index.html`, inside `pimcoreHistoryFilters`, add:

```html
          <button id="pimcoreHistoryExportCsvButton" type="button" class="secondary-button">Eksport CSV</button>
          <button id="pimcoreHistoryExportJsonButton" type="button" class="secondary-button">Eksport JSON</button>
```

In `app.js`, query buttons:

```javascript
const pimcoreHistoryExportCsvButton = document.querySelector("#pimcoreHistoryExportCsvButton");
const pimcoreHistoryExportJsonButton = document.querySelector("#pimcoreHistoryExportJsonButton");
```

Add:

```javascript
function pimcoreHistoryExportParams(format) {
  const data = new FormData(pimcoreHistoryFilters);
  const params = new URLSearchParams({ format });
  for (const key of ["operation_type", "result", "user", "query"]) {
    const value = String(data.get(key) || "").trim();
    if (value) params.set(key === "result" ? "status" : key, value);
  }
  return params;
}

function exportPimcoreSubmissions(format) {
  const params = pimcoreHistoryExportParams(format);
  window.location.href = `/api/settings/pimcore/submissions/export?${params.toString()}`;
}
```

Wire listeners:

```javascript
pimcoreHistoryExportCsvButton?.addEventListener("click", () => exportPimcoreSubmissions("csv"));
pimcoreHistoryExportJsonButton?.addEventListener("click", () => exportPimcoreSubmissions("json"));
```

- [ ] **Step 4: Run test and verify it passes**

Run:

```powershell
python -m pytest tests/test_web_ui_integrity.py::SourceIntegrityTests::test_pimcore_history_has_submission_export_actions -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add picorgftp_sql/web/static/app.js picorgftp_sql/web/static/index.html tests/test_web_ui_integrity.py
git commit -m "feat: add pimcore submission export UI"
```

## Task 11: Focused Integration And Regression

**Files:**
- Modify: `README.md`
- Test: all focused test files from previous tasks

- [ ] **Step 1: Add README note**

Add a short section under the Pimcore/template settings documentation:

```markdown
### Pimcore SQL profiles

The default SQL profile is always used by Sloty. Additional SQL profiles can be
created in the SQL settings tab and selected only by Pimcore mappings whose
template field is set to `SQL`. In that mode the mapping uses the separate SQL
query field and writes the first column of the first row into the Pimcore form.
Create and test forms apply SQL results only to empty fields; edit forms require
explicit recalculation and show manual differences before applying a calculated
value.
```

- [ ] **Step 2: Run focused backend tests**

Run:

```powershell
python -m pytest tests/test_sql_profiles.py tests/test_pimcore_sql_service.py tests/test_config.py tests/test_pimcore_config.py tests/test_pimcore_web.py tests/test_sqlite_store.py tests/test_web_data_users.py -q
```

Expected: PASS.

- [ ] **Step 3: Run focused UI/source tests**

Run:

```powershell
python -m pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py -q
```

Expected: PASS.

- [ ] **Step 4: Run full suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit docs and final adjustments**

Run:

```powershell
git add README.md
git commit -m "docs: describe pimcore sql profiles"
```

## Self-Review

- Spec coverage: SQL profiles are covered by Tasks 1, 4, and 8; SQL execution by Tasks 2 and 5; Pimcore mapping configuration by Tasks 3 and 8; runtime automatic and explicit recalculation by Tasks 5 and 9; SQLite persistence by Task 6; export by Tasks 7 and 10; regression docs and tests by Task 11.
- Placeholder scan: this plan contains no open work markers such as deferred details or "fill in later" notes. The word placeholder appears only for the product's template/SQL placeholder feature.
- Type consistency: profile IDs use `id`; the default ID is `default`; additional profiles are stored under `sql_profiles`; Pimcore mappings use `sql_query` and `sql_profile_id`; runtime metadata uses `calculated_values` and `changed`; SQLite methods are `append_pimcore_submission` and `query_pimcore_submissions`.
