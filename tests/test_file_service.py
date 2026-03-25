"""Unit tests for file workflow state helpers."""

from __future__ import annotations

import unittest

from picorgftp_sql.product_state import ProductState, merge_lookup_state


class MergeLookupStateTests(unittest.TestCase):
    def test_merge_lookup_state_keeps_user_addition_and_enables_ftp_toggle(self) -> None:
        current_state = ProductState()
        current_state.pending_additions[0] = "/tmp/new-main.jpg"
        lookup_state = ProductState()
        lookup_state.original_files["01"] = "5901234567890_01_MAIN.jpg"
        lookup_state.ftp_remote_only["01"] = {
            "filename": "5901234567890_01.jpg",
            "temp_path": "/tmp/ftp-main.jpg",
        }
        lookup_state.ftp_remote_only["02"] = {
            "filename": "5901234567890_02.jpg",
            "temp_path": "/tmp/ftp-detail.jpg",
        }
        lookup_state.ftp_presence["01"] = "5901234567890_01.jpg"
        lookup_state.ftp_presence["02"] = "5901234567890_02.jpg"

        merged = merge_lookup_state(current_state, lookup_state, {0: "01", 1: "02"})

        self.assertEqual(merged.pending_additions, {0: "/tmp/new-main.jpg"})
        self.assertNotIn("01", merged.ftp_remote_only)
        self.assertIn("01", merged.ftp_preview_files)
        self.assertEqual(
            merged.ftp_preview_files["01"]["filename"],
            "5901234567890_01.jpg",
        )
        self.assertIn("02", merged.ftp_remote_only)
        self.assertEqual(merged.original_files["01"], "5901234567890_01_MAIN.jpg")

    def test_merge_lookup_state_keeps_existing_preview_when_partial_lookup_clears_ftp(self) -> None:
        current_state = ProductState()
        current_state.pending_additions[0] = "/tmp/new-main.jpg"
        current_state.ftp_preview_files["01"] = {
            "filename": "5901234567890_01.jpg",
            "temp_path": "/tmp/ftp-main.jpg",
        }
        current_state.ftp_presence["01"] = "5901234567890_01.jpg"
        current_state.sql_values["01"] = "https://sql.example/img/5901234567890_01.jpg"
        lookup_state = ProductState()

        merged = merge_lookup_state(current_state, lookup_state, {0: "01"})

        self.assertIn("01", merged.ftp_preview_files)
        self.assertEqual(
            merged.ftp_preview_files["01"]["temp_path"],
            "/tmp/ftp-main.jpg",
        )
        self.assertEqual(merged.ftp_presence["01"], "5901234567890_01.jpg")
        self.assertEqual(
            merged.sql_values["01"],
            "https://sql.example/img/5901234567890_01.jpg",
        )

    def test_merge_lookup_state_respects_pending_remote_deletion(self) -> None:
        current_state = ProductState()
        current_state.pending_ftp_deletions[1] = "5901234567890_02.jpg"
        lookup_state = ProductState()
        lookup_state.ftp_remote_only["02"] = {
            "filename": "5901234567890_02.jpg",
            "temp_path": "/tmp/ftp-detail.jpg",
        }
        lookup_state.ftp_preview_files["02"] = {
            "filename": "5901234567890_02.jpg",
            "temp_path": "/tmp/ftp-detail.jpg",
        }

        merged = merge_lookup_state(current_state, lookup_state, {1: "02"})

        self.assertEqual(
            merged.pending_ftp_deletions,
            {1: "5901234567890_02.jpg"},
        )
        self.assertNotIn("02", merged.ftp_remote_only)
        self.assertNotIn("02", merged.ftp_preview_files)


if __name__ == "__main__":
    unittest.main()
