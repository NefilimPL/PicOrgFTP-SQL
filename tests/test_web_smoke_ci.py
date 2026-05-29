"""CI smoke tests for the FastAPI web panel."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("PICORGFTP_SQL_HEADLESS", "1")
os.environ.setdefault("PICORG_WEB_AUTH", "0")

try:
    from fastapi.testclient import TestClient
except Exception as exc:  # pragma: no cover - depends on CI test dependencies
    TestClient = None
    TEST_CLIENT_IMPORT_ERROR = exc
else:
    TEST_CLIENT_IMPORT_ERROR = None

from picorgftp_sql.web import app as web_app


@unittest.skipIf(
    TestClient is None,
    f"FastAPI TestClient unavailable: {TEST_CLIENT_IMPORT_ERROR}",
)
class WebSmokeCiTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["PICORG_WEB_AUTH"] = "0"

    def test_health_endpoint_returns_versioned_ok_payload(self) -> None:
        client = TestClient(web_app.app)

        response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIs(payload["ok"], True)
        self.assertTrue(str(payload["version"]).strip())
        self.assertTrue(str(payload["time"]).strip())

    def test_public_pages_and_static_assets_are_served(self) -> None:
        client = TestClient(web_app.app)

        index = client.get("/")
        login = client.get("/login")
        app_js = client.get("/static/app.js")
        app_css = client.get("/static/app.css")

        self.assertEqual(index.status_code, 200)
        self.assertIn("PicOrgFTP-SQL Web", index.text)
        self.assertIn('id="productForm"', index.text)
        self.assertIn('id="slotGrid"', index.text)
        self.assertIn(login.status_code, {200, 303})
        self.assertEqual(app_js.status_code, 200)
        self.assertIn("const state", app_js.text)
        self.assertEqual(app_css.status_code, 200)
        self.assertIn(".slot-grid", app_css.text)

    def test_critical_backend_routes_remain_registered(self) -> None:
        route_paths = {
            getattr(route, "path", "")
            for route in web_app.app.routes
        }

        expected_paths = {
            "/",
            "/login",
            "/api/health",
            "/api/login",
            "/api/logout",
            "/api/bootstrap",
            "/api/data",
            "/api/process",
            "/api/upload-cache",
            "/api/browser-extension/download",
            "/api/browser-extension/imports",
            "/api/browser-extension/ping",
            "/api/browser-extension/upload-cache",
            "/api/web-images/scan",
            "/api/web-images/cache",
            "/api/entries/search",
            "/api/entries/save",
            "/api/entries/photos",
            "/api/file",
            "/api/thumbnail",
            "/api/settings",
            "/api/users",
        }
        self.assertEqual(expected_paths - route_paths, set())

    def test_auth_enabled_protects_routes_and_accepts_login_session(self) -> None:
        previous = os.environ.get("PICORG_WEB_AUTH")
        os.environ["PICORG_WEB_AUTH"] = "1"
        try:
            client = TestClient(web_app.app)

            anonymous = client.post("/api/logout")
            self.assertEqual(anonymous.status_code, 401)

            login = client.post(
                "/api/login",
                data={"username": "admin", "password": "admin"},
            )
            self.assertEqual(login.status_code, 200)

            authenticated = client.post("/api/logout")
            self.assertEqual(authenticated.status_code, 200)
        finally:
            if previous is None:
                os.environ.pop("PICORG_WEB_AUTH", None)
            else:
                os.environ["PICORG_WEB_AUTH"] = previous

    def test_app_secret_change_returns_relogin_response_instead_of_401(self) -> None:
        previous = os.environ.get("PICORG_WEB_AUTH")
        os.environ["PICORG_WEB_AUTH"] = "1"
        try:
            client = TestClient(web_app.app)
            with patch.object(web_app.common, "APP_SECRET", "old-session-secret"):
                login = client.post(
                    "/api/login",
                    data={"username": "admin", "password": "admin"},
                )
                self.assertEqual(login.status_code, 200)

                def fake_update_settings(_payload):
                    web_app.common.APP_SECRET = "new-session-secret"
                    return {"version": "test", "processing": {}}

                with patch.object(web_app, "update_settings", side_effect=fake_update_settings):
                    response = client.post(
                        "/api/settings",
                        json={"app": {"app_secret": "new-session-secret"}},
                    )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["session_invalidated"])
            self.assertIn("Zaloguj", payload["session_message"])
        finally:
            if previous is None:
                os.environ.pop("PICORG_WEB_AUTH", None)
            else:
                os.environ["PICORG_WEB_AUTH"] = previous


if __name__ == "__main__":
    unittest.main()
