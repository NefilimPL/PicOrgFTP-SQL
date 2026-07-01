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
            issues.append(
                f"Mapowanie {index}: niepoprawne pole Pimcore {target or '[puste]'}."
            )
        elif target in targets:
            issues.append(f"Mapowanie {index}: zduplikowane pole Pimcore {target}.")
        if element_type not in SUPPORTED_ELEMENT_TYPES:
            issues.append(f"Mapowanie {index}: nieobslugiwany typ {element_type}.")
        if parser not in SUPPORTED_PARSERS:
            issues.append(f"Mapowanie {index}: nieobslugiwany parser {parser}.")
        elif element_type in SUPPORTED_ELEMENT_TYPES and element_type not in parser_types[parser]:
            issues.append(
                f"Mapowanie {index}: parser {parser} nie pasuje do typu {element_type}."
            )
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
