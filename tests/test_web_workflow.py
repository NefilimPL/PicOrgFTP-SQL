"""Tests for the LAN web upload workflow."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from picorgftp_sql.web_workflow import (
    WebProductForm,
    WebUploadedSlot,
    process_web_uploads,
    slot_definitions_from_config,
    validate_product_form,
)


class WebWorkflowTests(unittest.TestCase):
    def test_process_web_uploads_saves_file_with_desktop_style_name(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            source = Path(temp_dir) / "source.txt"
            source.write_text("not an image", encoding="utf-8")
            output_root = Path(temp_dir) / "processed"

            result = process_web_uploads(
                base_output_dir=str(output_root),
                form=WebProductForm(
                    name="Maggiore",
                    type_name="komoda",
                    model="MA03",
                    color1="bialy",
                    color2="dab artisan",
                    extra="led_rgb",
                    ean="5901234567890",
                ),
                uploaded_slots=[
                    WebUploadedSlot(
                        prefix="03",
                        label="DETAIL_pic",
                        source_path=str(source),
                        original_filename="front.txt",
                    )
                ],
            )

            self.assertEqual(result.ean, "5901234567890")
            self.assertEqual(len(result.saved_files), 1)
            saved = result.saved_files[0]
            self.assertEqual(
                saved.filename,
                "5901234567890_03_DETAIL_MAGGIORE_KOMODA_MA03_BIALY_DAB ARTISAN_LED-RGB.txt",
            )
            self.assertTrue(Path(saved.path).is_file())
            self.assertTrue(str(saved.path).startswith(str(output_root)))

    def test_validate_product_form_rejects_invalid_ean(self) -> None:
        errors = validate_product_form(
            WebProductForm(
                name="Name",
                type_name="Type",
                model="Model",
                color1="Color",
                ean="123",
            )
        )

        self.assertIn("EAN musi miec 13 cyfr albo zostac pusty.", errors)

    def test_slot_definitions_from_config_uses_defaults_when_missing(self) -> None:
        slots = slot_definitions_from_config({})

        self.assertGreaterEqual(len(slots), 1)
        self.assertEqual(slots[0]["prefix"], "01")


if __name__ == "__main__":
    unittest.main()
