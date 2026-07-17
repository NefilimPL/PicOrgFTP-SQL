"""Static source checks that do not require GUI/runtime dependencies."""

from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest


class SourceIntegrityTests(unittest.TestCase):
    def test_mail_settings_ui_wires_both_channels_rules_and_redacted_test(self) -> None:
        root = Path(__file__).resolve().parents[1]
        html_source = (
            root / "picorgftp_sql" / "web" / "static" / "index.html"
        ).read_text(encoding="utf-8")
        js_source = (
            root / "picorgftp_sql" / "web" / "static" / "app.js"
        ).read_text(encoding="utf-8")
        css_source = (
            root / "picorgftp_sql" / "web" / "static" / "app.css"
        ).read_text(encoding="utf-8")

        pimcore_tab = html_source.index('data-settings-tab="pimcore"')
        mail_tab = html_source.index('data-settings-tab="mail"')
        slots_tab = html_source.index('data-settings-tab="slots"')
        self.assertLess(pimcore_tab, mail_tab)
        self.assertLess(mail_tab, slots_tab)
        self.assertIn("function renderSettingsMail()", js_source)
        self.assertIn('requestJson("/api/settings/email/test"', js_source)
        for name in (
            "email_primary_channel",
            "email_fallback_enabled",
            "email_entra_tenant_id",
            "email_entra_client_id",
            "email_entra_client_secret",
            "email_entra_from_address",
            "email_smtp_host",
            "email_smtp_port",
            "email_smtp_security",
            "email_smtp_username",
            "email_smtp_password",
            "email_smtp_from_address",
            "email_smtp_from_name",
            "email_test_recipient",
            "email_test_channel",
            "email_test_use_fallback",
        ):
            self.assertIn(name, js_source)
        for severity in ("info", "warning", "error", "critical"):
            self.assertIn(f"email_rule_{severity}_enabled", js_source)
            self.assertIn(f"email_rule_{severity}_recipients", js_source)
            self.assertIn(f"email_rule_{severity}_include_actor", js_source)
        self.assertIn("splitEmailRecipients", js_source)
        self.assertIn("mail-test-attempt", css_source)
        self.assertIn("@media (max-width: 920px)", css_source)

    def test_header_contains_smoothed_backend_health_indicator(self) -> None:
        root = Path(__file__).resolve().parents[1]
        html_source = (
            root / "picorgftp_sql" / "web" / "static" / "index.html"
        ).read_text(encoding="utf-8")
        js_source = (
            root / "picorgftp_sql" / "web" / "static" / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn('id="backendHealthStatus"', html_source)
        self.assertIn("HEALTH_SLOW_MS = 300", js_source)
        self.assertIn("HEALTH_CRITICAL_MS = 1000", js_source)
        self.assertIn("HEALTH_OFFLINE_FAILURES = 3", js_source)
        self.assertIn("healthSamples.slice(-5)", js_source)

    def test_backend_health_poll_ignores_hidden_aborted_and_stale_requests(self) -> None:
        root = Path(__file__).resolve().parents[1]
        js_source = (
            root / "picorgftp_sql" / "web" / "static" / "app.js"
        ).read_text(encoding="utf-8")

        poll_start = js_source.index("async function pollBackendHealth")
        poll_end = js_source.index("function setBackendHealthDetailsExpanded", poll_start)
        poll_source = js_source[poll_start:poll_end]
        visibility_start = js_source.index('document.addEventListener("visibilitychange"')
        visibility_end = js_source.index("});", visibility_start) + 3
        visibility_source = js_source[visibility_start:visibility_end]

        self.assertIn("new AbortController()", poll_source)
        self.assertIn("requestGeneration !== healthPollGeneration", poll_source)
        self.assertIn("controller.signal.aborted", poll_source)
        self.assertIn('error?.name === "AbortError"', poll_source)
        self.assertLess(
            poll_source.index("requestGeneration !== healthPollGeneration"),
            poll_source.index("healthSamples.push"),
        )
        self.assertIn("scheduleBackendHealthPoll(requestGeneration)", poll_source)
        self.assertIn("healthPollGeneration += 1", visibility_source)
        self.assertIn("healthPollController?.abort()", visibility_source)
        self.assertIn("pollBackendHealth().catch(() => {})", visibility_source)
        self.assertNotIn("scheduleBackendHealthPoll(0)", visibility_source)

    def test_backend_health_offline_reuses_normalized_last_successful_components(self) -> None:
        root = Path(__file__).resolve().parents[1]
        js_source = (
            root / "picorgftp_sql" / "web" / "static" / "app.js"
        ).read_text(encoding="utf-8")
        docs_source = (root / "docs" / "web-panel.md").read_text(encoding="utf-8")

        self.assertIn("lastSuccessfulHealthComponents", js_source)
        self.assertIn("function normalizedHealthComponents", js_source)
        self.assertIn(
            'updateBackendHealthStatus("offline", 0, lastSuccessfulHealthComponents)',
            js_source,
        )
        self.assertIn("ostatni znany stan komponentów", docs_source.lower())

    def test_web_logs_use_durable_observability_apis(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")

        self.assertIn("new EventSource(", source)
        self.assertIn('"/api/observability/stream?after_id="', source)
        self.assertIn('"/api/observability/events', source)
        self.assertIn('"/api/observability/incidents', source)
        self.assertIn('"/api/observability/jobs', source)
        self.assertIn('"/api/observability/read"', source)
        self.assertIn('logsLoadMoreButton.textContent = "Wczytaj wiecej"', source)
        self.assertNotIn("for (const log of logs)", source)
        self.assertNotIn("function logReadStorageKey", source)

    def test_web_logs_guard_stream_and_cursor_races(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")

        seed_start = source.index("async function seedLiveLogs")
        seed_end = source.index("function appendLiveEvent", seed_start)
        seed_source = source[seed_start:seed_end]
        self.assertIn("seedGeneration", seed_source)
        self.assertIn("live_seed", seed_source)
        self.assertIn("stream_after_id", seed_source)
        self.assertIn("if (!streamAfterId)", seed_source)
        self.assertIn("mergeLiveItems", seed_source)
        self.assertLess(
            seed_source.index('"/api/observability/events?"'),
            seed_source.index("startObservabilityStream(streamAfterId);"),
        )
        self.assertNotIn("seedBuffer", seed_source)
        paused_seed = seed_source[
            seed_source.index("if (state.observability.paused)") : seed_source.index(
                "} else", seed_source.index("if (state.observability.paused)")
            )
        ]
        self.assertIn("appendPausedObservabilityEvents(seedItems)", paused_seed)
        self.assertNotIn("live.items =", paused_seed)
        self.assertNotIn("renderLogs()", paused_seed)
        seed_catch = seed_source[seed_source.index("} catch (error)") :]
        self.assertIn(
            "if (state.observability.seedGeneration !== seedGeneration) return;",
            seed_catch,
        )
        self.assertIn("if (state.observability.streamAfterId)", seed_catch)
        self.assertNotIn("observability-live-high-water", source)
        paused_buffer = source[
            source.index("function appendPausedObservabilityEvents") : seed_start
        ]
        self.assertIn("live.items", paused_buffer)
        stream_source = source[
            source.index("function startObservabilityStream") : source.index(
                "function stopObservabilityStream"
            )
        ]
        self.assertIn("encodeURIComponent(afterId)", stream_source)
        self.assertNotIn(': new EventSource("/api/observability/stream")', stream_source)
        self.assertIn("streamConnected = true", stream_source)
        self.assertIn("streamConnected = false", stream_source)
        self.assertIn('state.observability.paused ? "Wstrzymano" : "Polaczono"', stream_source)
        self.assertIn("if (tab.loading) return;", source)
        self.assertIn("logsLoadMoreButton.disabled = Boolean(tab.loading)", source)
        self.assertIn("state.observability.activeTab === tabName", source)
        append_live = source[
            source.index("function appendLiveEvent") : source.index(
                "function handleObservabilityEvent"
            )
        ]
        self.assertIn("logsOutput.appendChild(renderLogEvent(event))", append_live)
        self.assertNotIn("renderLogs()", append_live)

    def test_web_logs_gate_reads_navigation_unread_and_filters(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")

        self.assertIn("function waitForLogsPaint", source)
        self.assertIn("window.requestAnimationFrame", source)
        self.assertIn('logsView?.classList.contains("active")', source)
        self.assertIn("tab.requestId !== requestId", source)
        self.assertIn(
            'logsOutput.querySelector(".log-incident[data-observability-id]")',
            source,
        )
        self.assertIn("card.getClientRects().length", source)
        self.assertIn("async function walkObservabilityPages", source)
        self.assertIn("async function openObservabilityRecord", source)
        self.assertIn("focusObservabilityRecord", source)
        self.assertNotIn("OBSERVABILITY_RECORD_PAGE_LIMIT", source)
        self.assertIn("visitedCursors.has(nextCursor)", source)
        self.assertIn("unreadRequestId", source)
        self.assertIn("applyObservabilityUnread", source)
        request_source = source[
            source.index("async function requestObservabilityPayload") : source.index(
                "function showLogsError"
            )
        ]
        self.assertNotIn("authoritativeUnread", request_source)
        self.assertEqual(request_source.count("unreadRequestId ="), 1)
        self.assertIn("committedFilters", source)
        self.assertIn('logsFilters?.addEventListener("reset"', source)
        job_renderer = source[
            source.index("function renderJobCard") : source.index(
                "function logItemMatchesFilters"
            )
        ]
        self.assertNotIn(': "error"', job_renderer)
        walk_source = source[
            source.index("async function walkObservabilityPages") : source.index(
                "function focusObservabilityRecord"
            )
        ]
        self.assertIn("findIncidentRecord", walk_source)
        self.assertIn("loadIncidentThroughRecord", walk_source)
        discovery_source = source[
            source.index("async function findIncidentRecord") : source.index(
                "async function loadIncidentThroughRecord"
            )
        ]
        self.assertNotIn("appendUniqueObservabilityItems", discovery_source)
        severity_walk = source[
            source.index("async function loadIncidentThroughRecord") : source.index(
                "async function walkObservabilityPages"
            )
        ]
        self.assertIn("observabilityEndpoint(severity, cursor)", severity_walk)
        self.assertIn("tab.nextCursor = payload.next_cursor", severity_walk)
        jobs_walk = source[
            source.index("async function loadJobThroughRecord") : source.index(
                "async function walkObservabilityPages"
            )
        ]
        self.assertIn("jobs.nextCursor = payload.next_cursor", jobs_walk)
        resume_source = source[
            source.index('logsPauseButton?.addEventListener("click"') : source.index(
                "if (logsAutoscrollToggle)"
            )
        ]
        self.assertIn("state.observability.streamConnected", resume_source)
        self.assertIn('"Rozlaczono"', resume_source)

    def test_web_client_reports_deduplicated_global_failures(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")

        self.assertIn("function reportClientFailure", source)
        self.assertIn('requestJson("/api/observability/client-errors"', source)
        self.assertIn('window.addEventListener("error"', source)
        self.assertIn('window.addEventListener("unhandledrejection"', source)
        self.assertIn("CLIENT_FAILURE_DEDUPE_MS", source)
        self.assertIn("clientFailureFingerprints", source)

    def test_desktop_uses_generic_product_field_settings(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "picorgftp_sql" / "app.py"
        source = app_path.read_text(encoding="utf-8")

        self.assertIn("def _refresh_product_fields", source)
        self.assertIn("def _missing_required_product_fields", source)
        self.assertIn("product_field_vars", source)
        self.assertIn("D[PRODUCT_FIELDS_KEY] = normalize_product_fields", source)
        self.assertIn("A._refresh_product_fields()", source)
        self.assertIn("missing_fields = A._missing_required_product_fields()", source)
        self.assertNotIn(
            "D[COLOR_FIELD_LABELS_KEY] = A._normalize_color_field_label_overrides",
            source,
        )

    def test_web_process_applies_active_product_field_settings(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "app.py"
        )
        source = app_path.read_text(encoding="utf-8")

        self.assertIn("field_settings = _active_product_field_settings()", source)
        self.assertIn("product = effective_product_form(product, field_settings)", source)
        self.assertIn("field_settings=field_settings", source)

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

    def test_history_exposes_detailed_changes_modal(self) -> None:
        root = Path(__file__).resolve().parents[1]
        js_source = (root / "picorgftp_sql" / "web" / "static" / "app.js").read_text(
            encoding="utf-8"
        )
        html_source = (
            root / "picorgftp_sql" / "web" / "static" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn('id="historyChangesModal"', html_source)
        self.assertIn('changesButton.textContent = "Zmiany"', js_source)
        self.assertIn("renderHistoryChanges(item)", js_source)
        self.assertIn(
            "Szczegolowy zapis zmian nie byl jeszcze dostepny",
            js_source,
        )

    def test_history_changes_preserve_structured_values_and_pimcore_job_ids(self) -> None:
        root = Path(__file__).resolve().parents[1]
        js_source = (root / "picorgftp_sql" / "web" / "static" / "app.js").read_text(
            encoding="utf-8"
        )
        web_data_source = (root / "picorgftp_sql" / "web_data.py").read_text(
            encoding="utf-8"
        )
        pimcore_history_item = {
            "details": {
                "pimcore_operation": {"operation_id": "pimcore-operation-123"},
                "change_set": {"pimcore": {"operation_id": "structured-operation-456"}},
            }
        }

        self.assertEqual(
            pimcore_history_item["details"]["pimcore_operation"]["operation_id"],
            "pimcore-operation-123",
        )
        self.assertIn('"pimcore_operation": redact_pimcore_log_value(report)', web_data_source)
        self.assertIn("JSON.stringify", js_source)
        self.assertIn("Object.keys(nested).sort()", js_source)
        self.assertIn("historyChangeRow(key, value)", js_source)
        self.assertIn("details.pimcore_operation?.operation_id", js_source)
        self.assertIn("changeSet.pimcore?.operation_id", js_source)

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
        root = Path(__file__).resolve().parents[1]
        app_path = (
            root / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        )
        source = app_path.read_text(encoding="utf-8")
        html_source = (
            root / "picorgftp_sql" / "web" / "static" / "index.html"
        ).read_text(encoding="utf-8")
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
        self.assertIn('id="secretRevealModal"', html_source)
        self.assertIn('id="secretRevealPassword" type="password"', html_source)
        self.assertIn("requestSecretRevealPassword", source)
        self.assertNotIn("window.prompt", source)

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
                (
                    "Runtime aplikacji",
                    [
                        "versionNote",
                        "configNote",
                        "runtimeWarning",
                        '"data_mode"',
                        '"image_dir"',
                        '"database_location_mode"',
                        '"database_path"',
                        "importLegacyDataButton",
                    ],
                ),
                ("Indeks lokalny", ['"local_file_index"', "diagnosticButton", "fileIndexRefreshButton"]),
                ("Widok panelu", ['"user_show_timing_details"']),
                ("Pola produktu", ["productFieldsNote", "productFieldSettingsList", "s.product_fields"]),
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
                (
                    "Tryb SQL",
                    [
                        '"type"',
                        '"sql_update_enabled"',
                        '"query"',
                        "diagnosticButton",
                        '"mssql_server"',
                        '"mssql_database"',
                        'credentialField("mssql_user"',
                        '"mysql_server"',
                        '"mysql_database"',
                        'credentialField("mysql_user"',
                    ],
                ),
                ("Profile dodatkowe SQL", ["additionalSqlProfiles", "addProfile"]),
            ],
            "renderSettingsSlots": [
                ("Lista slotow", ["note", "list", "addButton", "detectSqlColumnsButton"]),
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

    def test_web_sql_settings_show_placeholder_help(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "picorgftp_sql" / "web" / "static" / "app.js").read_text(encoding="utf-8")
        sql_start = source.index("function renderSettingsSql")
        slots_start = source.index("function renderSettingsSlots", sql_start)
        sql_body = source[sql_start:slots_start]

        self.assertIn("sqlPlaceholderHelp", source)
        self.assertIn("{ean}", sql_body)
        self.assertIn("{filename}", sql_body)
        self.assertIn("{col}", sql_body)
        self.assertIn("{column}", sql_body)

    def test_web_settings_include_sqlite_repair_and_backup_controls(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "picorgftp_sql" / "web" / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn("repairSqliteDatabaseButton", source)
        self.assertIn("manualSqliteBackupButton", source)
        self.assertIn("backupHistoryButton", source)
        self.assertIn("sqliteBackupScheduleGrid", source)
        self.assertIn("/api/settings/sqlite/repair", source)
        self.assertIn("/api/settings/sqlite/backup", source)
        self.assertIn("/api/settings/sqlite/backups", source)
        self.assertIn("/api/settings/sqlite/restore", source)
        self.assertIn("/api/settings/sqlite/backup-diff", source)

    def test_pimcore_settings_wires_save_test_and_csv_import(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("function renderSettingsPimcore()", source)
        self.assertIn('requestJson("/api/settings/pimcore/test"', source)
        self.assertIn('requestJson("/api/settings/pimcore/import-csv-headers"', source)
        self.assertIn("field_mappings: collectSimplePimcoreMappings(form)", source)

    def test_pimcore_compact_settings_hide_technical_controls(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("pimcoreAdvancedSettings", source)
        self.assertIn("advanced.open = false", source)
        self.assertIn("Odswiez klasy i foldery", source)
        self.assertIn("Typ danych wykryty automatycznie", source)
        self.assertIn("pimcoreCsvImportButton", source)

    def test_pimcore_write_test_keeps_modal_open_and_polls_incrementally(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("function openPimcoreWriteTest()", source)
        self.assertIn("after_sequence", source)
        self.assertIn("500", source)
        self.assertIn("pimcoreTestForm.reset()", source)
        self.assertNotIn('pimcoreTestModal.classList.remove("active"); // submit', source)
        self.assertIn("cleanup_policy", source)

    def test_pimcore_live_log_history_uses_dedicated_endpoint(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("/api/settings/pimcore/test-create-runs", source)
        self.assertIn("/api/settings/pimcore/operations", source)
        self.assertIn("function appendPimcoreLiveEvents", source)

    def test_pimcore_diagnostics_use_expandable_details(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn('document.createElement("details")', source)
        self.assertIn('document.createElement("summary")', source)
        self.assertIn('status === "skipped"', source)

    def test_pimcore_wizard_discovers_then_completes_setup(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("openPimcoreSetupWizard", source)
        self.assertIn("/api/settings/pimcore/discover/classes", source)
        self.assertIn("/api/settings/pimcore/discover/folders", source)
        self.assertIn("/api/settings/pimcore/discover/fields", source)
        self.assertIn("/api/settings/pimcore/setup", source)
        self.assertIn("setup_complete", source)

    def test_pimcore_wizard_explains_product_field_controls(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("Ktore dane uzytkownik ma wpisywac", source)
        self.assertIn("Zapisz pole", source)
        self.assertIn("Pole w Pimcore", source)
        self.assertIn("Nazwa w formularzu", source)
        self.assertIn("Wymagane", source)
        self.assertIn("function pimcoreDiscoveryErrorText", source)
        self.assertIn("Nie wykryto folderow Pimcore", source)

    def test_ean_input_debounces_pimcore_lookup_and_rechecks_on_create(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("function schedulePimcoreStatusLookup()", source)
        self.assertIn("/api/pimcore/product-status", source)
        self.assertIn('requestJson("/api/pimcore/products"', source)
        self.assertIn("500", source)
        self.assertIn("pimcoreCreateEan.readOnly = true", source)

    def test_pimcore_runtime_gates_lookup_and_cancel_does_not_create(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("function applyPimcoreRuntimeCapabilities", source)
        self.assertIn("if (!state.pimcoreRuntimeEnabled) return;", source)
        self.assertIn("productForm.elements.ean?.addEventListener(\"input\", handlePimcoreEanInput)", source)
        self.assertIn("pimcoreCreateModal.classList.remove(\"active\");", source)
        self.assertIn("pimcoreCreateCancelButton?.addEventListener(\"click\"", source)
        cancel_start = source.index("pimcoreCreateCancelButton?.addEventListener")
        cancel_end = source.index("pimcoreCreateForm?.addEventListener", cancel_start)
        self.assertNotIn("requestJson", source[cancel_start:cancel_end])

    def test_pimcore_edit_loads_selected_fields_and_cancel_does_not_put(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "picorgftp_sql"
            / "web"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("openPimcoreEditModal", source)
        self.assertIn('requestJson(`/api/pimcore/products/${encodeURIComponent(objectId)}`)', source)
        self.assertIn('method: "PUT"', source)
        self.assertIn("pimcoreEditEan.readOnly = true", source)
        cancel_start = source.index('pimcoreEditCancelButton?.addEventListener("click"')
        cancel_end = source.index("});", cancel_start)
        self.assertNotIn("requestJson", source[cancel_start:cancel_end])

    def test_sqlite_backup_schedule_uses_day_hour_slots_and_nested_modal_layer(self) -> None:
        root = Path(__file__).resolve().parents[1]
        js_source = (root / "picorgftp_sql" / "web" / "static" / "app.js").read_text(encoding="utf-8")
        css_source = (root / "picorgftp_sql" / "web" / "static" / "app.css").read_text(encoding="utf-8")

        self.assertIn('input.name = "sqlite_backup_slot"', js_source)
        self.assertIn("input.value = `${key}:${hour}`", js_source)
        self.assertIn('querySelectorAll(\'[name="sqlite_backup_slot"]:checked\')', js_source)
        self.assertIn(".modal-view.nested-modal.active", css_source)

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

    def test_desktop_settings_include_storage_controls(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "picorgftp_sql" / "app.py"
        source = app_path.read_text(encoding="utf-8")

        self.assertIn("data_mode_var", source)
        self.assertIn("database_location_mode_var", source)
        self.assertIn("database_path_var", source)
        self.assertIn("Importuj stare dane do SQLite", source)
        self.assertIn("storage_settings.save_bootstrap_settings", source)

    def test_desktop_local_file_index_uses_active_cache_store(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "picorgftp_sql" / "app.py"
        source = app_path.read_text(encoding="utf-8")
        index_start = source.index("B._file_index = LocalFileIndex(")
        index_block = source[index_start : index_start + 500]

        self.assertIn("cache_store=", index_block)
        self.assertIn("data_store.get_active_store", source)

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
