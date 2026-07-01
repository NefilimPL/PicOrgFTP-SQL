from picorgftp_sql.pimcore_config import (
    PIMCORE_API_KEY,
    PIMCORE_SETTINGS_KEY,
    field_mapping_issues,
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
    assert result["existence_fields"] == ["EAN", "Towar_powiazany_z_SKU"]
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
    assert result["class_name"] == "Product"
    assert PIMCORE_SETTINGS_KEY == "pimcore"


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
