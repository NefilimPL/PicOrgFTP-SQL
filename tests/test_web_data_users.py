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

    def test_invalidate_ftp_preview_cache_removes_changed_slot_file(self) -> None:
        temp_dir = _workspace_temp("web_data_ftp_cache_invalidate")
        try:
            with patch.object(web_data.settings, "AC", str(temp_dir)):
                cache_dir = Path(web_data._ftp_cache_dir("5901234567890", cache_scope="admin-session"))
                cache_dir.mkdir(parents=True)
                cached = cache_dir / web_data._ftp_cache_filename("5901234567890_03.jpg")
                cached.write_bytes(b"old")

                result = web_data.invalidate_ftp_preview_cache(
                    "5901234567890",
                    {"5901234567890_03.jpg"},
                    cache_scope="admin-session",
                )
        finally:
            shutil.rmtree(temp_dir)

        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["errors"], [])
        self.assertFalse(cached.exists())

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

    def test_find_product_photos_reports_sql_presence_without_sql_urls(self) -> None:
        config_payload = {
            web_data.SLOT_DEFS_KEY: [
                {"prefix": "03", "label": "DETAIL_pic"},
                {"prefix": "04", "label": "MAIN_pic"},
            ],
            web_data.SQL_COLUMN_MAP_KEY: {"03": "img_03", "04": "img_04"},
        }
        with (
            patch.object(web_data.config, "CONFIG", config_payload),
            patch.object(web_data, "should_check_presence", return_value=True),
            patch.object(
                web_data,
                "extract_presence_context",
                return_value=("object_query_1", " WHERE EAN = '5901234567890'"),
            ),
            patch.object(
                web_data,
                "query_presence_details",
                return_value=(
                    {"03": True, "04": False},
                    {"03": "https://xml.wipmebgroup.pl/img/5901234567890_03.jpg", "04": ""},
                ),
            ),
        ):
            photos = web_data.find_product_photos(
                {
                    "ean": "5901234567890",
                    "name": "Maggiore",
                    "type_name": "komoda",
                    "model": "MA03",
                    "color1": "bialy",
                },
                include_local=False,
                include_ftp=False,
                include_sql=True,
            )

        self.assertEqual([photo["prefix"] for photo in photos], ["03"])
        self.assertTrue(photos[0]["sql"])
        self.assertTrue(photos[0]["sql_checked"])
        self.assertEqual(
            photos[0]["sql_value"],
            "https://xml.wipmebgroup.pl/img/5901234567890_03.jpg",
        )
        self.assertFalse(photos[0]["is_image"])

    def test_find_product_photos_keeps_local_slot_when_sql_is_empty(self) -> None:
        temp_dir = _workspace_temp("web_data_local_sql_empty")
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
            config_payload = {
                web_data.SLOT_DEFS_KEY: [{"prefix": "03", "label": "DETAIL_pic"}],
                web_data.SQL_COLUMN_MAP_KEY: {"03": "img_03"},
            }
            with (
                patch.object(web_data.settings, "l", str(temp_dir / "processed")),
                patch.object(web_data.config, "CONFIG", config_payload),
                patch.object(web_data, "_get_file_index", return_value=None),
                patch.object(web_data, "should_check_presence", return_value=True),
                patch.object(
                    web_data,
                    "extract_presence_context",
                    return_value=("object_query_1", " WHERE EAN = '5901234567890'"),
                ),
                patch.object(
                    web_data,
                    "query_presence_details",
                    return_value=({"03": False}, {"03": ""}),
                ),
            ):
                photos = web_data.find_product_photos(
                    {
                        "ean": "5901234567890",
                        "name": "Maggiore",
                        "type_name": "komoda",
                        "model": "MA03",
                        "color1": "bialy",
                    },
                    include_local=True,
                    include_ftp=False,
                    include_sql=True,
                )
        finally:
            shutil.rmtree(temp_dir)

        self.assertEqual(len(photos), 1)
        self.assertEqual(photos[0]["prefix"], "03")
        self.assertTrue(photos[0]["local"])
        self.assertFalse(photos[0]["sql"])
        self.assertTrue(photos[0]["sql_checked"])
        self.assertEqual(photos[0]["sql_value"], "")

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

    def test_update_settings_reloads_target_config_after_base_dir_change(self) -> None:
        old_config = {"old_only": True, web_data.LOCAL_FILE_INDEX_KEY: False}
        target_config = {"target_only": True, web_data.LOCAL_FILE_INDEX_KEY: False}
        saved_configs = []

        def reload_target_config(*_args, **_kwargs):
            web_data.config.CONFIG.clear()
            web_data.config.CONFIG.update(target_config)
            return web_data.config.CONFIG

        def capture_save_config(config_payload, *_args, **_kwargs):
            saved_configs.append(dict(config_payload))

        with (
            patch.object(web_data.config, "CONFIG", old_config),
            patch.object(web_data, "_apply_base_dir_from_web", return_value=True),
            patch.object(web_data.config, "initialize_config", side_effect=reload_target_config),
            patch.object(web_data, "save_config", side_effect=capture_save_config),
            patch.object(web_data, "settings_snapshot", return_value={}),
        ):
            web_data.update_settings(
                {"app": {"base_dir": "C:\\PicOrgFTP-SQL", web_data.LOCAL_FILE_INDEX_KEY: True}}
            )

        self.assertEqual(len(saved_configs), 1)
        saved_config = saved_configs[0]
        self.assertNotIn("old_only", saved_config)
        self.assertTrue(saved_config["target_only"])
        self.assertTrue(saved_config[web_data.LOCAL_FILE_INDEX_KEY])

    def test_update_settings_preserves_unsubmitted_encrypted_secrets(self) -> None:
        preserve = web_data._preserve_unsubmitted_config_secrets(
            {
                "ftp": {"host": "ftp.example.com", "user": "", "password": ""},
                "database": {
                    "mssql": {"server": "sql", "user": "", "password": ""},
                    "mysql": {"server": "mysql", "user": "new-user", "password": ""},
                },
            }
        )

        self.assertEqual(preserve[web_data.H], {web_data.N, web_data.M})
        self.assertEqual(preserve[web_data.P], {web_data.N, web_data.M})
        self.assertEqual(preserve[web_data.K], {web_data.M})

    def test_settings_secret_values_returns_current_decrypted_config(self) -> None:
        config_payload = {
            web_data.H: {web_data.N: "ftp-user", web_data.M: "ftp-pass"},
            web_data.P: {web_data.N: "mssql-user", web_data.M: "mssql-pass"},
            web_data.K: {web_data.N: "mysql-user", web_data.M: "mysql-pass"},
        }
        with (
            patch.object(web_data.config, "CONFIG", config_payload),
            patch.object(web_data.common, "APP_SECRET", "secret-from-local-settings"),
        ):
            payload = web_data.settings_secret_values()

        self.assertEqual(payload["app_secret"], "secret-from-local-settings")
        self.assertEqual(payload["ftp"]["user"], "ftp-user")
        self.assertEqual(payload["ftp"]["password"], "ftp-pass")
        self.assertEqual(payload["database"]["mssql"]["password"], "mssql-pass")
        self.assertEqual(payload["database"]["mysql"]["user"], "mysql-user")


if __name__ == "__main__":
    unittest.main()
