"""Unit tests for config normalization helpers."""

from __future__ import annotations

import unittest

from picorgftp_sql.config import _normalize_color_field_labels


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


if __name__ == "__main__":
    unittest.main()
