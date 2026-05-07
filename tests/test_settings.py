"""Tests for runtime base directory resolution."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from picorgftp_sql import settings


class SettingsBaseDirTests(unittest.TestCase):
    def test_interactive_first_run_prompts_instead_of_using_default_root(self) -> None:
        settings_path = r"C:\App\local_settings.json"
        fallback_dir = r"C:\App"
        selected_dir = r"D:\PicOrgData"

        with (
            patch.object(settings, "HEADLESS_ENV", False),
            patch.object(settings, "_load_saved_base_dir_override", return_value=""),
            patch.object(
                settings,
                "_prompt_for_base_dir",
                return_value=(selected_dir, None),
            ) as prompt,
            patch.object(settings, "_ensure_directory_access") as ensure_access,
        ):
            resolved, warning = settings._ensure_base_dir_override(
                settings_path,
                dict(settings.BASE_DIR_SETTINGS_TEMPLATE),
                fallback_dir,
            )

        self.assertEqual(resolved, selected_dir)
        self.assertIsNone(warning)
        prompt.assert_called_once()
        self.assertEqual(prompt.call_args.args[2], fallback_dir)
        ensure_access.assert_not_called()

    def test_interactive_uses_saved_override_without_prompting(self) -> None:
        settings_path = r"C:\App\local_settings.json"
        selected_dir = r"D:\PicOrgData"

        with (
            patch.object(settings, "HEADLESS_ENV", False),
            patch.object(
                settings, "_load_saved_base_dir_override", return_value=selected_dir
            ),
            patch.object(
                settings, "_ensure_directory_access", return_value=(True, None)
            ),
            patch.object(settings, "_prompt_for_base_dir") as prompt,
        ):
            resolved, warning = settings._ensure_base_dir_override(
                settings_path,
                dict(settings.BASE_DIR_SETTINGS_TEMPLATE),
                r"C:\App",
            )

        self.assertEqual(resolved, selected_dir)
        self.assertIsNone(warning)
        prompt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
