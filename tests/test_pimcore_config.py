from picorgftp_sql.pimcore_config import (
    PIMCORE_API_KEY,
    PIMCORE_SETTINGS_KEY,
    field_mapping_issues,
    infer_field_mapping,
    normalize_pimcore_settings,
    parse_mapping_value,
)


def test_normalize_pimcore_settings_cleans_mappings_and_bounds_timeout():
    result = normalize_pimcore_settings(
        {
            "enabled": 1,
            "base_url": " http://10.10.0.5/ ",
            PIMCORE_API_KEY: "secret-key",
            "class_name": " Product ",
            "parent_id": "123",
            "timeout_seconds": 999,
            "existence_fields": ["EAN", "EAN", "Bad field", "Towar_powiazany_z_SKU"],
            "field_mappings": [
                {
                    "source": "EAN",
                    "label": "Kod EAN",
                    "pimcore_field": "EAN",
                    "type": "input",
                    "required": True,
                    "parser": "text",
                },
                {"source": "", "pimcore_field": "ignored"},
            ],
        }
    )

    assert result["base_url"] == "http://10.10.0.5"
    assert result["timeout_seconds"] == 120
    assert result["existence_fields"] == ["EAN"]
    assert result["field_mappings"] == [
        {
            "source": "EAN",
            "label": "Kod EAN",
            "pimcore_field": "EAN",
            "type": "input",
            "language": None,
            "required": True,
            "default": "",
            "parser": "text",
            "value_template": "",
            "translate": False,
            "target_language": None,
        }
    ]


def test_mapping_parsers_accept_polish_csv_values():
    assert parse_mapping_value(" 62,5 ", "decimal_comma") == 62.5
    assert parse_mapping_value("12", "integer") == 12
    assert parse_mapping_value("tak", "boolean") is True
    assert parse_mapping_value("nie", "boolean") is False
    assert parse_mapping_value("  ", "empty_to_null") is None


def test_default_section_keeps_integration_disabled():
    result = normalize_pimcore_settings(None)
    assert result[PIMCORE_API_KEY] == ""
    assert result["enabled"] is False
    assert result["base_url"] == ""
    assert result["class_name"] == ""
    assert PIMCORE_SETTINGS_KEY == "pimcore"


def test_guided_setup_defaults_hide_technical_choices():
    result = normalize_pimcore_settings({})

    assert result["setup_complete"] is False
    assert result["class_id"] == ""
    assert result["class_name"] == ""
    assert result["parent_path"] == ""
    assert result["object_key_template"] == "{EAN}"
    assert result["timeout_seconds"] == 30


def test_complete_legacy_configuration_infers_setup_complete():
    result = normalize_pimcore_settings(
        {
            "base_url": "http://10.10.0.5",
            "api_key": "secret",
            "class_name": "product",
            "parent_id": "6626",
            "field_mappings": [
                {
                    "source": "EAN",
                    "pimcore_field": "EAN",
                    "type": "input",
                    "required": True,
                    "parser": "text",
                }
            ],
        }
    )

    assert result["setup_complete"] is True
    assert result["existence_fields"] == ["EAN"]
    assert result["object_key_template"] == "{EAN}"


def test_explicit_disabled_complete_setup_stays_complete():
    result = normalize_pimcore_settings(
        {
            "setup_complete": True,
            "enabled": False,
            "class_name": "product",
            "parent_id": "6626",
            "field_mappings": [],
        }
    )

    assert result["setup_complete"] is True
    assert result["enabled"] is False


def test_infer_field_mapping_uses_class_type_and_locks_ean():
    ean = infer_field_mapping(
        source="EAN",
        label="EAN",
        pimcore_field="eanCode",
        field_type="input",
        required=False,
    )
    weight = infer_field_mapping(
        source="TOTAL WEIGHT",
        label="Waga calkowita",
        pimcore_field="totalWeight",
        field_type="numeric",
        required=False,
    )

    assert ean == {
        "source": "EAN",
        "label": "EAN",
        "pimcore_field": "eanCode",
        "type": "input",
        "language": None,
        "required": True,
        "default": "",
        "parser": "text",
        "value_template": "",
        "translate": False,
        "target_language": None,
    }
    assert weight["parser"] == "decimal_comma"


def test_field_mapping_issues_report_exact_row_and_problem():
    issues = field_mapping_issues(
        [
            {"source": "", "pimcore_field": "EAN", "type": "input", "parser": "text"},
            {
                "source": "WEIGHT",
                "pimcore_field": "TOTAL_WEIGHT",
                "type": "input",
                "parser": "decimal_comma",
            },
            {
                "source": "WEIGHT",
                "pimcore_field": "OTHER_WEIGHT",
                "type": "numeric",
                "parser": "decimal_comma",
            },
        ]
    )
    assert issues == [
        "Mapowanie 1: brak kolumny zrodlowej.",
        "Mapowanie 2: parser decimal_comma nie pasuje do typu input.",
        "Mapowanie 3: zduplikowana kolumna zrodlowa WEIGHT.",
    ]


def test_mapping_template_options_round_trip():
    result = normalize_pimcore_settings(
        {
            "field_mappings": [
                {
                    "source": "TITLE",
                    "label": "Tytul",
                    "pimcore_field": "title",
                    "type": "input",
                    "parser": "text",
                    "value_template": "{NAZWA} - {TYP}",
                    "translate": True,
                    "target_language": "en",
                }
            ]
        }
    )

    mapping = result["field_mappings"][0]
    assert mapping["value_template"] == "{NAZWA} - {TYP}"
    assert mapping["translate"] is True
    assert mapping["target_language"] == "en"


def test_invalid_template_is_reported_by_mapping_validation():
    issues = field_mapping_issues(
        [
            {
                "source": "TITLE",
                "pimcore_field": "title",
                "type": "input",
                "parser": "text",
                "value_template": "{NAZWA",
            }
        ]
    )

    assert issues == ["Mapowanie 1: Niezamkniety placeholder."]


def test_translation_requires_template_and_target_language():
    issues = field_mapping_issues(
        [
            {
                "source": "TITLE",
                "pimcore_field": "title",
                "type": "input",
                "parser": "text",
                "value_template": "{NAZWA}",
                "translate": True,
                "target_language": "",
            }
        ]
    )

    assert issues == ["Mapowanie 1: wybierz jezyk docelowy tlumaczenia."]


def test_field_mapping_issues_allow_same_target_for_different_languages():
    issues = field_mapping_issues(
        [
            {
                "source": "NAME_EN",
                "pimcore_field": "name",
                "type": "input",
                "parser": "text",
                "language": "en",
            },
            {
                "source": "NAME_PL",
                "pimcore_field": "name",
                "type": "input",
                "parser": "text",
                "language": "pl",
            },
        ]
    )

    assert issues == []


def test_incomplete_legacy_default_url_is_cleared():
    result = normalize_pimcore_settings({"base_url": "http://10.10.0.5"})

    assert result["base_url"] == ""


def test_configured_legacy_default_url_is_preserved():
    result = normalize_pimcore_settings(
        {
            "base_url": "http://10.10.0.5",
            "api_key": "secret",
            "class_name": "product",
            "parent_id": "6626",
        }
    )

    assert result["base_url"] == "http://10.10.0.5"
