# Realistic Test Alerts and Exception Attachments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the five-message email test suite look like real operational incidents without creating side effects, and deliver a bounded, redacted diagnostic attachment for genuine exception alerts.

**Architecture:** A frozen MailAttachment model is carried by MailMessage through Microsoft Graph and SMTP. NotificationService builds a safe attachment only for error or critical events that have exception data, persists only this safe representation, and recreates it at send time. The test suite uses the same alert-message builder to simulate five fixed incidents. The ordinary single-message test remains solely a generic mail connection test.

**Tech stack:** Python 3.14, SQLite notification outbox, Microsoft Graph REST, SMTP, FastAPI, vanilla JavaScript, pytest.

## Global constraints

- send_test_message remains unchanged in purpose: it is only a generic connection test.
- The suite sends exactly five direct, no-side-effect messages: PIMcore rejection, FTP failure, unavailable photo location, backend exception, and Entra Client Secret expiry in seven days.
- Every suite subject and visible text/HTML body starts with [TEST][SYMULACJA].
- No suite scenario creates events, incidents, outbox intents, deliveries, notification history, or other application-side effects.
- There is no immediate information scenario; the daily summary owns informational product changes.
- Only error and critical messages with top-level exception_type or traceback_text get picorgftp-sql-exception.txt.
- Validation, forbidden file/slot, bad input, non-exception photo location, and Entra-expiry cases get no attachment.
- The attachment is UTF-8 plain text, has the fixed filename, redacts password/token/Client Secret/key-ID values, and is capped at 24 KiB after sanitization.
- Regular text/HTML mail bodies, persisted delivery JSON, and public API responses never expose a raw traceback.
- Microsoft Graph and SMTP receive the same attachment content. Recipient routing, selected channel, and fallback behavior stay unchanged.

## Task 1: Add a transport-neutral text attachment model

**Files:**

- Modify: picorgftp_sql/email_delivery.py
- Modify: tests/test_email_delivery.py

**Step 1: Write failing Graph and SMTP tests**

Import base64 and MailAttachment in tests/test_email_delivery.py. Add a Graph transport test that sends one MailMessage attachment and asserts:

    attachment = payload["message"]["attachments"][0]
    assert attachment["@odata.type"] == "#microsoft.graph.fileAttachment"
    assert attachment["name"] == "picorgftp-sql-exception.txt"
    assert attachment["contentType"] == "text/plain"
    assert base64.b64decode(attachment["contentBytes"]).decode("utf-8") == "RuntimeError: safe diagnostic"

Add an SMTP test using the existing fake SMTP seam. Send a MailMessage with one attachment and assert that its serialized message contains the Content-Disposition attachment header, the fixed filename, and the diagnostic text.

**Step 2: Verify RED**

Run:

    python -m pytest tests/test_email_delivery.py -k "graph_transport_encodes_text_attachment or smtp_transport_serializes_text_attachment" -q --basetemp=pytest-temp\codex-realistic-alerts-red-transport

Expected: collection or assertions fail because MailAttachment and attachment serialization do not exist.

**Step 3: Implement the minimal shared model**

In picorgftp_sql/email_delivery.py import base64 and define the following frozen model immediately before MailMessage:

    @dataclass(frozen=True)
    class MailAttachment:
        filename: str
        content_type: str
        content: str

Add a trailing default field to MailMessage:

    attachments: Sequence[MailAttachment] = ()

In GraphMailTransport.send, base64 encode each attachment content with UTF-8 and emit an item containing the Microsoft Graph fileAttachment type, name, contentType, and contentBytes. Add the attachments property only when the sequence is nonempty, preserving current Graph payloads for ordinary mail.

In SmtpMailTransport.send, after the plain and HTML alternatives are created, add every text attachment with EmailMessage.add_attachment. Preserve the supplied filename and use text/plain subtype.

**Step 4: Verify GREEN**

Run:

    python -m pytest tests/test_email_delivery.py -q --basetemp=pytest-temp\codex-realistic-alerts-green-transport

Expected: all email delivery tests pass and ordinary Graph payloads omit the attachments property.

**Step 5: Commit**

    git add picorgftp_sql/email_delivery.py tests/test_email_delivery.py
    git commit -m "feat: add mail exception attachments"

## Task 2: Build and preserve redacted exception attachments for real alerts

**Files:**

- Modify: picorgftp_sql/notification_service.py
- Modify: tests/test_notification_service.py
- Verify: tests/test_secret_persistence.py

**Step 1: Write failing real-alert tests**

Beside the existing incident-message tests, add a test that queues and processes an error RuntimeError whose traceback contains password=PASSWORD_SENTINEL, key_id=KEY_ID_SENTINEL, and more than 30,000 filler characters. Assert:

- the delivered message has one attachment named picorgftp-sql-exception.txt with content type text/plain;
- UTF-8 byte length is at most 24 * 1024;
- neither sentinel is in the attachment;
- the persisted delivery message does not contain either sentinel.

Add a parameterized test for a warning event with exception data and an error event without exception data. Process each delivery and assert that MailMessage.attachments is exactly ().

Keep the existing normal body-redaction tests; this task adds a separate diagnostic boundary.

**Step 2: Verify RED**

Run:

    python -m pytest tests/test_notification_service.py -k "attaches_redacted or nonexception_or_nonerror" -q --basetemp=pytest-temp\codex-realistic-alerts-red-attachment

Expected: tests fail because alert payloads do not contain a safe attachment and MailMessage gets no attachments.

**Step 3: Implement a bounded local exception sanitizer**

In notification_service.py import re, Mapping, MailAttachment, and the existing sanitize_free_text helper as needed. Define constants near the other notification constants:

    _EXCEPTION_ATTACHMENT_FILENAME = "picorgftp-sql-exception.txt"
    _EXCEPTION_ATTACHMENT_LIMIT = 24 * 1024

Add a local regex that redacts values following password, token, client secret, credential key id, and key id assignments. The replacement must preserve the field label and replace only the value with [REDACTED].

Implement _safe_exception_attachment_text(value) to sanitize, apply that local regex, and sanitize again with the same byte/character boundary. Keep key-ID logic local to this helper so existing credential_key_id persistence behavior cannot change.

Implement _exception_attachment_payload(event). It returns None unless severity is error or critical and the event has a top-level exception_type or traceback_text. For qualifying events, generate a short Polish diagnostic heading, then optional exception type and traceback text; sanitize it; and return only:

    {
        "filename": _EXCEPTION_ATTACHMENT_FILENAME,
        "content_type": "text/plain",
        "content": content,
    }

**Step 4: Persist only the safe form and rebuild it at send time**

Change the return annotations of _message_payload and _append_runtime_context to dict[str, object]. After existing message fields are built, add exception_attachment only when _exception_attachment_payload returns data.

When _append_runtime_context reconstructs its mapping, retain exception_attachment only if it is a Mapping. Never add this mapping to the rendered text or HTML bodies.

In _mail_message, accept only the fixed filename and text/plain content type, sanitize the content again, and construct either an empty tuple or one MailAttachment. Pass it as attachments to MailMessage. Do not put exception type or traceback text into subject, text_body, or html_body.

**Step 5: Verify GREEN and regression safety**

Run:

    python -m pytest tests/test_notification_service.py tests/test_secret_persistence.py -q --basetemp=pytest-temp\codex-realistic-alerts-green-attachment

Expected: all selected tests pass. They prove redaction, the 24 KiB cap, safe persistence, severity gating, no attachment for ordinary failures, and unchanged secret persistence.

**Step 6: Commit**

    git add picorgftp_sql/notification_service.py tests/test_notification_service.py
    git commit -m "feat: attach redacted exception diagnostics"

## Task 3: Replace generic suite mail with five realistic simulations

**Files:**

- Modify: picorgftp_sql/notification_service.py
- Modify: tests/test_notification_service.py

**Step 1: Update the suite test first**

Modify test_send_test_notification_suite_routes_five_scenarios_without_store_writes to expect this exact kind order:

    pimcore_rejection
    ftp_failure
    photo_location_unavailable
    backend_exception
    entra_secret_expiry

Configure warning, error, and critical rules; make the primary transport fail so the test proves fallback. Assert severity order warning, error, error, critical, critical; a [TEST][SYMULACJA] prefix in every subject and visible body; no store mutations; and attachment counts 0, 1, 0, 1, 0.

**Step 2: Verify RED**

Run:

    python -m pytest tests/test_notification_service.py -k send_test_notification_suite -q --basetemp=pytest-temp\codex-realistic-alerts-red-suite

Expected: failure because the old suite uses generic severity scenarios and creates no simulated exception diagnostics.

**Step 3: Implement five fixed scenarios**

Replace _TEST_NOTIFICATION_SCENARIOS with five mappings containing kind, severity, event_type, summary, and recommended_action:

- pimcore_rejection: warning and no exception data;
- ftp_failure: error, exception_type OSError, and a synthetic FTP-transfer traceback;
- photo_location_unavailable: error and no exception data;
- backend_exception: critical, exception_type RuntimeError, and a synthetic backend traceback;
- entra_secret_expiry: critical, an explicit seven-day expiry message, and no exception data.

Add _test_suite_message(scenario, message_id, now). It should create temporary event and incident mappings, call the real _message_payload, then prefix subject, text_body, and html_body with a clear [TEST][SYMULACJA] marker and a sentence that this is a safe simulation.

Have send_test_notification_suite call _test_suite_message and then _mail_message, so FTP and backend simulations use the same attachment logic as real incident delivery. Do not call create_event, create_or_update_incident, or any store write method. Remove now-unused imports.

**Step 4: Verify GREEN**

Run:

    python -m pytest tests/test_notification_service.py -q --basetemp=pytest-temp\codex-realistic-alerts-green-suite

Expected: all notification service tests pass.

**Step 5: Commit**

    git add picorgftp_sql/notification_service.py tests/test_notification_service.py
    git commit -m "feat: simulate realistic mail alert scenarios"

## Task 4: Align safe API output and UI labels

**Files:**

- Modify: picorgftp_sql/web/app.py
- Modify: picorgftp_sql/web/static/app.js
- Modify: tests/test_observability_api.py
- Modify: tests/test_web_smoke_ci.py
- Modify: tests/test_source_integrity.py

**Step 1: Write failing API and UI checks**

Update the test-suite endpoint test for the five new kinds. For every result, assert the public projection contains only kind, severity, status, used_channel, recipient_count, and attempts.

In a UI/API fixture, include an FTP result containing private message_id, recipients, and exception_attachment fields with a unique secret-like sentinel. Assert that none of those private values reaches the public response.

Add source-integrity checks for all five JavaScript labels.

**Step 2: Verify RED**

Run:

    python -m pytest tests/test_observability_api.py tests/test_web_smoke_ci.py tests/test_source_integrity.py -q --basetemp=pytest-temp\codex-realistic-alerts-red-web

Expected: failures because the API allow-list and JavaScript labels describe the old generic suite.

**Step 3: Implement minimal UI/API changes**

Replace _EMAIL_TEST_SUITE_KINDS in web/app.py with exactly the five scenario kinds. Preserve existing endpoint authorization, five-result requirement, and response-field allow-list.

Replace the JavaScript label map in renderMailTestSuiteResult with labels for PIMcore data rejection, FTP transfer failure, unavailable photo location, unhandled backend exception, and Entra Client Secret expiry in seven days. Keep rendering status, selected channel, recipient count, and attempts unchanged.

Do not change the ordinary connection-test button or its endpoint.

**Step 4: Verify GREEN**

Run:

    python -m pytest tests/test_observability_api.py tests/test_web_smoke_ci.py tests/test_source_integrity.py -q --basetemp=pytest-temp\codex-realistic-alerts-green-web

Expected: all selected tests pass and sensitive attachment/message metadata is absent from the response.

**Step 5: Commit**

    git add picorgftp_sql/web/app.py picorgftp_sql/web/static/app.js tests/test_observability_api.py tests/test_web_smoke_ci.py tests/test_source_integrity.py
    git commit -m "feat: show realistic mail test scenarios"

## Task 5: Perform integration verification and clean generated artifacts

**Files:**

- Verify: picorgftp_sql/
- Verify: tests/
- Verify: docs/superpowers/plans/2026-07-21-realistic-test-alerts-and-exception-attachments.md

**Step 1: Run focused regression tests**

Run:

    python -m pytest tests/test_email_delivery.py tests/test_notification_service.py tests/test_observability_api.py tests/test_web_smoke_ci.py tests/test_source_integrity.py tests/test_secret_persistence.py -q --basetemp=pytest-temp\codex-realistic-alerts-focused

Expected: pass. This covers both mail transports, safe diagnostics, five simulations, API projection, UI labels, and existing secret safeguards.

**Step 2: Run static checks**

Run:

    python -m compileall -q picorgftp_sql
    git diff --check

Expected: no compilation or whitespace errors. Run a JavaScript syntax check only if node is available.

**Step 3: Run the full suite**

Run:

    python -m pytest -q --basetemp=pytest-temp\codex-realistic-alerts-full

Expected: pass.

**Step 4: Inspect final state**

Run:

    git status --short
    git diff --check
    git log --oneline -5

Expected: only expected commits and no unrelated user changes. Do not push, merge, reset, or discard changes.

**Step 5: Clean only this task's generated test directories**

Before deletion, read and resolve the exact absolute paths for all pytest-temp directories created by the commands in this plan. Remove only those directories after verification, then report what was removed. Never clean a broad pytest-temp parent or user-owned data.
