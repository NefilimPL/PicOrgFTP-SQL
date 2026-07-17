"""Contract tests for Microsoft Graph and generic SMTP delivery."""

from __future__ import annotations

import json
import ssl
from types import SimpleNamespace

import pytest

from picorgftp_sql import email_delivery
from picorgftp_sql.email_delivery import (
    GraphMailTransport,
    MailMessage,
    SmtpMailTransport,
    build_transport,
)


def sample_message() -> MailMessage:
    return MailMessage(
        message_id="incident-1",
        subject="Incident test",
        text_body="Plain incident body",
        html_body="<p>HTML incident body</p>",
        sender_address="sender+alerts@example.com",
        sender_name="PicOrgFTP SQL",
        recipients=("first@example.com", "second@example.com"),
    )


class FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeSmtp:
    def __init__(
        self,
        *,
        send_error: Exception | None = None,
        send_result: object = None,
    ) -> None:
        self.calls: list[str] = []
        self.login_args: tuple[str, str] | None = None
        self.message = ""
        self.starttls_context: ssl.SSLContext | None = None
        self.send_error = send_error
        self.send_result = send_result

    def ehlo(self) -> None:
        self.calls.append("ehlo")

    def starttls(self, *, context: ssl.SSLContext) -> None:
        self.calls.append("starttls")
        self.starttls_context = context

    def login(self, username: str, password: str) -> None:
        self.calls.append("login")
        self.login_args = (username, password)

    def send_message(self, message: object) -> object:
        self.calls.append("send_message")
        self.message = message.as_string()
        if self.send_error is not None:
            raise self.send_error
        return self.send_result

    def quit(self) -> None:
        self.calls.append("quit")

    def close(self) -> None:
        self.calls.append("close")


def test_graph_transport_requests_token_and_posts_expected_payload(monkeypatch) -> None:
    applications: list[object] = []
    requests: list[tuple[object, int]] = []
    response = FakeResponse(202)

    class FakeMsalApplication:
        def __init__(self, client_id: str, *, authority: str, client_credential: str) -> None:
            self.client_id = client_id
            self.authority = authority
            self.client_credential = client_credential
            self.scopes: list[str] | None = None
            applications.append(self)

        def acquire_token_for_client(self, scopes: list[str]) -> dict[str, str]:
            self.scopes = scopes
            return {"access_token": "access-token-sensitive"}

    def fake_urlopen(request: object, *, timeout: int) -> FakeResponse:
        requests.append((request, timeout))
        return response

    monkeypatch.setattr(
        email_delivery,
        "msal",
        SimpleNamespace(ConfidentialClientApplication=FakeMsalApplication),
    )
    monkeypatch.setattr(email_delivery.urllib.request, "urlopen", fake_urlopen)

    transport = GraphMailTransport(
        {
            "tenant_id": "tenant-id",
            "client_id": "client-id",
            "client_secret": "client-secret-sensitive",
        }
    )
    result = transport.send(sample_message())

    application = applications[0]
    assert application.client_id == "client-id"
    assert application.authority == "https://login.microsoftonline.com/tenant-id"
    assert application.client_credential == "client-secret-sensitive"
    assert application.scopes == ["https://graph.microsoft.com/.default"]

    request, timeout = requests[0]
    assert timeout == 20
    assert request.get_method() == "POST"
    assert request.full_url == (
        "https://graph.microsoft.com/v1.0/users/"
        "sender%2Balerts%40example.com/sendMail"
    )
    assert request.headers["Authorization"] == "Bearer access-token-sensitive"
    assert json.loads(request.data.decode("utf-8")) == {
        "message": {
            "subject": "Incident test",
            "body": {"contentType": "HTML", "content": "<p>HTML incident body</p>"},
            "toRecipients": [
                {"emailAddress": {"address": "first@example.com"}},
                {"emailAddress": {"address": "second@example.com"}},
            ],
            "internetMessageHeaders": [
                {"name": "x-picorg-message-id", "value": "incident-1"}
            ],
        },
        "saveToSentItems": True,
    }
    assert response.closed is True
    assert result["channel"] == "entra"
    assert result["status_code"] == 202
    assert isinstance(result["elapsed_ms"], int)
    assert "access-token-sensitive" not in repr(result)
    assert "client-secret-sensitive" not in repr(result)


@pytest.mark.parametrize("status", [200, 201, 204, 400, 500])
def test_graph_transport_accepts_only_http_202(monkeypatch, status: int) -> None:
    class FakeMsalApplication:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def acquire_token_for_client(self, _scopes: list[str]) -> dict[str, str]:
            return {"access_token": "token-sensitive"}

    monkeypatch.setattr(
        email_delivery,
        "msal",
        SimpleNamespace(ConfidentialClientApplication=FakeMsalApplication),
    )
    monkeypatch.setattr(
        email_delivery.urllib.request,
        "urlopen",
        lambda _request, *, timeout: FakeResponse(status),
    )

    with pytest.raises(RuntimeError) as exc_info:
        GraphMailTransport(
            {
                "tenant_id": "tenant",
                "client_id": "client",
                "client_secret": "secret-sensitive",
            }
        ).send(sample_message())

    assert "token-sensitive" not in str(exc_info.value)
    assert "secret-sensitive" not in str(exc_info.value)


def test_graph_transport_redacts_auth_and_http_failures(monkeypatch) -> None:
    password = "password-sensitive"
    secret = "client-secret-sensitive"
    token = "access-token-sensitive"

    class FailingMsalApplication:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def acquire_token_for_client(self, _scopes: list[str]) -> dict[str, str]:
            return {
                "error": "invalid_client",
                "error_description": f"{secret} {password} {token}",
            }

    monkeypatch.setattr(
        email_delivery,
        "msal",
        SimpleNamespace(ConfidentialClientApplication=FailingMsalApplication),
    )
    settings = {
        "tenant_id": "tenant",
        "client_id": "client",
        "client_secret": secret,
    }
    with pytest.raises(RuntimeError) as auth_error:
        GraphMailTransport(settings).send(sample_message())
    for sensitive in (password, secret, token):
        assert sensitive not in str(auth_error.value)

    class SuccessfulMsalApplication(FailingMsalApplication):
        def acquire_token_for_client(self, _scopes: list[str]) -> dict[str, str]:
            return {"access_token": token}

    monkeypatch.setattr(
        email_delivery,
        "msal",
        SimpleNamespace(ConfidentialClientApplication=SuccessfulMsalApplication),
    )

    def failing_urlopen(_request: object, *, timeout: int) -> FakeResponse:
        raise OSError(f"server echoed {password} {secret} {token}")

    monkeypatch.setattr(email_delivery.urllib.request, "urlopen", failing_urlopen)
    with pytest.raises(RuntimeError) as http_error:
        GraphMailTransport(settings).send(sample_message())
    for sensitive in (password, secret, token):
        assert sensitive not in str(http_error.value)


def test_graph_transport_fails_safely_when_msal_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(email_delivery, "msal", None)

    with pytest.raises(RuntimeError) as exc_info:
        GraphMailTransport(
            {
                "tenant_id": "tenant",
                "client_id": "client",
                "client_secret": "secret-sensitive",
            }
        ).send(sample_message())

    assert "secret-sensitive" not in str(exc_info.value)
    assert "MSAL" in str(exc_info.value)


def test_smtp_transport_uses_starttls_login_and_message_id(monkeypatch) -> None:
    smtp = FakeSmtp()
    monkeypatch.setattr(
        email_delivery.smtplib,
        "SMTP",
        lambda host, port, timeout: smtp,
    )
    transport = SmtpMailTransport(
        {
            "host": "smtp.example",
            "port": 587,
            "security": "starttls",
            "username": "sender",
            "password": "secret",
        }
    )
    result = transport.send(sample_message())

    assert smtp.calls[:2] == ["ehlo", "starttls"]
    assert smtp.login_args == ("sender", "secret")
    assert smtp.starttls_context is not None
    assert smtp.starttls_context.verify_mode == ssl.CERT_REQUIRED
    assert smtp.starttls_context.check_hostname is True
    assert "Message-ID: <incident-1@picorgftp-sql>" in smtp.message
    assert "Subject: Incident test" in smtp.message
    assert "first@example.com, second@example.com" in smtp.message
    assert "Plain incident body" in smtp.message
    assert "HTML incident body" in smtp.message
    assert smtp.calls[-1] == "quit"
    assert result["channel"] == "smtp"
    assert result["status"] == "sent"
    assert isinstance(result["elapsed_ms"], int)
    assert "secret" not in repr(result)


def test_smtp_transport_uses_implicit_tls_without_empty_username_login(monkeypatch) -> None:
    smtp = FakeSmtp(send_result={})
    calls: list[tuple[str, int, int, ssl.SSLContext]] = []

    def fake_smtp_ssl(
        host: str,
        port: int,
        timeout: int,
        *,
        context: ssl.SSLContext,
    ) -> FakeSmtp:
        calls.append((host, port, timeout, context))
        return smtp

    monkeypatch.setattr(email_delivery.smtplib, "SMTP_SSL", fake_smtp_ssl)

    result = SmtpMailTransport(
        {
            "host": "smtp.example",
            "port": 465,
            "security": "tls",
            "username": "  ",
            "password": "password-sensitive",
        }
    ).send(sample_message())

    assert calls[0][:3] == ("smtp.example", 465, 20)
    assert calls[0][3].verify_mode == ssl.CERT_REQUIRED
    assert calls[0][3].check_hostname is True
    assert smtp.login_args is None
    assert "starttls" not in smtp.calls
    assert result["channel"] == "smtp"
    assert "password-sensitive" not in repr(result)


def test_smtp_transport_supports_plain_mode_without_tls(monkeypatch) -> None:
    smtp = FakeSmtp()
    calls: list[tuple[str, int, int]] = []

    def fake_smtp(host: str, port: int, timeout: int) -> FakeSmtp:
        calls.append((host, port, timeout))
        return smtp

    monkeypatch.setattr(email_delivery.smtplib, "SMTP", fake_smtp)

    SmtpMailTransport(
        {
            "host": "smtp.example",
            "port": 25,
            "security": "none",
            "username": "",
            "password": "password-sensitive",
        }
    ).send(sample_message())

    assert calls == [("smtp.example", 25, 20)]
    assert "starttls" not in smtp.calls
    assert smtp.login_args is None
    assert smtp.calls[-1] == "quit"


def test_smtp_transport_redacts_errors_and_always_cleans_up(monkeypatch) -> None:
    password = "password-sensitive"
    smtp = FakeSmtp(send_error=OSError(f"server echoed {password}"))
    monkeypatch.setattr(
        email_delivery.smtplib,
        "SMTP",
        lambda host, port, timeout: smtp,
    )

    with pytest.raises(RuntimeError) as exc_info:
        SmtpMailTransport(
            {
                "host": "smtp.example",
                "port": 25,
                "security": "none",
                "username": "sender",
                "password": password,
            }
        ).send(sample_message())

    assert password not in str(exc_info.value)
    assert smtp.calls[-1] == "quit"


def test_smtp_transport_rejects_redacted_recipient_refusals_and_cleans_up(
    monkeypatch,
) -> None:
    sensitive_response = (
        "550 password-sensitive recipient@example.com Plain incident body"
    )
    smtp = FakeSmtp(
        send_result={
            "recipient@example.com": (550, sensitive_response.encode("utf-8"))
        }
    )
    monkeypatch.setattr(
        email_delivery.smtplib,
        "SMTP",
        lambda host, port, timeout: smtp,
    )

    with pytest.raises(RuntimeError) as exc_info:
        SmtpMailTransport(
            {
                "host": "smtp.example",
                "port": 25,
                "security": "none",
                "username": "sender",
                "password": "password-sensitive",
            }
        ).send(sample_message())

    assert str(exc_info.value) == "SMTP delivery failed."
    for sensitive in (
        sensitive_response,
        "password-sensitive",
        "recipient@example.com",
        "Plain incident body",
    ):
        assert sensitive not in str(exc_info.value)
    assert smtp.calls[-1] == "quit"


def test_build_transport_selects_supported_channel() -> None:
    assert isinstance(build_transport("entra", {}), GraphMailTransport)
    assert isinstance(build_transport("smtp", {}), SmtpMailTransport)
    with pytest.raises(ValueError):
        build_transport("unsupported", {"password": "password-sensitive"})
