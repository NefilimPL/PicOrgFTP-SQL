"""Helpers for managing photo slot definitions and SQL column mappings."""

from __future__ import annotations

from typing import Dict, List, Tuple

from .common import DEFAULT_SLOT_DEFS, SQL_COLUMN_MAP_KEY, SLOT_DEFS_KEY


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def normalize_slot_definitions(raw_defs) -> Tuple[List[Dict[str, str]], List[dict]]:
    """Return a cleaned list of slot definitions and any issues found."""

    issues = []
    slot_defs: List[Dict[str, str]] = []
    seen = set()
    if isinstance(raw_defs, list):
        for entry in raw_defs:
            prefix = ""
            label = ""
            if isinstance(entry, dict):
                prefix = _as_text(entry.get("prefix") or entry.get("id"))
                label = _as_text(entry.get("label"))
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                prefix = _as_text(entry[0])
                label = _as_text(entry[1])
            if not prefix or not label:
                if entry:
                    issues.append({"type": "slot_def_invalid", "entry": entry})
                continue
            if prefix in seen:
                issues.append({"type": "slot_def_duplicate", "prefix": prefix})
                continue
            slot_defs.append({"prefix": prefix, "label": label})
            seen.add(prefix)
    if not slot_defs:
        slot_defs = [dict(item) for item in DEFAULT_SLOT_DEFS]
        if raw_defs:
            issues.append({"type": "slot_def_fallback"})
    return slot_defs, issues


def normalize_sql_column_map(raw_map, slot_defs) -> Tuple[Dict[str, str], List[dict]]:
    """Return a cleaned SQL column map aligned with the provided slot defs."""

    issues = []
    normalized: Dict[str, str] = {}
    if isinstance(raw_map, dict):
        for key, value in raw_map.items():
            prefix = _as_text(key)
            if not prefix:
                continue
            normalized[prefix] = _as_text(value)
    prefixes = {slot["prefix"] for slot in slot_defs}
    for prefix in list(normalized):
        if prefix not in prefixes:
            issues.append({"type": "sql_map_extra", "prefix": prefix})
            normalized.pop(prefix, None)
    for slot in slot_defs:
        prefix = slot["prefix"]
        if prefix not in normalized:
            normalized[prefix] = _as_text(slot.get("label"))
    return normalized, issues


def next_slot_prefix(slot_defs) -> str:
    """Return a new numeric prefix that does not collide with existing slots."""

    used = []
    for slot in slot_defs or []:
        prefix = _as_text(slot.get("prefix"))
        if prefix.isdigit():
            used.append(int(prefix))
    if used:
        next_num = max(used) + 1
    else:
        next_num = 1
    width = max(2, len(str(next_num)))
    return str(next_num).zfill(width)


def slot_config_from_config(config_dict) -> Tuple[List[Dict[str, str]], Dict[str, str], List[dict]]:
    """Load slot definitions and SQL map from the provided config dict."""

    raw_defs = config_dict.get(SLOT_DEFS_KEY)
    slot_defs, slot_issues = normalize_slot_definitions(raw_defs)
    raw_map = config_dict.get(SQL_COLUMN_MAP_KEY)
    sql_map, map_issues = normalize_sql_column_map(raw_map, slot_defs)
    return slot_defs, sql_map, slot_issues + map_issues
