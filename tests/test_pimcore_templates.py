import pytest

from picorgftp_sql.pimcore_templates import (
    SourceDefinition,
    TemplateError,
    build_source_catalog,
    generate_test_values,
    render_mapping_templates,
    render_template,
)


def resolver(values):
    return lambda source: values.get(source.casefold(), "")


@pytest.mark.parametrize(
    ("template", "values", "expected"),
    [
        (
            "{NAZWA} - {TYP} {KOLOR 1}(/{KOLOR 2})",
            {"nazwa": "Vivo", "typ": "sideboard", "kolor 1": "white", "kolor 2": "black"},
            "VIVO - SIDEBOARD WHITE/BLACK",
        ),
        (
            "{Nazwa} - {Typ} {kolor 1}(/{kolor 2})",
            {"nazwa": "VIVO", "typ": "SIDEBOARD", "kolor 1": "WHITE", "kolor 2": "BLACK"},
            "Vivo - Sideboard white/black",
        ),
        ("{KOLOR 1}(/{KOLOR 2})", {"kolor 1": "white", "kolor 2": ""}, "WHITE"),
        (r"\({NAZWA|keep}\)", {"nazwa": "Vivo"}, "(Vivo)"),
        ('{MODEL|trim|replace:"_"," "|upper}', {"model": "  ab_cd  "}, "AB CD"),
        ('{BRAK|default:"wartosc"|title}', {}, "Wartosc"),
        ('{TekSt|substring:1,3}', {"tekst": "abcdefgh"}, "bcd"),
        ('{TekSt|truncate:4,"..."}', {"tekst": "abcdefgh"}, "abcd..."),
        ('{TekSt|normalize_spaces}', {"tekst": "  a   b  "}, "a b"),
        ('{TekSt|strip_diacritics}', {"tekst": "żółć"}, "zolc"),
        ('{TekSt|slug}', {"tekst": "  Żółty   stół  "}, "zolty-stol"),
        ('{LICZBA|number:2,","," "}', {"liczba": "1234,5"}, "1 234,50"),
    ],
)
def test_render_template_supports_literals_groups_case_and_functions(template, values, expected):
    assert render_template(template, resolver(values)) == expected


def test_render_template_evaluates_math_expression_with_pimcore_placeholders():
    template = (
        "{PIMCORE:parcel_1_weight|keep}+"
        "({PIMCORE:parcel_1_width|keep}/"
        "{PIMCORE:parcel_1_depth|keep}/"
        "{PIMCORE:parcel_1_height|keep})*4"
    )

    assert render_template(
        template,
        resolver(
            {
                "pimcore:parcel_1_weight": "10",
                "pimcore:parcel_1_width": "8",
                "pimcore:parcel_1_depth": "2",
                "pimcore:parcel_1_height": "2",
            }
        ),
    ) == "18"


def test_render_template_keeps_math_parentheses_for_precedence():
    assert render_template(
        "({A|keep}+{B|keep})*{C|keep}",
        resolver({"a": "2", "b": "3", "c": "4"}),
    ) == "20"


def test_render_template_accepts_decimal_comma_in_math_expression():
    assert render_template(
        "{A|keep}+{B|keep}",
        resolver({"a": "1,5", "b": "2.25"}),
    ) == "3.75"


def test_render_template_leaves_non_math_text_with_operator_unchanged():
    assert render_template("Waga: {A|keep}+2", resolver({"a": "3"})) == "Waga: 3+2"


def test_render_template_rejects_math_division_by_zero():
    with pytest.raises(TemplateError) as captured:
        render_template("{A|keep}/{B|keep}", resolver({"a": "1", "b": "0"}))

    assert captured.value.code == "math_division_by_zero"


def test_render_template_calculates_oblicz_block_inside_mixed_text():
    template = (
        'oblicz(2*(5415413+{PIMCORE:parcel_11_weight|keep|default:"1110"})) '
        '(/{PRODUCT:model|keep})'
    )

    assert render_template(
        template,
        resolver(
            {
                "pimcore:parcel_11_weight": "",
                "product:model": "M-20",
            }
        ),
    ) == "10833046 /M-20"


def test_render_template_calculates_calc_alias():
    assert render_template(
        "calc(2*(2+{PIMCORE:parcel_11_weight|keep}))",
        resolver({"pimcore:parcel_11_weight": "3"}),
    ) == "10"


def test_render_template_rejects_text_inside_oblicz_block():
    with pytest.raises(TemplateError) as captured:
        render_template(
            "oblicz(2+{PRODUCT:model|keep})",
            resolver({"product:model": "M-20"}),
        )

    assert captured.value.code == "invalid_math_expression"


@pytest.mark.parametrize(
    ("template", "code"),
    [
        ("{NAZWA", "unclosed_placeholder"),
        ("({NAZWA}", "unclosed_group"),
        ("(tekst)", "condition_without_placeholder"),
        ("{NAZWA|unknown}", "unknown_function"),
        ("{NAZWA|substring:x,2}", "invalid_arguments"),
    ],
)
def test_invalid_templates_raise_structured_errors(template, code):
    with pytest.raises(TemplateError) as captured:
        render_template(template, resolver({"nazwa": "Vivo"}))

    assert captured.value.code == code
    assert captured.value.position >= 0


MAPPINGS = [
    {
        "source": "EAN",
        "label": "EAN",
        "type": "input",
        "parser": "text",
        "value_template": "",
    },
    {
        "source": "COLOR",
        "label": "Kolor",
        "type": "input",
        "parser": "text",
        "value_template": "{KOLOR 1}(/{KOLOR 2})",
    },
    {
        "source": "TITLE",
        "label": "Tytul",
        "type": "input",
        "parser": "text",
        "value_template": "{NAZWA} - {PIMCORE:COLOR}",
    },
]


def test_catalog_supports_friendly_technical_and_qualified_sources():
    catalog = build_source_catalog(MAPPINGS)

    assert catalog.resolve("NAZWA") == "PRODUCT:name"
    assert catalog.resolve("PIMCORE:TITLE") == "PIMCORE:TITLE"
    assert catalog.resolve("title") == "PIMCORE:TITLE"


def test_mapping_templates_render_in_dependency_order():
    result = render_mapping_templates(
        MAPPINGS,
        product_values={
            "name": "Vivo",
            "color1": "white",
            "color2": "black",
        },
        pimcore_values={"EAN": "5904804578169"},
    )

    assert result.values["COLOR"] == "WHITE/BLACK"
    assert result.values["TITLE"] == "VIVO - WHITE/BLACK"
    assert result.order == ("COLOR", "TITLE")


def test_mapping_cycle_is_rejected_with_sources():
    mappings = [
        {"source": "A", "type": "input", "value_template": "{PIMCORE:B}"},
        {"source": "B", "type": "input", "value_template": "{PIMCORE:A}"},
    ]

    with pytest.raises(TemplateError) as captured:
        render_mapping_templates(mappings, product_values={}, pimcore_values={})

    assert captured.value.code == "dependency_cycle"
    assert "A" in captured.value.message
    assert "B" in captured.value.message


def test_external_provider_can_register_source_without_template_changes():
    mappings = [
        {
            "source": "STOCK_TEXT",
            "type": "input",
            "value_template": "Stan: {SQL:STOCK}",
        }
    ]
    source = SourceDefinition("SQL:stock", "Stan SQL", "sql", ("SQL:STOCK",))

    result = render_mapping_templates(
        mappings,
        product_values={},
        pimcore_values={},
        extra_sources=[source],
        extra_values={"SQL:stock": "12"},
    )

    assert result.values["STOCK_TEXT"] == "Stan: 12"


def test_test_values_are_fresh_field_specific_and_type_compatible():
    mappings = MAPPINGS + [
        {"source": "WEIGHT", "type": "numeric", "parser": "decimal_comma"},
        {"source": "ACTIVE", "type": "checkbox", "parser": "boolean"},
    ]

    first = generate_test_values(mappings)
    second = generate_test_values(mappings)

    assert first["EAN"].isdigit()
    assert len(first["EAN"]) == 13
    assert first["EAN"] != second["EAN"]
    assert first["COLOR"] != first["TITLE"]
    assert "," in first["WEIGHT"]
    assert first["ACTIVE"] in {"tak", "nie"}
