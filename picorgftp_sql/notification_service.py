"""Durable incident e-mail queue, recipient rules, and background worker."""

from __future__ import annotations

import html
import json
import re
import threading
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from .email_delivery import MailMessage, MailTransport, build_transport
from .email_settings import (
    EMAIL_SETTINGS_KEY,
    normalize_email_address,
    normalize_email_settings,
)


WORKER_POLL_SECONDS = 2.0
WORKER_BATCH_LIMIT = 20
WORKER_STOP_TIMEOUT_SECONDS = 23.0
STALE_SENDING_AFTER = timedelta(minutes=5)
OUTBOX_DONE_RETENTION = timedelta(days=7)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    current = value
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _text(value: object, limit: int = 2_000) -> str:
    return str(value or "").strip()[:limit]


def _header_text(value: object, limit: int = 300) -> str:
    return " ".join(_text(value, limit).splitlines())[:limit]


def _default_settings_loader() -> dict[str, object]:
    from . import config

    configured = config.load_config(interactive=False)
    return normalize_email_settings(configured.get(EMAIL_SETTINGS_KEY, {}))


def _default_user_lookup(username: str) -> dict[str, object] | None:
    from .web_data import find_user

    return find_user(username)


def _default_event_emitter(**kwargs: object) -> object:
    from .observability import emit_event

    return emit_event(**kwargs)


def resolve_recipients(
    event: Mapping[str, object],
    settings: Mapping[str, object],
    user_lookup: Callable[[str], Mapping[str, object] | None],
    *,
    tolerate_lookup_errors: bool = True,
) -> list[str]:
    """Resolve, validate and case-insensitively deduplicate one severity rule."""

    severity = _text(event.get("severity")).lower()
    rules = settings.get("rules")
    rule = rules.get(severity) if isinstance(rules, Mapping) else None
    if not isinstance(rule, Mapping) or not bool(rule.get("enabled")):
        return []

    raw_recipients = rule.get("recipients", [])
    if isinstance(raw_recipients, str):
        candidates: list[object] = raw_recipients.split(",")
    elif isinstance(raw_recipients, (list, tuple, set)):
        candidates = list(raw_recipients)
    else:
        candidates = []

    if bool(rule.get("include_actor")):
        username = _text(event.get("username"))
        try:
            user = user_lookup(username) if username else None
        except Exception:
            if not tolerate_lookup_errors:
                raise
            user = None
        if isinstance(user, Mapping):
            candidates.append(user.get("email", ""))

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            address = normalize_email_address(candidate)
        except ValueError:
            continue
        identity = address.casefold()
        if not address or identity in seen:
            continue
        seen.add(identity)
        result.append(address)
    return result


_MAIL_CONTEXT_BLOCKED_KEY = re.compile(
    r"traceback|config|authorization|cookie|headers?|request_body|raw_content",
    re.IGNORECASE,
)


def _project_mail_context(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _project_mail_context(item)
            for key, item in value.items()
            if not _MAIL_CONTEXT_BLOCKED_KEY.search(str(key))
        }
    if isinstance(value, list):
        return [_project_mail_context(item) for item in value[:50]]
    return value


def _safe_details(event: Mapping[str, object]) -> str:
    from .observability import redact_value

    details = redact_value(event.get("details", {}))
    if not isinstance(details, dict):
        return ""
    details.pop("suppress_notifications", None)
    return json.dumps(
        _project_mail_context(details),
        ensure_ascii=False,
        sort_keys=True,
        separators=(", ", ": "),
    )[:4_000]


def _safe_incident_context(incident: Mapping[str, object]) -> str:
    from .observability import redact_value

    context = redact_value(incident.get("context", {}))
    if not isinstance(context, dict):
        return ""
    return json.dumps(
        _project_mail_context(context),
        ensure_ascii=False,
        sort_keys=True,
        separators=(", ", ": "),
    )[:4_000]


def _message_payload(
    event: Mapping[str, object], incident: Mapping[str, object], message_id: str
) -> dict[str, str]:
    severity = _text(event.get("severity")).upper()
    summary = _text(event.get("summary")) or "Zdarzenie wymaga uwagi"
    subject = _header_text(f"[PicOrgFTP-SQL][{severity}] {summary}")
    try:
        occurrence_count = max(1, int(incident.get("occurrence_count") or 1))
    except (TypeError, ValueError):
        occurrence_count = 1
    rows = [
        ("Poziom", severity),
        ("Typ", _text(event.get("event_type"))),
        ("Czas", _text(event.get("created_at"))),
        ("Incydent", _text(incident.get("id"))),
        ("Liczba wystąpień", str(occurrence_count)),
        ("Zadanie", _text(event.get("job_id"))),
        ("EAN", _text(event.get("ean"))),
        ("Użytkownik", _text(event.get("username"))),
        ("Podsumowanie", summary),
        ("Zalecane działanie", _text(event.get("recommended_action"))),
        ("Szczegóły", _safe_details(event)),
        ("Kontekst incydentu", _safe_incident_context(incident)),
    ]
    populated = [(label, value) for label, value in rows if value]
    text_body = "\n".join(f"{label}: {value}" for label, value in populated)
    html_rows = "".join(
        "<tr><th style=\"text-align:left;vertical-align:top\">"
        f"{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"
        for label, value in populated
    )
    return {
        "message_id": message_id,
        "subject": subject,
        "text_body": text_body,
        "html_body": f"<h2>Incydent PicOrgFTP-SQL</h2><table>{html_rows}</table>",
    }


def _runtime_context_lines(
    context: Mapping[str, object],
) -> list[tuple[str, list[str]]]:
    from .observability import redact_value

    sections: list[tuple[str, list[str]]] = []
    for key, label, cap in (
        ("before", "Przed", 3),
        ("problem", "Problem", 5),
        ("after", "Po", 3),
    ):
        raw_items = context.get(key)
        items = raw_items if isinstance(raw_items, list) else []
        lines: list[str] = []
        for raw in items[:cap]:
            safe = redact_value(raw)
            if not isinstance(safe, Mapping):
                continue
            parts = [
                _text(safe.get("created_at"), 40),
                _text(safe.get("severity"), 20).upper(),
                _text(safe.get("summary"), 500),
            ]
            details = safe.get("details")
            if isinstance(details, Mapping):
                projected = _project_mail_context(dict(details))
                if projected:
                    parts.append(
                        json.dumps(
                            projected,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(", ", ": "),
                        )[:1_000]
                    )
            line = " | ".join(part for part in parts if part)
            if line:
                lines.append(line)
        sections.append((label, lines))
    return sections


def _escape_html_bounded(value: object, budget: int) -> str:
    pieces: list[str] = []
    used = 0
    for character in str(value or ""):
        escaped = html.escape(character)
        if used + len(escaped) > max(0, budget):
            break
        pieces.append(escaped)
        used += len(escaped)
    return "".join(pieces)


def _html_context_section(label: str, lines: list[str], budget: int) -> str:
    opening = f"<section><h3>{html.escape(label)}</h3>"
    closing = "</section>"
    empty = "<p>Brak zdarzeń.</p>"
    if not lines:
        return opening + empty + closing
    list_open, list_close = "<ul>", "</ul>"
    fixed_size = len(opening) + len(list_open) + len(list_close) + len(closing)
    remaining = max(0, budget - fixed_size)
    items: list[str] = []
    for index, line in enumerate(lines):
        item_tags_size = len("<li></li>")
        if remaining <= item_tags_size:
            break
        remaining_items = max(1, len(lines) - index)
        text_budget = max(0, remaining // remaining_items - item_tags_size)
        escaped = _escape_html_bounded(line, text_budget)
        item = f"<li>{escaped}</li>"
        if len(item) > remaining:
            break
        items.append(item)
        remaining -= len(item)
    if not items:
        return opening + empty + closing
    return opening + list_open + "".join(items) + list_close + closing


def _text_context_section(label: str, lines: list[str], budget: int) -> str:
    heading = f"{label}:"
    if not lines:
        return f"{heading} Brak zdarzeń."
    remaining = max(0, budget - len(heading) - 1)
    items: list[str] = []
    for index, line in enumerate(lines):
        prefix = "- "
        separator_size = 1 if items else 0
        if remaining <= len(prefix) + separator_size:
            break
        remaining_items = max(1, len(lines) - index)
        line_budget = max(
            0,
            (remaining - separator_size) // remaining_items - len(prefix),
        )
        item = prefix + str(line or "")[:line_budget]
        consumed = separator_size + len(item)
        if consumed > remaining:
            break
        items.append(item)
        remaining -= consumed
    if not items:
        return f"{heading} Brak zdarzeń."
    return heading + "\n" + "\n".join(items)


def _append_runtime_context(
    message: Mapping[str, object], context: Mapping[str, object]
) -> dict[str, str]:
    enriched = {
        "message_id": _text(message.get("message_id")),
        "subject": _text(message.get("subject"), 300),
        "text_body": _text(message.get("text_body"), 10_000),
        "html_body": _text(message.get("html_body"), 20_000),
    }
    sections = _runtime_context_lines(context)
    text_sections = []
    html_sections = []
    text_section_budgets = {"Przed": 1_200, "Problem": 2_400, "Po": 1_200}
    section_budgets = {"Przed": 1_800, "Problem": 3_200, "Po": 1_800}
    for label, lines in sections:
        text_sections.append(
            _text_context_section(label, lines, text_section_budgets[label])
        )
        html_sections.append(
            _html_context_section(label, lines, section_budgets[label])
        )
    text_context = "\n\nKontekst zdarzeń\n" + "\n\n".join(text_sections)
    html_context = (
        "<div><h2>Kontekst zdarzeń</h2>"
        + "".join(html_sections)
        + "</div>"
    )
    text_base_budget = max(0, 10_000 - len(text_context))
    enriched["text_body"] = enriched["text_body"][:text_base_budget] + text_context
    html_base_budget = max(0, 20_000 - len(html_context))
    html_base = enriched["html_body"]
    if len(html_base) > html_base_budget:
        pre_open, pre_close = "<pre>", "</pre>"
        excerpt_budget = max(0, html_base_budget - len(pre_open) - len(pre_close))
        html_base = (
            pre_open
            + _escape_html_bounded(html_base, excerpt_budget)
            + pre_close
        )
    enriched["html_body"] = html_base + html_context
    return enriched


def _channel_sender(
    channel: str, settings: Mapping[str, object]
) -> tuple[str, str]:
    channel_settings = settings.get(channel)
    values = channel_settings if isinstance(channel_settings, Mapping) else {}
    address = _text(values.get("from_address"))
    if channel == "smtp" and not address:
        address = _text(values.get("username"))
    name = _text(values.get("from_name")) or "PicOrgFTP-SQL"
    return address, name


def _safe_attempt(channel: str, result: Mapping[str, object]) -> dict[str, object]:
    status = _text(result.get("status")).lower()
    if status not in {"sent", "partial", "refused"}:
        status = "sent"
    attempt: dict[str, object] = {"channel": channel, "status": status}
    for key in ("status_code", "elapsed_ms"):
        value = result.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            attempt[key] = max(0, value)
    if status in {"partial", "refused"}:
        for key in ("accepted_count", "refused_count"):
            value = result.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                attempt[key] = max(0, value)
        raw_codes = result.get("refusal_codes")
        if isinstance(raw_codes, (list, tuple, set)):
            attempt["refusal_codes"] = sorted(
                {
                    max(0, value)
                    for value in raw_codes
                    if isinstance(value, int) and not isinstance(value, bool)
                }
            )[:20]
    return attempt


def _failure_attempt(
    channel: str, *, code: str, category: str, message: str
) -> dict[str, object]:
    return {
        "channel": channel,
        "status": "error",
        "code": code,
        "category": category,
        "message": message,
    }


def _verified_refused_recipients(
    message: MailMessage,
    result: Mapping[str, object],
) -> list[str] | None:
    """Return a verified refused subset or None when routing is ambiguous."""

    if result.get("routing_known") is not True:
        return None
    original = [_text(address) for address in message.recipients]
    identities = [address.casefold() for address in original]
    if not original or any(not identity for identity in identities):
        return None
    if len(set(identities)) != len(identities):
        return None
    allowed = dict(zip(identities, original))
    raw_refused = result.get("refused_recipients")
    if not isinstance(raw_refused, list) or not raw_refused:
        return None
    refused: list[str] = []
    seen: set[str] = set()
    for raw_address in raw_refused:
        if not isinstance(raw_address, str):
            return None
        identity = _text(raw_address).casefold()
        address = allowed.get(identity)
        if not address or identity in seen:
            return None
        seen.add(identity)
        refused.append(address)
    accepted_count = result.get("accepted_count")
    refused_count = result.get("refused_count")
    if (
        not isinstance(accepted_count, int)
        or isinstance(accepted_count, bool)
        or not isinstance(refused_count, int)
        or isinstance(refused_count, bool)
    ):
        return None
    if refused_count != len(refused):
        return None
    if accepted_count != len(original) - refused_count:
        return None
    status = _text(result.get("status")).lower()
    if status == "partial" and not (0 < refused_count < len(original)):
        return None
    if status == "refused" and not (
        refused_count == len(original) and accepted_count == 0
    ):
        return None
    return refused if status in {"partial", "refused"} else None


class NotificationService:
    """Coordinate durable queue state without exposing transport secrets."""

    def __init__(
        self,
        *,
        store: object,
        transport_factory: Callable[[str, Mapping[str, object]], MailTransport] = build_transport,
        settings_loader: Callable[[], Mapping[str, object]] = _default_settings_loader,
        user_lookup: Callable[[str], Mapping[str, object] | None] = _default_user_lookup,
        event_emitter: Callable[..., object] = _default_event_emitter,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.store = store
        self.transport_factory = transport_factory
        self.settings_loader = settings_loader
        self.user_lookup = user_lookup
        self.event_emitter = event_emitter
        self.now = now

    def _settings(self) -> dict[str, object]:
        return normalize_email_settings(self.settings_loader())

    def queue_incident_notification(
        self, event: Mapping[str, object], incident: Mapping[str, object]
    ) -> dict[str, object] | None:
        if not bool(incident.get("notification_due")):
            return None
        details = event.get("details")
        if isinstance(details, Mapping) and bool(details.get("suppress_notifications")):
            return None
        severity = _text(event.get("severity")).lower()
        if severity not in {"warning", "error", "critical"}:
            return None

        settings = self._settings()
        recipients = resolve_recipients(event, settings, self.user_lookup)
        created_at = _iso_utc(self.now())
        delivery_id = f"delivery-{uuid.uuid4().hex}"
        message_id = f"{_text(incident.get('id')) or 'incident'}-{uuid.uuid4().hex}"
        message = _message_payload(event, incident, message_id)
        record: dict[str, object] = {
            "id": delivery_id,
            "incident_id": _text(incident.get("id")),
            "event_id": _text(event.get("id")),
            "severity": severity,
            "status": "pending" if recipients else "skipped",
            "primary_channel": _text(settings.get("primary_channel")).lower(),
            "used_channel": "",
            "recipients": recipients,
            "message": message,
            "attempts": [],
            "created_at": created_at,
            "updated_at": created_at,
            "next_attempt_at": "",
        }
        return self.store.enqueue_notification_delivery(record)

    def process_notification_intent(self, intent_id: str) -> bool:
        """Materialize one durable outbox intent, leaving transient failures pending."""

        try:
            context = self.store.notification_intent_context(_text(intent_id))
            if not isinstance(context, Mapping):
                return False
            event = context.get("event")
            incident = context.get("incident")
            if not isinstance(event, Mapping):
                return False
            incident_values = incident if isinstance(incident, Mapping) else {}
            settings = self._settings()
            recipients = resolve_recipients(
                event,
                settings,
                self.user_lookup,
                tolerate_lookup_errors=False,
            )
            severity = _text(event.get("severity")).lower()
            completed_at = _iso_utc(self.now())
            if severity == "info" and not recipients:
                self.store.materialize_notification_intent(
                    _text(intent_id), delivery=None, completed_at=completed_at
                )
                return True
            event_id = _text(event.get("id"))
            message_id = f"notify-{event_id}"
            delivery_id = f"delivery-{event_id}"
            delivery: dict[str, object] = {
                "id": delivery_id,
                "incident_id": _text(incident_values.get("id")),
                "event_id": event_id,
                "severity": severity,
                "status": "pending" if recipients else "skipped",
                "primary_channel": _text(settings.get("primary_channel")).lower(),
                "used_channel": "",
                "recipients": recipients,
                "message": _message_payload(event, incident_values, message_id),
                "attempts": [],
                "created_at": completed_at,
                "updated_at": completed_at,
                "next_attempt_at": "",
            }
            self.store.materialize_notification_intent(
                _text(intent_id), delivery=delivery, completed_at=completed_at
            )
            return True
        except Exception:
            # The source intent remains pending; diagnostics here would recurse.
            return False

    def process_notification_intents(self, limit: int = WORKER_BATCH_LIMIT) -> int:
        processed = 0
        try:
            intents = self.store.pending_notification_intents(limit=limit)
        except Exception:
            return 0
        for intent in intents:
            if isinstance(intent, Mapping) and self.process_notification_intent(
                _text(intent.get("id"))
            ):
                processed += 1
        return processed

    def _mail_message(
        self,
        delivery: Mapping[str, object],
        channel: str,
        settings: Mapping[str, object],
    ) -> MailMessage:
        payload = delivery.get("message")
        message = payload if isinstance(payload, Mapping) else {}
        sender_address, sender_name = _channel_sender(channel, settings)
        recipients = delivery.get("recipients")
        return MailMessage(
            message_id=_text(message.get("message_id")),
            subject=_text(message.get("subject"), 300),
            text_body=_text(message.get("text_body"), 10_000),
            html_body=_text(message.get("html_body"), 20_000),
            sender_address=sender_address,
            sender_name=sender_name,
            recipients=list(recipients) if isinstance(recipients, list) else [],
        )

    def _with_delivery_context(
        self, delivery: Mapping[str, object]
    ) -> Mapping[str, object]:
        try:
            context = self.store.query_incident_context(
                _text(delivery.get("incident_id")),
                problem_limit=5,
                before_limit=3,
                after_limit=3,
            )
        except Exception:
            return delivery
        safe_context = context if isinstance(context, Mapping) else {}
        payload = delivery.get("message")
        message = payload if isinstance(payload, Mapping) else {}
        enriched = dict(delivery)
        enriched["message"] = _append_runtime_context(message, safe_context)
        return enriched

    def _send_channel(
        self,
        delivery: Mapping[str, object],
        channel: str,
        settings: Mapping[str, object],
    ) -> tuple[dict[str, object], bool, list[str], bool]:
        try:
            channel_settings = settings.get(channel)
            transport = self.transport_factory(
                channel,
                channel_settings if isinstance(channel_settings, Mapping) else {},
            )
        except Exception:
            return _failure_attempt(
                channel,
                code="transport_unavailable",
                category="transport",
                message="Nie można przygotować kanału wysyłki.",
            ), False, [], True
        try:
            message = self._mail_message(delivery, channel, settings)
        except Exception:
            return _failure_attempt(
                channel,
                code="message_invalid",
                category="message",
                message="Nie można przygotować wiadomości.",
            ), False, [], True
        try:
            result = transport.send(message)
            safe_result = result if isinstance(result, Mapping) else {}
            attempt = _safe_attempt(channel, safe_result)
            status = _text(safe_result.get("status")).lower()
            if status in {"partial", "refused", "routing_unknown"}:
                refused = _verified_refused_recipients(message, safe_result)
                if refused is not None:
                    return attempt, False, refused, True
                return _failure_attempt(
                    channel,
                    code="partial_routing_unknown",
                    category="delivery",
                    message=(
                        "Nie można bezpiecznie ustalić odrzuconych odbiorców."
                    ),
                ), False, [], False
            return attempt, True, [], False
        except Exception:
            return _failure_attempt(
                channel,
                code="delivery_failed",
                category="delivery",
                message="Kanał nie wysłał wiadomości.",
            ), False, [], True

    def _deliver_claimed(
        self,
        claimed: Mapping[str, object],
        settings: Mapping[str, object],
        *,
        allow_fallback: bool,
    ) -> tuple[str, str, list[dict[str, object]]]:
        primary = _text(claimed.get("primary_channel")).lower()
        attempts: list[dict[str, object]] = []
        attempt, success, refused, fallback_safe = self._send_channel(
            claimed, primary, settings
        )
        attempts.append(attempt)
        if success:
            return "sent", primary, attempts
        if allow_fallback and fallback_safe:
            fallback = "smtp" if primary == "entra" else "entra"
            fallback_delivery = claimed
            if refused:
                fallback_delivery = dict(claimed)
                fallback_delivery["recipients"] = refused
            attempt, success, _fallback_refused, _fallback_safe = self._send_channel(
                fallback_delivery, fallback, settings
            )
            attempts.append(attempt)
            if success:
                return "fallback", fallback, attempts
            return "error", fallback, attempts
        return "error", primary, attempts

    def process_delivery(self, delivery_id: str) -> dict[str, object]:
        claimed = self.store.update_notification_delivery(
            _text(delivery_id), status="sending", updated_at=_iso_utc(self.now())
        )
        if not claimed:
            return {}
        primary = _text(claimed.get("primary_channel")).lower()
        try:
            settings = self._settings()
        except Exception:
            status = "error"
            used_channel = primary
            attempts = [
                _failure_attempt(
                    primary,
                    code="settings_unavailable",
                    category="configuration",
                    message="Nie można wczytać konfiguracji poczty.",
                )
            ]
        else:
            try:
                delivery_for_send = self._with_delivery_context(claimed)
                status, used_channel, attempts = self._deliver_claimed(
                    delivery_for_send,
                    settings,
                    allow_fallback=bool(settings.get("fallback_enabled")),
                )
            except Exception:
                status = "error"
                used_channel = primary
                attempts = [
                    _failure_attempt(
                        primary,
                        code="processing_failed",
                        category="internal",
                        message="Nie można zakończyć obsługi powiadomienia.",
                    )
                ]
        completed = self.store.update_notification_delivery(
            _text(delivery_id),
            status=status,
            used_channel=used_channel,
            attempts=attempts,
            updated_at=_iso_utc(self.now()),
        )
        try:
            self.event_emitter(
                severity="info" if status != "error" else "error",
                event_type=(
                    "notification.sent" if status != "error" else "notification.failed"
                ),
                module="notifications",
                stage="delivery",
                summary=(
                    "Powiadomienie e-mail wysłane."
                    if status != "error"
                    else "Nie udało się wysłać powiadomienia e-mail."
                ),
                details={
                    "delivery_id": _text(delivery_id),
                    "incident_id": _text(claimed.get("incident_id")),
                    "used_channel": used_channel,
                    "suppress_notifications": True,
                },
            )
        except Exception:
            pass
        return completed

    def recover_stale_deliveries(self) -> int:
        threshold = self.now() - STALE_SENDING_AFTER
        recovered = 0
        cursor = ""
        seen: set[str] = set()
        while True:
            page = self.store.query_notification_deliveries(cursor=cursor, limit=100)
            for delivery in page.get("items", []):
                if not isinstance(delivery, dict) or delivery.get("status") != "sending":
                    continue
                updated_at = _parse_utc(delivery.get("updated_at"))
                if updated_at is None or updated_at > threshold:
                    continue
                result = self.store.update_notification_delivery(
                    _text(delivery.get("id")),
                    status="pending",
                    updated_at=_iso_utc(self.now()),
                    next_attempt_at="",
                )
                recovered += bool(result)
            next_cursor = _text(page.get("next_cursor"))
            if not next_cursor or next_cursor in seen:
                break
            seen.add(next_cursor)
            cursor = next_cursor
        return recovered

    def process_pending_batch(self, limit: int = WORKER_BATCH_LIMIT) -> int:
        self.process_notification_intents(limit=limit)
        processed = 0
        for delivery in self.store.pending_notification_deliveries(limit=limit):
            if self.process_delivery(_text(delivery.get("id"))):
                processed += 1
        try:
            self.store.prune_done_notification_intents(
                _iso_utc(self.now() - OUTBOX_DONE_RETENTION)
            )
        except Exception:
            pass
        return processed

    def send_test_message(
        self, *, channel: str, recipient: str, use_fallback: bool = False
    ) -> dict[str, object]:
        selected = _text(channel).lower()
        if selected not in {"entra", "smtp"}:
            raise ValueError("Niepoprawny kanał wysyłki.")
        address = normalize_email_address(recipient)
        if not address:
            raise ValueError("Niepoprawny adres e-mail.")
        try:
            settings = self._settings()
        except Exception:
            return {
                "status": "error",
                "used_channel": selected,
                "attempts": [
                    _failure_attempt(
                        selected,
                        code="settings_unavailable",
                        category="configuration",
                        message="Nie można wczytać konfiguracji poczty.",
                    )
                ],
                "message_id": "",
            }
        try:
            now = _iso_utc(self.now())
            message_id = f"test-{uuid.uuid4().hex}"
            delivery = {
                "id": f"test-{uuid.uuid4().hex}",
                "incident_id": "",
                "primary_channel": selected,
                "recipients": [address],
                "message": {
                    "message_id": message_id,
                    "subject": "[TEST] PicOrgFTP-SQL — wiadomość testowa",
                    "text_body": f"To jest wiadomość testowa. Czas: {now}",
                    "html_body": (
                        "<h2>Wiadomość testowa PicOrgFTP-SQL</h2>"
                        f"<p>Czas: {html.escape(now)}</p>"
                    ),
                },
            }
        except Exception:
            return {
                "status": "error",
                "used_channel": selected,
                "attempts": [
                    _failure_attempt(
                        selected,
                        code="message_invalid",
                        category="message",
                        message="Nie można przygotować wiadomości testowej.",
                    )
                ],
                "message_id": "",
            }
        status, used_channel, attempts = self._deliver_claimed(
            delivery,
            settings,
            allow_fallback=(
                use_fallback and bool(settings.get("fallback_enabled"))
            ),
        )
        return {
            "status": status,
            "used_channel": used_channel,
            "attempts": attempts,
            "message_id": message_id,
        }


def _default_service() -> NotificationService:
    from .observability import observability_store

    return NotificationService(store=observability_store())


def queue_incident_notification(
    event: Mapping[str, object], incident: Mapping[str, object]
) -> dict[str, object] | None:
    return _default_service().queue_incident_notification(event, incident)


def process_delivery(delivery_id: str) -> dict[str, object]:
    return _default_service().process_delivery(delivery_id)


def send_test_message(
    *, channel: str, recipient: str, use_fallback: bool = False
) -> dict[str, object]:
    return _default_service().send_test_message(
        channel=channel, recipient=recipient, use_fallback=use_fallback
    )


_WORKER_LOCK = threading.Lock()
_WORKER_STOP: threading.Event | None = None
_WORKER_THREAD: threading.Thread | None = None
_WORKER_SERVICE: NotificationService | None = None


def _worker_loop(service: NotificationService, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            service.process_pending_batch(limit=WORKER_BATCH_LIMIT)
        except Exception:
            # Queue processing is isolated from the web/product request paths.
            pass
        if stop_event.wait(WORKER_POLL_SECONDS):
            break


def start_notification_worker() -> None:
    """Recover stale claims and start one bounded daemon queue worker."""

    global _WORKER_SERVICE, _WORKER_STOP, _WORKER_THREAD
    with _WORKER_LOCK:
        if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
            return
        _WORKER_THREAD = None
        _WORKER_SERVICE = None
        _WORKER_STOP = None
        try:
            service = _default_service()
        except Exception:
            return
        try:
            service.recover_stale_deliveries()
        except Exception:
            pass
        stop_event = threading.Event()
        _WORKER_SERVICE = service
        _WORKER_STOP = stop_event
        _WORKER_THREAD = threading.Thread(
            target=_worker_loop,
            args=(service, stop_event),
            name="picorg-notification-worker",
            daemon=True,
        )
        _WORKER_THREAD.start()


def stop_notification_worker() -> None:
    """Stop and join the current notification worker."""

    global _WORKER_SERVICE, _WORKER_STOP, _WORKER_THREAD
    with _WORKER_LOCK:
        thread = _WORKER_THREAD
        stop_event = _WORKER_STOP
        if stop_event is not None:
            stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=WORKER_STOP_TIMEOUT_SECONDS)
    with _WORKER_LOCK:
        if _WORKER_THREAD is not thread:
            return
        if thread is not None and thread.is_alive():
            return
        _WORKER_THREAD = None
        _WORKER_SERVICE = None
        _WORKER_STOP = None
