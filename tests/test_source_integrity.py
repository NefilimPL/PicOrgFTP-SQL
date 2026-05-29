"""Static source checks that do not require GUI/runtime dependencies."""

from __future__ import annotations

import ast
from pathlib import Path
import re
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
        self.assertIn('createPoller("processQueue", 2500, refreshProcessQueue)', js_source)
        self.assertIn("document.hidden", js_source)
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

        self.assertIn("MAX_AUTOCOMPLETE_OPTIONS = 80", source)
        self.assertIn("uniqueValues([...local, ...values])", source)
        self.assertIn('panel.dataset.selecting === "1"', source)
        self.assertIn("setActiveAutocompleteOption", source)

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

    def test_web_settings_tabs_use_consistent_field_groups(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")

        def function_body(name: str, next_name: str) -> str:
            start = source.index(f"function {name}")
            end = source.index(f"function {next_name}", start + len(f"function {name}"))
            return source[start:end]

        checks = {
            "renderSettingsApp": [
                ("Runtime aplikacji", ["versionNote", "configNote", "runtimeWarning", '"base_dir"']),
                ("Indeks lokalny", ['"local_file_index"', "diagnosticButton", "fileIndexRefreshButton"]),
                ("Widok panelu", ['"user_show_timing_details"']),
                ("Nazwy pol kolorow", ['"color1"', '"color2"', '"color3"']),
            ],
            "renderSettingsSecurity": [
                ("Sekret aplikacji", ['credentialField("app_secret"']),
                ("Limity uploadu", ['"max_upload_mb"', '"max_upload_pixels"']),
                (
                    "Typy plikow uploadu",
                    ['"allowed_upload_extensions"', '"blocked_upload_extensions"', '"block_executable_uploads"'],
                ),
            ],
            "renderSettingsFtp": [
                ("Polaczenie FTP", ['"enabled"', '"host"', '"port"', '"path"', "diagnosticButton"]),
                ("Dane logowania FTP", ['credentialField("user"', 'credentialField("password"']),
            ],
            "renderSettingsSql": [
                ("Tryb SQL", ['"type"', '"sql_update_enabled"', '"query"', "diagnosticButton"]),
                ("MS SQL", ['"mssql_server"', '"mssql_database"', 'credentialField("mssql_user"']),
                ("MySQL", ['"mysql_server"', '"mysql_database"', 'credentialField("mysql_user"']),
            ],
            "renderSettingsSlots": [
                ("Lista slotow", ["note", "list", "addButton"]),
            ],
            "renderSettingsUsers": [
                ("Nowy uzytkownik", ["addForm"]),
                ("Lista uzytkownikow", ["list"]),
            ],
        }
        boundaries = {
            "renderSettingsApp": "renderSettingsProcessing",
            "renderSettingsSecurity": "renderSettingsFtp",
            "renderSettingsFtp": "renderSettingsSql",
            "renderSettingsSql": "renderSettingsSlots",
            "renderSettingsSlots": "renderSettingsUsers",
            "renderSettingsUsers": "renderSettings",
        }

        for function_name, groups in checks.items():
            body = function_body(function_name, boundaries[function_name])
            for title, expected_fields in groups:
                marker = f'settingsFieldGroup("{title}"'
                start = body.index(marker)
                next_group = body.find("settingsFieldGroup(", start + len(marker))
                block = body[start:] if next_group == -1 else body[start:next_group]
                for field in expected_fields:
                    self.assertIn(field, block)

    def test_web_settings_field_groups_are_full_width_cards(self) -> None:
        css_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.css"
        )
        source = css_path.read_text(encoding="utf-8")

        def css_block(selector: str) -> str:
            pattern = rf"(?m)^{re.escape(selector)}\s*\{{(?P<body>.*?)\n\}}"
            match = re.search(pattern, source, flags=re.S)
            self.assertIsNotNone(match, f"Missing CSS block for {selector}")
            return match.group("body")

        settings_form = css_block(".settings-form")
        settings_group = css_block(".settings-field-group")
        settings_group_title = css_block(".settings-field-group h2")

        self.assertIn("grid-template-columns: 1fr", settings_form)
        self.assertIn("grid-column: 1 / -1", settings_group)
        self.assertIn("grid-template-columns: repeat(auto-fit, minmax(220px, 1fr))", settings_group)
        self.assertIn("align-items: start", settings_group)
        self.assertIn("grid-column: 1 / -1", settings_group_title)

    def test_web_client_validates_slot_upload_format_before_xhr(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")

        validation_start = source.index("function uploadFileValidationError")
        validation_end = source.index("function fileListFromInput", validation_start)
        validation_body = source[validation_start:validation_end]
        for required in (
            "allowed_upload_extensions",
            "blocked_upload_extensions",
            "block_executable_uploads",
            "CLIENT_EXECUTABLE_UPLOAD_EXTENSIONS",
        ):
            self.assertIn(required, validation_body)
        self.assertIn("nie jest na bialej liscie", validation_body)

        set_slot_start = source.index("function setSlotFile")
        set_slot_end = source.index("function getSlotAssignment", set_slot_start)
        set_slot_body = source[set_slot_start:set_slot_end]
        validation_call = set_slot_body.index("uploadFileValidationError(file)")
        upload_call = set_slot_body.index("uploadSlotFile(prefix, item)")
        self.assertLess(validation_call, upload_call)
        self.assertIn("item.error = validationError", set_slot_body)
        self.assertIn("return", set_slot_body[validation_call:upload_call])

        assign_start = source.index("function assignFilesFromSlot")
        assign_end = source.index("function applyDefaultSlotSource", assign_start)
        assign_body = source[assign_start:assign_end]
        self.assertIn("slotUploadError(item)", assign_body)
        self.assertIn("Odrzucono", assign_body)

        self.assertIn('`${base} - blad uploadu: ${slotUploadError(item)}`', source)
        self.assertIn('`Upload nieudany: ${error}`', source)
        self.assertIn("Upload nieudany: slot", source)


if __name__ == "__main__":
    unittest.main()
