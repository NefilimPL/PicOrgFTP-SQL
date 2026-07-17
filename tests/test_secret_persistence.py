from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from picorgftp_sql import logging_utils, observability, web_data
from picorgftp_sql.sqlite_store import SqliteStore
from picorgftp_sql.web import app as web_app


def _assert_secret_absent(value: object, sentinel: str) -> None:
    __tracebackhide__ = True
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    if sentinel in serialized:
        pytest.fail(
            "secret sentinel reached a durable or public boundary",
            pytrace=False,
        )


def _assert_all_secrets_absent(value: object, sentinels: list[str]) -> None:
    for sentinel in sentinels:
        _assert_secret_absent(value, sentinel)


def test_free_text_redaction_covers_credentials_without_harming_identifiers() -> None:
    sentinels = [
        "AUTH_SENTINEL_F1",
        "BEARER_SENTINEL_F1",
        "BASIC_SENTINEL_F1",
        "PASSWORD_SENTINEL_F1",
        "TOKEN_SENTINEL_F1",
        "APIKEY_SENTINEL_F1",
        "COOKIE_SENTINEL_F1",
        "URI_SENTINEL_F1",
        "CONNECTION_SENTINEL_F1",
    ]
    payload = {
        "authorization_header": "Authorization: Custom AUTH_SENTINEL_F1",
        "bearer": "upstream replied Bearer BEARER_SENTINEL_F1",
        "basic": "proxy used Basic BASIC_SENTINEL_F1",
        "quoted": 'password="PASSWORD_SENTINEL_F1"',
        "plain_with_context": (
            "password=PASSWORD_SENTINEL_F1 dalsza diagnoza EAN 5901234567890"
        ),
        "json_text": '{"access_token": "TOKEN_SENTINEL_F1"}',
        "api": "api key: APIKEY_SENTINEL_F1",
        "cookie_header": "Cookie: session=COOKIE_SENTINEL_F1; Path=/",
        "uri": "mssql://operator:URI_SENTINEL_F1@sql.local/catalog",
        "connection": (
            "Server=sql.local;User Id=operator;Password="
            "CONNECTION_SENTINEL_F1;Database=products"
        ),
        "diagnostic": (
            "Nie udało się zaktualizować produktu EAN 5901234567890, "
            "object ID 12842, plik C:\\obrazy\\5901234567890_01.jpg"
        ),
    }

    redacted = observability.redact_value(payload)

    _assert_all_secrets_absent(redacted, sentinels)
    assert json.dumps(redacted, ensure_ascii=False).count("[REDACTED]") >= len(sentinels)
    diagnostic = str(redacted["diagnostic"])
    assert "5901234567890" in diagnostic
    assert "12842" in diagnostic
    assert "C:\\obrazy\\5901234567890_01.jpg" in diagnostic
    assert "dalsza diagnoza EAN 5901234567890" in str(
        redacted["plain_with_context"]
    )
    assert observability.redact_value(redacted) == redacted


def test_sqlite_persistence_sanitizes_events_incidents_and_history(tmp_path: Path) -> None:
    sentinels = [
        "SUMMARY_SENTINEL_F1",
        "ACTION_SENTINEL_F1",
        "TRACE_SENTINEL_F1",
        "DETAIL_SENTINEL_F1",
        "CONTEXT_SENTINEL_F1",
        "HISTORY_SENTINEL_F1",
    ]
    store = SqliteStore(str(tmp_path / "app.sqlite"))
    event = store.append_operational_event(
        {
            "id": "evt-secret-boundary",
            "created_at": "2026-07-17T10:00:00.000Z",
            "severity": "error",
            "event_type": "integration.failed",
            "summary": "Authorization: Bearer SUMMARY_SENTINEL_F1",
            "recommended_action": "password=ACTION_SENTINEL_F1",
            "traceback_text": (
                "RuntimeError: smtp://worker:TRACE_SENTINEL_F1@mail.local"
            ),
            "details": {
                "provider_error": "access_token: DETAIL_SENTINEL_F1",
                "ean": "5901234567890",
            },
        }
    )
    incident = store.upsert_incident(
        {
            "id": "inc-secret-boundary",
            "fingerprint": "fingerprint-secret-boundary",
            "severity": "error",
            "event_type": "integration.failed",
            "first_seen_at": "2026-07-17T10:00:00.000Z",
            "last_seen_at": "2026-07-17T10:00:00.000Z",
            "context": {
                "provider_error": "Basic CONTEXT_SENTINEL_F1",
                "object_id": "12842",
            },
        }
    )
    store.append_history(
        {
            "id": "hist-secret-boundary",
            "created_at": "2026-07-17T10:00:00.000Z",
            "ean": "5901234567890",
            "summary": "Pimcore token=HISTORY_SENTINEL_F1",
            "details": {
                "integrations": {
                    "ftp": {
                        "error": "ftp://operator:HISTORY_SENTINEL_F1@ftp.local"
                    }
                }
            },
        }
    )

    with sqlite3.connect(store.path) as conn:
        raw_rows = {
            "event": conn.execute(
                "SELECT summary, recommended_action, traceback_text, details_json "
                "FROM operational_events WHERE id = ?",
                ("evt-secret-boundary",),
            ).fetchone(),
            "incident": conn.execute(
                "SELECT context_json FROM incidents WHERE id = ?",
                ("inc-secret-boundary",),
            ).fetchone(),
            "history": conn.execute(
                "SELECT payload_json FROM web_history WHERE id = ?",
                ("hist-secret-boundary",),
            ).fetchone(),
        }

    durable_and_loaded = {
        "rows": raw_rows,
        "event": event,
        "incident": incident,
        "events_api_source": store.query_operational_events(limit=20),
        "incidents_api_source": store.query_incidents(limit=20),
        "history": store.load_history(),
    }
    _assert_all_secrets_absent(durable_and_loaded, sentinels)
    serialized = json.dumps(durable_and_loaded, ensure_ascii=False, default=str)
    assert serialized.count("[REDACTED]") >= len(sentinels)
    assert "5901234567890" in serialized
    assert "12842" in serialized


def test_pimcore_submission_audit_sanitizes_nested_integration_errors(
    tmp_path: Path,
) -> None:
    sentinel = "PIMCORE_AUDIT_SENTINEL_F1"
    store = SqliteStore(str(tmp_path / "app.sqlite"))

    stored = store.append_pimcore_submission(
        {
            "id": "pim-secret-boundary",
            "operation_id": "operation-12842",
            "operation_type": "update",
            "ean": "5901234567890",
            "object_id": "12842",
            "status": "failed",
            "values": {"Name": "Krzesło"},
            "payload": {
                "integrations": {
                    "sql": {"error": f"password={sentinel}"},
                    "ftp": {"error": f"Bearer {sentinel}"},
                }
            },
            "result": {"provider_error": f"client_secret: {sentinel}"},
            "warnings": [f"api key={sentinel}"],
            "created_at": "2026-07-17T10:00:00.000Z",
        }
    )

    with sqlite3.connect(store.path) as conn:
        raw = conn.execute(
            "SELECT values_json, payload_json, result_json, warnings_json "
            "FROM pimcore_submissions WHERE id = ?",
            ("pim-secret-boundary",),
        ).fetchone()
    projected = store.query_pimcore_submissions(limit=20)

    _assert_secret_absent(
        {"stored": stored, "raw": raw, "projected": projected},
        sentinel,
    )
    serialized = json.dumps(
        {"stored": stored, "raw": raw, "projected": projected},
        ensure_ascii=False,
        default=str,
    )
    assert serialized.count("[REDACTED]") >= 4
    assert "5901234567890" in serialized
    assert "12842" in serialized


def test_event_mirror_and_legacy_text_files_receive_only_sanitized_values(
    tmp_path: Path, monkeypatch
) -> None:
    sentinels = [
        "MIRROR_SENTINEL_F1",
        "MIRROR_DETAIL_SENTINEL_F1",
        "DIRECT_MIRROR_SENTINEL_F1",
        "HISTORY_JSON_SENTINEL_F1",
        "WEB_LOG_SENTINEL_F1",
    ]

    class BrokenStore:
        def append_operational_event(self, _event):
            raise OSError("storage unavailable")

    mirrored: list[dict[str, object]] = []
    monkeypatch.setattr(observability, "observability_store", lambda: BrokenStore())
    observability.register_event_mirror(lambda event: mirrored.append(dict(event)))
    try:
        observability.emit_event(
            severity="info",
            event_type="mirror.test",
            summary="Bearer MIRROR_SENTINEL_F1",
            details={"provider": "client_secret: MIRROR_DETAIL_SENTINEL_F1"},
        )
        observability._mirror_event(
            {"summary": "password=DIRECT_MIRROR_SENTINEL_F1"}
        )
    finally:
        observability.register_event_mirror(None)

    monkeypatch.setattr(web_data, "_active_sqlite_store", lambda: None)
    monkeypatch.setattr(web_data.settings, "AC", str(tmp_path))
    history = web_data.record_history(
        username="admin",
        action="process",
        ean="5901234567890",
        summary="Pimcore password=HISTORY_JSON_SENTINEL_F1",
        details={"ftp": {"error": "token: HISTORY_JSON_SENTINEL_F1"}},
    )
    history_file = (tmp_path / web_data.WEB_HISTORY_PATH).read_text(encoding="utf-8")

    monkeypatch.setattr(web_app.settings, "LOG_DIR", str(tmp_path / "logs"))
    web_app._write_web_event(
        level="error",
        event="PROCESS_FAILED",
        username="admin",
        message="Authorization: Basic WEB_LOG_SENTINEL_F1",
        details={"error": "api_key=WEB_LOG_SENTINEL_F1"},
    )
    web_log = (Path(web_app.settings.LOG_DIR) / "picorg_web_events.log").read_text(
        encoding="utf-8"
    )

    persisted = {
        "mirror": mirrored,
        "history": history,
        "history_file": history_file,
        "web_log": web_log,
    }
    _assert_all_secrets_absent(persisted, sentinels)
    assert json.dumps(persisted, ensure_ascii=False).count("[REDACTED]") >= 4


def test_rotating_log_writers_sanitize_exception_derived_free_text(
    tmp_path: Path, monkeypatch
) -> None:
    sentinel = "ROTATING_LOG_SENTINEL_F1"
    error_path = tmp_path / "error.log"
    info_path = tmp_path / "changes.log"
    monkeypatch.setattr(logging_utils.settings, "AM", str(error_path))
    monkeypatch.setattr(logging_utils.settings, "BM", str(info_path))

    logging_utils.log_error(
        f"RuntimeError: mssql://worker:{sentinel}@sql.local/products"
    )
    logging_utils.log_info(f"Provider replied access_token={sentinel}")

    content = error_path.read_text(encoding="utf-8") + info_path.read_text(
        encoding="utf-8"
    )
    _assert_secret_absent(content, sentinel)
    assert content.count("[REDACTED]") >= 2


def test_observability_public_projection_sanitizes_untrusted_exception_strings(
    monkeypatch,
) -> None:
    sentinel = "PUBLIC_SENTINEL_F1"

    class Store:
        @staticmethod
        def unread_alert_summary(_username: str) -> dict[str, int]:
            return {"warning": 0, "error": 1, "critical": 0}

    monkeypatch.setattr(web_app, "observability_store", lambda: Store())
    payload = web_app._observability_api_payload(
        "admin",
        {
            "items": [
                {
                    "id": "evt-public-boundary",
                    "summary": "password=PUBLIC_SENTINEL_F1",
                    "traceback_text": "Bearer PUBLIC_SENTINEL_F1",
                    "details": {"exception": "api key: PUBLIC_SENTINEL_F1"},
                }
            ],
            "next_cursor": "",
        },
    )

    _assert_secret_absent(payload, sentinel)
    assert json.dumps(payload).count("[REDACTED]") >= 3
