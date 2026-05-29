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

    def test_web_submit_removes_cached_slot_file_inputs(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")

        delete_index = source.index("data.delete(`slot_${slot.prefix}`);")
        cache_index = source.index("data.set(`existing_slot_${prefix}`, token);")
        self.assertLess(delete_index, cache_index)

    def test_web_has_background_ftp_lookup_without_forcing_slot_edits(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")

        self.assertIn('requestEntryPhotos(entry, "ftp", null, { timeoutMs: 15000 })', source)
        self.assertIn("background_ftp_key", source)
        self.assertIn("applyPhotoPayload(photos, { force: false })", source)
        self.assertIn("scheduleBackgroundFtpLookup", source)

    def test_web_photo_loading_renders_only_changed_slots(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")
        apply_start = source.index("function applyPhotoPayload")
        apply_end = source.index("async function requestEntryPhotos", apply_start)
        body = source[apply_start:apply_end]

        self.assertIn("state.files.has(photo.prefix)", body)
        self.assertIn("renderChangedSlots(changedPrefixes);", body)
        self.assertNotIn("renderSlots();", body)
        self.assertIn("timeoutMs: Number(options.timeoutMs || photoRequestTimeoutMs(source))", source)

    def test_web_submit_uses_background_process_queue(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")

        self.assertIn('requestJson("/api/process/background"', source)
        self.assertIn("trackProcessJob(job);", source)
        self.assertIn("resetCurrentDraft({", source)
        self.assertIn("processAlertLoadButton", source)

    def test_web_has_global_process_queue_panel(self) -> None:
        root = Path(__file__).resolve().parents[1]
        js_source = (root / "picorgftp_sql" / "web" / "static" / "app.js").read_text(encoding="utf-8")
        html_source = (root / "picorgftp_sql" / "web" / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="processQueuePanel"', html_source)
        self.assertIn('class="process-queue-section"', html_source)
        self.assertNotIn('class="slots-layout"', html_source)
        self.assertIn('requestJson("/api/process-jobs/active")', js_source)
        self.assertIn("renderProcessQueue(payload)", js_source)
        self.assertIn("setInterval(() => {\n  refreshProcessQueue()", js_source)
        self.assertIn("renderProcessMeasurements(payload)", js_source)

    def test_web_history_has_search_pagination_and_timing_modal(self) -> None:
        root = Path(__file__).resolve().parents[1]
        js_source = (root / "picorgftp_sql" / "web" / "static" / "app.js").read_text(encoding="utf-8")
        html_source = (root / "picorgftp_sql" / "web" / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="historySearchInput"', html_source)
        self.assertIn('id="historyPrevButton"', html_source)
        self.assertIn('id="historyNextButton"', html_source)
        self.assertIn('id="historyTimingModal"', html_source)
        self.assertIn("data-close-history-timing", html_source)
        self.assertIn('page_size: String(state.historyPageSize || 50)', js_source)
        self.assertIn('query: historySearchInput?.value || ""', js_source)
        self.assertIn('timingButton.textContent = "Czasy"', js_source)
        self.assertIn("renderHistoryTiming(item)", js_source)
        self.assertIn("historySearchInput?.addEventListener", js_source)

    def test_web_autocomplete_keeps_local_values_first(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")

        self.assertIn("MAX_AUTOCOMPLETE_OPTIONS = Number.POSITIVE_INFINITY", source)
        self.assertIn("uniqueValues([...local, ...values])", source)
        self.assertIn('panel.dataset.selecting === "1"', source)

    def test_web_settings_security_tab_owns_secret_and_upload_limits(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")
        app_start = source.index("function renderSettingsApp")
        processing_start = source.index("function renderSettingsProcessing")
        security_start = source.index("function renderSettingsSecurity")
        ftp_start = source.index("function renderSettingsFtp")
        app_body = source[app_start:processing_start]
        processing_body = source[processing_start:security_start]
        security_body = source[security_start:ftp_start]

        self.assertNotIn('credentialField("app_secret"', app_body)
        self.assertNotIn("max_upload_mb", processing_body)
        self.assertIn('credentialField("app_secret"', security_body)
        self.assertIn("max_upload_mb", security_body)
        self.assertIn("allowed_upload_extensions", security_body)
        self.assertIn("blocked_upload_extensions", security_body)
        self.assertIn("block_executable_uploads", security_body)
        self.assertIn("uploadAcceptAttribute", source)

    def test_web_settings_processing_groups_related_controls(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")
        app_start = source.index("function renderSettingsApp")
        processing_start = source.index("function renderSettingsProcessing")
        security_start = source.index("function renderSettingsSecurity")
        app_body = source[app_start:processing_start]
        processing_body = source[processing_start:security_start]

        self.assertIn("function settingsFieldGroup", source)
        self.assertIn('"user_show_timing_details"', app_body)
        self.assertNotIn('"user_show_timing_details"', processing_body)

        expectations = {
            'settingsFieldGroup("Zmniejszanie obrazu"': ('"resize_enabled"', '"max_dim"'),
            'settingsFieldGroup("Kompresja JPG/WEBP"': ('"compress_enabled"', '"compress_quality"'),
            'settingsFieldGroup("Limit rozmiaru pliku"': ('"max_size_enabled"', '"max_file_kb"'),
            'settingsFieldGroup("Konwersja formatu"': ('"convert_enabled"', '"target_format"'),
        }
        for marker, required in expectations.items():
            start = processing_body.index(marker)
            next_group = processing_body.find("settingsFieldGroup(", start + len(marker))
            block = processing_body[start:] if next_group == -1 else processing_body[start:next_group]
            for needle in required:
                self.assertIn(needle, block)


if __name__ == "__main__":
    unittest.main()
