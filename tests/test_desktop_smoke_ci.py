"""CI smoke tests for desktop launchers and packaged assets."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import py_compile
import unittest


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PICORGFTP_SQL_HEADLESS", "1")
os.environ.setdefault("CI", "1")


class DesktopSmokeCiTests(unittest.TestCase):
    def test_desktop_entrypoints_compile(self) -> None:
        entrypoints = [
            ROOT / "PicOrgFTP-SQL.pyw",
            ROOT / "PicOrgFTP-SQL-WEB.pyw",
            ROOT / "PicOrgFTP-SQL-QtSlots.pyw",
        ]

        for entrypoint in entrypoints:
            with self.subTest(entrypoint=entrypoint.name):
                py_compile.compile(str(entrypoint), doraise=True)

    def test_critical_modules_import_in_headless_mode(self) -> None:
        modules = [
            "picorgftp_sql.bootstrap",
            "picorgftp_sql.config",
            "picorgftp_sql.settings",
            "picorgftp_sql.workflow_utils",
            "picorgftp_sql.web_workflow",
            "picorgftp_sql.web_data",
            "picorgftp_sql.web.app",
            "picorgftp_sql.app",
        ]

        errors: dict[str, str] = {}
        for module_name in modules:
            try:
                importlib.import_module(module_name)
            except Exception as exc:  # pragma: no cover - failure is reported below
                errors[module_name] = f"{type(exc).__name__}: {exc}"

        self.assertEqual(errors, {})

    def test_localization_files_are_valid_json(self) -> None:
        localization_dir = ROOT / "picorgftp_sql" / "Localization"
        expected_files = {"pl.json", "eng.json", "ua.json"}
        found_files = {path.name for path in localization_dir.glob("*.json")}

        self.assertEqual(expected_files - found_files, set())
        for path in sorted(localization_dir.glob("*.json")):
            with self.subTest(path=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)
                self.assertGreater(len(payload), 10)

    def test_required_image_assets_exist_for_desktop_and_web(self) -> None:
        required_assets = [
            ROOT / "pic" / "PIC_LOCAL.png",
            ROOT / "pic" / "PIC_WEB.png",
            ROOT / "picorgftp_sql" / "VERSION",
            ROOT / "picorgftp_sql" / "web" / "static" / "index.html",
            ROOT / "picorgftp_sql" / "web" / "static" / "login.html",
            ROOT / "picorgftp_sql" / "web" / "static" / "app.css",
            ROOT / "picorgftp_sql" / "web" / "static" / "app.js",
        ]

        missing_or_empty = [
            str(path.relative_to(ROOT))
            for path in required_assets
            if not path.is_file() or path.stat().st_size <= 0
        ]

        self.assertEqual(missing_or_empty, [])


if __name__ == "__main__":
    unittest.main()
