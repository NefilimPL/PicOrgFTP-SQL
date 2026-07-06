"""SQL value lookups for Pimcore placeholder mappings."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import re

from ..common import E, K, M, N, b, c, mysql, pyodbc
from ..settings import BW
from ..workflow_utils import normalize_sql_value

MAX_SQL_VALUE_QUERY_LENGTH = 8000
UNSAFE_SQL_RE = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|truncate|exec|execute|call|create|grant|revoke)\b",
    re.I,
)
PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


class SqlValueError(ValueError):
    """Raised when a Pimcore SQL value lookup cannot be validated or executed."""


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
    """Return a sanitized single SELECT query or raise ``SqlValueError``."""

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


def _placeholder_value(
    token: str,
    product_values: dict[str, object],
    pimcore_values: dict[str, object],
) -> str:
    key = _text(token)
    folded = key.casefold()
    if folded.startswith("pimcore:"):
        return _text(pimcore_values.get(key.split(":", 1)[1]))
    if folded == "ean":
        return _text(
            product_values.get("ean")
            or product_values.get("EAN")
            or pimcore_values.get("EAN")
        )
    return _text(product_values.get(folded) or product_values.get(key) or pimcore_values.get(key))


def bind_sql_value_query(
    query: object,
    product_values: dict[str, object],
    pimcore_values: dict[str, object],
    db_type: str,
) -> tuple[str, Sequence[str]]:
    """Bind supported ``{token}`` placeholders as DB parameters."""

    safe_query = validate_sql_value_query(query)
    marker = "%s" if str(db_type or K).casefold() == K else "?"
    params: list[str] = []

    def replace(match: re.Match[str]) -> str:
        params.append(_placeholder_value(match.group(1), product_values, pimcore_values))
        return marker

    return PLACEHOLDER_RE.sub(replace, safe_query), tuple(params)


def connect_profile(profile: dict[str, object]):
    """Open a DB connection for a normalized SQL profile."""

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

    server = _text(profile.get("host"))
    database = _text(profile.get("database"))
    user = _text(profile.get("user"))
    password = _text(profile.get("password"))
    extra = "Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=5"
    last_exc = None
    for driver in BW:
        try:
            conn_str = (
                f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
                f"UID={user};PWD={password};{extra}"
            )
            return pyodbc.connect(conn_str)
        except E as exc:
            last_exc = exc
    raise E(last_exc or "Brak dzialajacego sterownika ODBC do MSSQL.")


def execute_sql_value_query(
    profile: dict[str, object],
    query: object,
    product_values: dict[str, object],
    pimcore_values: dict[str, object],
    *,
    connector: Callable[[dict[str, object]], object] = connect_profile,
) -> SqlValueResult:
    """Execute a SQL value lookup and return the first column of the first row."""

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
        return SqlValueResult(
            "",
            [{"code": "no_rows", "message": "SQL nie zwrocil wiersza."}],
        )

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
