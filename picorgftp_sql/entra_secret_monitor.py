"""Durable, redacted Microsoft Entra client-secret expiry monitoring."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from .email_settings import EMAIL_SETTINGS_KEY, normalize_email_settings
from .entra_secret_expiry import fetch_entra_secret_expiry
from .observability import emit_event, observability_store
from .redaction import sanitize_free_text


REMINDER_THRESHOLDS = (14, 7, 3, 2, 1)
STATUS_CACHE_FOR = timedelta(hours=24)
_PUBLIC_FIELDS = (
    "tenant_id", "client_id", "status", "expires_at", "credential_name",
    "application_name", "source", "last_checked_at", "last_success_at",
    "error_code", "error_message",
)


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _load_email_settings() -> dict[str, object]:
    from . import config

    configured = config.load_config(interactive=False)
    return normalize_email_settings(configured.get(EMAIL_SETTINGS_KEY, {}))


def _store():
    return observability_store()


def _identity(settings: Mapping[str, object]) -> tuple[str, str, str]:
    normalized = normalize_email_settings(settings)
    entra = normalized.get("entra")
    source = entra if isinstance(entra, Mapping) else {}
    return tuple(str(source.get(key) or "").strip() for key in ("tenant_id", "client_id", "client_secret"))


def _empty_status(tenant_id: str = "", client_id: str = "") -> dict[str, str]:
    return {
        "tenant_id": tenant_id, "client_id": client_id, "status": "unavailable",
        "expires_at": "", "credential_name": "", "application_name": "",
        "source": "saved", "last_checked_at": "", "last_success_at": "",
        "error_code": "malformed_settings", "error_message": "Ustaw poprawne dane Microsoft Entra.",
    }


def _public(value: Mapping[str, object], *, source: str | None = None) -> dict[str, str]:
    projected = {field: str(value.get(field) or "") for field in _PUBLIC_FIELDS}
    if source is not None:
        projected["source"] = source
    return projected


def _safe_graph_text(value: object, *sensitive_values: str) -> str:
    text = value if isinstance(value, str) else ""
    for sensitive in sensitive_values:
        if sensitive:
            text = text.replace(sensitive, "[REDACTED]")
    return re.sub(r"(?i)\b\S*(?:secret|token)\S*\b", "[REDACTED]", sanitize_free_text(text, limit=512)).strip()


def _is_fresh(status: Mapping[str, object], now: datetime) -> bool:
    checked = _parse(status.get("last_checked_at"))
    return checked is not None and now - checked < STATUS_CACHE_FOR


def entra_secret_status() -> dict[str, str]:
    """Return only the persisted public Entra expiry projection."""

    tenant_id, client_id, _secret = _identity(_load_email_settings())
    if not tenant_id or not client_id:
        return _empty_status(tenant_id, client_id)
    stored = _store().get_entra_secret_status(tenant_id, client_id)
    return _public(stored, source="saved") if stored else _empty_status(tenant_id, client_id)


def refresh_entra_secret_status(*, force: bool = False, now: datetime | None = None) -> dict:
    """Refresh Graph expiry data, preserving a prior successful result on failure."""

    current = _utc_now(now)
    settings = _load_email_settings()
    tenant_id, client_id, client_secret = _identity(settings)
    if not tenant_id or not client_id or not client_secret:
        return _empty_status(tenant_id, client_id)
    store = _store()
    saved = store.get_entra_secret_status(tenant_id, client_id)
    if saved and not force and _is_fresh(saved, current):
        return _public(saved, source="saved")

    graph = fetch_entra_secret_expiry(
        {"tenant_id": tenant_id, "client_id": client_id, "client_secret": client_secret}, now=current
    )
    code = str(graph.get("code") or "transport_unavailable")
    graph_ok = graph.get("status") == "ok" and code == "ok"
    if graph_ok:
        persisted = store.upsert_entra_secret_status({
            "tenant_id": tenant_id, "client_id": client_id, "status": "ok",
            "expires_at": graph.get("expires_at"),
            "credential_name": _safe_graph_text(graph.get("credential_name"), client_secret),
            "credential_key_id": graph.get("credential_key_id"),
            "source": "microsoft_graph", "last_checked_at": _iso(current),
            "last_success_at": _iso(current), "error_code": "", "error_message": "",
            "application_name": _safe_graph_text(graph.get("application_name"), client_secret),
        })
        return _public(persisted, source="microsoft_graph")

    error_message = str(graph.get("error_message") or "Nie można teraz odczytać statusu Microsoft Entra.")
    was_successful = bool(saved and saved.get("status") == "ok" and saved.get("expires_at"))
    persisted = store.upsert_entra_secret_status({
        "tenant_id": tenant_id, "client_id": client_id,
        "status": "ok" if was_successful else "unavailable",
        "expires_at": saved.get("expires_at", "") if was_successful else "",
        "credential_name": saved.get("credential_name", "") if was_successful else "",
        "application_name": saved.get("application_name", "") if was_successful else "",
        "source": "cached" if was_successful else "microsoft_graph",
        "last_checked_at": _iso(current),
        "last_success_at": saved.get("last_success_at", "") if was_successful else "",
        "error_code": code, "error_message": error_message,
    })
    if code == "permission_required" and (not saved or saved.get("error_code") != code or saved.get("status") != persisted.get("status")):
        emit_event(
            severity="warning", event_type="entra.secret_expiry_permission_required",
            summary="Brak uprawnień do odczytu terminu ważności Client Secret.",
            module="entra", stage="secret_expiry", username="",
            recommended_action="Dodaj Application.Read.All i zatwierdź admin consent.",
            details={"code": code, "suppress_notifications": True},
        )
    return _public(persisted, source="cached" if was_successful else "microsoft_graph")


def _claim_key(client_id: str, expires_at: str) -> str:
    return hashlib.sha256(f"{client_id}|{expires_at}".encode("utf-8")).hexdigest()


def _emit_due(status: Mapping[str, str], threshold: int, *, expired: bool) -> None:
    event_type = "entra.secret_expired" if expired else "entra.secret_expiry_due"
    summary = "Client Secret Microsoft Entra wygasł." if expired else "Client Secret Microsoft Entra wkrótce wygaśnie."
    details: dict[str, object] = {"expires_at": status["expires_at"], "status": status["status"]}
    if not expired:
        details["threshold_days"] = threshold
    emit_event(
        severity="critical", event_type=event_type, summary=summary,
        module="entra", stage="secret_expiry", username="",
        recommended_action="Utwórz nowy Client Secret i zaktualizuj konfigurację.", details=details,
    )


def process_due_entra_secret_reminders(*, now: datetime | None = None) -> int:
    """Claim and emit at most one due reminder for the active application."""

    current = _utc_now(now)
    status = refresh_entra_secret_status(now=current)
    if status.get("status") != "ok":
        return 0
    expires = _parse(status.get("expires_at"))
    tenant_id, client_id, _secret = _identity(_load_email_settings())
    if expires is None or not tenant_id or not client_id:
        return 0
    store = _store()
    expires_at = status["expires_at"]
    key = _claim_key(client_id, expires_at)
    if expires <= current:
        if store.claim_entra_secret_reminder(tenant_id, client_id, key, expires_at, 0, _iso(current)):
            _emit_due(status, 0, expired=True)
            return 1
        return 0
    remaining_seconds = (expires - current).total_seconds()
    for threshold in sorted(REMINDER_THRESHOLDS):
        if remaining_seconds > threshold * 86_400:
            continue
        if store.claim_entra_secret_reminder(tenant_id, client_id, key, expires_at, threshold, _iso(current)):
            _emit_due(status, threshold, expired=False)
            return 1
        # This is the current nearest due threshold, already emitted by another
        # monitor pass.  Never back-fill a less urgent historical threshold.
        return 0
    return 0
