"""Unit tests for config normalization helpers."""

from __future__ import annotations

import unittest

from picorgftp_sql.config import _normalize_color_field_labels, _normalize_processing_settings


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
            }
        )

        self.assertFalse(settings["resize_enabled"])
        self.assertEqual(settings["max_dim"], 20000)
        self.assertEqual(settings["compress_quality"], 1)
        self.assertEqual(settings["max_file_kb"], 1)
        self.assertEqual(settings["target_format"], "JPG")


if __name__ == "__main__":
    unittest.main()
