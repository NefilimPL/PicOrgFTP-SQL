"""Static source checks that do not require GUI/runtime dependencies."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


class SourceIntegrityTests(unittest.TestCase):
    def test_app_imports_all_used_excel_header_constants(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "picorgftp_sql" / "app.py"
        source = app_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(app_path))

        defined: set[str] = set(dir(__builtins__))
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    defined.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    defined.add(alias.asname or alias.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for name in ast.walk(target):
                        if isinstance(name, ast.Name):
                            defined.add(name.id)

        missing = sorted(
            {
                node.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Load)
                and node.id.endswith("_HEADER")
                and node.id not in defined
            }
        )
        self.assertEqual(missing, [])

    def test_web_submit_only_marks_explicit_slot_changes_as_pending(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")

        self.assertIn("if (!state.files.has(prefix) && photo.dirty)", source)
        self.assertNotIn("shouldRepair = photoNeedsRepair", source)
        self.assertNotIn("shouldSyncLocal = !updateMode", source)

    def test_web_app_does_not_use_sha1_hashes(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "picorgftp_sql" / "web" / "app.py"
        source = app_path.read_text(encoding="utf-8")

        self.assertNotIn("hashlib.sha1", source)


if __name__ == "__main__":
    unittest.main()
