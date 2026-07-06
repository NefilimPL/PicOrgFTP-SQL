"""Tests for shared configurable product-field behavior."""

from __future__ import annotations

from picorgftp_sql.product_fields import (
    PRODUCT_FIELD_KEYS,
    effective_product_values,
    missing_required_fields,
    normalize_product_fields,
)


def test_defaults_preserve_current_form_contract() -> None:
    settings = normalize_product_fields(None)

    assert tuple(settings) == PRODUCT_FIELD_KEYS
    assert all(item["enabled"] for item in settings.values())
    assert [key for key, item in settings.items() if item["required"]] == [
        "name",
        "type",
        "model",
        "color1",
    ]
    assert [item["order"] for item in settings.values()] == list(
        range(len(PRODUCT_FIELD_KEYS))
    )
    assert all(item["group"] == "" for item in settings.values())


def test_normalization_migrates_legacy_labels_and_rejects_unknown_fields() -> None:
    settings = normalize_product_fields(
        {
            "name": {"label": " Produkt*: ", "enabled": "yes", "required": 1},
            "color1": {"enabled": False, "required": True},
            "unknown": {"enabled": True},
        },
        legacy_color_labels={"color1": "Korpus", "color2": " Front: "},
    )

    assert settings["name"] == {
        "label": "Produkt",
        "enabled": True,
        "required": True,
        "group": "",
        "order": 0,
    }
    assert settings["color1"] == {
        "label": "Korpus",
        "enabled": False,
        "required": False,
        "group": "",
        "order": 3,
    }
    assert settings["color2"]["label"] == "Front"
    assert "unknown" not in settings


def test_normalization_keeps_group_and_order() -> None:
    settings = normalize_product_fields(
        {
            "ean": {"group": " Identyfikacja*: ", "order": "1"},
            "color2": {"group": "Kolory", "order": 4},
            "model": {"order": "bledna"},
        }
    )

    assert settings["ean"]["group"] == "Identyfikacja"
    assert settings["ean"]["order"] == 1
    assert settings["color2"]["group"] == "Kolory"
    assert settings["color2"]["order"] == 4
    assert settings["model"]["order"] == 2


def test_explicit_empty_label_takes_precedence_over_legacy_label() -> None:
    settings = normalize_product_fields(
        {"color1": {"label": ""}},
        legacy_color_labels={"color1": "Korpus"},
    )

    assert settings["color1"]["label"] == ""


def test_disabled_values_are_cleared_and_required_labels_are_effective() -> None:
    settings = normalize_product_fields(
        {
            "name": {"label": "Kolekcja", "enabled": True, "required": True},
            "type": {"enabled": False, "required": True},
            "ean": {"enabled": False},
        }
    )

    values = effective_product_values(
        {
            "name": "",
            "type_name": "KOMODA",
            "model": "MA03",
            "color1": "BIALY",
            "ean": "5901234567890",
        },
        settings,
    )

    assert values["type_name"] == ""
    assert values["ean"] == ""
    assert missing_required_fields(values, settings) == [("name", "Kolekcja")]
