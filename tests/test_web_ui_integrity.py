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

    def test_web_images_modal_contains_url_input_filters_and_actions(self) -> None:
        html = _parse(INDEX_HTML)

        self.assertIn("webImagesModal", html.ids)
        self.assertIn("webImageUrl", html.ids)
        self.assertIn("scanWebImagesButton", html.button_ids)
        self.assertIn("webImageMinWidth", html.ids)
        self.assertIn("webImageMinHeight", html.ids)
        self.assertIn("webImageMinKb", html.ids)
        self.assertIn("webImageHideThumbnails", html.ids)
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

    def test_login_page_keeps_accessible_login_form(self) -> None:
        html = _parse(LOGIN_HTML)

        self.assertIn("loginForm", html.ids)
        self.assertIn("loginMessage", html.ids)
        self.assertIn("username", html.input_names)
        self.assertIn("password", html.input_names)
        self.assertTrue(html.has_tag("button", type="submit"))
        self.assertEqual(html.duplicate_ids, set())


if __name__ == "__main__":
    unittest.main()
