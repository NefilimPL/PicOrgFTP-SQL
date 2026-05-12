"""Tests for web API file token and local deletion helpers."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from picorgftp_sql.web import app as web_app


def _workspace_temp(name: str) -> Path:
    root = Path(__file__).resolve().parents[1] / "tmp_test" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    return root


class WebAppFileTests(unittest.TestCase):
    def test_delete_token_can_be_resolved_after_file_disappears(self) -> None:
        temp_dir = _workspace_temp("web_app_delete_token")
        try:
            processed = temp_dir / "processed"
            processed.mkdir()
            target = processed / "old.jpg"
            target.write_bytes(b"old")
            token = web_app._file_token(str(target))
            target.unlink()

            with (
                patch.object(web_app.settings, "l", str(processed)),
                patch.object(web_app.settings, "AC", str(temp_dir)),
            ):
                self.assertEqual(
                    Path(web_app._path_from_file_token(token, require_exists=False)),
                    target,
                )
                with self.assertRaises(HTTPException):
                    web_app._path_from_file_token(token)
        finally:
            shutil.rmtree(temp_dir)

    def test_delete_local_files_is_idempotent_and_preserves_saved_paths(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            root = Path(temp_dir)
            delete_file = root / "delete.jpg"
            saved_file = root / "saved.jpg"
            missing_file = root / "missing.jpg"
            delete_file.write_bytes(b"delete")
            saved_file.write_bytes(b"saved")

            result = web_app._delete_local_files(
                [
                    {"local_path": str(delete_file)},
                    {"local_path": str(saved_file)},
                    {"local_path": str(missing_file)},
                ],
                {str(saved_file)},
            )

            self.assertEqual(result["deleted"], 1)
            self.assertEqual(result["skipped"], 2)
            self.assertEqual(result["errors"], [])
            self.assertFalse(delete_file.exists())
            self.assertTrue(saved_file.exists())

    def test_ftp_sync_skips_upload_for_backfilled_prefixes(self) -> None:
        result = SimpleNamespace(
            output_dir="processed",
            saved_files=[
                SimpleNamespace(
                    prefix="03",
                    filename="5901234567890_03_DETAIL_MAGGIORE.jpg",
                )
            ],
        )

        with (
            patch.dict(web_app.config.CONFIG, {web_app.ft: True, web_app.H: {}}, clear=False),
            patch.object(
                web_app,
                "sync_remote_files",
                return_value={"uploaded": 0, "deleted": 0, "elapsed_ms": 1, "error": ""},
            ) as sync_remote,
        ):
            payload = web_app._sync_result_to_ftp(
                result,
                [],
                skip_upload_prefixes={"03"},
            )

        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["uploaded"], 0)
        sync_remote.assert_not_called()

    def test_existing_local_photos_are_migrated_when_product_path_changes(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            root = Path(temp_dir)
            processed = root / "processed"
            old_file = processed / "MAGGIORE" / "KOMODA" / "MA03" / "BIALY" / "NO-LED"
            old_file.mkdir(parents=True)
            photo_path = old_file / "5901234567890_03_DETAIL_MAGGIORE_KOMODA_MA03_BIALY_NO-LED.jpg"
            photo_path.write_bytes(b"old")
            uploaded_slots = []
            delete_requests = []
            existing_entry = {
                "product_id": "PRD-1",
                "ean": "5901234567890",
                "name": "MAGGIORE",
                "type_name": "KOMODA",
                "model": "MA03",
                "color1": "BIALY",
                "color2": "",
                "color3": "",
                "extra": "NO-LED",
            }
            product = web_app.WebProductForm(
                product_id="PRD-1",
                ean="5901234567890",
                name="MAGGIORE",
                type_name="KOMODA",
                model="MA03",
                color1="BIALY",
                color2="DAB",
                extra="NO-LED",
            )

            with (
                patch.object(web_app.settings, "l", str(processed)),
                patch.object(
                    web_app,
                    "find_product_photos",
                    return_value=[
                        {
                            "prefix": "03",
                            "path": str(photo_path),
                            "filename": photo_path.name,
                        }
                    ],
                ),
            ):
                migrated = web_app._append_existing_photo_migrations(
                    existing_entry=existing_entry,
                    product=product,
                    uploaded_slots=uploaded_slots,
                    delete_requests=delete_requests,
                    slot_by_prefix={"03": {"prefix": "03", "label": "DETAIL_pic"}},
                )

            self.assertEqual(migrated, ["03"])
            self.assertEqual(uploaded_slots[0].prefix, "03")
            self.assertEqual(uploaded_slots[0].source_path, str(photo_path))
            self.assertEqual(delete_requests[0]["local_path"], str(photo_path))

    def test_ftp_only_photos_are_downloaded_when_local_file_is_missing(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            root = Path(temp_dir)
            processed = root / "processed"
            cache_file = root / "cache" / "5901234567890_03.jpg"
            cache_file.parent.mkdir(parents=True)
            cache_file.write_bytes(b"ftp")
            uploaded_slots = []
            delete_requests = []
            existing_entry = {
                "product_id": "PRD-1",
                "ean": "5901234567890",
                "name": "MAGGIORE",
                "type_name": "KOMODA",
                "model": "MA03",
                "color1": "BIALY",
                "extra": "NO-LED",
            }
            product = web_app.WebProductForm(
                product_id="PRD-1",
                ean="5901234567890",
                name="MAGGIORE",
                type_name="KOMODA",
                model="MA03",
                color1="BIALY",
                extra="NO-LED",
            )

            with (
                patch.object(web_app.settings, "l", str(processed)),
                patch.object(
                    web_app,
                    "find_product_photos",
                    return_value=[
                        {
                            "ean": "5901234567890",
                            "prefix": "03",
                            "path": "",
                            "ftp_filename": "5901234567890_03.jpg",
                        }
                    ],
                ),
                patch.object(web_app, "cache_ftp_preview", return_value=str(cache_file)) as cache_ftp,
            ):
                appended = web_app._append_existing_photo_migrations(
                    existing_entry=existing_entry,
                    product=product,
                    uploaded_slots=uploaded_slots,
                    delete_requests=delete_requests,
                    slot_by_prefix={"03": {"prefix": "03", "label": "DETAIL_pic"}},
                )

            self.assertEqual(appended, ["03"])
            cache_ftp.assert_called_once_with("5901234567890", "5901234567890_03.jpg")
            self.assertEqual(uploaded_slots[0].source_path, str(cache_file))
            self.assertEqual(delete_requests[0]["local_path"], "")
            self.assertEqual(delete_requests[0]["ftp_filename"], "5901234567890_03.jpg")
            self.assertTrue(delete_requests[0]["ftp_backfill"])

    def test_deleted_ftp_only_slot_is_not_downloaded_again(self) -> None:
        product = web_app.WebProductForm(
            product_id="PRD-1",
            ean="5901234567890",
            name="MAGGIORE",
            type_name="KOMODA",
            model="MA03",
            color1="BIALY",
        )
        delete_requests = [{"prefix": "03", "ftp_filename": "5901234567890_03.jpg"}]

        with (
            patch.object(
                web_app,
                "find_product_photos",
                return_value=[
                    {
                        "ean": "5901234567890",
                        "prefix": "03",
                        "path": "",
                        "ftp_filename": "5901234567890_03.jpg",
                    }
                ],
            ),
            patch.object(web_app, "cache_ftp_preview") as cache_ftp,
        ):
            appended = web_app._append_existing_photo_migrations(
                existing_entry={"ean": "5901234567890"},
                product=product,
                uploaded_slots=[],
                delete_requests=delete_requests,
                slot_by_prefix={"03": {"prefix": "03", "label": "DETAIL_pic"}},
            )

        self.assertEqual(appended, [])
        cache_ftp.assert_not_called()

    def test_log_parser_groups_traceback_into_one_critical_event(self) -> None:
        events = web_app._parse_log_events(
            {
                "key": "errors",
                "label": "Bledy",
                "path": "errors.log",
                "lines": [
                    "[2026-05-11 14:14:11] [USER: user] [PC: pc] ERROR: WEB POST /api/ftp-preview: boom",
                    "Traceback (most recent call last):",
                    "  File \"app.py\", line 1, in handler",
                    "RuntimeError: boom",
                    "[2026-05-11 14:15:00] [USER: user] [PC: pc] ERROR: Brak dostepu",
                ],
            }
        )

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["severity"], "critical")
        self.assertEqual(len(events[0]["lines"]), 4)
        self.assertEqual(events[1]["severity"], "warning")

    def test_log_parser_splits_plain_lines_and_strips_control_sequences(self) -> None:
        events = web_app._parse_log_events(
            {
                "key": "web_out",
                "label": "Web stdout",
                "path": "out.log",
                "lines": [
                    '\x1b[32mINFO\x1b[0m:     127.0.0.1:1 - "GET /ok HTTP/1.1" 200 OK',
                    'INFO:     127.0.0.1:2 - "GET /missing HTTP/1.1" 404 Not Found',
                ],
            }
        )

        self.assertEqual(len(events), 2)
        self.assertNotIn("\x1b", events[0]["summary"])
        self.assertEqual(events[0]["severity"], "info")
        self.assertEqual(events[1]["severity"], "warning")

    def test_log_payloads_are_newest_first_and_hide_successful_access_logs(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            log_path = Path(temp_dir) / "picorg_web_out.log"
            log_path.write_text(
                "\n".join(
                    [
                        "INFO:     Custom maintenance event.",
                        'INFO:     127.0.0.1:1 - "GET /api/logs?limit=120 HTTP/1.1" 200 OK',
                        'INFO:     127.0.0.1:2 - "GET /crash HTTP/1.1" 500 Internal Server Error',
                    ]
                ),
                encoding="utf-8",
            )
            targets = [{"key": "web_out", "label": "Web stdout", "path": log_path}]

            with patch.object(web_app, "_log_targets", return_value=targets):
                payload = web_app._log_payloads(20)[0]

            summaries = [event["summary"] for event in payload["events"]]
            self.assertEqual(len(summaries), 2)
            self.assertIn("/crash", summaries[0])
            self.assertEqual(summaries[1], "Custom maintenance event.")

    def test_runtime_logs_hide_uvicorn_startup_and_400_access_noise(self) -> None:
        startup_event = {
            "source": "web_err",
            "lines": ["INFO:     Uvicorn running on http://0.0.0.0:8010 (Press CTRL+C to quit)"],
        }
        bad_request_event = {
            "source": "web_out",
            "lines": ['INFO:     127.0.0.1:1 - "POST /api/process HTTP/1.1" 400 Bad Request'],
        }
        server_error_event = {
            "source": "web_out",
            "lines": ['INFO:     127.0.0.1:1 - "POST /api/process HTTP/1.1" 500 Internal Server Error'],
        }

        self.assertFalse(web_app._is_visible_log_event(startup_event))
        self.assertFalse(web_app._is_visible_log_event(bad_request_event))
        self.assertTrue(web_app._is_visible_log_event(server_error_event))

    def test_existing_photo_conflicts_detect_unloaded_replacement(self) -> None:
        upload = web_app.WebUploadedSlot(
            prefix="03",
            label="DETAIL_pic",
            source_path="new.jpg",
            original_filename="new.jpg",
        )
        conflicts = web_app._existing_photo_conflicts(
            [{"prefix": "03", "local": True, "path": "old.jpg", "filename": "old.jpg"}],
            [upload],
            [],
        )

        self.assertEqual(conflicts[0]["prefix"], "03")
        self.assertEqual(conflicts[0]["sources"], ["LOCAL"])

    def test_existing_photo_conflicts_ignores_explicit_ftp_source(self) -> None:
        upload = web_app.WebUploadedSlot(
            prefix="03",
            label="DETAIL_pic",
            source_path="cache.jpg",
            original_filename="5901234567890_03.jpg",
        )
        conflicts = web_app._existing_photo_conflicts(
            [{"prefix": "03", "ftp": True, "ftp_filename": "5901234567890_03.jpg"}],
            [upload],
            [],
        )

        self.assertEqual(conflicts, [])

    def test_system_change_filter_hides_product_and_photo_entries(self) -> None:
        settings_event = {
            "source": "changes",
            "lines": ["[2026-05-12 10:00:00] [USER: user] Settings saved (images/FTP/SQL)."],
        }
        image_event = {
            "source": "changes",
            "lines": ["[2026-05-12 10:01:00] [USER: user] Added/modified image 123.jpg"],
        }
        entry_event = {
            "source": "changes",
            "lines": ["[2026-05-12 10:02:00] [USER: user] Updated Excel entry for EAN 5901234567890."],
        }

        self.assertTrue(web_app._is_system_change_event(settings_event))
        self.assertFalse(web_app._is_system_change_event(image_event))
        self.assertFalse(web_app._is_system_change_event(entry_event))

    def test_clear_log_files_truncates_configured_targets(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            root = Path(temp_dir)
            error_log = root / "error_log.txt"
            changes_log = root / "changes_log.txt"
            error_log.write_text("error\n", encoding="utf-8")
            changes_log.write_text("change\n", encoding="utf-8")
            targets = [
                {"key": "errors", "label": "Bledy", "path": error_log},
                {"key": "changes", "label": "Zmiany", "path": changes_log},
            ]

            with patch.object(web_app, "_log_targets", return_value=targets):
                result = web_app._clear_log_files()

            self.assertEqual(result["errors"], [])
            self.assertEqual(error_log.read_text(encoding="utf-8"), "")
            self.assertEqual(changes_log.read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
