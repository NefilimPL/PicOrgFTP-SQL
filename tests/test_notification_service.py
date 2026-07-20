from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

import pytest

from picorgftp_sql import notification_service


UTC = timezone.utc
NOW = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)


def _settings(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "primary_channel": "entra",
        "fallback_enabled": True,
        "entra": {
            "tenant_id": "tenant",
            "client_id": "client",
            "client_secret": "secret",
            "from_address": "alerts@example.com",
        },
        "smtp": {
            "host": "smtp.example.com",
            "port": 587,
            "security": "starttls",
            "username": "sender",
            "password": "secret",
            "from_address": "alerts@example.com",
            "from_name": "PicOrgFTP-SQL",
        },
        "rules": {
            severity: {
                "enabled": severity != "info",
                "recipients": ["Admin@Example.com", "ops@example.com"],
                "include_actor": True,
            }
            for severity in ("info", "warning", "error", "critical")
        },
    }
    result.update(overrides)
    return result


def test_worker_runs_entra_expiry_monitor_at_most_once_each_24_hours(monkeypatch):
    calls = []
    service = type("Service", (), {"process_pending_batch": lambda self, limit: None})()
    stop_event = type("Stop", (), {"is_set": lambda self: False, "wait": lambda self, value: True})()
    monkeypatch.setattr(notification_service, "process_due_entra_secret_reminders", lambda: calls.append(True))
    monkeypatch.setattr(notification_service, "_WORKER_LAST_ENTRA_MONITOR_AT", None)
    monkeypatch.setattr(notification_service, "_utc_now", lambda: NOW)
    notification_service._worker_loop(service, stop_event)
    notification_service._worker_loop(service, stop_event)

    assert calls == [True]


def test_worker_isolates_entra_expiry_monitor_errors(monkeypatch):
    calls = []
    service = type("Service", (), {"process_pending_batch": lambda self, limit: calls.append("delivery")})()
    stop_event = type("Stop", (), {"is_set": lambda self: False, "wait": lambda self, value: True})()
    monkeypatch.setattr(notification_service, "process_due_entra_secret_reminders", lambda: (_ for _ in ()).throw(RuntimeError("monitor failed")))
    monkeypatch.setattr(notification_service, "_WORKER_LAST_ENTRA_MONITOR_AT", None)
    monkeypatch.setattr(notification_service, "_utc_now", lambda: NOW)

    notification_service._worker_loop(service, stop_event)

    assert calls == ["delivery"]


def test_starting_a_fresh_worker_resets_the_entra_monitor_guard(monkeypatch):
    started = []

    class Thread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            started.append(True)

        def is_alive(self):
            return False

    service = type("Service", (), {"recover_stale_deliveries": lambda self: None})()
    monkeypatch.setattr(notification_service, "_default_service", lambda: service)
    monkeypatch.setattr(notification_service.threading, "Thread", Thread)
    monkeypatch.setattr(notification_service, "_WORKER_THREAD", None)
    monkeypatch.setattr(notification_service, "_WORKER_LAST_ENTRA_MONITOR_AT", NOW)

    notification_service.start_notification_worker()

    assert started == [True]
    assert notification_service._WORKER_LAST_ENTRA_MONITOR_AT is None


def _event(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "id": "evt-1",
        "created_at": "2026-07-17T09:59:00.000Z",
        "severity": "error",
        "event_type": "pimcore.update_failed",
        "module": "pimcore",
        "stage": "update",
        "username": "alice",
        "ean": "5900000000001",
        "job_id": "job-1",
        "correlation_id": "corr-1",
        "summary": "Aktualizacja <nieudana>",
        "recommended_action": "Ponów & sprawdź",
        "details": {"safe": "wartość", "password": "secret"},
    }
    result.update(overrides)
    return result


def _incident(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "id": "inc-1",
        "event_type": "pimcore.update_failed",
        "severity": "error",
        "notification_due": True,
        "occurrence_count": 1,
        "first_seen_at": "2026-07-17T09:59:00.000Z",
        "last_seen_at": "2026-07-17T09:59:00.000Z",
    }
    result.update(overrides)
    return result


class FakeStore:
    def __init__(self) -> None:
        self.deliveries: dict[str, dict[str, object]] = {}
        self.incident_context: dict[str, object] | None = None

    def enqueue_notification_delivery(
        self, record: dict[str, object]
    ) -> dict[str, object]:
        stored = dict(record)
        stored["recipients"] = list(record.get("recipients") or [])
        stored["message"] = dict(record.get("message") or {})
        stored["attempts"] = list(record.get("attempts") or [])
        self.deliveries[str(stored["id"])] = stored
        return dict(stored)

    def pending_notification_deliveries(
        self, limit: int = 20
    ) -> list[dict[str, object]]:
        return [
            dict(item)
            for item in sorted(
                self.deliveries.values(),
                key=lambda item: (str(item["created_at"]), str(item["id"])),
            )
            if item["status"] == "pending"
        ][:limit]

    def update_notification_delivery(
        self,
        delivery_id: str,
        *,
        status: str,
        used_channel: str = "",
        attempts: object = None,
        updated_at: str,
        next_attempt_at: str = "",
    ) -> dict[str, object]:
        item = self.deliveries.get(delivery_id)
        if item is None:
            return {}
        expected = "pending" if status == "sending" else "sending"
        if item["status"] != expected:
            return {}
        item.update(
            status=status,
            used_channel=used_channel,
            updated_at=updated_at,
            next_attempt_at=next_attempt_at,
        )
        if attempts is not None:
            item["attempts"] = list(attempts)
        return dict(item)

    def query_notification_deliveries(
        self, *, incident_id: str = "", cursor: str = "", limit: int = 20
    ) -> dict[str, object]:
        del cursor
        items = list(self.deliveries.values())
        if incident_id:
            items = [item for item in items if item["incident_id"] == incident_id]
        return {"items": [dict(item) for item in items[:limit]], "next_cursor": ""}

    def query_incident_context(
        self, incident_id: str, **_kwargs: object
    ) -> dict[str, object] | None:
        del incident_id
        return self.incident_context


class FakeTransport:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.messages: list[object] = []

    def send(self, message: object) -> dict[str, object]:
        self.messages.append(message)
        if self.error:
            raise self.error
        return {"status": "sent", "elapsed_ms": 12, "secret": "never-store"}


def _service(
    store: FakeStore,
    transports: dict[str, FakeTransport] | None = None,
    settings: dict[str, object] | None = None,
    emitted: list[dict[str, object]] | None = None,
) -> notification_service.NotificationService:
    channels = transports or {"entra": FakeTransport(), "smtp": FakeTransport()}
    event_sink = emitted if emitted is not None else []
    return notification_service.NotificationService(
        store=store,
        transport_factory=lambda channel, _settings: channels[channel],
        settings_loader=lambda: settings or _settings(),
        user_lookup=lambda username: {
            "username": username,
            "email": "admin@example.com",
        },
        event_emitter=lambda **kwargs: event_sink.append(kwargs),
        now=lambda: NOW,
    )


def test_resolve_recipients_obeys_exact_rule_actor_and_casefold_dedupe() -> None:
    settings = _settings()

    recipients = notification_service.resolve_recipients(
        _event(severity="error"),
        settings,
        lambda _username: {"email": "admin@example.com"},
    )

    assert recipients == ["Admin@example.com", "ops@example.com"]
    assert notification_service.resolve_recipients(
        _event(severity="info"), settings, lambda _username: None
    ) == []


def test_resolve_recipients_ignores_invalid_fixed_and_actor_addresses() -> None:
    settings = _settings()
    settings["rules"]["error"]["recipients"] = [
        "ok@example.com",
        "bad address",
        "OK@example.com",
    ]

    result = notification_service.resolve_recipients(
        _event(), settings, lambda _username: {"email": "also bad"}
    )

    assert result == ["ok@example.com"]


def test_queue_incident_notification_only_when_due_and_escapes_message() -> None:
    store = FakeStore()
    service = _service(store)

    assert service.queue_incident_notification(
        _event(), _incident(notification_due=False)
    ) is None
    queued = service.queue_incident_notification(_event(), _incident())

    assert queued is not None
    assert queued["status"] == "pending"
    assert queued["recipients"] == ["Admin@example.com", "ops@example.com"]
    message = queued["message"]
    assert "Aktualizacja <nieudana>" in message["text_body"]
    assert "Aktualizacja &lt;nieudana&gt;" in message["html_body"]
    assert "Ponów &amp; sprawdź" in message["html_body"]
    assert "secret" not in str(message)


def test_incident_message_includes_bounded_redacted_occurrence_context() -> None:
    store = FakeStore()
    service = _service(store)

    queued = service.queue_incident_notification(
        _event(
            details={
                "safe": "wartość",
                "config": {"host": "private.internal"},
                "traceback_text": "very long internal stack",
                "cookie": "session-secret",
            }
        ),
        _incident(
            occurrence_count=7,
            context={
                "slot": "01 <front>",
                "reason": "Brak & blokada",
                "authorization": "Bearer secret-token",
                "nested": {"password": "smtp-secret"},
            },
        ),
    )

    assert queued is not None
    message = queued["message"]
    assert "Liczba wystąpień: 7" in message["text_body"]
    assert '"slot": "01 <front>"' in message["text_body"]
    assert "01 &lt;front&gt;" in message["html_body"]
    assert "Brak &amp; blokada" in message["html_body"]
    assert "secret-token" not in str(message)
    assert "smtp-secret" not in str(message)
    assert "private.internal" not in str(message)
    assert "internal stack" not in str(message)
    assert "session-secret" not in str(message)
    assert len(message["text_body"]) <= 10_000
    assert len(message["html_body"]) <= 20_000


def test_queue_message_subject_cannot_contain_header_newlines() -> None:
    store = FakeStore()
    service = _service(store)

    queued = service.queue_incident_notification(
        _event(summary="Awaria\r\nBcc: intruder@example.com"), _incident()
    )

    assert queued is not None
    assert "\r" not in queued["message"]["subject"]
    assert "\n" not in queued["message"]["subject"]


@pytest.mark.parametrize("severity", ["warning", "error", "critical"])
def test_disabled_incident_rule_records_skipped_delivery(severity: str) -> None:
    store = FakeStore()
    settings = _settings()
    settings["rules"][severity]["enabled"] = False
    service = _service(store, settings=settings)

    skipped = service.queue_incident_notification(
        _event(severity=severity), _incident(severity=severity)
    )

    assert skipped is not None
    assert skipped["status"] == "skipped"
    assert skipped["recipients"] == []


def test_process_delivery_falls_back_once_with_same_message_id() -> None:
    store = FakeStore()
    primary = FakeTransport(error=RuntimeError("primary secret down"))
    fallback = FakeTransport()
    service = _service(store, {"entra": primary, "smtp": fallback})
    queued = service.queue_incident_notification(_event(), _incident())

    result = service.process_delivery(str(queued["id"]))

    assert len(primary.messages) == 1
    assert len(fallback.messages) == 1
    assert primary.messages[0].message_id == fallback.messages[0].message_id
    assert result["status"] == "fallback"
    assert result["used_channel"] == "smtp"
    assert result["attempts"] == [
        {
            "channel": "entra",
            "status": "error",
            "code": "delivery_failed",
            "category": "delivery",
            "message": "Kanał nie wysłał wiadomości.",
        },
        {"channel": "smtp", "status": "sent", "elapsed_ms": 12},
    ]
    assert "secret" not in str(result["attempts"])


def test_process_delivery_primary_success_does_not_call_fallback() -> None:
    store = FakeStore()
    primary, fallback = FakeTransport(), FakeTransport()
    service = _service(store, {"entra": primary, "smtp": fallback})
    queued = service.queue_incident_notification(_event(), _incident())

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "sent"
    assert len(primary.messages) == 1
    assert fallback.messages == []


def test_smtp_partial_refusal_falls_back_only_refused_recipients_without_persisting_addresses(
) -> None:
    class PartialTransport(FakeTransport):
        def send(self, message: object) -> dict[str, object]:
            self.messages.append(message)
            return {
                "status": "partial",
                "routing_known": True,
                "elapsed_ms": 4,
                "accepted_count": 1,
                "refused_count": 1,
                "refusal_codes": [452],
                "refused_recipients": ["ops@example.com"],
            }

    store = FakeStore()
    primary = PartialTransport()
    fallback = FakeTransport()
    service = _service(store, {"entra": primary, "smtp": fallback})
    queued = service.queue_incident_notification(_event(), _incident())

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "fallback"
    assert primary.messages[0].recipients == [
        "Admin@example.com",
        "ops@example.com",
    ]
    assert fallback.messages[0].recipients == ["ops@example.com"]
    assert primary.messages[0].message_id == fallback.messages[0].message_id
    assert result["attempts"][0] == {
        "channel": "entra",
        "status": "partial",
        "elapsed_ms": 4,
        "accepted_count": 1,
        "refused_count": 1,
        "refusal_codes": [452],
    }
    assert "ops@example.com" not in str(result["attempts"])


def test_partial_refusal_without_fallback_finishes_error_without_resending_accepted(
) -> None:
    class PartialTransport(FakeTransport):
        def send(self, message: object) -> dict[str, object]:
            self.messages.append(message)
            return {
                "status": "partial",
                "routing_known": True,
                "accepted_count": 1,
                "refused_count": 1,
                "refusal_codes": [452],
                "refused_recipients": ["ops@example.com"],
            }

    store = FakeStore()
    settings = _settings(fallback_enabled=False)
    primary = PartialTransport()
    fallback = FakeTransport()
    service = _service(store, {"entra": primary, "smtp": fallback}, settings=settings)
    queued = service.queue_incident_notification(_event(), _incident())

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "error"
    assert result["attempts"][0]["status"] == "partial"
    assert fallback.messages == []


def test_all_refused_fallback_receives_all_recipients_and_failure_stays_safe() -> None:
    class RefusedTransport(FakeTransport):
        def send(self, message: object) -> dict[str, object]:
            self.messages.append(message)
            return {
                "status": "refused",
                "routing_known": True,
                "accepted_count": 0,
                "refused_count": 2,
                "refusal_codes": [550, 551],
                "refused_recipients": list(message.recipients),
                "server_response": "private server text",
            }

    store = FakeStore()
    primary = RefusedTransport()
    fallback = FakeTransport(error=RuntimeError("private fallback failure"))
    service = _service(store, {"entra": primary, "smtp": fallback})
    queued = service.queue_incident_notification(_event(), _incident())

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "error"
    assert fallback.messages[0].recipients == [
        "Admin@example.com",
        "ops@example.com",
    ]
    assert result["attempts"][0] == {
        "channel": "entra",
        "status": "refused",
        "accepted_count": 0,
        "refused_count": 2,
        "refusal_codes": [550, 551],
    }
    assert result["attempts"][1]["status"] == "error"
    assert "private" not in str(result["attempts"])


@pytest.mark.parametrize(
    "unsafe_result",
    [
        {
            "status": "partial",
            "routing_known": True,
            "accepted_count": 1,
            "refused_count": 1,
        },
        {
            "status": "partial",
            "routing_known": True,
            "accepted_count": 0,
            "refused_count": 2,
            "refused_recipients": ["ops@example.com"],
        },
        {
            "status": "partial",
            "routing_known": True,
            "accepted_count": 1,
            "refused_count": 1,
            "refused_recipients": ["unknown@example.com"],
        },
        {
            "status": "partial",
            "routing_known": True,
            "accepted_count": 0,
            "refused_count": 2,
            "refused_recipients": ["ops@example.com", "OPS@example.com"],
        },
        {
            "status": "partial",
            "routing_known": False,
            "accepted_count": 1,
            "refused_count": 1,
            "refused_recipients": ["ops@example.com"],
        },
    ],
    ids=["missing", "count-mismatch", "unknown", "duplicate", "unverified"],
)
def test_partial_unknown_routing_fails_closed_without_fallback(
    unsafe_result: dict[str, object],
) -> None:
    class UnsafePartialTransport(FakeTransport):
        def send(self, message: object) -> dict[str, object]:
            self.messages.append(message)
            return dict(unsafe_result)

    store = FakeStore()
    primary = UnsafePartialTransport()
    fallback = FakeTransport()
    service = _service(store, {"entra": primary, "smtp": fallback})
    queued = service.queue_incident_notification(_event(), _incident())

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "error"
    assert result["attempts"] == [
        {
            "channel": "entra",
            "status": "error",
            "code": "partial_routing_unknown",
            "category": "delivery",
            "message": "Nie można bezpiecznie ustalić odrzuconych odbiorców.",
        }
    ]
    assert fallback.messages == []


def test_explicit_routing_unknown_never_becomes_success_or_fallback() -> None:
    class UnknownRoutingTransport(FakeTransport):
        def send(self, message: object) -> dict[str, object]:
            self.messages.append(message)
            return {
                "status": "routing_unknown",
                "routing_known": False,
                "refusal_codes": [],
                "refused_recipients": [],
            }

    store = FakeStore()
    primary = UnknownRoutingTransport()
    fallback = FakeTransport()
    service = _service(store, {"entra": primary, "smtp": fallback})
    queued = service.queue_incident_notification(_event(), _incident())

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "error"
    assert result["attempts"][0]["code"] == "partial_routing_unknown"
    assert fallback.messages == []


def test_process_delivery_enriches_mail_with_bounded_redacted_runtime_context() -> None:
    store = FakeStore()
    store.incident_context = {
        "before": [
            _event(
                id="evt-before",
                summary="Przygotowanie <start>",
                details={"safe": "before", "client_secret": "never-leak"},
            )
        ],
        "problem": [
            _event(
                id="evt-problem",
                summary="Problem FTP",
                details={"safe": "problem", "password": "never-leak"},
            )
        ],
        "after": [],
        "problem_next_cursor": "ignored",
    }
    transport = FakeTransport()
    service = _service(store, {"entra": transport, "smtp": FakeTransport()})
    queued = service.queue_incident_notification(_event(), _incident())
    assert "Przygotowanie" not in queued["message"]["text_body"]

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "sent"
    message = transport.messages[0]
    assert "Przed:" in message.text_body
    assert "Przygotowanie <start>" in message.text_body
    assert "Problem:" in message.text_body
    assert "Problem FTP" in message.text_body
    assert "Po: Brak zdarzeń." in message.text_body
    assert "Przygotowanie &lt;start&gt;" in message.html_body
    assert "never-leak" not in message.text_body
    assert "never-leak" not in message.html_body
    assert "Przygotowanie" not in store.deliveries[str(queued["id"])]["message"][
        "text_body"
    ]


def test_process_delivery_context_lookup_failure_uses_safe_queued_message() -> None:
    class BrokenContextStore(FakeStore):
        def query_incident_context(self, *_args: object, **_kwargs: object):
            raise RuntimeError("password=context-secret")

    store = BrokenContextStore()
    transport = FakeTransport()
    service = _service(store, {"entra": transport, "smtp": FakeTransport()})
    queued = service.queue_incident_notification(_event(), _incident())

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "sent"
    assert len(transport.messages) == 1
    assert "context-secret" not in transport.messages[0].text_body


def test_delivery_context_is_preserved_when_queued_body_is_near_size_cap() -> None:
    store = FakeStore()
    store.incident_context = {
        "before": [],
        "problem": [_event(summary="Runtime context marker")],
        "after": [],
    }
    transport = FakeTransport()
    service = _service(store, {"entra": transport, "smtp": FakeTransport()})
    queued = service.queue_incident_notification(_event(), _incident())
    store.deliveries[str(queued["id"])]["message"]["text_body"] = "x" * 9_999
    store.deliveries[str(queued["id"])]["message"]["html_body"] = "x" * 19_999

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "sent"
    assert "Runtime context marker" in transport.messages[0].text_body
    assert "Runtime context marker" in transport.messages[0].html_body
    assert len(transport.messages[0].text_body) <= 10_000
    assert len(transport.messages[0].html_body) <= 20_000


def test_delivery_context_html_keeps_complete_sections_under_worst_case_budget() -> None:
    store = FakeStore()
    huge = "<&>" * 2_000
    store.incident_context = {
        "before": [_event(id=f"before-{index}", summary=huge) for index in range(3)],
        "problem": [_event(id=f"problem-{index}", summary=huge) for index in range(5)],
        "after": [_event(id=f"after-{index}", summary=huge) for index in range(3)],
    }
    transport = FakeTransport()
    service = _service(store, {"entra": transport, "smtp": FakeTransport()})
    queued = service.queue_incident_notification(_event(), _incident())
    store.deliveries[str(queued["id"])]["message"]["html_body"] = "x" * 19_999

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "sent"
    body = transport.messages[0].html_body
    assert len(body) <= 20_000
    assert body.endswith("</div>")
    for label in ("Przed", "Problem", "Po"):
        assert f"<h3>{label}</h3>" in body
    for tag in ("div", "section", "ul", "li", "pre"):
        assert body.count(f"<{tag}") == body.count(f"</{tag}>")
    assert not re.search(r"&(?:[A-Za-z]*|#[0-9]*)$", body)


def test_delivery_context_text_keeps_all_headings_under_worst_case_budget() -> None:
    store = FakeStore()
    huge = "problem-context-" * 2_000
    store.incident_context = {
        "before": [
            _event(id=f"before-{index}", summary=huge, details={"blob": huge})
            for index in range(3)
        ],
        "problem": [
            _event(id=f"problem-{index}", summary=huge, details={"blob": huge})
            for index in range(5)
        ],
        "after": [
            _event(id=f"after-{index}", summary=huge, details={"blob": huge})
            for index in range(3)
        ],
    }
    transport = FakeTransport()
    service = _service(store, {"entra": transport, "smtp": FakeTransport()})
    queued = service.queue_incident_notification(_event(), _incident())
    store.deliveries[str(queued["id"])]["message"]["text_body"] = "x" * 9_999

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "sent"
    body = transport.messages[0].text_body
    assert len(body) <= 10_000
    assert "Kontekst zdarzeń" in body
    assert body.index("Przed:") < body.index("Problem:") < body.index("Po:")
    assert "problem-context" in body


def test_process_delivery_records_both_failures_and_suppresses_recursion() -> None:
    store = FakeStore()
    emitted: list[dict[str, object]] = []
    service = _service(
        store,
        {
            "entra": FakeTransport(error=RuntimeError("entra secret")),
            "smtp": FakeTransport(error=RuntimeError("smtp password")),
        },
        emitted=emitted,
    )
    queued = service.queue_incident_notification(_event(), _incident())

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "error"
    assert result["attempts"] == [
        {
            "channel": "entra",
            "status": "error",
            "code": "delivery_failed",
            "category": "delivery",
            "message": "Kanał nie wysłał wiadomości.",
        },
        {
            "channel": "smtp",
            "status": "error",
            "code": "delivery_failed",
            "category": "delivery",
            "message": "Kanał nie wysłał wiadomości.",
        },
    ]
    assert "secret" not in str(result["attempts"])
    assert "password" not in str(result["attempts"])
    assert emitted[-1]["event_type"] == "notification.failed"
    assert emitted[-1]["details"]["suppress_notifications"] is True


def test_recover_stale_sending_and_process_pending_batch() -> None:
    store = FakeStore()
    service = _service(store)
    stale = service.queue_incident_notification(_event(), _incident())
    store.update_notification_delivery(
        str(stale["id"]),
        status="sending",
        updated_at=(NOW - timedelta(minutes=6)).isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
    )

    assert service.recover_stale_deliveries() == 1
    assert store.deliveries[str(stale["id"])]["status"] == "pending"
    assert service.process_pending_batch(limit=10) == 1
    assert store.deliveries[str(stale["id"])]["status"] == "sent"


def test_settings_loader_failure_after_claim_finishes_delivery_as_safe_error() -> None:
    store = FakeStore()
    queued = _service(store).queue_incident_notification(_event(), _incident())
    service = notification_service.NotificationService(
        store=store,
        settings_loader=lambda: (_ for _ in ()).throw(
            RuntimeError("client_secret=super-sensitive")
        ),
        user_lookup=lambda _username: None,
        event_emitter=lambda **_kwargs: None,
        now=lambda: NOW,
    )

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "error"
    assert result["attempts"] == [
        {
            "channel": "entra",
            "status": "error",
            "code": "settings_unavailable",
            "category": "configuration",
            "message": "Nie można wczytać konfiguracji poczty.",
        }
    ]
    assert store.deliveries[str(queued["id"])]["status"] == "error"
    assert "super-sensitive" not in str(result)


def test_transport_factory_failure_is_terminal_and_redacted() -> None:
    store = FakeStore()
    queued = _service(store).queue_incident_notification(_event(), _incident())
    service = notification_service.NotificationService(
        store=store,
        transport_factory=lambda _channel, _settings: (_ for _ in ()).throw(
            RuntimeError("smtp_password=factory-secret")
        ),
        settings_loader=_settings,
        user_lookup=lambda _username: None,
        event_emitter=lambda **_kwargs: None,
        now=lambda: NOW,
    )

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "error"
    assert [item["code"] for item in result["attempts"]] == [
        "transport_unavailable",
        "transport_unavailable",
    ]
    assert "factory-secret" not in str(result)


def test_message_build_failure_is_terminal_and_redacted() -> None:
    class BrokenMessageService(notification_service.NotificationService):
        def _mail_message(self, *_args, **_kwargs):
            raise ValueError("authorization=message-secret")

    store = FakeStore()
    queued = _service(store).queue_incident_notification(_event(), _incident())
    service = BrokenMessageService(
        store=store,
        transport_factory=lambda _channel, _settings: FakeTransport(),
        settings_loader=_settings,
        user_lookup=lambda _username: None,
        event_emitter=lambda **_kwargs: None,
        now=lambda: NOW,
    )

    result = service.process_delivery(str(queued["id"]))

    assert result["status"] == "error"
    assert [item["code"] for item in result["attempts"]] == [
        "message_invalid",
        "message_invalid",
    ]
    assert "message-secret" not in str(result)


def test_process_delivery_claims_directly_without_scanning_history() -> None:
    store = FakeStore()
    queued = _service(store).queue_incident_notification(_event(), _incident())
    store.query_notification_deliveries = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("history scan is forbidden")
    )

    result = _service(store).process_delivery(str(queued["id"]))

    assert result["status"] == "sent"


def test_send_test_message_is_direct_and_can_fallback() -> None:
    store = FakeStore()
    primary = FakeTransport(error=RuntimeError("down"))
    fallback = FakeTransport()
    service = _service(store, {"entra": primary, "smtp": fallback})

    result = service.send_test_message(
        channel="entra", recipient="test@example.com", use_fallback=True
    )

    assert result["status"] == "fallback"
    assert store.deliveries == {}
    assert "TEST" in primary.messages[0].subject
    assert primary.messages[0].message_id == fallback.messages[0].message_id


def test_send_test_notification_suite_routes_five_scenarios_without_store_writes() -> None:
    store = FakeStore()
    primary = FakeTransport(error=RuntimeError("down"))
    fallback = FakeTransport()
    settings = _settings()
    settings["rules"]["info"]["enabled"] = True
    settings["rules"]["warning"]["enabled"] = False
    for severity, rule in settings["rules"].items():
        rule["recipients"] = [f"{severity}@example.com"]
    lookups: list[str] = []
    service = notification_service.NotificationService(
        store=store,
        transport_factory=lambda channel, _settings: {
            "entra": primary,
            "smtp": fallback,
        }[channel],
        settings_loader=lambda: settings,
        user_lookup=lambda username: lookups.append(username) or None,
        event_emitter=lambda **_kwargs: pytest.fail("test suite must not emit events"),
        now=lambda: NOW,
    )

    result = service.send_test_notification_suite(channel="entra", use_fallback=True)

    scenarios = result["scenarios"]
    assert [item["severity"] for item in scenarios] == [
        "info",
        "warning",
        "error",
        "critical",
        "critical",
    ]
    assert [item["status"] for item in scenarios] == [
        "fallback",
        "skipped",
        "fallback",
        "fallback",
        "fallback",
    ]
    assert scenarios[-1]["kind"] == "entra_secret_expiry"
    assert all(item["recipient_count"] == 1 for item in scenarios if item["status"] != "skipped")
    assert scenarios[1]["recipient_count"] == 0
    assert len(primary.messages) == len(fallback.messages) == 4
    assert all("[TEST]" in message.subject for message in fallback.messages)
    assert any("Client Secret" in message.text_body for message in fallback.messages)
    assert store.deliveries == {}
    assert lookups == []


def test_send_test_message_rejects_invalid_recipient_without_network() -> None:
    transport = FakeTransport()
    service = _service(FakeStore(), {"entra": transport, "smtp": FakeTransport()})

    with pytest.raises(ValueError, match="adres"):
        service.send_test_message(channel="entra", recipient="bad address")

    assert transport.messages == []


def test_send_test_message_redacts_settings_loader_exception() -> None:
    store = FakeStore()
    transport = FakeTransport()
    service = notification_service.NotificationService(
        store=store,
        transport_factory=lambda _channel, _settings: transport,
        settings_loader=lambda: (_ for _ in ()).throw(
            RuntimeError("client_secret=LEAK")
        ),
        user_lookup=lambda _username: None,
        event_emitter=lambda **_kwargs: None,
        now=lambda: NOW,
    )

    result = service.send_test_message(
        channel="entra", recipient="test@example.com"
    )

    assert result == {
        "status": "error",
        "used_channel": "entra",
        "attempts": [
            {
                "channel": "entra",
                "status": "error",
                "code": "settings_unavailable",
                "category": "configuration",
                "message": "Nie można wczytać konfiguracji poczty.",
            }
        ],
        "message_id": "",
    }
    assert "LEAK" not in str(result)
    assert store.deliveries == {}
    assert transport.messages == []


def test_worker_start_is_best_effort_when_store_is_unavailable(monkeypatch) -> None:
    notification_service.stop_notification_worker()
    monkeypatch.setattr(
        notification_service,
        "_default_service",
        lambda: (_ for _ in ()).throw(RuntimeError("sqlite unavailable")),
    )

    notification_service.start_notification_worker()

    assert notification_service._WORKER_THREAD is None


def test_worker_stop_retains_live_handles_and_start_cannot_overlap(monkeypatch) -> None:
    import threading

    notification_service.stop_notification_worker()
    entered = threading.Event()
    release = threading.Event()
    services: list[object] = []

    class BlockingService:
        def recover_stale_deliveries(self) -> int:
            return 0

        def process_pending_batch(self, limit: int) -> int:
            del limit
            entered.set()
            release.wait()
            return 0

    def factory() -> object:
        service = BlockingService()
        services.append(service)
        return service

    monkeypatch.setattr(notification_service, "_default_service", factory)
    monkeypatch.setattr(notification_service, "WORKER_STOP_TIMEOUT_SECONDS", 0.01)
    notification_service.start_notification_worker()
    assert entered.wait(1)
    first_thread = notification_service._WORKER_THREAD
    first_stop = notification_service._WORKER_STOP

    notification_service.stop_notification_worker()
    assert notification_service._WORKER_THREAD is first_thread
    assert notification_service._WORKER_STOP is first_stop
    assert notification_service._WORKER_SERVICE is services[0]
    notification_service.start_notification_worker()
    assert len(services) == 1

    release.set()
    first_thread.join(timeout=1)
    notification_service.stop_notification_worker()
    assert notification_service._WORKER_THREAD is None
    assert notification_service._WORKER_STOP is None


def test_worker_default_stop_timeout_covers_transport_and_poll_margin() -> None:
    assert notification_service.WORKER_STOP_TIMEOUT_SECONDS >= 22


def test_notification_worker_health_reads_existing_thread_without_starting_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AliveThread:
        def is_alive(self) -> bool:
            return True

    monkeypatch.setattr(notification_service, "_WORKER_THREAD", AliveThread())
    monkeypatch.setattr(
        notification_service, "_WORKER_OBSERVED_AT", "2026-07-17T08:01:02.003Z"
    )
    monkeypatch.setattr(
        notification_service,
        "_default_service",
        lambda: (_ for _ in ()).throw(AssertionError("health must not start worker")),
    )

    assert notification_service.notification_worker_health() == {
        "status": "online",
        "observed_at": "2026-07-17T08:01:02.003Z",
    }
