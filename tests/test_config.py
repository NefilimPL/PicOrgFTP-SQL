"""Unit tests for config normalization helpers."""

from __future__ import annotations

import unittest
from copy import deepcopy
from unittest.mock import patch

from picorgftp_sql import common, config
from picorgftp_sql.config import (
    _normalize_color_field_labels,
    _normalize_processing_settings,
    _normalize_security_settings,
)
from picorgftp_sql.product_fields import PRODUCT_FIELDS_KEY
from picorgftp_sql.sqlite_store import SqliteStore


class DefaultConfigSafetyTests(unittest.TestCase):
    def test_default_sql_query_is_empty_and_contains_no_production_url(self) -> None:
        self.assertEqual(common.DEFAULT_CONFIG["sql_query"], "")
        self.assertEqual(common.SQL_UPDATE_TEMPLATE, "")
        self.assertNotIn("xml.wipmebgroup.pl", repr(common.DEFAULT_CONFIG))
        self.assertNotIn("object_query_1", repr(common.DEFAULT_CONFIG))


class ConfigTests(unittest.TestCase):
    def test_normalize_color_field_labels_strips_suffixes_and_blanks(self) -> None:
        labels = _normalize_color_field_labels(
            {
                "color1": "  Korpus*: ",
                "color2": "Front:",
                "color3": "   ",
                "other": "ignored",
            }
        )

        self.assertEqual(
            labels,
            {
                "color1": "Korpus",
                "color2": "Front",
            },
        )

    def test_normalize_color_field_labels_ignores_invalid_payload(self) -> None:
        self.assertEqual(_normalize_color_field_labels(None), {})

    def test_normalize_processing_settings_bounds_values(self) -> None:
        settings = _normalize_processing_settings(
            {
                "resize_enabled": False,
                "max_dim": "999999",
                "compress_quality": "0",
                "max_file_kb": "-5",
                "target_format": "jpeg",
                "upload_processing_mode": "client",
                "show_timing_details": True,
            }
        )

        self.assertFalse(settings["resize_enabled"])
        self.assertEqual(settings["max_dim"], 20000)
        self.assertEqual(settings["compress_quality"], 1)
        self.assertEqual(settings["max_file_kb"], 1)
        self.assertEqual(settings["target_format"], "JPG")
        self.assertEqual(settings["upload_processing_mode"], "client")
        self.assertTrue(settings["show_timing_details"])

    def test_normalize_security_settings_bounds_and_cleans_extensions(self) -> None:
        settings = _normalize_security_settings(
            {
                "max_upload_mb": "999999",
                "max_upload_pixels": "0",
                "allowed_upload_extensions": "jpg, .PNG, exe, dziwny!",
                "blocked_upload_extensions": ["EXE", ".bat", " "],
                "block_executable_uploads": False,
                "antivirus_scan_uploads": True,
            }
        )

        self.assertEqual(settings["max_upload_mb"], 2048)
        self.assertEqual(settings["max_upload_pixels"], 1)
        self.assertEqual(settings["allowed_upload_extensions"], ["jpg", "png", "exe"])
        self.assertEqual(settings["blocked_upload_extensions"], ["exe", "bat"])
        self.assertFalse(settings["block_executable_uploads"])
        self.assertTrue(settings["antivirus_scan_uploads"])

    def test_merge_raw_config_migrates_color_labels_to_product_fields(self) -> None:
        target = deepcopy(common.DEFAULT_CONFIG)

        merged = config._merge_raw_config(
            {"color_field_labels": {"color1": "Korpus"}},
            target,
        )

        self.assertEqual(merged[PRODUCT_FIELDS_KEY]["color1"]["label"], "Korpus")
        self.assertTrue(merged[PRODUCT_FIELDS_KEY]["name"]["required"])

    def test_save_config_persists_normalized_product_fields_to_sqlite(self) -> None:
        payload = deepcopy(common.DEFAULT_CONFIG)
        payload[PRODUCT_FIELDS_KEY] = {
            "model": {"enabled": False, "required": True}
        }
        store = unittest.mock.Mock(database_path="test.sqlite")

        with patch.object(config, "_active_sqlite_store", return_value=store):
            config.save_config(payload)

        saved = store.save_config.call_args.args[0][PRODUCT_FIELDS_KEY]
        self.assertEqual(
            saved["model"],
            {"label": "", "enabled": False, "required": False},
        )

    def test_save_config_roundtrips_product_fields_through_sqlite(self) -> None:
        from pathlib import Path
        import shutil

        temp_dir = Path(__file__).resolve().parents[1] / "tmp_test" / "config-product-fields"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True)
        try:
            payload = deepcopy(common.DEFAULT_CONFIG)
            payload[PRODUCT_FIELDS_KEY] = {
                "name": {
                    "label": "Kolekcja",
                    "enabled": True,
                    "required": True,
                }
            }
            store = SqliteStore(temp_dir / "product-fields.sqlite")

            with patch.object(config, "_active_sqlite_store", return_value=store):
                config.save_config(payload)

            self.assertEqual(
                store.load_config()[PRODUCT_FIELDS_KEY]["name"]["label"],
                "Kolekcja",
            )
        finally:
            shutil.rmtree(temp_dir)

    def test_save_config_encrypts_pimcore_api_key(self) -> None:
        payload = deepcopy(common.DEFAULT_CONFIG)
        payload["pimcore"] = {
            **payload["pimcore"],
            "enabled": True,
            "api_key": "pimcore-secret",
            "setup_complete": True,
            "class_id": "7",
            "parent_path": "/Produkty",
        }

        with (
            patch.object(config, "_active_sqlite_store", return_value=None),
            patch.object(config, "_write_json_atomic") as write_atomic,
        ):
            config.save_config(payload)

        raw = write_atomic.call_args.args[1]
        self.assertNotEqual(raw["pimcore"]["api_key"], "pimcore-secret")
        self.assertEqual(config.decrypt(raw["pimcore"]["api_key"]), "pimcore-secret")
        self.assertIs(raw["pimcore"]["setup_complete"], True)
        self.assertEqual(raw["pimcore"]["class_id"], "7")
        self.assertEqual(raw["pimcore"]["parent_path"], "/Produkty")


if __name__ == "__main__":
    unittest.main()
