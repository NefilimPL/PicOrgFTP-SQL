"""Tests for local web user account helpers."""

from __future__ import annotations

from pathlib import Path
import shutil
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


if __name__ == "__main__":
    unittest.main()
