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


if __name__ == "__main__":
    unittest.main()
