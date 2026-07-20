"""Durable incident e-mail queue, recipient rules, and background worker."""

from __future__ import annotations

import html
import json
import re
import secrets
import threading
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .email_delivery import MailMessage, MailTransport, build_transport
from .email_settings import (
    EMAIL_SETTINGS_KEY,
    normalize_email_address,
    normalize_email_settings,
)
from .entra_secret_monitor import process_due_entra_secret_reminders


WORKER_POLL_SECONDS = 2.0
WORKER_BATCH_LIMIT = 20
WORKER_STOP_TIMEOUT_SECONDS = 23.0
STALE_SENDING_AFTER = timedelta(minutes=5)
OUTBOX_DONE_RETENTION = timedelta(days=7)
DAILY_SUMMARY_TIME_ZONE = ZoneInfo("Europe/Warsaw")
DAILY_SUMMARY_RETRY_DELAY = timedelta(minutes=5)
DAILY_SUMMARY_STALE_CLAIM_AFTER = timedelta(minutes=10)


_TEST_NOTIFICATION_SCENARIOS: tuple[dict[str, object], ...] = (
    {
        "kind": "information",
        "severity": "info",
        "title": "Informacja testowa",
        "descriptions": (
            "Symulacja poprawnego zakończenia zadania.",
            "Symulacja zwykłej informacji operacyjnej.",
        ),
    },
    {
        "kind": "warning",
        "severity": "warning",
        "title": "Ostrzeżenie testowe",
        "descriptions": (
            "Symulacja niepełnych danych przekazanych przez użytkownika.",
            "Symulacja problemu wymagającego sprawdzenia konfiguracji.",
        ),
    },
    {
        "kind": "error",
        "severity": "error",
        "title": "Błąd testowy",
        "descriptions": (
            "Symulacja błędu podczas wysyłania danych.",
            "Symulacja błędu lokalnej aktualizacji danych.",
        ),
    },
    {
        "kind": "critical",
        "severity": "critical",
        "title": "Błąd krytyczny testowy",
        "descriptions": (
            "Symulacja wyjątku backendu blokującego zadanie.",
            "Symulacja krytycznej awarii uniemożliwiającej aktualizację danych.",
        ),
    },
    {
        "kind": "entra_secret_expiry",
        "severity": "critical",
        "title": "Test wygasania Client Secret Entra",
        "descriptions": (
            "Symulacja alertu: Client Secret Microsoft Entra zbliża się do wygaśnięcia.",
            "Symulacja krytycznego alertu o wygasającym Client Secret Microsoft Entra.",
        ),
    },
)


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


def _daily_summary_due_end(now: datetime, schedule: object) -> str:
    """Return the latest configured Warsaw run slot, or an empty value before it."""

    text = _text(schedule, 5)
    if len(text) != 5 or text[2] != ":" or not (text[:2] + text[3:]).isdigit():
        return ""
    hour, minute = int(text[:2]), int(text[3:])
    if hour > 23 or minute > 59:
        return ""
    current = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    local = current.astimezone(DAILY_SUMMARY_TIME_ZONE)
    # A fall-back hour occurs twice; fold=0 makes the daily wall-clock slot
    # stable, so the second occurrence cannot create a duplicate report.
    scheduled = local.replace(
        hour=hour, minute=minute, second=0, microsecond=0, fold=0
    )
    if local < scheduled:
        return ""
    return _iso_utc(scheduled)


def _daily_change_sources(record: Mapping[str, object]) -> list[Mapping[str, object]]:
    details = record.get("details")
    if not isinstance(details, Mapping):
        return []
    change_set = details.get("change_set")
    if not isinstance(change_set, Mapping):
        return []
    sources: list[Mapping[str, object]] = [change_set]
    pimcore = change_set.get("pimcore")
    if isinstance(pimcore, Mapping):
        sources.append(pimcore)
    return sources


def _compact_daily_change_rows(
    history: list[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Project history into user-facing EAN rows without operational evidence."""

    grouped: dict[str, dict[str, object]] = {}
    for record in history:
        ean = _text(record.get("ean"), 128)
        if not ean or ean == "BRAK-EAN":
            continue
        sources = _daily_change_sources(record)
        if not sources:
            continue
        row = grouped.setdefault(
            ean, {"ean": ean, "created": False, "fields": set(), "slots": set()}
        )
        for source in sources:
            created_source = _text(source.get("kind")).lower() == "created"
            if created_source:
                row["created"] = True
            raw_fields = source.get("fields")
            if not created_source and isinstance(raw_fields, list):
                fields = row["fields"]
                if isinstance(fields, set):
                    for item in raw_fields:
                        if isinstance(item, Mapping):
                            label = _text(item.get("label") or item.get("key"), 200)
                            if label:
                                fields.add(label)
            raw_files = source.get("files")
            if isinstance(raw_files, list):
                slots = row["slots"]
                if isinstance(slots, set):
                    for item in raw_files:
                        if isinstance(item, Mapping):
                            slot = _text(item.get("slot") or item.get("prefix"), 40)
                            if slot:
                                slots.add(slot)
    rows: list[dict[str, object]] = []
    for ean in sorted(grouped):
        row = grouped[ean]
        fields = sorted(row["fields"]) if isinstance(row["fields"], set) else []
        slots = sorted(row["slots"]) if isinstance(row["slots"], set) else []
        if bool(row["created"]) or fields or slots:
            rows.append({"ean": ean, "created": bool(row["created"]), "fields": fields, "slots": slots})
    return rows


def _daily_summary_message(
    rows: list[Mapping[str, object]], *, window_start: str, window_end: str
) -> dict[str, str]:
    lines: list[str] = []
    html_items: list[str] = []
    for row in rows:
        parts: list[str] = []
        if bool(row.get("created")):
            parts.append("utworzono nowy wpis")
        fields = row.get("fields")
        if isinstance(fields, list) and fields:
            parts.append("zaktualizowano dane PIMcore: " + ", ".join(_text(value, 200) for value in fields))
        slots = row.get("slots")
        if isinstance(slots, list) and slots:
            parts.append("zaktualizowano zdjęcia: sloty " + ", ".join(_text(value, 40) for value in slots))
        line = f"{_text(row.get('ean'), 128)} — " + "; ".join(parts)
        lines.append("• " + line)
        html_items.append(f"<li>{html.escape(line)}</li>")
    start = _text(window_start, 40)
    end = _text(window_end, 40)
    heading = "Dzienne podsumowanie zmian produktów"
    text_body = f"{heading}\nOkres: {start} — {end}\n\n" + "\n".join(lines)
    return {
        "message_id": f"daily-change-summary-{_text(window_end, 40)}",
        "subject": "[PicOrgFTP-SQL] Dzienne podsumowanie zmian",
        "text_body": text_body,
        "html_body": (
            f"<h2>{html.escape(heading)}</h2><p>Okres: {html.escape(start)} — "
            f"{html.escape(end)}</p><ul>{''.join(html_items)}</ul>"
        ),
    }


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
            severity = _text(event.get("severity")).lower()
            # Releases made before daily summaries existed may still contain
            # informational intents. Complete them without sending stale spam.
            if severity == "info":
                self.store.materialize_notification_intent(
                    _text(intent_id), delivery=None, completed_at=_iso_utc(self.now())
                )
                return True
            settings = self._settings()
            recipients = resolve_recipients(
                event,
                settings,
                self.user_lookup,
                tolerate_lookup_errors=False,
            )
            completed_at = _iso_utc(self.now())
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

    def process_due_daily_change_summary(self) -> dict[str, object]:
        """Send exactly one compact daily report for the current Warsaw slot."""

        settings = self._settings()
        window_end = _daily_summary_due_end(
            self.now(), settings.get("daily_summary_time", "16:00")
        )
        if not window_end:
            return {"status": "not_due", "product_count": 0}
        recipients = resolve_recipients(
            {"severity": "info", "username": ""}, settings, self.user_lookup
        )
        if not recipients:
            return {"status": "not_configured", "product_count": 0}
        claim = self.store.claim_daily_change_summary(
            window_end, claimed_at=_iso_utc(self.now())
        )
        if not isinstance(claim, Mapping):
            return {"status": "already_processed", "product_count": 0}
        report_end = _text(claim.get("window_end"), 40)
        if not report_end:
            return {"status": "error", "product_count": 0}
        start = _text(claim.get("window_start"), 40)
        try:
            history = self.store.daily_change_history(
                window_start=start, window_end=report_end
            )
            records = [item for item in history if isinstance(item, Mapping)]
            rows = _compact_daily_change_rows(records)
        except Exception:
            self.store.finalize_daily_change_summary(
                report_end,
                status="pending",
                next_attempt_at=_iso_utc(self.now() + DAILY_SUMMARY_RETRY_DELAY),
            )
            return {"status": "error", "product_count": 0}
        if not rows:
            self.store.finalize_daily_change_summary(report_end, status="sent")
            return {"status": "skipped", "product_count": 0}
        delivery = {
            "id": f"daily-summary-{report_end}",
            "primary_channel": _text(settings.get("primary_channel")).lower(),
            "recipients": recipients,
            "message": _daily_summary_message(
                rows, window_start=start, window_end=report_end
            ),
        }
        status, _channel, _attempts = self._deliver_claimed(
            delivery, settings, allow_fallback=bool(settings.get("fallback_enabled"))
        )
        final_status = "sent" if status != "error" else "pending"
        self.store.finalize_daily_change_summary(
            report_end,
            status=final_status,
            next_attempt_at=(
                _iso_utc(self.now() + DAILY_SUMMARY_RETRY_DELAY)
                if final_status == "pending"
                else ""
            ),
        )
        return {"status": status, "product_count": len(rows)}

    def recover_daily_change_summaries(self) -> int:
        """Release only report sends abandoned longer than the claim timeout."""

        recover = getattr(self.store, "recover_daily_change_summaries", None)
        if not callable(recover):
            return 0
        return max(
            0,
            int(
                recover(
                    stale_before=_iso_utc(
                        self.now() - DAILY_SUMMARY_STALE_CLAIM_AFTER
                    )
                )
                or 0
            ),
        )

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
        try:
            self.process_due_daily_change_summary()
        except Exception:
            # Daily reports are isolated from incident delivery and are retryable.
            pass
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

    def send_test_notification_suite(
        self, *, channel: str, use_fallback: bool = False
    ) -> dict[str, object]:
        """Send five direct test messages without recording any operational state."""

        selected = _text(channel).lower()
        if selected not in {"entra", "smtp"}:
            raise ValueError("Niepoprawny kanał wysyłki.")
        try:
            settings = self._settings()
        except Exception:
            settings = None

        results: list[dict[str, object]] = []
        for scenario in _TEST_NOTIFICATION_SCENARIOS:
            kind = _text(scenario.get("kind"))
            severity = _text(scenario.get("severity")).lower()
            title = _header_text(scenario.get("title"))
            descriptions = scenario.get("descriptions")
            choices = (
                tuple(item for item in descriptions if isinstance(item, str))
                if isinstance(descriptions, tuple)
                else ()
            )
            description = _text(secrets.choice(choices) if choices else title, 1_000)
            result: dict[str, object] = {
                "kind": kind,
                "severity": severity,
                "status": "error",
                "used_channel": selected,
                "recipient_count": 0,
                "attempts": [],
            }
            if settings is None:
                result["attempts"] = [
                    _failure_attempt(
                        selected,
                        code="settings_unavailable",
                        category="configuration",
                        message="Nie można wczytać konfiguracji poczty.",
                    )
                ]
                results.append(result)
                continue

            event = {"severity": severity, "username": ""}
            recipients = resolve_recipients(event, settings, self.user_lookup)
            result["recipient_count"] = len(recipients)
            if not recipients:
                result["status"] = "skipped"
                results.append(result)
                continue

            now = _iso_utc(self.now())
            message_id = f"test-suite-{uuid.uuid4().hex}"
            delivery = {
                "id": f"test-suite-{uuid.uuid4().hex}",
                "incident_id": "",
                "primary_channel": selected,
                "recipients": recipients,
                "message": {
                    "message_id": message_id,
                    "subject": f"[TEST] PicOrgFTP-SQL — {title}",
                    "text_body": f"[TEST] {description}\nCzas: {now}",
                    "html_body": (
                        "<h2>[TEST] PicOrgFTP-SQL</h2>"
                        f"<p>{html.escape(description)}</p>"
                        f"<p>Czas: {html.escape(now)}</p>"
                    ),
                },
            }
            try:
                status, used_channel, attempts = self._deliver_claimed(
                    delivery,
                    settings,
                    allow_fallback=(
                        use_fallback and bool(settings.get("fallback_enabled"))
                    ),
                )
            except Exception:
                status, used_channel, attempts = (
                    "error",
                    selected,
                    [
                        _failure_attempt(
                            selected,
                            code="test_failed",
                            category="internal",
                            message="Nie można zakończyć testu wysyłki.",
                        )
                    ],
                )
            result.update(
                status=status,
                used_channel=used_channel,
                attempts=attempts,
                message_id=message_id,
            )
            results.append(result)
        return {"scenarios": results}


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


def send_test_notification_suite(
    *, channel: str, use_fallback: bool = False
) -> dict[str, object]:
    return _default_service().send_test_notification_suite(
        channel=channel, use_fallback=use_fallback
    )


_WORKER_LOCK = threading.Lock()
_WORKER_STOP: threading.Event | None = None
_WORKER_THREAD: threading.Thread | None = None
_WORKER_SERVICE: NotificationService | None = None
_WORKER_OBSERVED_AT = ""
_WORKER_LAST_ENTRA_MONITOR_AT: datetime | None = None


def _worker_loop(service: NotificationService, stop_event: threading.Event) -> None:
    global _WORKER_LAST_ENTRA_MONITOR_AT
    while not stop_event.is_set():
        monitor_now = _utc_now()
        if (
            _WORKER_LAST_ENTRA_MONITOR_AT is None
            or monitor_now - _WORKER_LAST_ENTRA_MONITOR_AT >= timedelta(hours=24)
        ):
            try:
                process_due_entra_secret_reminders()
            except Exception:
                # Monitoring must never delay or stop notification delivery.
                pass
            finally:
                _WORKER_LAST_ENTRA_MONITOR_AT = monitor_now
        try:
            service.process_pending_batch(limit=WORKER_BATCH_LIMIT)
        except Exception:
            # Queue processing is isolated from the web/product request paths.
            pass
        if stop_event.wait(WORKER_POLL_SECONDS):
            break


def start_notification_worker() -> None:
    """Recover stale claims and start one bounded daemon queue worker."""

    global _WORKER_LAST_ENTRA_MONITOR_AT, _WORKER_OBSERVED_AT, _WORKER_SERVICE, _WORKER_STOP, _WORKER_THREAD
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
        try:
            service.recover_daily_change_summaries()
        except Exception:
            pass
        stop_event = threading.Event()
        _WORKER_SERVICE = service
        _WORKER_STOP = stop_event
        _WORKER_LAST_ENTRA_MONITOR_AT = None
        _WORKER_THREAD = threading.Thread(
            target=_worker_loop,
            args=(service, stop_event),
            name="picorg-notification-worker",
            daemon=True,
        )
        _WORKER_THREAD.start()
        _WORKER_OBSERVED_AT = _iso_utc(_utc_now())


def stop_notification_worker() -> None:
    """Stop and join the current notification worker."""

    global _WORKER_OBSERVED_AT, _WORKER_SERVICE, _WORKER_STOP, _WORKER_THREAD
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
        _WORKER_OBSERVED_AT = _iso_utc(_utc_now())


def notification_worker_health() -> dict[str, str]:
    """Return current worker state without constructing or starting a worker."""

    with _WORKER_LOCK:
        thread = _WORKER_THREAD
        return {
            "status": "online" if thread is not None and thread.is_alive() else "critical",
            "observed_at": _WORKER_OBSERVED_AT,
        }
