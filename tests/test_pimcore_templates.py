import pytest

from picorgftp_sql.pimcore_templates import TemplateError, render_template


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
