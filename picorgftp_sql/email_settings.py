"""Normalization and public projection for e-mail notification settings."""

from __future__ import annotations

import copy


EMAIL_SETTINGS_KEY = "email_notifications"
EMAIL_CLIENT_SECRET = "client_secret"
EMAIL_SMTP_PASSWORD = "password"
EMAIL_SEVERITIES = ("info", "warning", "error", "critical")


def default_email_settings() -> dict[str, object]:
    return {
        "primary_channel": "entra",
        "fallback_enabled": False,
        "entra": {
            "tenant_id": "",
            "client_id": "",
            EMAIL_CLIENT_SECRET: "",
            "from_address": "",
        },
        "smtp": {
            "host": "",
            "port": 587,
            "security": "starttls",
            "username": "",
            EMAIL_SMTP_PASSWORD: "",
            "from_address": "",
            "from_name": "",
        },
        "rules": {
            severity: {
                "enabled": False,
                "recipients": [],
                "include_actor": False,
            }
            for severity in EMAIL_SEVERITIES
        },
    }


def _text(value: object) -> str:
    return str(value or "").strip()


def _recipients(value: object) -> list[str]:
    values = value.split(",") if isinstance(value, str) else value
    if not isinstance(values, (list, tuple, set)):
        return []
    return [text for item in values if (text := _text(item))]


def normalize_email_settings(raw: object) -> dict[str, object]:
    defaults = default_email_settings()
    source = raw if isinstance(raw, dict) else {}

    primary_channel = _text(source.get("primary_channel")).lower()
    if primary_channel not in {"entra", "smtp"}:
        primary_channel = "entra"

    raw_entra = source.get("entra")
    if not isinstance(raw_entra, dict):
        raw_entra = {}
    entra = {
        key: _text(raw_entra.get(key, default))
        for key, default in defaults["entra"].items()
    }

    raw_smtp = source.get("smtp")
    if not isinstance(raw_smtp, dict):
        raw_smtp = {}
    try:
        port = int(raw_smtp.get("port", defaults["smtp"]["port"]))
    except (TypeError, ValueError):
        port = int(defaults["smtp"]["port"])
    port = max(1, min(65_535, port))
    security = _text(raw_smtp.get("security", "starttls")).lower()
    if security not in {"starttls", "tls", "none"}:
        security = "starttls"
    smtp = {
        key: _text(raw_smtp.get(key, default))
        for key, default in defaults["smtp"].items()
        if key not in {"port", "security"}
    }
    smtp["port"] = port
    smtp["security"] = security

    raw_rules = source.get("rules")
    if not isinstance(raw_rules, dict):
        raw_rules = {}
    rules: dict[str, dict[str, object]] = {}
    for severity in EMAIL_SEVERITIES:
        raw_rule = raw_rules.get(severity)
        if not isinstance(raw_rule, dict):
            raw_rule = {}
        rules[severity] = {
            "enabled": bool(raw_rule.get("enabled", False)),
            "recipients": _recipients(raw_rule.get("recipients", [])),
            "include_actor": bool(raw_rule.get("include_actor", False)),
        }

    return {
        "primary_channel": primary_channel,
        "fallback_enabled": bool(source.get("fallback_enabled", False)),
        "entra": entra,
        "smtp": smtp,
        "rules": rules,
    }


def public_email_settings(raw: object) -> dict[str, object]:
    settings = copy.deepcopy(normalize_email_settings(raw))
    client_secret = settings["entra"].pop(EMAIL_CLIENT_SECRET, "")
    smtp_password = settings["smtp"].pop(EMAIL_SMTP_PASSWORD, "")
    settings["entra"]["client_secret_set"] = bool(_text(client_secret))
    settings["smtp"]["password_set"] = bool(_text(smtp_password))
    return settings
