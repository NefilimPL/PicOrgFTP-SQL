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
        self.assertIn(".product-field-settings-list", css)
        self.assertIn(".product-field-settings-row", css)

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


if __name__ == "__main__":
    unittest.main()
