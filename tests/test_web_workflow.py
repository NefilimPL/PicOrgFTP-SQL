"""Tests for the LAN web upload workflow."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from picorgftp_sql.web_workflow import (
    Image,
    WebProductForm,
    WebUploadedSlot,
    WebProcessingOptions,
    _slot_category,
    processing_options_from_config,
    process_web_uploads,
    slot_definitions_from_config,
    normalized_product_payload,
    validate_product_form,
)
from picorgftp_sql.workflow_utils import build_product_directory, build_slot_filename


class WebWorkflowTests(unittest.TestCase):
    def _make_image(self, path: Path) -> None:
        if Image is None:
            self.skipTest("Pillow is not available")
        Image.new("RGB", (16, 16), "white").save(path)

    def test_process_web_uploads_saves_file_with_desktop_style_name(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            source.write_bytes(b"%PDF-1.4\n")
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
                        original_filename="front.pdf",
                    )
                ],
            )

            self.assertEqual(result.ean, "5901234567890")
            self.assertEqual(len(result.saved_files), 1)
            saved = result.saved_files[0]
            self.assertEqual(
                saved.filename,
                "5901234567890_03_DETAIL_MAGGIORE_KOMODA_MA03_BIALY_DAB ARTISAN_LED-RGB.pdf",
            )
            self.assertTrue(Path(saved.path).is_file())
            self.assertTrue(str(saved.path).startswith(str(output_root)))

    def test_process_web_uploads_rejects_non_image_non_pdf(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            source = Path(temp_dir) / "source.txt"
            source.write_text("not an image", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Dozwolone sa pliki graficzne oraz PDF"):
                process_web_uploads(
                    base_output_dir=str(Path(temp_dir) / "processed"),
                    form=WebProductForm(
                        name="Maggiore",
                        type_name="komoda",
                        model="MA03",
                        color1="bialy",
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

    def test_process_web_uploads_normalizes_common_jpeg_extension_typo(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            source_jpg = Path(temp_dir) / "source.jpg"
            source = Path(temp_dir) / "source.peg"
            self._make_image(source_jpg)
            source_jpg.rename(source)

            result = process_web_uploads(
                base_output_dir=str(Path(temp_dir) / "processed"),
                form=WebProductForm(
                    name="Maggiore",
                    type_name="komoda",
                    model="MA03",
                    color1="bialy",
                    ean="5901234567890",
                ),
                uploaded_slots=[
                    WebUploadedSlot(
                        prefix="03",
                        label="DETAIL_pic",
                        source_path=str(source),
                        original_filename="front.peg",
                    )
                ],
                options=WebProcessingOptions(resize_enabled=False),
            )

            self.assertTrue(result.saved_files[0].filename.endswith(".jpg"))

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

    def test_process_web_uploads_allows_empty_change_when_requested(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            result = process_web_uploads(
                base_output_dir=str(Path(temp_dir) / "processed"),
                form=WebProductForm(
                    name="Maggiore",
                    type_name="komoda",
                    model="MA03",
                    color1="bialy",
                    ean="5901234567890",
                ),
                uploaded_slots=[],
                allow_empty=True,
            )

            self.assertEqual(result.ean, "5901234567890")
            self.assertEqual(result.saved_files, [])
            self.assertTrue(Path(result.output_dir).is_dir())

    def test_process_web_uploads_allows_existing_file_at_target_path(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            output_root = Path(temp_dir) / "processed"
            form = WebProductForm(
                name="Maggiore",
                type_name="komoda",
                model="MA03",
                color1="bialy",
                extra="NO-LED",
                ean="5901234567890",
            )
            payload = normalized_product_payload(form)
            output_dir = build_product_directory(
                str(output_root),
                payload["name"],
                payload["type_name"],
                payload["model"],
                payload["colors"],
                payload["extra"],
            )
            filename = build_slot_filename(
                payload["ean"],
                "03",
                _slot_category("DETAIL_pic"),
                payload["name"],
                payload["type_name"],
                payload["model"],
                payload["colors"],
                payload["extra"],
                ".pdf",
            )
            source = Path(output_dir) / filename
            source.parent.mkdir(parents=True)
            source.write_bytes(b"%PDF-1.4\n")

            result = process_web_uploads(
                base_output_dir=str(output_root),
                form=form,
                uploaded_slots=[
                    WebUploadedSlot(
                        prefix="03",
                        label="DETAIL_pic",
                        source_path=str(source),
                        original_filename=filename,
                    )
                ],
            )

            self.assertEqual(result.saved_files[0].path, str(source))
            self.assertEqual(source.read_bytes(), b"%PDF-1.4\n")

    def test_process_web_uploads_rejects_empty_change_by_default(self) -> None:
        with self.assertRaises(ValueError):
            process_web_uploads(
                base_output_dir="processed",
                form=WebProductForm(
                    name="Maggiore",
                    type_name="komoda",
                    model="MA03",
                    color1="bialy",
                    ean="5901234567890",
                ),
                uploaded_slots=[],
            )

    def test_process_web_uploads_uses_global_fit_as_default(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            source = Path(temp_dir) / "source.png"
            self._make_image(source)

            with patch(
                "picorgftp_sql.web_workflow.fit_image_to_content",
                side_effect=lambda image: image,
            ) as fit:
                process_web_uploads(
                    base_output_dir=str(Path(temp_dir) / "processed"),
                    form=WebProductForm(
                        name="Maggiore",
                        type_name="komoda",
                        model="MA03",
                        color1="bialy",
                        ean="5901234567890",
                    ),
                    uploaded_slots=[
                        WebUploadedSlot(
                            prefix="03",
                            label="DETAIL_pic",
                            source_path=str(source),
                            original_filename="front.png",
                        )
                    ],
                    options=WebProcessingOptions(
                        resize_enabled=False,
                        auto_content_fit=True,
                    ),
                )

            fit.assert_called_once()

    def test_process_web_uploads_allows_fit_override_false(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            source = Path(temp_dir) / "source.png"
            self._make_image(source)

            with patch(
                "picorgftp_sql.web_workflow.fit_image_to_content",
                side_effect=lambda image: image,
            ) as fit:
                process_web_uploads(
                    base_output_dir=str(Path(temp_dir) / "processed"),
                    form=WebProductForm(
                        name="Maggiore",
                        type_name="komoda",
                        model="MA03",
                        color1="bialy",
                        ean="5901234567890",
                    ),
                    uploaded_slots=[
                        WebUploadedSlot(
                            prefix="03",
                            label="DETAIL_pic",
                            source_path=str(source),
                            original_filename="front.png",
                            content_fit=False,
                        )
                    ],
                    options=WebProcessingOptions(
                        resize_enabled=False,
                        auto_content_fit=True,
                    ),
                )

            fit.assert_not_called()

    def test_processing_options_from_config_uses_web_processing_settings(self) -> None:
        options = processing_options_from_config(
            {
                "processing": {
                    "resize_enabled": False,
                    "max_dim": 1200,
                    "compress_enabled": True,
                    "compress_quality": 72,
                    "max_size_enabled": True,
                    "max_file_kb": 250,
                    "convert_enabled": True,
                    "target_format": "WEBP",
                },
                "auto_content_fit": True,
            }
        )

        self.assertFalse(options.resize_enabled)
        self.assertEqual(options.max_dim, 1200)
        self.assertTrue(options.compress_enabled)
        self.assertEqual(options.compress_quality, 72)
        self.assertTrue(options.max_size_enabled)
        self.assertEqual(options.max_file_kb, 250)
        self.assertTrue(options.convert_enabled)
        self.assertEqual(options.target_format, "WEBP")
        self.assertTrue(options.auto_content_fit)

    def test_slot_definitions_from_config_uses_defaults_when_missing(self) -> None:
        slots = slot_definitions_from_config({})

        self.assertGreaterEqual(len(slots), 1)
        self.assertEqual(slots[0]["prefix"], "01")


if __name__ == "__main__":
    unittest.main()
