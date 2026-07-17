"""Structured operational events, redaction, and incident correlation."""

from __future__ import annotations

import hashlib
import json
import re
import traceback
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from . import storage_settings
from .sqlite_store import SqliteStore


SEVERITIES = ("info", "warning", "error", "critical")
SECRET_KEY_RE = re.compile(
    r"password|pass|pwd|secret|token|authorization|api[_-]?key|cookie",
    re.IGNORECASE,
)
SCALAR_TEXT_LIMIT = 8 * 1024
TRACEBACK_TEXT_LIMIT = 32 * 1024
INCIDENT_NOTIFICATION_WINDOW = timedelta(minutes=15)
LIVE_EVENT_RETENTION = timedelta(hours=24)

EventMirror = Callable[[dict[str, object]], object]
_event_mirror: EventMirror | None = None


def _truncate_utf8(value: str, limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore")


def _text(value: object) -> str:
    return _truncate_utf8(str(value or "").strip(), SCALAR_TEXT_LIMIT)


def _utc_datetime(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _iso_utc(value: datetime | None = None) -> str:
    return _utc_datetime(value).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _utc_datetime(value)
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc_datetime(parsed)


def redact_value(value: object, key: str = "") -> object:
    """Recursively redact secret-bearing keys and bound scalar strings."""

    if key and SECRET_KEY_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return _truncate_utf8(value, SCALAR_TEXT_LIMIT)
    return value


def register_event_mirror(callback: EventMirror | None) -> None:
    """Register the single best-effort fallback mirror for structured events."""

    global _event_mirror
    _event_mirror = callback


def _mirror_event(event: dict[str, object]) -> None:
    callback = _event_mirror
    if callback is None:
        return
    try:
        callback(dict(event))
    except Exception:
        # The mirror is a last-resort sink and must never recurse or mask SQLite.
        pass


def observability_store() -> SqliteStore:
    """Resolve and initialize the configured observability database."""

    store = SqliteStore(storage_settings.resolve_sqlite_path())
    store.initialize()
    return store


def emit_event(
    *,
    severity: str,
    event_type: str,
    summary: str,
    module: str = "",
    stage: str = "",
    username: str = "",
    ean: str = "",
    product_id: str = "",
    slot: str = "",
    job_id: str = "",
    correlation_id: str = "",
    recommended_action: str = "",
    details: object = None,
    exception: BaseException | None = None,
    strict: bool = False,
) -> dict[str, object]:
    """Normalize, redact, and persist one operational event."""

    normalized_severity = _text(severity).lower()
    if normalized_severity not in SEVERITIES:
        raise ValueError(f"Unsupported event severity: {severity!r}")

    exception_type = ""
    traceback_text = ""
    if exception is not None:
        exception_type = _text(type(exception).__name__)
        traceback_text = _truncate_utf8(
            "".join(
                traceback.format_exception(
                    type(exception), exception, exception.__traceback__
                )
            ),
            TRACEBACK_TEXT_LIMIT,
        )

    safe_details = redact_value(details if isinstance(details, dict) else {})
    event: dict[str, object] = {
        "id": f"evt-{uuid.uuid4().hex}",
        "created_at": _iso_utc(),
        "severity": normalized_severity,
        "event_type": _text(event_type),
        "module": _text(module),
        "stage": _text(stage),
        "username": _text(username),
        "ean": _text(ean),
        "product_id": _text(product_id),
        "slot": _text(slot),
        "job_id": _text(job_id),
        "correlation_id": _text(correlation_id),
        "incident_id": "",
        "summary": _text(summary),
        "recommended_action": _text(recommended_action),
        "details": safe_details,
        "exception_type": exception_type,
        "traceback_text": traceback_text,
    }
    if normalized_severity == "info":
        try:
            return observability_store().append_operational_event(event)
        except Exception:
            _mirror_event(event)
            if strict:
                raise
            return event
    try:
        incident = coalesce_incident(event)
    except Exception:
        _mirror_event(event)
        if strict:
            raise
        return event
    if incident is None:
        return event
    safe_details = event.get("details")
    suppress = isinstance(safe_details, dict) and bool(
        safe_details.get("suppress_notifications")
    )
    if suppress or not bool(incident.get("notification_due")):
        return event
    try:
        from .notification_service import queue_incident_notification

        delivery = queue_incident_notification(event, incident)
        if delivery is None:
            raise RuntimeError("notification queue did not persist a delivery")
    except Exception:
        _release_notification_claim(incident)
        _emit_queue_failure_diagnostic(event, incident)
    return event


def _release_notification_claim(incident: dict[str, object]) -> None:
    claimed_at = _text(incident.get("notification_claim_at"))
    if not claimed_at:
        return
    try:
        store = observability_store()
        release = getattr(store, "release_incident_notification", None)
        if callable(release):
            release(
                _text(incident.get("id")),
                claimed_at=claimed_at,
                previous_at=_text(
                    incident.get("notification_previous_window_at")
                ),
            )
    except Exception:
        pass


def _emit_queue_failure_diagnostic(
    event: dict[str, object], incident: dict[str, object]
) -> None:
    try:
        emit_event(
            severity="error",
            event_type="notification.queue_failed",
            module="notifications",
            stage="queue",
            job_id=_text(event.get("job_id")),
            correlation_id=_text(event.get("correlation_id")),
            summary="Nie udało się trwale zapisać powiadomienia e-mail.",
            recommended_action="Sprawdź stan SQLite i konfigurację powiadomień.",
            details={
                "code": "notification_queue_unavailable",
                "incident_id": _text(incident.get("id")),
                "event_id": _text(event.get("id")),
                "suppress_notifications": True,
            },
        )
    except Exception:
        pass


def record_job(job: dict[str, object]) -> dict[str, object]:
    """Redact and persist one durable process-job snapshot."""

    safe_job = redact_value(job)
    if not isinstance(safe_job, dict):
        safe_job = {}
    return observability_store().upsert_job_run(safe_job)


def _fingerprint_value(value: object) -> str:
    return _text(value).casefold()


def _incident_fingerprint(event: dict[str, object]) -> str:
    stable = {
        "event_type": _fingerprint_value(event.get("event_type")),
        "module": _fingerprint_value(event.get("module")),
        "stage": _fingerprint_value(event.get("stage")),
        "exception_type": _fingerprint_value(event.get("exception_type")),
        "ean": _fingerprint_value(event.get("ean")),
        "slot": _fingerprint_value(event.get("slot")),
    }
    encoded = json.dumps(
        stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _incident_context_payload(event: dict[str, object]) -> dict[str, object]:
    context: dict[str, object] = {}
    for key in (
        "module",
        "stage",
        "username",
        "ean",
        "product_id",
        "slot",
        "summary",
        "recommended_action",
    ):
        value = _text(event.get(key))
        if value:
            context[key] = value
    details = redact_value(event.get("details"))
    if isinstance(details, dict) and details:
        context["details"] = details
    return context


def _higher_severity(first: object, second: object) -> str:
    left = _text(first).lower()
    right = _text(second).lower()
    left_rank = SEVERITIES.index(left) if left in SEVERITIES else -1
    right_rank = SEVERITIES.index(right) if right in SEVERITIES else -1
    return left if left_rank >= right_rank else right


def coalesce_incident(
    event: dict[str, object], now: datetime | None = None
) -> dict[str, object] | None:
    """Create or update the open incident matching a stable event fingerprint."""

    severity = _text(event.get("severity")).lower()
    if severity == "info":
        return None

    current = _utc_datetime(now)
    current_iso = _iso_utc(current)
    fingerprint = _incident_fingerprint(event)
    store = observability_store()
    latest_context = _incident_context_payload(event)
    atomic_coalesce = getattr(store, "coalesce_incident", None)
    if callable(atomic_coalesce):
        incident_result = dict(
            atomic_coalesce(
                {
                    "id": f"inc-{uuid.uuid4().hex}",
                    "fingerprint": fingerprint,
                    "severity": severity,
                    "event_type": _text(event.get("event_type")),
                    "status": "open",
                    "first_seen_at": current_iso,
                    "last_seen_at": current_iso,
                    "occurrence_count": 1,
                    "first_event_id": _text(event.get("id")),
                    "latest_event_id": _text(event.get("id")),
                    "job_id": _text(event.get("job_id")),
                    "correlation_id": _text(event.get("correlation_id")),
                    "notification_window_at": current_iso,
                    "context": latest_context,
                }
            )
        )
        notification_due = bool(incident_result.get("notification_due"))
    else:
        incident_result, notification_due = _coalesce_with_legacy_store(
            store,
            event,
            fingerprint=fingerprint,
            severity=severity,
            current=current,
            current_iso=current_iso,
            latest_context=latest_context,
        )

    incident_result["notification_due"] = notification_due

    event["incident_id"] = _text(incident_result.get("id"))
    persisted_event = redact_value(event)
    if not isinstance(persisted_event, dict):
        persisted_event = {}
    persisted_event.pop("notification_due", None)
    store.append_operational_event(persisted_event)
    return incident_result


def _coalesce_with_legacy_store(
    store: object,
    event: dict[str, object],
    *,
    fingerprint: str,
    severity: str,
    current: datetime,
    current_iso: str,
    latest_context: dict[str, object],
) -> tuple[dict[str, object], bool]:
    """Keep lightweight test doubles compatible; SQLite uses its atomic method."""

    existing = store.find_open_incident(fingerprint)
    notification_due = existing is None
    notification_previous_window_at = ""
    notification_claim_at = current_iso if existing is None else ""

    if existing is None:
        incident: dict[str, object] = {
            "id": f"inc-{uuid.uuid4().hex}",
            "fingerprint": fingerprint,
            "severity": severity,
            "event_type": _text(event.get("event_type")),
            "status": "open",
            "first_seen_at": current_iso,
            "last_seen_at": current_iso,
            "occurrence_count": 1,
            "first_event_id": _text(event.get("id")),
            "latest_event_id": _text(event.get("id")),
            "job_id": _text(event.get("job_id")),
            "correlation_id": _text(event.get("correlation_id")),
            "notification_window_at": current_iso,
            "context": latest_context,
        }
    else:
        incident = dict(existing)
        notification_previous_window_at = _text(
            incident.get("notification_window_at")
        )
        previous_context = incident.get("context")
        merged_context = (
            dict(previous_context) if isinstance(previous_context, dict) else {}
        )
        merged_context.update(latest_context)
        try:
            occurrence_count = int(incident.get("occurrence_count") or 0) + 1
        except (TypeError, ValueError):
            occurrence_count = 2
        incident.update(
            {
                "severity": _higher_severity(incident.get("severity"), severity),
                "last_seen_at": current_iso,
                "occurrence_count": occurrence_count,
                "latest_event_id": _text(event.get("id")),
                "context": merged_context,
            }
        )
        latest_job_id = _text(event.get("job_id"))
        latest_correlation_id = _text(event.get("correlation_id"))
        if latest_job_id or latest_correlation_id:
            incident["job_id"] = latest_job_id
            incident["correlation_id"] = latest_correlation_id
        window_started = _parse_datetime(incident.get("notification_window_at"))
        if window_started is None or current - window_started >= INCIDENT_NOTIFICATION_WINDOW:
            notification_due = True
            incident["notification_window_at"] = current_iso
            notification_claim_at = current_iso

    persisted = store.upsert_incident(incident)
    incident_result = dict(persisted)
    incident_result["notification_claim_at"] = notification_claim_at
    incident_result["notification_previous_window_at"] = (
        notification_previous_window_at
    )
    return incident_result, notification_due


def _correlated_events(incident: dict[str, object]) -> list[dict[str, object]]:
    store = observability_store()
    job_id = _text(incident.get("job_id"))
    correlation_id = _text(incident.get("correlation_id"))
    if not job_id and not correlation_id:
        return []

    items: list[dict[str, object]] = []
    cursor = ""
    seen_cursors: set[str] = set()
    while True:
        query: dict[str, object] = {"cursor": cursor, "limit": 20}
        if job_id:
            query["job_id"] = job_id
        else:
            query["correlation_id"] = correlation_id
        page = store.query_operational_events(**query)
        page_items = page.get("items", []) if isinstance(page, dict) else []
        for item in page_items if isinstance(page_items, list) else []:
            if not isinstance(item, dict):
                continue
            if job_id and _text(item.get("job_id")) != job_id:
                continue
            if not job_id and _text(item.get("correlation_id")) != correlation_id:
                continue
            items.append(dict(item))
        next_cursor = _text(page.get("next_cursor")) if isinstance(page, dict) else ""
        if not next_cursor or next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return items


def _bounded_context_limit(value: object) -> int:
    try:
        return max(0, min(5, int(value)))
    except (TypeError, ValueError):
        return 5


def incident_context(
    incident: dict[str, object], *, before_limit: int = 5, after_limit: int = 5
) -> dict[str, list[dict[str, object]]]:
    """Return chronological before/problem/after events from one correlation."""

    events = _correlated_events(incident)
    events.sort(key=lambda item: (_text(item.get("created_at")), _text(item.get("id"))))
    first_id = _text(incident.get("first_event_id"))
    latest_id = _text(incident.get("latest_event_id"))
    positions = {_text(item.get("id")): index for index, item in enumerate(events)}
    if latest_id not in positions:
        return {"before": [], "problem": [], "after": []}
    latest_index = positions[latest_id]
    first_index = positions.get(first_id, latest_index)
    if latest_index < first_index:
        first_index, latest_index = latest_index, first_index
    before_count = _bounded_context_limit(before_limit)
    after_count = _bounded_context_limit(after_limit)
    return {
        "before": events[max(0, first_index - before_count) : first_index],
        "problem": events[first_index : latest_index + 1],
        "after": events[latest_index + 1 : latest_index + 1 + after_count],
    }


def prune_live_events(now: datetime | None = None) -> int:
    """Remove informational live-console events older than 24 hours."""

    boundary = _utc_datetime(now) - LIVE_EVENT_RETENTION
    return observability_store().prune_info_events(_iso_utc(boundary))
