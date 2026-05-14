"""Tests for local web user account helpers."""

from __future__ import annotations

import os
import json
from pathlib import Path
import shutil
import time
import unittest
from unittest.mock import patch

from picorgftp_sql import web_data


def _workspace_temp(name: str) -> Path:
    root = Path(__file__).resolve().parents[1] / "tmp_test" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    return root


class WebDataUserTests(unittest.TestCase):
    def test_default_admin_can_authenticate(self) -> None:
        temp_dir = _workspace_temp("web_data_users_default")
        try:
            with patch.object(web_data.settings, "AC", str(temp_dir)):
                user = web_data.authenticate_user("admin", "admin")
        finally:
            shutil.rmtree(temp_dir)

        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "admin")

    def test_update_user_blocks_disabling_current_account(self) -> None:
        temp_dir = _workspace_temp("web_data_users_update")
        try:
            with patch.object(web_data.settings, "AC", str(temp_dir)):
                web_data.add_user("operator", "secret", "user")
                with self.assertRaises(ValueError):
                    web_data.update_user("operator", enabled=False, current_username="operator")

                users = web_data.update_user("operator", enabled=False, current_username="admin")
        finally:
            shutil.rmtree(temp_dir)

        operator = next(user for user in users if user["username"] == "operator")
        self.assertFalse(operator["enabled"])

    def test_add_list_value_rejects_case_insensitive_duplicate(self) -> None:
        with (
            patch.object(web_data, "prepare_excel_lists", return_value={"NAZWY": ["Żyrandol"]}),
            patch.object(web_data, "add_to_list") as add_to_list,
        ):
            with self.assertRaises(ValueError):
                web_data.add_list_value("names", "zyrandol")

        add_to_list.assert_not_called()

    def test_remove_list_value_blocks_values_used_by_entries(self) -> None:
        used_by = [{"product_id": "PRD-1", "ean": "5901234567890", "label": "MAGGIORE"}]
        with (
            patch.object(web_data, "find_list_value_usage", return_value=used_by),
            patch.object(web_data, "remove_from_list") as remove_from_list,
        ):
            with self.assertRaises(web_data.ListValueInUseError) as caught:
                web_data.remove_list_value("names", "MAGGIORE")

        self.assertEqual(caught.exception.used_by, used_by)
        remove_from_list.assert_not_called()

    def test_ftp_cache_dir_can_be_scoped_per_user_session(self) -> None:
        temp_dir = _workspace_temp("web_data_ftp_cache_scope")
        try:
            with patch.object(web_data.settings, "AC", str(temp_dir)):
                scoped = Path(web_data._ftp_cache_dir("5901234567890", cache_scope="admin-session"))
                unscoped = Path(web_data._ftp_cache_dir("5901234567890"))
        finally:
            shutil.rmtree(temp_dir)

        self.assertEqual(scoped, temp_dir / "web_ftp_cache" / "admin-session" / "5901234567890")
        self.assertEqual(unscoped, temp_dir / "web_ftp_cache" / "5901234567890")

    def test_cleanup_web_ftp_cache_removes_only_stale_files(self) -> None:
        temp_dir = _workspace_temp("web_data_ftp_cache_cleanup")
        try:
            cache_dir = temp_dir / "web_ftp_cache" / "admin-session" / "5901234567890"
            cache_dir.mkdir(parents=True)
            old_file = cache_dir / "old.jpg"
            new_file = cache_dir / "new.jpg"
            old_file.write_bytes(b"old")
            new_file.write_bytes(b"new")
            old_time = time.time() - 3 * 24 * 60 * 60
            os.utime(old_file, (old_time, old_time))

            with patch.object(web_data.settings, "AC", str(temp_dir)):
                result = web_data.cleanup_web_ftp_cache(
                    max_age_seconds=24 * 60 * 60,
                    min_interval_seconds=1,
                    force=True,
                )

            self.assertEqual(result["deleted_files"], 1)
            self.assertFalse(old_file.exists())
            self.assertTrue(new_file.exists())
        finally:
            shutil.rmtree(temp_dir)

    def test_save_web_entry_preserves_ean_for_existing_product_id_when_missing(self) -> None:
        with (
            patch.object(
                web_data,
                "find_entry_by_identity",
                return_value={"product_id": "PRD-1", "ean": "5901234567890"},
            ),
            patch.object(
                web_data,
                "save_ean_entry",
                return_value={"updated": True, "product_id": "PRD-1", "entry": {}},
            ) as save_ean_entry,
        ):
            result = web_data.save_web_entry(
                {
                    "product_id": "PRD-1",
                    "name": "Maggiore",
                    "type_name": "Komoda",
                    "model": "MA03",
                    "color1": "Bialy",
                }
            )

        self.assertEqual(result["product_id"], "PRD-1")
        args, kwargs = save_ean_entry.call_args
        self.assertEqual(args[0], "5901234567890")
        self.assertEqual(kwargs["product_id"], "PRD-1")

    def test_find_product_photos_merges_live_files_when_index_is_stale(self) -> None:
        class StaleIndex:
            def has_snapshot(self) -> bool:
                return True

            def get_product_files(self, *_args, **_kwargs):
                return []

        temp_dir = _workspace_temp("web_data_live_photos")
        try:
            product_dir = Path(
                web_data.build_product_directory(
                    str(temp_dir / "processed"),
                    "Maggiore",
                    "komoda",
                    "MA03",
                    ["bialy", "", ""],
                    "",
                )
            )
            product_dir.mkdir(parents=True)
            filename = "5901234567890_03_DETAIL_MAGGIORE_KOMODA_MA03_BIALY_NO-LED.jpg"
            (product_dir / filename).write_bytes(b"fake")
            with (
                patch.object(web_data.settings, "l", str(temp_dir / "processed")),
                patch.object(web_data, "_get_file_index", return_value=StaleIndex()),
            ):
                photos = web_data.find_product_photos(
                    {
                        "ean": "5901234567890",
                        "name": "Maggiore",
                        "type_name": "komoda",
                        "model": "MA03",
                        "color1": "bialy",
                    },
                    include_ftp=False,
                    include_sql=False,
                )
        finally:
            shutil.rmtree(temp_dir)

        self.assertEqual(len(photos), 1)
        self.assertEqual(photos[0]["prefix"], "03")
        self.assertTrue(photos[0]["local"])

    def test_web_base_dir_change_updates_local_settings_and_runtime(self) -> None:
        temp_dir = _workspace_temp("web_data_base_dir_change")
        old_values = {
            name: getattr(web_data.settings, name, None)
            for name in (
                "AC",
                "l",
                "LISTS_WORKBOOK_PATH",
                "AD",
                "AM",
                "BM",
                "AN",
                "BASE_DIR_OVERRIDE",
                "BASE_DIR_OVERRIDE_WARNING",
                "BASE_DIR_SETTINGS_PATH",
                "_RUNTIME_INITIALIZED",
            )
        }
        try:
            settings_path = temp_dir / "settings-root" / "local_settings.json"
            requested = temp_dir / "new-base"
            with patch.object(web_data.settings, "BASE_DIR_SETTINGS_PATH", str(settings_path)):
                changed = web_data._apply_base_dir_from_web(f'"{requested}"')

            self.assertTrue(changed)
            payload = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(Path(payload["base_dir_override"]), requested.resolve())
            self.assertEqual(Path(web_data.settings.AC), requested.resolve())
        finally:
            for name, value in old_values.items():
                setattr(web_data.settings, name, value)
            shutil.rmtree(temp_dir)

    def test_web_base_dir_change_reports_inaccessible_path(self) -> None:
        temp_dir = _workspace_temp("web_data_base_dir_invalid")
        try:
            settings_path = temp_dir / "local_settings.json"
            with (
                patch.object(web_data.settings, "BASE_DIR_SETTINGS_PATH", str(settings_path)),
                patch.object(
                    web_data.settings,
                    "_ensure_directory_access",
                    return_value=(False, PermissionError("denied")),
                ),
            ):
                with self.assertRaises(ValueError) as caught:
                    web_data._apply_base_dir_from_web(str(temp_dir / "denied"))

            self.assertIn("Nie mozna uzyc katalogu bazowego", str(caught.exception))
            self.assertFalse(settings_path.exists())
        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
