"""Static integrity tests for the browser UI."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "picorgftp_sql" / "web" / "static" / "index.html"
LOGIN_HTML = ROOT / "picorgftp_sql" / "web" / "static" / "login.html"
APP_JS = ROOT / "picorgftp_sql" / "web" / "static" / "app.js"


class _HtmlCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: dict[str, str] = {}
        self.duplicate_ids: set[str] = set()
        self.input_names: set[str] = set()
        self.button_ids: set[str] = set()
        self.data_modals: set[str] = set()
        self.classes: set[str] = set()
        self.tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        self.tags.append((tag, attr_map))
        element_id = attr_map.get("id", "")
        if element_id:
            if element_id in self.ids:
                self.duplicate_ids.add(element_id)
            self.ids[element_id] = tag
        if tag == "input" and attr_map.get("name"):
            self.input_names.add(attr_map["name"])
        if tag == "button" and element_id:
            self.button_ids.add(element_id)
        if attr_map.get("data-modal"):
            self.data_modals.add(attr_map["data-modal"])
        for class_name in attr_map.get("class", "").split():
            self.classes.add(class_name)

    def has_tag(self, tag: str, **attrs: str) -> bool:
        for found_tag, found_attrs in self.tags:
            if found_tag != tag:
                continue
            if all(found_attrs.get(key) == value for key, value in attrs.items()):
                return True
        return False


def _parse(path: Path) -> _HtmlCollector:
    parser = _HtmlCollector()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


class WebUiIntegrityTests(unittest.TestCase):
    def test_mail_settings_tab_has_safe_secrets_and_responsive_channel_cards(self) -> None:
        html = _parse(INDEX_HTML)
        source = APP_JS.read_text(encoding="utf-8")
        css = (
            ROOT / "picorgftp_sql" / "web" / "static" / "app.css"
        ).read_text(encoding="utf-8")

        self.assertTrue(html.has_tag("button", **{"data-settings-tab": "mail"}))
        mail_start = source.index("function renderSettingsMail()")
        mail_end = source.index("function renderSettingsSlots", mail_start)
        mail_source = source[mail_start:mail_end]
        self.assertIn('type: "password"', mail_source)
        self.assertIn("email.entra?.client_secret_set", mail_source)
        self.assertIn("email.smtp?.password_set", mail_source)
        self.assertNotIn("email.entra?.client_secret ||", mail_source)
        self.assertNotIn("email.smtp?.password ||", mail_source)
        self.assertIn("client_secret: data.get(\"email_entra_client_secret\")", mail_source)
        self.assertIn("password: data.get(\"email_smtp_password\")", mail_source)
        self.assertIn('security !== "none"', mail_source)
        self.assertIn("Nie szyfruje polaczenia", mail_source)
        self.assertIn("testButton.disabled = true", mail_source)
        self.assertIn("testButton.disabled = false", mail_source)
        self.assertIn("result.used_channel", source)
        self.assertIn("result.attempts", source)
        self.assertIn("error.payload = payload", source)
        recipients_start = source.index("function splitEmailRecipients")
        recipients_end = source.index("const MAIL_SEVERITY_RULES", recipients_start)
        recipients_source = source[recipients_start:recipients_end]
        self.assertIn("new Set()", recipients_source)
        self.assertIn("toLowerCase()", recipients_source)
        self.assertIn("seen.has", recipients_source)
        self.assertIn(".mail-channel-grid", css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", css)
        responsive_start = css.index("@media (max-width: 920px)")
        self.assertIn("grid-template-columns: 1fr", css[responsive_start:])
        self.assertNotIn("animation", css[css.index(".mail-test-status"):responsive_start])

    def test_user_settings_forms_send_optional_email_fields(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        css = (
            ROOT / "picorgftp_sql" / "web" / "static" / "app.css"
        ).read_text(encoding="utf-8")
        users_source = source[
            source.index("function renderSettingsUsers") : source.index(
                "function renderSettings()", source.index("function renderSettingsUsers")
            )
        ]

        self.assertIn('emailInput.name = "email"', users_source)
        self.assertIn('emailInput.type = "email"', users_source)
        self.assertIn('emailInput.autocomplete = "email"', users_source)
        self.assertIn('userEmailInput.type = "email"', users_source)
        self.assertIn('userEmailInput.autocomplete = "email"', users_source)
        self.assertIn("email: emailInput.value", users_source)
        self.assertIn("email: userEmailInput.value", users_source)
        self.assertIn(".user-add-form", css)
        self.assertIn(".user-row", css)

    def test_backend_health_indicator_is_accessible_safe_and_visibility_aware(self) -> None:
        html_source = INDEX_HTML.read_text(encoding="utf-8")
        js_source = APP_JS.read_text(encoding="utf-8")
        css_source = (
            ROOT / "picorgftp_sql" / "web" / "static" / "app.css"
        ).read_text(encoding="utf-8")

        brand_start = html_source.index('<div class="topbar-brand">')
        brand_end = html_source.index("</header>", brand_start)
        brand_source = html_source[brand_start:brand_end]
        self.assertIn('id="backendHealthStatus"', brand_source)
        self.assertIn('aria-live="polite"', brand_source)
        self.assertIn('aria-controls="backendHealthDetails"', brand_source)
        self.assertIn('aria-expanded="false"', brand_source)
        self.assertIn('class="backend-health-dot"', brand_source)
        self.assertIn('id="backendHealthText"', brand_source)
        self.assertIn('id="backendHealthDetails"', brand_source)
        self.assertIn('id="backendHealthDetails" class="backend-health-details" role="tooltip" hidden', brand_source)
        for label in ("Backend", "SQLite", "Proces zadan", "Powiadomienia", "FTP", "SQL", "Profile SQL", "Pimcore"):
            self.assertIn(label, brand_source)

        health_start = js_source.index("function healthLevel")
        health_end = js_source.index("function scheduleBackendHealthPoll", health_start)
        health_source = js_source[health_start:health_end]
        self.assertIn('components.backend?.status !== "online"', health_source)
        self.assertIn('components.sqlite?.status === "critical"', health_source)
        self.assertIn('components.job_processor?.status === "critical"', health_source)
        self.assertIn('components.notification_worker?.status === "critical"', health_source)
        self.assertIn("payloadOk === false", health_source)
        self.assertIn("ms > HEALTH_CRITICAL_MS", health_source)
        self.assertIn("ms >= HEALTH_SLOW_MS", health_source)
        self.assertIn('item.status === "degraded"', health_source)
        self.assertIn("performance.now()", js_source)
        self.assertIn('requestJson("/api/health", { signal: controller.signal })', js_source)
        self.assertIn("healthFailures = 0", js_source)
        self.assertIn("healthFailures >= HEALTH_OFFLINE_FAILURES", js_source)
        self.assertIn("document.hidden", js_source)
        self.assertIn("pollBackendHealth().catch(() => {})", js_source)
        self.assertNotIn("backendHealthDetailsList.innerHTML", js_source)
        self.assertIn("backendHealthDetailsList.replaceChildren", js_source)
        self.assertIn("observed_at", js_source)
        self.assertIn("serverTime", js_source)
        self.assertIn("currentLatencyMs", js_source)
        self.assertIn("medianLatencyMs", js_source)

        disclosure_start = js_source.index("function setBackendHealthDetailsExpanded")
        disclosure_end = js_source.index("function showLogsError", disclosure_start)
        disclosure_source = js_source[disclosure_start:disclosure_end]
        self.assertIn("backendHealthDetails.hidden = !expanded", disclosure_source)
        self.assertIn('setAttribute("aria-expanded", expanded ? "true" : "false")', disclosure_source)
        self.assertIn("healthDetailsPinned", disclosure_source)
        self.assertIn("healthDetailsPointerInside = true", disclosure_source)
        self.assertIn("healthDetailsPointerInside = false", disclosure_source)
        self.assertNotIn('matches(":hover")', disclosure_source)
        for event_name in ("pointerenter", "pointerleave", "focusin", "focusout", "click"):
            self.assertIn(f'addEventListener("{event_name}"', disclosure_source)

        self.assertIn(".backend-health-dot", css_source)
        self.assertIn('[data-level="offline"]', css_source)
        self.assertNotIn(".backend-health-indicator:hover .backend-health-details", css_source)
        self.assertNotIn(".backend-health-indicator:focus-within .backend-health-details", css_source)

    def test_logs_use_tabs_live_stream_and_cursor_loading(self) -> None:
        html_source = INDEX_HTML.read_text(encoding="utf-8")
        js_source = APP_JS.read_text(encoding="utf-8")
        css_source = (
            ROOT / "picorgftp_sql" / "web" / "static" / "app.css"
        ).read_text(encoding="utf-8")

        for tab in ("live", "critical", "error", "warning", "jobs"):
            self.assertIn(f'data-log-tab="{tab}"', html_source)
            self.assertIn(f'data-log-badge="{tab}"', html_source)
        for control_id in (
            "logsTextFilter",
            "logsSeverityFilter",
            "logsModuleFilter",
            "logsUserFilter",
            "logsEanFilter",
            "logsJobFilter",
            "logsPauseButton",
            "logsAutoscrollToggle",
            "logsLoadMoreButton",
            "logsResetFiltersButton",
        ):
            self.assertIn(f'id="{control_id}"', html_source)
        self.assertIn("observability:", js_source)
        self.assertIn("nextCursor", js_source)
        self.assertIn("unread", js_source)
        self.assertIn("MAX_LIVE_LOG_EVENTS = 2000", js_source)
        self.assertIn("localStorage.getItem(LOG_AUTOSCROLL_KEY)", js_source)
        self.assertIn('classList.toggle("log-alert-error"', js_source)
        self.assertIn(".nav-button.log-alert-error", css_source)
        self.assertIn(".log-card-highlight", css_source)
        self.assertIn("data-observability-id", js_source)
        self.assertIn("live_seed", js_source)
        self.assertIn("stream_after_id", js_source)
        logs_renderer = js_source[
            js_source.index("function renderLogEvent") : js_source.index("function createPoller")
        ]
        self.assertNotIn("innerHTML", logs_renderer)
        self.assertIn("textContent", logs_renderer)

    def test_incident_cards_render_safe_delivery_status_details(self) -> None:
        js_source = APP_JS.read_text(encoding="utf-8")
        css_source = (
            ROOT / "picorgftp_sql" / "web" / "static" / "app.css"
        ).read_text(encoding="utf-8")

        for status, label in (
            ("pending", "Oczekuje"),
            ("sending", "Oczekuje"),
            ("sent", "Wysłano"),
            ("fallback", "Fallback"),
            ("skipped", "Pominięto"),
            ("error", "Błąd"),
        ):
            self.assertIn(f'{status}: "{label}"', js_source)
        incident_renderer = js_source[
            js_source.index("function renderIncidentCard") : js_source.index(
                "function renderJobCard"
            )
        ]
        self.assertIn("renderIncidentDeliveries", incident_renderer)
        self.assertNotIn("innerHTML", incident_renderer)
        self.assertIn(".log-delivery-badge", css_source)
        self.assertIn(".log-delivery-details", css_source)
        delivery_styles = css_source[
            css_source.index(".log-delivery-summary") : css_source.index(
                ".log-card-highlight"
            )
        ]
        self.assertIn("var(--local)", delivery_styles)
        self.assertNotIn("var(--success)", delivery_styles)

    def test_incident_context_is_loaded_lazily_and_problem_is_cursor_paginated(self) -> None:
        js_source = APP_JS.read_text(encoding="utf-8")
        incident_renderer = js_source[
            js_source.index("function renderIncidentCard") : js_source.index(
                "function renderJobCard"
            )
        ]

        self.assertNotIn('renderIncidentContext(incident, "before"', incident_renderer)
        self.assertIn("renderLazyIncidentContext", incident_renderer)
        self.assertIn("/context?", js_source)
        self.assertIn("problem_next_cursor", js_source)
        self.assertIn("Wczytaj wiecej", js_source)
        self.assertIn('addEventListener("toggle"', js_source)

    def test_live_archive_load_more_keeps_fixed_seed_boundary_and_deduplicates(self) -> None:
        js_source = APP_JS.read_text(encoding="utf-8")

        self.assertIn("archiveSince", js_source)
        self.assertIn("payload.archive_since", js_source)
        self.assertIn("liveArchiveEndpoint", js_source)
        self.assertIn('params.set("since", live.archiveSince)', js_source)
        self.assertIn("mergeLiveItems", js_source)
        self.assertIn("live.nextCursor", js_source)
        self.assertNotIn('tabName === "live" || !tab.nextCursor', js_source)
        append_live = js_source[
            js_source.index("function appendLiveEvent") : js_source.index(
                "function handleObservabilityEvent"
            )
        ]
        self.assertIn("live.archiveSince", append_live)
        self.assertIn("live.items.sort", append_live)

    def test_app_js_static_id_selectors_exist_in_index_html(self) -> None:
        html = _parse(INDEX_HTML)
        source = APP_JS.read_text(encoding="utf-8")
        selector_ids = set(
            re.findall(
                r"document\.querySelector(?:All)?\([\"']#([A-Za-z][A-Za-z0-9_-]*)[\"']\)",
                source,
            )
        )
        created_ids = set(
            re.findall(r"\.id\s*=\s*[\"']([A-Za-z][A-Za-z0-9_-]*)[\"']", source)
        )

        missing = sorted(selector_ids - set(html.ids) - created_ids)

        self.assertEqual(missing, [])
        self.assertEqual(html.duplicate_ids, set())

    def test_product_form_keeps_required_fields_and_actions(self) -> None:
        html = _parse(INDEX_HTML)

        required_inputs = {
            "product_id",
            "name",
            "type_name",
            "model",
            "color1",
            "color2",
            "color3",
            "extra",
            "ean",
        }
        required_buttons = {
            "webImagesButton",
            "findByEanButton",
            "findProductButton",
            "submitButton",
            "clearButton",
            "logoutButton",
            "themeToggleButton",
        }

        self.assertIn("productForm", html.ids)
        self.assertEqual(required_inputs - html.input_names, set())
        self.assertEqual(required_buttons - html.button_ids, set())
        self.assertIn("entrySelect", html.ids)
        self.assertIn("formStatus", html.ids)

    def test_all_product_fields_have_dynamic_containers_and_labels(self) -> None:
        html = _parse(INDEX_HTML)
        canonical = {
            "name",
            "type",
            "model",
            "color1",
            "color2",
            "color3",
            "extra",
            "ean",
        }
        containers = {
            attrs.get("data-product-field")
            for _tag, attrs in html.tags
            if attrs.get("data-product-field")
        }
        labels = {
            attrs.get("data-product-field-label")
            for _tag, attrs in html.tags
            if attrs.get("data-product-field-label")
        }

        self.assertEqual(canonical - containers, set())
        self.assertEqual(canonical - labels, set())

    def test_web_settings_builds_vertical_product_field_rows(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        css = (
            ROOT / "picorgftp_sql" / "web" / "static" / "app.css"
        ).read_text(encoding="utf-8")

        self.assertIn("function productFieldSettingsList", source)
        self.assertIn('className = "product-field-settings-list wide-field"', source)
        self.assertIn('className = "product-field-settings-row"', source)
        self.assertIn("function collectProductFieldSettings", source)
        self.assertNotIn("function productFieldSettingsOrder", source)
        self.assertNotIn("function renderProductFieldLayout", source)
        self.assertNotIn("function moveProductFieldSettingsRow", source)
        self.assertNotIn("product_field_${key}_group", source)
        self.assertNotIn("product_field_${key}_order", source)
        self.assertNotIn("product-field-order-actions", source)
        self.assertIn(".product-field-settings-list", css)
        self.assertIn(".product-field-settings-row", css)
        self.assertNotIn(".product-field-group-heading", css)
        self.assertNotIn(".product-field-order-actions", css)

    def test_topbar_contains_non_button_presence_before_web_images(self) -> None:
        source = INDEX_HTML.read_text(encoding="utf-8")
        html = _parse(INDEX_HTML)

        self.assertIn("activeUsersPresence", html.ids)
        self.assertIn("activeUsersList", html.ids)
        self.assertLess(
            source.index('id="activeUsersPresence"'),
            source.index('id="webImagesButton"'),
        )
        self.assertNotIn('activeUsersPresence" type="button', source)

    def test_github_status_button_and_modal_exist(self) -> None:
        source = INDEX_HTML.read_text(encoding="utf-8")
        html = _parse(INDEX_HTML)
        css = (
            ROOT / "picorgftp_sql" / "web" / "static" / "app.css"
        ).read_text(encoding="utf-8")

        self.assertIn("githubStatusButton", html.button_ids)
        self.assertIn("githubStatusModal", html.ids)
        self.assertIn("githubStatusOutput", html.ids)
        self.assertIn("githubStatusCheckedAt", html.ids)
        self.assertTrue(html.has_tag("button", id="githubStatusButton", type="button"))
        self.assertLess(
            source.index('id="githubStatusButton"'),
            source.index("<strong>PicOrgFTP-SQL Web</strong>"),
        )
        self.assertIn('viewBox="0 0 16 16" width="24" height="24"', source)
        self.assertIn(".github-status-button", css)
        self.assertRegex(css, r"\.github-status-button\s*\{[^}]*width:\s*42px;")
        self.assertRegex(css, r"\.github-status-button\s*\{[^}]*height:\s*42px;")
        self.assertIn(".github-status-button.update-available", css)
        self.assertIn("@keyframes github-status-pulse", css)

    def test_app_js_renders_active_user_presence(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        css = (
            ROOT / "picorgftp_sql" / "web" / "static" / "app.css"
        ).read_text(encoding="utf-8")

        self.assertIn("function renderActiveUsersPresence", source)
        self.assertIn("function refreshActiveUsersPresence", source)
        self.assertIn("/api/server/presence", source)
        self.assertIn("show_active_web_users", source)
        self.assertIn("Pokaz aktywnych uzytkownikow", source)
        self.assertIn(".active-users-presence", css)
        self.assertIn(".presence-user-label", css)
        self.assertIn(".presence-more-button", css)

    def test_app_js_loads_and_renders_github_status(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn('const githubStatusButton = document.querySelector("#githubStatusButton")', source)
        self.assertIn('const githubStatusModal = document.querySelector("#githubStatusModal")', source)
        self.assertIn('const githubStatusOutput = document.querySelector("#githubStatusOutput")', source)
        self.assertIn("function renderGithubStatus", source)
        self.assertIn("async function refreshGithubStatus", source)
        self.assertIn('requestJson("/api/github/repository"', source)
        self.assertIn('githubStatusButton.classList.toggle("update-available"', source)
        self.assertIn('document.querySelectorAll("[data-close-github-status]")', source)

    def test_app_js_marks_presence_client_and_leaves_on_pagehide(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn('CLIENT_ID_HEADER = "X-PicOrg-Client-Id"', source)
        self.assertIn("function activePresenceClientId", source)
        self.assertIn("function notifyActiveUsersPresenceLeave", source)
        self.assertIn("/api/server/presence/leave", source)
        self.assertIn('window.addEventListener("pagehide"', source)
        self.assertIn("keepalive: true", source)

    def test_web_images_modal_contains_url_input_filters_and_actions(self) -> None:
        html = _parse(INDEX_HTML)

        self.assertIn("webImagesModal", html.ids)
        self.assertIn("webImageUrl", html.ids)
        self.assertIn("webImageScanMode", html.ids)
        self.assertIn("scanWebImagesButton", html.button_ids)
        self.assertIn("webImageMinWidth", html.ids)
        self.assertIn("webImageMinHeight", html.ids)
        self.assertIn("webImageMinKb", html.ids)
        self.assertIn("webImageUrlFilter", html.ids)
        self.assertIn("webImageHideThumbnails", html.ids)
        self.assertIn("browserExtensionDownload", html.ids)
        self.assertIn("browserExtensionDownload", html.button_ids)
        self.assertIn("browserExtensionHelpButton", html.button_ids)
        self.assertIn("browserExtensionReceiveButton", html.button_ids)
        self.assertIn("browserExtensionHelp", html.ids)
        self.assertIn("webImagesClearDataButton", html.button_ids)
        self.assertIn("webImagesOutput", html.ids)
        self.assertTrue(html.has_tag("button", id="webImagesButton", type="button"))

    def test_modal_navigation_targets_have_matching_panels(self) -> None:
        html = _parse(INDEX_HTML)

        missing_targets = {
            name
            for name in html.data_modals
            if f"{name}View" not in html.ids and f"{name}Modal" not in html.ids
        }

        self.assertEqual(missing_targets, set())
        self.assertIn("modal-view", html.classes)
        self.assertIn("manager-panel", html.classes)

    def test_settings_tabs_include_security_section(self) -> None:
        html = _parse(INDEX_HTML)

        self.assertIn("settingsView", html.ids)
        self.assertTrue(
            html.has_tag(
                "button",
                type="button",
                **{"data-settings-tab": "security"},
            )
        )

    def test_settings_include_pimcore_tab(self) -> None:
        html = _parse(INDEX_HTML)

        self.assertTrue(html.has_tag("button", **{"data-settings-tab": "pimcore"}))

    def test_pimcore_test_and_history_modals_exist(self) -> None:
        html = _parse(INDEX_HTML)

        self.assertIn("pimcoreTestModal", html.ids)
        self.assertIn("pimcoreHistoryModal", html.ids)
        self.assertIn("pimcoreTestForm", html.ids)
        self.assertIn("pimcoreLiveLog", html.ids)
        self.assertIn("pimcoreTestRegenerateButton", html.button_ids)

    def test_pimcore_setup_wizard_has_four_steps_and_admin_controls(self) -> None:
        html = _parse(INDEX_HTML)
        for element_id in (
            "pimcoreSetupModal",
            "pimcoreSetupForm",
            "pimcoreSetupStepTitle",
            "pimcoreSetupBody",
            "pimcoreSetupBackButton",
            "pimcoreSetupNextButton",
            "pimcoreSetupCancelButton",
            "pimcoreSetupStatus",
        ):
            self.assertIn(element_id, html.ids)

    def test_runtime_pimcore_prompt_and_create_modals_exist(self) -> None:
        html = _parse(INDEX_HTML)

        self.assertIn("pimcoreMissingModal", html.ids)
        self.assertIn("pimcoreCreateModal", html.ids)
        self.assertIn("pimcoreCreateForm", html.ids)
        self.assertIn("pimcoreMissingCreateButton", html.ids)
        self.assertIn("pimcoreCreateRecalculateAllButton", html.ids)
        self.assertIn("pimcoreEditButton", html.ids)

    def test_runtime_pimcore_edit_modal_exists(self) -> None:
        html = _parse(INDEX_HTML)
        for element_id in (
            "pimcoreEditButton",
            "pimcoreEditModal",
            "pimcoreEditForm",
            "pimcoreEditSubmitButton",
            "pimcoreEditRecalculateAllButton",
            "pimcoreEditCancelButton",
            "pimcoreEditStatus",
        ):
            self.assertIn(element_id, html.ids)

    def test_pimcore_template_builder_modal_has_preview_and_translation_controls(self) -> None:
        html = _parse(INDEX_HTML)

        for element_id in (
            "pimcoreTemplateModal",
            "pimcoreTemplateText",
            "pimcoreTemplateSources",
            "pimcoreTemplatePreview",
            "pimcoreTemplateTranslate",
            "pimcoreTemplateLanguage",
            "pimcoreTemplatePreviewButton",
            "pimcoreTemplateSaveButton",
        ):
            self.assertIn(element_id, html.ids)

    def test_app_js_persists_and_previews_pimcore_mapping_templates(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn("function openPimcoreTemplateBuilder", source)
        self.assertIn("function previewPimcoreTemplate", source)
        self.assertIn("function insertPimcoreTemplateFunction", source)
        self.assertIn("/api/settings/pimcore/template-preview", source)
        self.assertIn("row.dataset.valueTemplate", source)
        self.assertIn("row.dataset.translate", source)
        self.assertIn("row.dataset.targetLanguage", source)
        self.assertIn('["Nazwa", "PRODUCT:name"]', source)
        self.assertIn('insertPimcoreTemplateText(`{${source}|keep}`)', source)
        self.assertIn("PIMCORE_TEMPLATE_MATH_TOKENS", source)
        self.assertIn('["Mnoz", "*"]', source)
        self.assertIn('["Oblicz", "oblicz()"]', source)
        self.assertIn("insertPimcoreTemplateText(token)", source)

    def test_runtime_pimcore_forms_load_samples_and_recalculate_saved_templates(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn("function populatePimcoreRuntimeForm", source)
        self.assertIn("async function loadPimcoreTestSample", source)
        self.assertIn("/api/settings/pimcore/test-sample", source)
        self.assertIn("/api/pimcore/render-templates", source)
        self.assertIn("Przelicz pole", source)
        self.assertIn("pimcore-recalculate-field", source)
        self.assertIn("async function recalculateAllPimcoreEditFields", source)
        self.assertIn("pimcoreEditRecalculateAllButton", source)

    def test_runtime_pimcore_create_modal_recalculates_and_reopens_for_missing_product(
        self,
    ) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        status_start = source.index("async function checkPimcoreProductStatus")
        status_end = source.index("function openPimcoreCreateModal", status_start)
        status_body = source[status_start:status_end]
        edit_start = source.index("async function openPimcoreEditModal")
        edit_end = source.index("function closePimcoreEditModal", edit_start)
        edit_body = source[edit_start:edit_end]

        self.assertIn("const pimcoreCreateRecalculateAllButton", source)
        self.assertIn("async function recalculateAllPimcoreCreateFields", source)
        self.assertIn(
            "pimcoreCreateRecalculateAllButton?.addEventListener("
            '"click", recalculateAllPimcoreCreateFields);',
            source,
        )
        self.assertIn(
            "pimcoreEditButton.disabled = state.pimcoreCreateSchema.length === 0;",
            status_body,
        )
        self.assertIn(
            "openPimcoreCreateModal(state.pimcoreMissingEan || currentEan);",
            edit_body,
        )

    def test_sql_profile_ui_and_pimcore_sql_mapping_controls_exist(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        css = (ROOT / "picorgftp_sql" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("function additionalSqlProfiles", source)
        self.assertIn('profile.usage === "pimcore_sql"', source)
        self.assertIn("Profile dodatkowe SQL", source)
        self.assertIn("Domyslne polaczenie dla zdjec i slotow", source)
        self.assertNotIn('settingsFieldGroup("MS SQL"', source)
        self.assertNotIn('settingsFieldGroup("MySQL"', source)
        self.assertNotIn("Profil domyslny jest zawsze uzywany przez Sloty", source)
        self.assertIn("function sqlProfileRow", source)
        self.assertIn("/api/settings/sql-profiles/", source)
        self.assertIn("mapping_sql_query", source)
        self.assertIn("mapping_sql_profile_id", source)
        self.assertIn("pimcore-runtime-calculated", source)
        self.assertIn("pimcore-runtime-different", css)
        self.assertIn("pimcore-template-sql-controls", source)
        self.assertIn("insertPimcoreTemplateSqlToken", source)
        self.assertNotIn("row.append(use, label, target, required, template, remove, pimcoreSqlMappingControls", source)
        self.assertNotIn("row.appendChild(pimcoreSqlMappingControls", source)
        self.assertIn(".sql-profile-card", css)
        self.assertIn(".sql-profile-card + .sql-profile-card", css)
        self.assertIn("20260706-sql-profiles", html)

    def test_pimcore_mapping_layout_controls_and_runtime_sections_exist(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        css = (ROOT / "picorgftp_sql" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("mapping_layout_group", source)
        self.assertIn("mapping_layout_order", source)
        self.assertNotIn("mapping_layout_width", source)
        self.assertIn("layout_group:", source)
        self.assertIn("layout_order:", source)
        self.assertNotIn("layout_width:", source)
        self.assertNotIn("pimcoreRuntimeFieldWidth", source)
        self.assertIn("function pimcoreRuntimeLayoutGroups", source)
        self.assertIn("pimcore-runtime-section", source)
        self.assertIn("pimcore-runtime-row", source)
        self.assertIn("--pimcore-runtime-columns", source)
        self.assertIn(".pimcore-runtime-section", css)
        self.assertIn(".pimcore-runtime-row", css)
        self.assertIn("border-left: 4px solid var(--accent)", css)

    def test_pimcore_runtime_difference_ui_preserves_manual_values(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn("function updatePimcoreRuntimeCalculatedState", source)
        self.assertIn("function updatePimcoreRuntimeFieldChangeState", source)
        self.assertIn("dataset.originalValue", source)
        self.assertIn("dataset.calculatedValue", source)
        self.assertIn("pimcore-runtime-different", source)
        self.assertIn("Zastosuj wyliczone", source)
        self.assertIn('mode: form.dataset.pimcoreMode || "create"', source)
        self.assertIn("if (!input.value)", source)

    def test_pimcore_runtime_difference_actions_are_compact_icon_buttons(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        css = (ROOT / "picorgftp_sql" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )

        self.assertIn('className = "pimcore-runtime-actions"', source)
        self.assertIn('className = "ghost-button pimcore-runtime-action-button', source)
        self.assertIn('textContent = "\\u2713"', source)
        self.assertIn('textContent = "\\u00d7"', source)
        self.assertIn('title = "Zastosuj wyliczone"', source)
        self.assertIn('title = "Cofnij zmiany"', source)
        self.assertIn("setAttribute(\"aria-label\"", source)
        self.assertIn(".pimcore-runtime-actions", css)
        self.assertIn(".pimcore-runtime-action-button", css)
        runtime_state_start = css.index(".pimcore-runtime-calculated,")
        runtime_state_end = css.index(".pimcore-runtime-calculated {", runtime_state_start)
        runtime_state_block = css[runtime_state_start:runtime_state_end]

        self.assertIn("display: flex;", runtime_state_block)
        self.assertIn("flex-wrap: wrap;", runtime_state_block)
        self.assertNotIn(
            "grid-template-columns: minmax(0, 1fr) auto auto;",
            runtime_state_block,
        )
        actions_block = css[
            css.index(".pimcore-runtime-actions {") : css.index(
                ".pimcore-runtime-action-button {"
            )
        ]
        self.assertIn("display: flex;", actions_block)
        self.assertIn("flex-wrap: nowrap;", actions_block)
        action_button_block = css[
            css.index(".pimcore-runtime-action-button {") : css.index(
                ".pimcore-runtime-apply-action {"
            )
        ]
        self.assertIn("width: 28px;", action_button_block)
        self.assertIn("min-width: 28px;", action_button_block)
        self.assertIn("padding: 0;", action_button_block)

    def test_pimcore_edit_recalculation_blocks_submit_until_resolved(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        css = (ROOT / "picorgftp_sql" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("function hasBlockingPimcoreRuntimeDifferences", source)
        self.assertIn("function focusFirstPimcoreRuntimeDifference", source)
        self.assertIn("function updatePimcoreEditSubmitState", source)
        self.assertIn("pimcore-runtime-conflict", source)
        self.assertIn("pimcore-runtime-pulse", source)
        self.assertIn("Cofnij zmiany", source)
        self.assertIn("Oryginalnie:", source)
        self.assertIn("pimcore-runtime-original", source)
        self.assertIn("pimcore-runtime-conflict", css)
        self.assertIn("body[data-theme=\"dark\"] .pimcore-runtime-conflict input", css)
        self.assertIn("@keyframes pimcore-runtime-pulse", css)

    def test_pimcore_runtime_forwards_latest_render_integration_context(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn("pimcoreCreateIntegrations", source)
        self.assertIn("pimcoreEditIntegrations", source)
        self.assertIn("result.integrations || { sql_profiles: [] }", source)
        self.assertNotIn("integration_results: state.pimcoreCreateIntegrations", source)
        self.assertNotIn("integration_results: state.pimcoreEditIntegrations", source)
        self.assertIn(
            "integration_context_id: state.pimcoreCreateIntegrationContextId",
            source,
        )
        self.assertIn(
            "integration_context_id: state.pimcoreEditIntegrationContextId",
            source,
        )
        self.assertIn("result.integration_context_id", source)
        self.assertIn("object_id:", source)

    def test_pimcore_history_has_submission_export_actions(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("exportPimcoreSubmissions", source)
        self.assertIn("/api/settings/pimcore/submissions/export", source)
        self.assertIn("Eksport CSV", html)
        self.assertIn("pimcoreHistoryExportCsvButton", html)
        self.assertIn("Eksport XLSX", html)
        self.assertIn("pimcoreHistoryExportXlsxButton", html)

    def test_pimcore_settings_has_modal_submission_export_action(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("function pimcoreSettingsExportButton", source)
        self.assertIn("function openPimcoreExportModal", source)
        self.assertIn("function closePimcoreExportModal", source)
        self.assertIn("Eksport danych Pimcore", source)
        self.assertIn("pimcoreExportModal", html)
        self.assertIn("pimcoreExportCsvButton", html)
        self.assertIn("pimcoreExportXlsxButton", html)
        self.assertIn('exportPimcoreSubmissions("csv", { includeFilters: false })', source)
        self.assertIn('exportPimcoreSubmissions("xlsx", { includeFilters: false })', source)
        self.assertNotIn("promptPimcoreSubmissionExportFormat", source)
        self.assertNotIn("Format eksportu danych Pimcore: CSV lub XLSX", source)
        self.assertIn("pimcoreSettingsExportButton()", source)

    def test_pimcore_edit_modal_opens_before_remote_object_load(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        start = source.index("async function openPimcoreEditModal")
        end = source.index("function closePimcoreEditModal", start)
        body = source[start:end]

        self.assertIn("++state.pimcoreEditRequestId", body)
        self.assertIn("Number(state.pimcoreExistingObject?.id || 0)", body)
        self.assertIn("Nie mozna edytowac produktu Pimcore bez poprawnego ID.", body)
        self.assertLess(
            body.index('pimcoreEditModal.classList.add("active")'),
            body.index("await requestJson"),
        )

    def test_pimcore_edit_click_resolves_current_ean_before_giving_up(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        start = source.index("async function openPimcoreEditModal")
        end = source.index("function closePimcoreEditModal", start)
        body = source[start:end]

        self.assertIn("let objectId = Number(state.pimcoreExistingObject?.id || 0);", body)
        self.assertIn("const currentEan = productForm.elements.ean.value.trim();", body)
        self.assertIn("await checkPimcoreProductStatus(currentEan);", body)
        self.assertIn("objectId = Number(state.pimcoreExistingObject?.id || 0);", body)

    def test_pimcore_status_enables_edit_only_for_positive_object_id(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        start = source.index("async function checkPimcoreProductStatus")
        end = source.index("function openPimcoreCreateModal", start)
        body = source[start:end]

        self.assertIn("Number(payload.object?.id || 0)", body)
        self.assertIn("Pimcore zwrocil produkt bez poprawnego ID", body)
        self.assertIn("pimcoreEditButton.disabled = false", body)

    def test_pimcore_ean_input_clears_cached_lookup_before_rechecking(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        start = source.index("function handlePimcoreEanInput")
        end = source.index("function schedulePimcoreStatusLookup", start)
        body = source[start:end]

        self.assertIn('state.pimcoreLastCheckedEan = "";', body)
        self.assertIn("schedulePimcoreStatusLookup();", body)

    def test_pimcore_metadata_refresh_replaces_current_settings_form(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        start = source.index("async function refreshCompactPimcoreMetadata")
        end = source.index("function pimcoreCsvImportButton", start)
        body = source[start:end]

        self.assertIn("renderSettings();", body)
        self.assertNotIn("renderSettingsPimcore();", body)

    def test_loading_existing_entry_triggers_pimcore_status_lookup(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        start = source.index("function fillForm")
        end = source.index("async function refreshData", start)
        body = source[start:end]

        self.assertIn("productForm.elements.ean.value = entry.ean || \"\";", body)
        self.assertIn("handlePimcoreEanInput();", body)

    def test_pimcore_ui_uses_example_placeholder_without_private_default(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        html_source = INDEX_HTML.read_text(encoding="utf-8")
        css = (ROOT / "picorgftp_sql" / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("http://10.10.0.5", source)
        self.assertIn("http://twoj-adres-pimcore.example", source)
        self.assertIn("20260706-sql-profiles", html_source)
        self.assertIn("flex-wrap: wrap", css[css.index(".lookup-actions"):])
        self.assertNotIn(".lookup-actions #pimcoreEditButton {\n  min-width", css)

    def test_slot_template_keeps_preview_and_file_input_controls(self) -> None:
        html = _parse(INDEX_HTML)

        self.assertIn("slotTemplate", html.ids)
        self.assertIn("slot-card", html.classes)
        self.assertIn("slot-preview", html.classes)
        self.assertIn("slot-empty", html.classes)
        self.assertTrue(
            html.has_tag(
                "input",
                type="file",
                accept="image/*,.pdf,.eps,.psd,.ai,.tif,.tiff",
            )
        )

    def test_app_js_treats_additional_image_formats_as_uploads(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        for extension in (
            ".jfif",
            ".jpe",
            ".peg",
            ".apng",
            ".dib",
            ".avifs",
            ".heic",
            ".heif",
            ".hif",
            ".jp2",
            ".j2k",
            ".jpc",
            ".jpx",
            ".ico",
            ".cur",
            ".tga",
            ".ppm",
            ".pgm",
            ".pbm",
            ".pnm",
            ".pcx",
        ):
            self.assertIn(f'"{extension}"', source)
        for extension in ("jpe", "peg", "jfif"):
            self.assertIn(f'sourceExt === "{extension}"', source)
        self.assertIn('sourceExt === "apng"', source)

    def test_app_js_swaps_two_occupied_slots_on_slot_drop(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn("const target = getSlotAssignment(targetPrefix);", source)
        self.assertIn("Zamieniono slot", source)
        self.assertLess(
            source.index("Zamieniono slot"),
            source.index("Przeniesiono slot"),
        )

    def test_app_js_displays_web_image_scan_errors_inside_modal(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn("renderWebImagesError", source)
        self.assertIn("Cloudflare/challenge 403", source)
        self.assertIn("Importer nie dostaje wtedy HTML-a produktu", source)

    def test_app_js_receives_browser_extension_imports(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn("/api/browser-extension/imports", source)
        self.assertIn("/api/browser-extension/download", source)
        self.assertIn("receiveBrowserExtensionImages", source)
        self.assertIn("downloadBrowserExtension", source)
        self.assertIn("clearLoadedWebImages", source)
        self.assertIn("parseWebImageUrlFilter", source)
        self.assertIn("!?<[^>]+>", source)
        self.assertIn("existingByUrl", source)
        self.assertIn("state.webImages.push(image)", source)
        self.assertIn("Odbierz z rozszerzenia", source)

    def test_app_js_uses_cached_preview_for_browser_extension_imports(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn("preview_url: cache.thumb_url || cache.url || item?.source_url || \"\"", source)
        self.assertIn("img.src = image.preview_url || image.thumb_url || image.url;", source)

    def test_login_page_keeps_accessible_login_form(self) -> None:
        html = _parse(LOGIN_HTML)

        self.assertIn("loginForm", html.ids)
        self.assertIn("loginMessage", html.ids)
        self.assertIn("username", html.input_names)
        self.assertIn("password", html.input_names)
        self.assertTrue(html.has_tag("button", type="submit"))
        self.assertEqual(html.duplicate_ids, set())
        login_source = LOGIN_HTML.read_text(encoding="utf-8")
        self.assertNotIn('value="admin"', login_source)

    def test_login_js_remembers_last_successful_username(self) -> None:
        source = (ROOT / "picorgftp_sql" / "web" / "static" / "login.js").read_text(encoding="utf-8")

        self.assertIn('LAST_LOGIN_USERNAME_KEY = "picorg-last-login-username"', source)
        self.assertIn("localStorage.getItem(LAST_LOGIN_USERNAME_KEY)", source)
        self.assertIn("localStorage.setItem(LAST_LOGIN_USERNAME_KEY, username)", source)
        self.assertLess(
            source.index("localStorage.setItem(LAST_LOGIN_USERNAME_KEY, username)"),
            source.index('window.location.href = "/"'),
        )

    def test_backup_history_and_diff_modals_exist(self) -> None:
        html = _parse(INDEX_HTML)

        self.assertIn("backupHistoryModal", html.ids)
        self.assertIn("backupHistoryOutput", html.ids)
        self.assertIn("backupDiffModal", html.ids)
        self.assertIn("backupDiffOutput", html.ids)

    def test_backup_modals_render_above_settings_modal(self) -> None:
        html = _parse(INDEX_HTML)
        modal_classes = {
            attrs.get("id"): set(attrs.get("class", "").split())
            for tag, attrs in html.tags
            if tag == "div" and attrs.get("id") in {"backupHistoryModal", "backupDiffModal"}
        }

        self.assertIn("nested-modal", modal_classes["backupHistoryModal"])
        self.assertIn("nested-modal", modal_classes["backupDiffModal"])

    def test_history_changes_modal_is_safe_detailed_and_responsive(self) -> None:
        html = _parse(INDEX_HTML)
        html_source = INDEX_HTML.read_text(encoding="utf-8")
        js_source = APP_JS.read_text(encoding="utf-8")
        css_source = (
            ROOT / "picorgftp_sql" / "web" / "static" / "app.css"
        ).read_text(encoding="utf-8")

        for element_id in (
            "historyChangesModal",
            "historyChangesTitle",
            "historyChangesOutput",
        ):
            self.assertIn(element_id, html.ids)
        self.assertIn('class="modal-view nested-modal"', html_source)
        self.assertIn('role="dialog"', html_source)
        self.assertIn('aria-modal="true"', html_source)
        self.assertIn('aria-labelledby="historyChangesTitle"', html_source)
        self.assertIn('tabindex="-1"', html_source)
        self.assertIn("data-close-history-changes", html_source)

        renderer_start = js_source.index("function renderHistoryChanges")
        renderer_end = js_source.index("function renderHistoryDetails", renderer_start)
        renderer = js_source[renderer_start:renderer_end]
        self.assertNotIn("innerHTML", renderer)
        self.assertNotIn("history-file-change-${operation}", renderer)
        for value in (
            "field.before",
            "field.after",
            "file.before_name",
            "file.after_name",
            "file.before_size_bytes",
            "file.after_size_bytes",
            "file.elapsed_ms",
            "file.evidence",
            "historyChangeJobId(details, changeSet)",
        ):
            self.assertIn(value, renderer)
        self.assertIn("textContent", renderer)
        for evidence_row in (
            'historyChangeRow("Lokalnie"',
            'historyChangeRow("FTP"',
            'historyChangeRow("SQL"',
            'historyChangeRow("ID obiektu"',
            'historyChangeRow("Sciezka obiektu"',
            'historyChangeRow("Czas calkowity"',
            'historyChangeRow("Wysylka"',
            'historyChangeRow("Weryfikacja"',
        ):
            self.assertIn(evidence_row, renderer)
        self.assertIn("historyChangesCloseButton?.focus()", js_source)
        self.assertIn(
            "changesButton.disabled = !hasChangeSet && !hasLegacyDetails",
            js_source,
        )
        self.assertIn("historyChangesReturnFocus.focus()", js_source)
        self.assertIn("history-change-before-after", css_source)
        self.assertIn("history-file-change-added", css_source)
        self.assertIn("history-file-change-deleted", css_source)
        self.assertIn("history-file-change-replaced", css_source)
        self.assertIn("@media (max-width: 700px)", css_source)

    def test_history_changes_formats_structured_values_and_unknown_durations(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        css_source = (
            ROOT / "picorgftp_sql" / "web" / "static" / "app.css"
        ).read_text(encoding="utf-8")
        self.assertIn("function formatHistoryDuration", source)
        value_start = source.index("function historyChangeValue")
        value_end = source.index("function formatBytes", value_start)
        value_formatter = source[value_start:value_end]
        duration_start = source.index("function formatHistoryDuration")
        duration_end = source.index("function historyChangeRow", duration_start)
        duration_formatter = source[duration_start:duration_end]

        self.assertIn('typeof value === "object"', value_formatter)
        self.assertIn("JSON.stringify", value_formatter)
        self.assertIn("Object.keys(nested).sort()", value_formatter)
        self.assertIn(
            'return serialized === undefined ? "Brak danych" : serialized',
            value_formatter,
        )
        self.assertIn('return "Brak danych"', duration_formatter)
        self.assertIn('return `${Math.max(0, Number(value))} ms`', duration_formatter)
        self.assertIn("formatHistoryDuration(file.elapsed_ms)", source)
        self.assertNotIn('`${historyChangeValue(file.elapsed_ms)} ms`', source)
        style_start = css_source.index(".history-change-row span,")
        style_end = css_source.index("}", style_start)
        self.assertIn("white-space: pre-wrap", css_source[style_start:style_end])

    def test_history_changes_resolves_pimcore_operation_identifier(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        self.assertIn("function historyChangeJobId", source)
        resolver_start = source.index("function historyChangeJobId")
        resolver_end = source.index("function historyFileOperationLabel", resolver_start)
        resolver = source[resolver_start:resolver_end]

        self.assertIn("details.job_id", resolver)
        self.assertIn("changeSet.job_id", resolver)
        self.assertIn("details.pimcore_operation?.operation_id", resolver)
        self.assertIn("changeSet.pimcore?.operation_id", resolver)
        self.assertIn("historyChangeJobId(details, changeSet)", source)

    def test_history_changes_modal_isolates_background_and_traps_focus(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn("historyChangesBackgroundState", source)
        self.assertIn('"#historyView.active, #historyDetailModal.active, #historyTimingModal.active"', source)
        self.assertIn('modal.getAttribute("inert")', source)
        self.assertIn('modal.setAttribute("inert", "")', source)
        self.assertIn('modal.setAttribute("aria-hidden", "true")', source)
        self.assertIn('modal.removeAttribute("inert")', source)
        self.assertIn('modal.removeAttribute("aria-hidden")', source)
        self.assertIn('event.key !== "Tab"', source)
        self.assertIn("event.shiftKey", source)
        self.assertIn('event.key === "Escape"', source)
        self.assertIn("closeHistoryChangesModal()", source)
        self.assertIn('historyChangesModal.classList.contains("active")', source)
        self.assertIn("if (historyChangesBackgroundState.length) return", source)
        self.assertIn("historyChangesReturnFocus.focus()", source)


if __name__ == "__main__":
    unittest.main()
