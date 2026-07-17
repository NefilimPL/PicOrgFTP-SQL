"""Bounded secret redaction for free text and nested persistence payloads."""

from __future__ import annotations

import re


DEFAULT_TEXT_LIMIT = 8 * 1024
REDACTED = "[REDACTED]"

SECRET_KEY_RE = re.compile(
    r"password|passwd|pass|pwd|secret|token|authorization|api[_ -]?key|cookie",
    re.IGNORECASE,
)

_SECRET_NAME = (
    r"password|passwd|pass|pwd|secret|client[_ -]?secret|secret[_ -]?key|"
    r"token|access[_ -]?token|refresh[_ -]?token|api[_ -]?key|"
    r"authorization|cookie"
)
_HEADER_RE = re.compile(
    r"(?im)(?P<prefix>\b(?:authorization|proxy-authorization|cookie|set-cookie)"
    r"\s*:\s*)[^\r\n]*"
)
_URI_USERINFO_RE = re.compile(
    r"(?i)(?P<prefix>\b[a-z][a-z0-9+.-]*://[^/\s:@]+:)[^@/\s]+@"
)
_DOUBLE_QUOTED_VALUE_RE = re.compile(
    rf"(?i)(?P<prefix>(?<![\w-])[\"']?(?:{_SECRET_NAME})[\"']?"
    r"\s*[:=]\s*)\"(?:\\.|[^\"\r\n])*\""
)
_SINGLE_QUOTED_VALUE_RE = re.compile(
    rf"(?i)(?P<prefix>(?<![\w-])[\"']?(?:{_SECRET_NAME})[\"']?"
    r"\s*[:=]\s*)'(?:\\.|[^'\r\n])*'"
)
_CONNECTION_VALUE_RE = re.compile(
    rf"(?i)(?P<prefix>(?:^|;)\s*(?:{_SECRET_NAME})\s*=\s*)"
    r"[^;\r\n]*(?=;)"
)
_PLAIN_VALUE_RE = re.compile(
    rf"(?i)(?P<prefix>(?<![\w-])[\"']?(?:{_SECRET_NAME})[\"']?"
    r"\s*[:=]\s*)(?!\[REDACTED\])[^\s,;\}\]\)\r\n]+"
)
_AUTH_SCHEME_RE = re.compile(
    r"(?i)(?P<prefix>\b(?:Bearer|Basic)\s+)[A-Za-z0-9._~+/=:-]{4,}"
)


def _truncate_utf8(value: str, limit: int) -> str:
    bounded = max(0, int(limit))
    encoded = value.encode("utf-8")
    if len(encoded) <= bounded:
        return value
    return encoded[:bounded].decode("utf-8", errors="ignore")


def _replace_value(match: re.Match[str]) -> str:
    return f"{match.group('prefix')}{REDACTED}"


def _replace_double_quoted_value(match: re.Match[str]) -> str:
    return f'{match.group("prefix")}\"{REDACTED}\"'


def _replace_single_quoted_value(match: re.Match[str]) -> str:
    return f"{match.group('prefix')}'{REDACTED}'"


def _replace_uri_password(match: re.Match[str]) -> str:
    return f"{match.group('prefix')}{REDACTED}@"


def sanitize_free_text(value: object, *, limit: int = DEFAULT_TEXT_LIMIT) -> str:
    """Redact credential-shaped fragments, then cap the result by UTF-8 bytes."""

    text = str(value or "")
    text = _URI_USERINFO_RE.sub(_replace_uri_password, text)
    text = _HEADER_RE.sub(_replace_value, text)
    text = _DOUBLE_QUOTED_VALUE_RE.sub(_replace_double_quoted_value, text)
    text = _SINGLE_QUOTED_VALUE_RE.sub(_replace_single_quoted_value, text)
    text = _CONNECTION_VALUE_RE.sub(_replace_value, text)
    text = _PLAIN_VALUE_RE.sub(_replace_value, text)
    text = _AUTH_SCHEME_RE.sub(_replace_value, text)
    return _truncate_utf8(text, limit)


def redact_sensitive_value(
    value: object,
    key: str = "",
    *,
    text_limit: int = DEFAULT_TEXT_LIMIT,
) -> object:
    """Recursively redact secret keys and credential fragments in string values."""

    if key and SECRET_KEY_RE.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {
            str(item_key): redact_sensitive_value(
                item,
                str(item_key),
                text_limit=text_limit,
            )
            for item_key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            redact_sensitive_value(item, text_limit=text_limit)
            for item in value
        ]
    if isinstance(value, str):
        return sanitize_free_text(value, limit=text_limit)
    return value
