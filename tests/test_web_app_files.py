"""Tests for web API file token and local deletion helpers."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
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


if __name__ == "__main__":
    unittest.main()
