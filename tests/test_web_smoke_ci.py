"""CI smoke tests for the FastAPI web panel."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import io

os.environ.setdefault("PICORGFTP_SQL_HEADLESS", "1")
os.environ.setdefault("PICORG_WEB_AUTH", "0")

try:
    from fastapi.testclient import TestClient
except Exception as exc:  # pragma: no cover - depends on CI test dependencies
    TestClient = None
    TEST_CLIENT_IMPORT_ERROR = exc
else:
    TEST_CLIENT_IMPORT_ERROR = None

from picorgftp_sql import web_data
from picorgftp_sql import observability
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
        self.assertEqual(payload["components"]["backend"]["status"], "online")
        self.assertIn(payload["components"]["sqlite"]["status"], {"online", "critical"})
        self.assertIn(
            payload["components"]["job_processor"]["status"],
            {"online", "critical"},
        )

    def test_client_error_route_requires_auth_and_csrf_and_emits_redacted_critical(self) -> None:
        class EventStore:
            def __init__(self) -> None:
                self.events = []

            def append_operational_event(self, event):
                self.events.append(dict(event))
                return dict(event)

        previous = os.environ.get("PICORG_WEB_AUTH")
        os.environ["PICORG_WEB_AUTH"] = "1"
        store = EventStore()
        try:
            client = TestClient(web_app.app)
            payload = {
                "kind": "error",
                "message": "Frontend exploded",
                "source": "app.js",
                "line": 42,
                "column": 7,
                "stack": "Error: Frontend exploded",
                "token": "browser-secret",
            }

            anonymous = client.post("/api/observability/client-errors", json=payload)
            self.assertEqual(anonymous.status_code, 401)

            login = client.post(
                "/api/login",
                data={"username": "admin", "password": "admin"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            self.assertEqual(login.status_code, 200)
            csrf = login.json()["csrf_token"]
            forged = client.post(
                "/api/observability/client-errors",
                json=payload,
                headers={"X-PicOrg-CSRF": "bad"},
            )
            self.assertEqual(forged.status_code, 403)

            with patch.object(observability, "observability_store", return_value=store):
                response = client.post(
                    "/api/observability/client-errors",
                    json=payload,
                    headers={"X-PicOrg-CSRF": csrf},
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"ok": True})
            event = store.events[-1]
            self.assertEqual(event["severity"], "critical")
            self.assertEqual(event["event_type"], "frontend.unhandled_error")
            self.assertEqual(event["details"]["token"], "[REDACTED]")
        finally:
            if previous is None:
                os.environ.pop("PICORG_WEB_AUTH", None)
            else:
                os.environ["PICORG_WEB_AUTH"] = previous

    def test_unhandled_backend_error_returns_only_safe_correlation_payload(self) -> None:
        test_app = web_app.create_app()

        @test_app.get("/api/test-unhandled-error")
        def fail_for_test():
            raise RuntimeError("database password=top-secret")

        client = TestClient(test_app, raise_server_exceptions=False)
        with (
            patch.object(web_app, "emit_event") as emit_event,
            patch.object(web_app, "log_error") as log_error,
        ):
            response = client.get("/api/test-unhandled-error")

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["detail"], "Wystapil nieoczekiwany blad aplikacji.")
        self.assertTrue(payload["correlation_id"])
        self.assertNotIn("password", response.text)
        self.assertEqual(emit_event.call_args.kwargs["severity"], "critical")
        self.assertEqual(
            emit_event.call_args.kwargs["correlation_id"], payload["correlation_id"]
        )
        self.assertIsInstance(emit_event.call_args.kwargs["exception"], RuntimeError)
        self.assertIn(payload["correlation_id"], log_error.call_args.args[0])

    def test_synchronous_process_endpoint_persists_correlated_success(self) -> None:
        snapshot = web_app._ProcessFormSnapshot(
            fields={"ean": "5901234567890", "name": "Created product"}
        )
        result = {
            "timing": {"stages": [{"key": "prepare", "elapsed_ms": 12}]},
            "ftp": {},
            "sql": {},
            "local_delete": {},
            "skipped_slots": [],
            "entry": {"product_id": "123"},
        }
        client = TestClient(web_app.app)

        with (
            patch.object(web_app, "_materialize_process_form", return_value=snapshot),
            patch.object(web_app, "_process_upload_snapshot", return_value=result) as process,
            patch.object(web_app, "record_job") as record_job,
            patch.object(web_app, "emit_event") as emit_event,
        ):
            response = client.post("/api/process", data={})

        self.assertEqual(response.status_code, 200)
        job_id = process.call_args.kwargs["job_id"]
        self.assertTrue(job_id)
        self.assertEqual(
            [call.args[0]["status"] for call in record_job.call_args_list],
            ["running", "completed"],
        )
        self.assertTrue(
            all(call.args[0]["id"] == job_id for call in record_job.call_args_list)
        )
        result_event = emit_event.call_args_list[-1]
        self.assertEqual(result_event.kwargs["event_type"], "process.completed")
        self.assertEqual(result_event.kwargs["severity"], "info")
        self.assertEqual(result_event.kwargs["job_id"], job_id)

    def test_synchronous_process_failure_is_job_correlated_and_returns_safe_500(self) -> None:
        snapshot = web_app._ProcessFormSnapshot(fields={"ean": "5901234567890"})
        client = TestClient(web_app.app, raise_server_exceptions=False)

        with (
            patch.object(web_app, "_materialize_process_form", return_value=snapshot),
            patch.object(
                web_app,
                "_process_upload_snapshot",
                side_effect=RuntimeError("database password=top-secret"),
            ) as process,
            patch.object(web_app, "record_job") as record_job,
            patch.object(web_app, "emit_event") as emit_event,
            patch.object(web_app, "log_error"),
        ):
            response = client.post("/api/process", data={})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Wystapil nieoczekiwany blad aplikacji.")
        job_id = process.call_args.kwargs["job_id"]
        self.assertTrue(job_id)
        self.assertEqual(record_job.call_args_list[-1].args[0]["status"], "failed")
        self.assertEqual(record_job.call_args_list[-1].args[0]["id"], job_id)
        process_failure = next(
            call
            for call in emit_event.call_args_list
            if call.kwargs["event_type"] == "process.failed"
        )
        self.assertEqual(process_failure.kwargs["severity"], "critical")
        self.assertEqual(process_failure.kwargs["job_id"], job_id)
        backend_failure = next(
            call
            for call in emit_event.call_args_list
            if call.kwargs["event_type"] == "backend.unhandled_error"
        )
        self.assertEqual(
            backend_failure.kwargs["correlation_id"], response.json()["correlation_id"]
        )


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
            "/api/github/repository",
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
            "/api/settings/import-legacy",
            "/api/settings/sqlite/repair",
            "/api/settings/sqlite/backup",
            "/api/settings/sqlite/backups",
            "/api/settings/sqlite/backup-diff",
            "/api/settings/sqlite/restore",
            "/api/settings/sql-columns/detect",
            "/api/server/presence",
            "/api/server/presence/leave",
            "/api/users",
        }
        self.assertEqual(expected_paths - route_paths, set())

    def test_github_repository_endpoint_returns_status_payload(self) -> None:
        client = TestClient(web_app.app)
        payload = {
            "available": True,
            "private": False,
            "repository": {"full_name": "NefilimPL/PicOrgFTP-SQL"},
            "latest_release": {"tag_name": "v1.2.3"},
            "license": {"spdx_id": "MIT"},
            "owner": {"login": "NefilimPL"},
            "contributors": [],
            "current_version": "dev",
            "update_available": True,
            "message": "",
            "checked_at": "2026-07-09T00:00:00Z",
        }

        with patch.object(web_app, "github_repository_status", return_value=payload):
            response = client.get("/api/github/repository")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)

    def test_legacy_import_endpoint_switches_to_sqlite(self) -> None:
        client = TestClient(web_app.app)
        with (
            patch.object(web_app.settings, "AC", "C:/Photos"),
            patch.object(web_app.storage_settings, "resolve_sqlite_path", return_value="C:/Data/app.sqlite"),
            patch.object(
                web_app,
                "import_legacy_to_sqlite",
                return_value={"ok": True, "entries": 1},
            ) as importer,
            patch.object(web_app.storage_settings, "save_bootstrap_settings") as save_bootstrap,
            patch.object(web_app.data_store, "reset_active_store_cache") as reset_store,
            patch.object(web_app.config, "initialize_config"),
            patch.object(web_app, "settings_snapshot", return_value={"data_mode": "sqlite"}),
        ):
            response = client.post("/api/settings/import-legacy")

        self.assertEqual(response.status_code, 200)
        importer.assert_called_once_with(
            legacy_dir="C:/Photos",
            database_path="C:/Data/app.sqlite",
        )
        save_bootstrap.assert_called_once_with({"data_mode": "sqlite"})
        reset_store.assert_called_once()
        self.assertEqual(response.json()["settings"]["data_mode"], "sqlite")

    def test_sqlite_repair_endpoint_returns_summary(self) -> None:
        client = TestClient(web_app.app)
        with (
            patch.object(web_app.storage_settings, "resolve_sqlite_path", return_value="C:/Data/app.sqlite"),
            patch.object(web_app.storage_settings, "resolve_backup_dir", return_value="C:/Data/BACKUP"),
            patch.object(web_app, "repair_sqlite_database", return_value={"ok": True, "integrity_check": "ok"}),
            patch.object(web_app, "settings_snapshot", return_value={"data_mode": "sqlite"}),
        ):
            response = client.post("/api/settings/sqlite/repair")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_sqlite_backup_history_endpoint_lists_backups(self) -> None:
        client = TestClient(web_app.app)
        with (
            patch.object(web_app.storage_settings, "resolve_backup_dir", return_value="C:/Data/BACKUP"),
            patch.object(web_app.sqlite_backup, "list_backups", return_value=[{"backup_path": "copy.sqlite"}]),
        ):
            response = client.get("/api/settings/sqlite/backups")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["backup_path"], "copy.sqlite")

    def test_backup_scheduler_runs_due_slots(self) -> None:
        with (
            patch.object(
                web_app.storage_settings,
                "load_backup_settings",
                return_value={
                    "enabled": True,
                    "days": ["mon"],
                    "hours": [8],
                    "max_copies": 2,
                    "last_run_slots": [],
                },
            ),
            patch.object(web_app.sqlite_backup, "due_schedule_slots", return_value=["2026-06-22T08"]),
            patch.object(web_app.sqlite_backup, "create_backup", return_value={"ok": True}),
            patch.object(web_app.storage_settings, "resolve_sqlite_path", return_value="C:/Data/app.sqlite"),
            patch.object(web_app.storage_settings, "resolve_backup_dir", return_value="C:/Data/BACKUP"),
            patch.object(
                web_app.sqlite_backup,
                "mark_schedule_slots_run",
                return_value={
                    "enabled": True,
                    "days": ["mon"],
                    "hours": [8],
                    "max_copies": 2,
                    "last_run_slots": ["2026-06-22T08"],
                },
            ),
            patch.object(web_app.storage_settings, "save_backup_settings") as save_backup_settings,
        ):
            result = web_app._run_due_sqlite_backups_once()

        self.assertEqual(result["created"], 1)
        save_backup_settings.assert_called_once()

    def test_live_event_pruning_runs_no_more_than_hourly(self) -> None:
        with (
            patch.object(web_app, "prune_live_events", return_value=3) as prune,
            patch.object(web_app.time, "monotonic", side_effect=[100.0, 200.0, 3701.0]),
        ):
            web_app._LIVE_EVENT_LAST_PRUNED = 0.0
            self.assertEqual(web_app._prune_live_events_if_due(force=True), 3)
            self.assertEqual(web_app._prune_live_events_if_due(), 0)
            self.assertEqual(web_app._prune_live_events_if_due(), 3)

        self.assertEqual(prune.call_count, 2)

    def test_sql_column_detection_endpoint_updates_settings(self) -> None:
        client = TestClient(web_app.app)
        cfg = {
            web_app.SQL_AVAILABLE_COLUMNS_KEY: [],
            web_app.H: {},
            web_app.P: {},
            web_app.K: {},
        }

        with (
            patch.object(web_app.config, "CONFIG", cfg),
            patch.object(
                web_app,
                "detect_available_columns",
                return_value={
                    "ok": True,
                    "columns": ["img_01", "img_02"],
                    "table": "object_query_1",
                    "preview": "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS",
                    "message": "Wykryto 2 pola SQL.",
                },
            ),
            patch.object(web_app.config, "save_config") as save_config,
            patch.object(
                web_app,
                "settings_snapshot",
                return_value={"sql_available_columns": ["img_01", "img_02"]},
            ),
        ):
            response = client.post("/api/settings/sql-columns/detect")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["columns"], ["img_01", "img_02"])
        self.assertEqual(cfg[web_app.SQL_AVAILABLE_COLUMNS_KEY], ["img_01", "img_02"])
        save_config.assert_called_once()

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
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            self.assertEqual(login.status_code, 200)
            csrf_headers = {"X-PicOrg-CSRF": login.json()["csrf_token"]}
            presence = client.get("/api/server/presence")
            self.assertEqual(presence.status_code, 200)
            self.assertEqual(presence.json(), {"enabled": False, "users": []})

            forged = client.post("/api/logout", headers={"X-PicOrg-CSRF": "bad"})
            self.assertEqual(forged.status_code, 403)

            authenticated = client.post("/api/logout", headers=csrf_headers)
            self.assertEqual(authenticated.status_code, 200)
        finally:
            if previous is None:
                os.environ.pop("PICORG_WEB_AUTH", None)
            else:
                os.environ["PICORG_WEB_AUTH"] = previous

    def test_security_headers_include_strict_csp(self) -> None:
        client = TestClient(web_app.app)

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        csp = response.headers.get("content-security-policy", "")
        self.assertIn("script-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertNotIn("unsafe-inline", csp)

    def test_login_rate_limit_is_per_ip(self) -> None:
        previous = os.environ.get("PICORG_WEB_AUTH")
        os.environ["PICORG_WEB_AUTH"] = "1"
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with (
                    patch.object(web_app.settings, "AC", temp_dir),
                    patch.object(web_app, "RATE_LIMIT_LOGIN_ATTEMPTS", 2),
                    patch.object(web_app, "RATE_LIMIT_LOGIN_WINDOW_SECONDS", 60),
                ):
                    web_app._RATE_LIMITS.clear()
                    client = TestClient(web_app.app)
                    for _index in range(2):
                        response = client.post(
                            "/api/login",
                            data={"username": "admin", "password": "bad"},
                            headers={"X-Requested-With": "XMLHttpRequest"},
                        )
                        self.assertEqual(response.status_code, 401)

                    limited = client.post(
                        "/api/login",
                        data={"username": "admin", "password": "bad"},
                        headers={"X-Requested-With": "XMLHttpRequest"},
                    )

            self.assertEqual(limited.status_code, 429)
            self.assertIn("Retry-After", limited.headers)
        finally:
            web_app._RATE_LIMITS.clear()
            if previous is None:
                os.environ.pop("PICORG_WEB_AUTH", None)
            else:
                os.environ["PICORG_WEB_AUTH"] = previous

    def test_failed_admin_login_is_logged_and_locked_until_manual_unlock(self) -> None:
        previous = os.environ.get("PICORG_WEB_AUTH")
        os.environ["PICORG_WEB_AUTH"] = "1"
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with (
                    patch.object(web_app.settings, "AC", temp_dir),
                    patch.object(web_app.settings, "LOG_DIR", temp_dir),
                ):
                    client = TestClient(web_app.app)
                    response = None
                    for _index in range(web_data.LOGIN_FAILURE_LIMIT):
                        response = client.post(
                            "/api/login",
                            data={"username": "admin", "password": "bad"},
                            headers={"X-Requested-With": "XMLHttpRequest"},
                        )

                    self.assertIsNotNone(response)
                    self.assertEqual(response.status_code, 423)
                    log_text = (web_app._web_events_log_path()).read_text(encoding="utf-8")
                    self.assertIn("LOGIN_FAILED", log_text)
                    self.assertIn("Konto administratora zablokowane", log_text)
        finally:
            if previous is None:
                os.environ.pop("PICORG_WEB_AUTH", None)
            else:
                os.environ["PICORG_WEB_AUTH"] = previous

    def test_password_change_invalidates_current_session(self) -> None:
        previous = os.environ.get("PICORG_WEB_AUTH")
        os.environ["PICORG_WEB_AUTH"] = "1"
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with patch.object(web_app.settings, "AC", temp_dir):
                    client = TestClient(web_app.app)
                    login = client.post(
                        "/api/login",
                        data={"username": "admin", "password": "admin"},
                        headers={"X-Requested-With": "XMLHttpRequest"},
                    )
                    self.assertEqual(login.status_code, 200)
                    headers = {"X-PicOrg-CSRF": login.json()["csrf_token"]}
                    response = client.patch(
                        "/api/users/admin",
                        json={"password": "new-admin"},
                        headers=headers,
                    )

                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.json()["session_invalidated"])
                    self.assertEqual(client.get("/api/bootstrap").status_code, 401)
        finally:
            if previous is None:
                os.environ.pop("PICORG_WEB_AUTH", None)
            else:
                os.environ["PICORG_WEB_AUTH"] = previous

    def test_browser_extension_token_version_can_be_revoked(self) -> None:
        previous = os.environ.get("PICORG_WEB_AUTH")
        os.environ["PICORG_WEB_AUTH"] = "1"
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with patch.object(web_app.settings, "AC", temp_dir):
                    client = TestClient(web_app.app)
                    login = client.post(
                        "/api/login",
                        data={"username": "admin", "password": "admin"},
                        headers={"X-Requested-With": "XMLHttpRequest"},
                    )
                    self.assertEqual(login.status_code, 200)
                    headers = {"X-PicOrg-CSRF": login.json()["csrf_token"]}
                    archive_response = client.get("/api/browser-extension/download")
                    self.assertEqual(archive_response.status_code, 200)
                    with zipfile.ZipFile(io.BytesIO(archive_response.content)) as archive:
                        defaults = archive.read(
                            "picorgftp-sql-browser-extension/defaults.js"
                        ).decode("utf-8")
                    self.assertIn("tokenVersion", defaults)
                    token = defaults.split('"apiToken": "', 1)[1].split('"', 1)[0]
                    ping = client.get(
                        "/api/browser-extension/ping",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    self.assertEqual(ping.status_code, 200)
                    self.assertEqual(ping.json()["token_version"], 0)

                    revoked = client.patch(
                        "/api/users/admin",
                        json={"revoke_extension_token": True},
                        headers=headers,
                    )
                    self.assertEqual(revoked.status_code, 200)
                    rejected = client.get(
                        "/api/browser-extension/ping",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    self.assertEqual(rejected.status_code, 401)
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
                    headers={"X-Requested-With": "XMLHttpRequest"},
                )
                self.assertEqual(login.status_code, 200)
                headers = {"X-PicOrg-CSRF": login.json()["csrf_token"]}

                def fake_update_settings(_payload):
                    web_app.common.APP_SECRET = "new-session-secret"
                    return {"version": "test", "processing": {}}

                with patch.object(web_app, "update_settings", side_effect=fake_update_settings):
                    response = client.post(
                        "/api/settings",
                        json={"app": {"app_secret": "new-session-secret"}},
                        headers=headers,
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
