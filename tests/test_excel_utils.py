"""Tests for Excel list maintenance helpers."""

from __future__ import annotations

from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from openpyxl import Workbook

from picorgftp_sql import excel_utils


def _workspace_temp(name: str) -> Path:
    root = Path(__file__).resolve().parents[1] / "tmp_test" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    return root


def _write_workbook(path: Path) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name in ["NAZWY", "TYPY", "MODELE", "KOLORY", "DODATKI"]:
        workbook.create_sheet(sheet_name)
    entries = workbook.create_sheet("ENTRIES")
    entries.append(excel_utils.ENTRY_HEADERS)
    entries.append(
        [
            "5901234567890",
            "MAGGIORE",
            "KOMODA",
            "MA03",
            "BIALY",
            "DAB",
            "",
            "LED-RGB",
            "PRD-1",
        ]
    )
    workbook.save(path)


class ExcelUtilsTests(unittest.TestCase):
    def test_find_list_value_usage_reads_entries_from_workbook(self) -> None:
        temp_dir = _workspace_temp("excel_usage")
        try:
            workbook_path = temp_dir / "lists.xlsx"
            _write_workbook(workbook_path)

            with patch.object(excel_utils.settings, "LISTS_WORKBOOK_PATH", str(workbook_path)):
                usage = excel_utils.find_list_value_usage("KOLORY", "bialy")

            self.assertEqual(len(usage), 1)
            self.assertEqual(usage[0]["product_id"], "PRD-1")
            self.assertEqual(usage[0]["fields"], "KOLOR1")
            self.assertIn("MAGGIORE", usage[0]["label"])
        finally:
            shutil.rmtree(temp_dir)

    def test_find_list_value_usage_normalizes_extra_underscores(self) -> None:
        temp_dir = _workspace_temp("excel_usage_extra")
        try:
            workbook_path = temp_dir / "lists.xlsx"
            _write_workbook(workbook_path)

            with patch.object(excel_utils.settings, "LISTS_WORKBOOK_PATH", str(workbook_path)):
                usage = excel_utils.find_list_value_usage("DODATKI", "led_rgb")

            self.assertEqual(len(usage), 1)
            self.assertEqual(usage[0]["fields"], "DODATKI")
        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
