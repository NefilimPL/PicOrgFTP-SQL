"""SQL workflow helpers."""

from __future__ import annotations

import re

from ..common import (
    AI,
    E,
    I,
    K,
    M,
    N,
    P,
    Q,
    SQL_UPDATE_TEMPLATE,
    b,
    c,
    p,
    w,
)
from ..database import connect_db
from ..workflow_utils import (
    build_sql_presence_query,
    has_presence_value,
    normalize_sql_value,
    unique_columns,
)

SAFE_IDENTIFIER_RE = re.compile(r"^[0-9A-Za-z_\.]+$")


def _safe_identifier(value):
    text = str(value or "").strip()
    if not text or not SAFE_IDENTIFIER_RE.fullmatch(text):
        return ""
    return text


def should_check_presence(config_dict):
    """Return True when database credentials are configured for lookups."""

    db_type = config_dict.get(p, K).lower()
    if db_type == K:
        mysql_cfg = config_dict.get(K, {})
        return all(mysql_cfg.get(key) for key in (c, b, N))
    sql_cfg = config_dict.get(P, {})
    if not (sql_cfg.get(c) and sql_cfg.get(b)):
        return False
    user = sql_cfg.get(N)
    password = sql_cfg.get(M)
    if user or password:
        return bool(user and password)
    return True


def extract_presence_context(config_dict, ean):
    """Return the table name and WHERE clause used for SQL presence checks."""

    if not ean:
        return None
    template = config_dict.get(w, SQL_UPDATE_TEMPLATE) or SQL_UPDATE_TEMPLATE
    update_match = re.search(r"(?is)update\s+([^\s]+)\s+set", template)
    if not update_match:
        return None
    table = _safe_identifier(update_match.group(1).strip().rstrip(";"))
    if not table:
        return None
    where_match = re.search(r"(?is)\bwhere\b(.+)", template)
    if where_match:
        where_template = " WHERE" + where_match.group(1)
    else:
        where_template = " WHERE EAN = '{ean}' OR Towar_powiazany_z_SKU = '{ean}'"
    where_clause = where_template.replace("{ean}", str(ean)).replace("{EAN}", str(ean))
    where_clause = where_clause.rstrip(";\n\r\t ")
    if where_clause and not where_clause.startswith(" "):
        where_clause = " " + where_clause
    return table, where_clause


def query_presence_map(columns, table, where_clause, db_type):
    """Fetch SQL presence for all mapped columns, batching when possible."""

    presence_map, _value_map = query_presence_details(columns, table, where_clause, db_type)
    return presence_map


def query_presence_details(columns, table, where_clause, db_type):
    """Fetch SQL presence flags together with the raw SQL values."""

    presence_map = {prefix: I for prefix, _, _ in columns}
    value_map = {prefix: "" for prefix, _, _ in columns}
    ordered_columns = unique_columns(
        [_safe_identifier(column_name) for _, column_name, _ in columns if column_name]
    )
    if not ordered_columns or not table:
        return presence_map, value_map
    conn = None
    cur = None
    try:
        conn = connect_db()
        cur = conn.cursor()
        batch_failed = False
        query = build_sql_presence_query(
            table,
            where_clause,
            ordered_columns,
            db_type,
            mysql_key=K,
        )
        if query:
            try:
                cur.execute(query)
                row = cur.fetchone()
            except E:
                batch_failed = True
            else:
                if not row:
                    for prefix, column_name, _ in columns:
                        if column_name:
                            presence_map[prefix] = False
                    return presence_map, value_map
                try:
                    values = list(row)
                except E:
                    values = [row]
                column_value_map = {
                    column_name: values[idx] if idx < Q(values) else I
                    for idx, column_name in enumerate(ordered_columns)
                }
                for prefix, column_name, _ in columns:
                    safe_column = _safe_identifier(column_name)
                    if not safe_column:
                        continue
                    raw_value = column_value_map.get(safe_column)
                    presence_map[prefix] = has_presence_value(raw_value)
                    value_map[prefix] = normalize_sql_value(raw_value)
                return presence_map, value_map
        if not batch_failed:
            return presence_map, value_map
        for prefix, column_name, _ in columns:
            safe_column = _safe_identifier(column_name)
            if not safe_column:
                continue
            if db_type == K:
                query = f"SELECT {safe_column} FROM {table}{where_clause}".rstrip(";\n\r\t ")
                if " limit " not in query.lower():
                    query = f"{query} LIMIT 1"
            else:
                query = f"SELECT TOP 1 {safe_column} FROM {table}{where_clause}".rstrip(";\n\r\t ")
            try:
                cur.execute(query)
                row = cur.fetchone()
            except E:
                presence_map[prefix] = I
                continue
            if not row:
                presence_map[prefix] = False
                continue
            try:
                value = row[0]
            except E:
                try:
                    row_values = list(row)
                except E:
                    row_values = [row]
                value = row_values[0] if row_values else I
            presence_map[prefix] = has_presence_value(value)
            value_map[prefix] = normalize_sql_value(value)
        return presence_map, value_map
    finally:
        if cur is not None:
            try:
                cur.close()
            except E:
                pass
        if conn is not None:
            try:
                conn.close()
            except E:
                pass
