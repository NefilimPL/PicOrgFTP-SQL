# Pimcore Template Builder And Runtime Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add editable Pimcore test samples, a persistent backend-owned template builder with optional translation, reliable runtime editing, class-wide lookup guarantees, and safe empty URL defaults.

**Architecture:** A new pure-Python template module owns syntax, source resolution, dependencies, and sample generation. A focused translation service and thin `web_data` adapters expose administrator preview/test models and authenticated rendering of saved templates; the existing Pimcore service remains responsible for lookup and mutations. The browser adds the builder and visible runtime states while all authoritative validation stays on the server.

**Tech Stack:** Python 3.11, FastAPI, pytest, standard-library `urllib`, vanilla JavaScript, HTML, CSS.

---

## File Structure

- Create `picorgftp_sql/pimcore_templates.py`: template parser, renderer, source catalogue, dependency resolver, and sample-value generation.
- Create `picorgftp_sql/services/translation_service.py`: provider-neutral translation result and Google/MyMemory/DeepL adapters.
- Create `tests/test_pimcore_templates.py`: focused syntax, dependency, source, and sample tests.
- Create `tests/test_translation_service.py`: provider request/response and fallback tests.
- Modify `picorgftp_sql/pimcore_config.py`: new mapping properties, validation, empty URL default, and legacy-default migration.
- Modify `picorgftp_sql/services/pimcore_service.py`: robust object identity and explicit class-wide lookup invariants.
- Modify `picorgftp_sql/web_data.py`: template source models, preview/render adapters, samples, translation orchestration, and runtime schemas.
- Modify `picorgftp_sql/web/app.py`: administrator preview/sample routes and authenticated saved-template rendering route.
- Modify `picorgftp_sql/web/static/index.html`: template-builder modal and test regeneration control.
- Modify `picorgftp_sql/web/static/app.js`: mapping persistence, builder UX, samples, create rendering, explicit edit recalculation, and stale-request protection.
- Modify `picorgftp_sql/web/static/app.css`: builder/modal styling and content-safe product action layout.
- Modify `tests/test_pimcore_config.py`, `tests/test_pimcore_service.py`, `tests/test_pimcore_web.py`, `tests/test_web_ui_integrity.py`, and `tests/test_source_integrity.py`: integration and regression coverage.
- Modify `README.md`: document templates, conditional groups, translation fallback, test samples, and lookup/create folder semantics.

## Task 1: Template Parser And Controlled Functions

**Files:**
- Create: `picorgftp_sql/pimcore_templates.py`
- Create: `tests/test_pimcore_templates.py`

- [ ] **Step 1: Write failing parser and renderer tests**

Create `tests/test_pimcore_templates.py` with the initial behavior contract:

```python
import pytest

from picorgftp_sql.pimcore_templates import TemplateError, render_template


def resolve(values):
    return lambda source: values.get(source.casefold(), "")


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("{NAZWA} - {TYP} {KOLOR 1}(/{KOLOR 2})", "VIVO - SIDEBOARD WHITE/BLACK"),
        ("{Nazwa} - {Typ} {kolor 1}(/{kolor 2})", "Vivo - Sideboard white/black"),
        ("{KOLOR 1}(/{KOLOR 2})", "WHITE"),
        (r"\({NAZWA|keep}\)", "(VIVO)"),
        ('{MODEL|trim|replace:"_"," "|upper}', "AB CD"),
        ('{BRAK|default:"wartosc"|title}', "Wartosc"),
        ('{TekSt|substring:1,3}', "bcd"),
        ('{TekSt|truncate:4,"..."}', "abcd..."),
        ('{TekSt|normalize_spaces}', "a b"),
        ('{TekSt|strip_diacritics}', "zolc"),
        ('{TekSt|slug}', "zolty-stol"),
        ('{LICZBA|number:2,","," "}', "1 234,50"),
    ],
)
def test_render_template_supports_literals_groups_case_and_functions(template, expected):
    values = {
        "nazwa": "VIVO",
        "typ": "sideboard",
        "kolor 1": "white",
        "kolor 2": "black" if "KOLOR 2" in template or "kolor 2" in template else "",
        "model": "  ab_cd  ",
        "tekst": (
            "  a   b  " if "normalize" in template
            else "  Żółty   stół  " if "slug" in template
            else "żółć" if "diacritics" in template
            else "abcdefgh"
        ),
        "liczba": "1234,5",
    }
    assert render_template(template, resolve(values)) == expected


def test_conditional_group_drops_literals_when_required_value_is_empty():
    values = {"kolor 1": "white", "kolor 2": ""}
    assert render_template("{KOLOR 1}(/{KOLOR 2})", resolve(values)) == "WHITE"


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
        render_template(template, resolve({"nazwa": "VIVO"}))
    assert captured.value.code == code
    assert captured.value.position >= 0
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m pytest tests/test_pimcore_templates.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'picorgftp_sql.pimcore_templates'`.

- [ ] **Step 3: Implement the parser and controlled functions**

Create `picorgftp_sql/pimcore_templates.py` with these public types and functions. Keep parsing recursive and bounded; do not use `eval`, dynamic imports, or regular-expression replacement as an expression engine.

```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import csv
import io
import re
import unicodedata
from typing import Callable, Iterable, Mapping

MAX_TEMPLATE_LENGTH = 4000
MAX_TEMPLATE_DEPTH = 8
MAX_OUTPUT_LENGTH = 16000
TRANSLITERATION = str.maketrans({"ł": "l", "Ł": "L", "đ": "d", "Đ": "D"})


@dataclass(frozen=True)
class TemplateError(ValueError):
    code: str
    message: str
    position: int = 0

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class LiteralNode:
    value: str


@dataclass(frozen=True)
class FunctionCall:
    name: str
    arguments: tuple[str, ...]


@dataclass(frozen=True)
class PlaceholderNode:
    source: str
    functions: tuple[FunctionCall, ...]
    position: int


@dataclass(frozen=True)
class GroupNode:
    children: tuple[object, ...]
    position: int


def _split_quoted(value: str, delimiter: str) -> list[str]:
    parts, current = [], []
    quote = ""
    escaped = False
    for char in value:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            current.append(char)
            escaped = True
        elif quote:
            current.append(char)
            if char == quote:
                quote = ""
        elif char in {'"', "'"}:
            current.append(char)
            quote = char
        elif char == delimiter:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if quote:
        raise TemplateError("invalid_arguments", "Niezamkniety cudzyslow.", 0)
    parts.append("".join(current).strip())
    return parts


def _arguments(value: str, position: int) -> tuple[str, ...]:
    if not value:
        return ()
    try:
        row = next(csv.reader(io.StringIO(value), skipinitialspace=True, escapechar="\\"))
    except (csv.Error, StopIteration) as exc:
        raise TemplateError("invalid_arguments", "Niepoprawne argumenty funkcji.", position) from exc
    return tuple(item for item in row)


def _placeholder(content: str, position: int) -> PlaceholderNode:
    parts = _split_quoted(content, "|")
    source = parts[0].strip()
    if not source:
        raise TemplateError("empty_placeholder", "Placeholder nie ma zrodla.", position)
    functions = []
    for raw in parts[1:]:
        name_and_args = _split_quoted(raw, ":")
        name = name_and_args[0].strip().lower()
        argument_text = raw[len(name_and_args[0]) + 1 :] if len(name_and_args) > 1 else ""
        functions.append(FunctionCall(name, _arguments(argument_text, position)))
    return PlaceholderNode(source, tuple(functions), position)


class _Parser:
    def __init__(self, template: str):
        if len(template) > MAX_TEMPLATE_LENGTH:
            raise TemplateError("template_too_long", "Szablon jest za dlugi.", MAX_TEMPLATE_LENGTH)
        self.template = template
        self.index = 0

    def parse(self) -> tuple[object, ...]:
        nodes = self._sequence("", 0)
        if self.index != len(self.template):
            raise TemplateError("unexpected_closing", "Nieoczekiwany znak zamykajacy.", self.index)
        return nodes

    def _sequence(self, closing: str, depth: int) -> tuple[object, ...]:
        if depth > MAX_TEMPLATE_DEPTH:
            raise TemplateError("nesting_too_deep", "Za duzo zagniezdzonych grup.", self.index)
        nodes, literal = [], []
        while self.index < len(self.template):
            char = self.template[self.index]
            if closing and char == closing:
                break
            if char == "\\":
                self.index += 1
                if self.index >= len(self.template):
                    raise TemplateError("dangling_escape", "Pusty znak ucieczki.", self.index - 1)
                literal.append(self.template[self.index])
                self.index += 1
                continue
            if char == "{":
                if literal:
                    nodes.append(LiteralNode("".join(literal)))
                    literal = []
                start = self.index
                self.index += 1
                content, quote, escaped = [], "", False
                while self.index < len(self.template):
                    current = self.template[self.index]
                    if escaped:
                        content.append(current)
                        escaped = False
                    elif current == "\\":
                        content.append(current)
                        escaped = True
                    elif quote:
                        content.append(current)
                        if current == quote:
                            quote = ""
                    elif current in {'"', "'"}:
                        content.append(current)
                        quote = current
                    elif current == "}":
                        break
                    else:
                        content.append(current)
                    self.index += 1
                if self.index >= len(self.template):
                    raise TemplateError("unclosed_placeholder", "Niezamkniety placeholder.", start)
                self.index += 1
                nodes.append(_placeholder("".join(content), start))
                continue
            if char == "(":
                if literal:
                    nodes.append(LiteralNode("".join(literal)))
                    literal = []
                start = self.index
                self.index += 1
                children = self._sequence(")", depth + 1)
                if self.index >= len(self.template) or self.template[self.index] != ")":
                    raise TemplateError("unclosed_group", "Niezamknieta grupa warunkowa.", start)
                self.index += 1
                if not any(isinstance(node, (PlaceholderNode, GroupNode)) for node in children):
                    raise TemplateError("condition_without_placeholder", "Grupa nie zawiera placeholdera.", start)
                nodes.append(GroupNode(children, start))
                continue
            if char in ")}":
                if closing == char:
                    break
                raise TemplateError("unexpected_closing", "Nieoczekiwany znak zamykajacy.", self.index)
            literal.append(char)
            self.index += 1
        if literal:
            nodes.append(LiteralNode("".join(literal)))
        return tuple(nodes)


def parse_template(template: object) -> tuple[object, ...]:
    return _Parser(str(template or "")).parse()


def _case_shortcut(source: str, calls: Iterable[FunctionCall]) -> str:
    if any(call.name in {"keep", "upper", "lower", "title", "capitalize"} for call in calls):
        return "keep"
    tail = source.rsplit(":", 1)[-1]
    letters = "".join(char for char in tail if char.isalpha())
    if letters and letters.isupper():
        return "upper"
    if letters and letters.islower():
        return "lower"
    if tail.istitle():
        return "title"
    return "keep"


def _strip_diacritics(value: str) -> str:
    translated = value.translate(TRANSLITERATION)
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", translated)
        if not unicodedata.combining(char)
    )


def _apply(value: str, call: FunctionCall, position: int) -> str:
    name, args = call.name, call.arguments
    try:
        if name == "keep" and not args:
            return value
        if name == "trim" and not args:
            return value.strip()
        if name == "normalize_spaces" and not args:
            return " ".join(value.split())
        if name == "upper" and not args:
            return value.upper()
        if name == "lower" and not args:
            return value.lower()
        if name == "title" and not args:
            return value.title()
        if name == "capitalize" and not args:
            return value[:1].upper() + value[1:].lower()
        if name == "replace" and len(args) == 2:
            return value.replace(args[0], args[1])
        if name == "default" and len(args) == 1:
            return value if value.strip() else args[0]
        if name == "substring" and len(args) in {1, 2}:
            start = int(args[0])
            return value[start:] if len(args) == 1 else value[start : start + int(args[1])]
        if name == "truncate" and len(args) in {1, 2}:
            length = max(0, int(args[0]))
            suffix = args[1] if len(args) == 2 else ""
            return value if len(value) <= length else value[:length] + suffix
        if name == "strip_diacritics" and not args:
            return _strip_diacritics(value)
        if name == "slug" and not args:
            plain = _strip_diacritics(value)
            return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
        if name == "number" and 1 <= len(args) <= 3:
            decimals = max(0, min(8, int(args[0])))
            decimal_separator = args[1] if len(args) >= 2 else "."
            group_separator = args[2] if len(args) == 3 else ""
            number = Decimal(value.replace(" ", "").replace(",", "."))
            rendered = f"{number:,.{decimals}f}"
            rendered = rendered.replace(",", "\x00").replace(".", decimal_separator).replace("\x00", group_separator)
            return rendered
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise TemplateError("invalid_arguments", f"Niepoprawne argumenty funkcji {name}.", position) from exc
    if name not in {"keep", "trim", "normalize_spaces", "upper", "lower", "title", "capitalize", "replace", "default", "substring", "truncate", "strip_diacritics", "slug", "number"}:
        raise TemplateError("unknown_function", f"Nieznana funkcja {name}.", position)
    raise TemplateError("invalid_arguments", f"Niepoprawne argumenty funkcji {name}.", position)


def render_template(template: object, resolver: Callable[[str], object]) -> str:
    def render_nodes(nodes: tuple[object, ...], conditional: bool) -> tuple[str, list[str]]:
        output, resolved = [], []
        for node in nodes:
            if isinstance(node, LiteralNode):
                output.append(node.value)
            elif isinstance(node, PlaceholderNode):
                value = str(resolver(node.source) or "")
                for call in node.functions:
                    value = _apply(value, call, node.position)
                shortcut = _case_shortcut(node.source, node.functions)
                value = _apply(value, FunctionCall(shortcut, ()), node.position)
                output.append(value)
                resolved.append(value)
            elif isinstance(node, GroupNode):
                value, group_values = render_nodes(node.children, True)
                output.append(value if all(item.strip() for item in group_values) else "")
                resolved.extend(group_values)
        text = "".join(output)
        if len(text) > MAX_OUTPUT_LENGTH:
            raise TemplateError("output_too_long", "Wynik szablonu jest za dlugi.", MAX_OUTPUT_LENGTH)
        return text, resolved

    return render_nodes(parse_template(template), False)[0]


def placeholder_sources(template: object) -> tuple[str, ...]:
    sources = []
    def visit(nodes):
        for node in nodes:
            if isinstance(node, PlaceholderNode) and node.source not in sources:
                sources.append(node.source)
            elif isinstance(node, GroupNode):
                visit(node.children)
    visit(parse_template(template))
    return tuple(sources)
```

- [ ] **Step 4: Run parser tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_pimcore_templates.py -q
```

Expected: all initial parser tests pass.

- [ ] **Step 5: Commit the parser**

```powershell
git add picorgftp_sql/pimcore_templates.py tests/test_pimcore_templates.py
git commit -m "feat: add pimcore value template engine"
```

## Task 2: Source Catalogue, Dependency Resolution, And Test Samples

**Files:**
- Modify: `picorgftp_sql/pimcore_templates.py`
- Modify: `tests/test_pimcore_templates.py`

- [ ] **Step 1: Add failing source, cycle, and sample tests**

Append:

```python
from picorgftp_sql.pimcore_templates import (
    SourceDefinition,
    build_source_catalog,
    generate_test_values,
    render_mapping_templates,
)


MAPPINGS = [
    {"source": "EAN", "label": "EAN", "type": "input", "parser": "text", "value_template": ""},
    {"source": "COLOR", "label": "Kolor", "type": "input", "parser": "text", "value_template": "{KOLOR 1}(/{KOLOR 2})"},
    {"source": "TITLE", "label": "Tytul", "type": "input", "parser": "text", "value_template": "{NAZWA} - {PIMCORE:COLOR}"},
]


def test_catalog_supports_friendly_technical_and_qualified_sources():
    catalog = build_source_catalog(MAPPINGS)
    assert catalog.resolve("NAZWA") == "PRODUCT:name"
    assert catalog.resolve("PIMCORE:TITLE") == "PIMCORE:TITLE"
    assert catalog.resolve("title") == "PIMCORE:TITLE"


def test_mapping_templates_render_in_dependency_order():
    result = render_mapping_templates(
        MAPPINGS,
        product_values={"name": "Vivo", "color1": "white", "color2": "black"},
        pimcore_values={"EAN": "5901234123457"},
    )
    assert result.values["COLOR"] == "WHITE/BLACK"
    assert result.values["TITLE"] == "VIVO - WHITE/BLACK"


def test_mapping_cycle_is_rejected_with_sources():
    mappings = [
        {"source": "A", "type": "input", "value_template": "{PIMCORE:B}"},
        {"source": "B", "type": "input", "value_template": "{PIMCORE:A}"},
    ]
    with pytest.raises(TemplateError) as captured:
        render_mapping_templates(mappings, product_values={}, pimcore_values={})
    assert captured.value.code == "dependency_cycle"
    assert "A" in captured.value.message and "B" in captured.value.message


def test_external_provider_can_register_source_without_template_changes():
    mappings = [{"source": "STOCK_TEXT", "type": "input", "value_template": "Stan: {SQL:STOCK}"}]
    source = SourceDefinition("SQL:stock", "Stan SQL", "sql", ("SQL:STOCK",))
    result = render_mapping_templates(
        mappings,
        product_values={},
        pimcore_values={},
        extra_sources=[source],
        extra_values={"SQL:stock": "12"},
    )
    assert result.values["STOCK_TEXT"] == "Stan: 12"


def test_test_values_are_fresh_field_specific_and_valid():
    first = generate_test_values(MAPPINGS)
    second = generate_test_values(MAPPINGS)
    assert first["EAN"].isdigit() and len(first["EAN"]) == 13
    assert first["EAN"] != second["EAN"]
    assert first["COLOR"] != first["TITLE"]
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
python -m pytest tests/test_pimcore_templates.py -q
```

Expected: import fails for `build_source_catalog`, `render_mapping_templates`, and `generate_test_values`.

- [ ] **Step 3: Implement source catalogue, graph resolution, and samples**

Append these public contracts to `picorgftp_sql/pimcore_templates.py` and implement the helpers they call in the same file:

```python
import secrets
import time

PRODUCT_SOURCES = {
    "name": ("Nazwa", "NAZWA", "name"),
    "type": ("Typ", "TYP", "type", "type_name"),
    "model": ("Model", "MODEL", "model"),
    "color1": ("Kolor 1", "KOLOR 1", "color1"),
    "color2": ("Kolor 2", "KOLOR 2", "color2"),
    "color3": ("Kolor 3", "KOLOR 3", "color3"),
    "extra": ("Dodatek", "DODATEK", "extra"),
    "ean": ("EAN", "ean"),
}


@dataclass(frozen=True)
class SourceDefinition:
    key: str
    label: str
    provider: str
    aliases: tuple[str, ...] = ()


class SourceCatalog:
    def __init__(self, definitions: Iterable[SourceDefinition]):
        self.definitions = tuple(definitions)
        aliases: dict[str, set[str]] = {}
        for definition in self.definitions:
            for alias in (definition.key, definition.label, *definition.aliases):
                aliases.setdefault(alias.casefold(), set()).add(definition.key)
        self._aliases = aliases

    def resolve(self, source: str) -> str:
        matches = self._aliases.get(str(source).strip().casefold(), set())
        if not matches:
            raise TemplateError("unknown_source", f"Nieznane zrodlo {source}.", 0)
        if len(matches) > 1:
            raise TemplateError("ambiguous_source", f"Niejednoznaczne zrodlo {source}.", 0)
        return next(iter(matches))

    def public_items(self) -> list[dict[str, object]]:
        return [
            {"key": item.key, "label": item.label, "provider": item.provider, "aliases": list(item.aliases)}
            for item in self.definitions
        ]


@dataclass(frozen=True)
class RenderedMappings:
    values: dict[str, object]
    order: tuple[str, ...]


def build_source_catalog(
    mappings: Iterable[Mapping[str, object]],
    extra_sources: Iterable[SourceDefinition] = (),
) -> SourceCatalog:
    definitions = [
        SourceDefinition(f"PRODUCT:{key}", values[0], "product", tuple(values[1:]))
        for key, values in PRODUCT_SOURCES.items()
    ]
    for mapping in mappings:
        source = str(mapping.get("source") or "").strip()
        if source:
            definitions.append(
                SourceDefinition(
                    f"PIMCORE:{source}",
                    str(mapping.get("label") or source),
                    "pimcore",
                    (source,),
                )
            )
    definitions.extend(extra_sources)
    return SourceCatalog(definitions)


def render_mapping_templates(
    mappings: Iterable[Mapping[str, object]],
    *,
    product_values: Mapping[str, object],
    pimcore_values: Mapping[str, object],
    targets: Iterable[str] | None = None,
    extra_sources: Iterable[SourceDefinition] = (),
    extra_values: Mapping[str, object] | None = None,
) -> RenderedMappings:
    rows = {str(item.get("source") or ""): dict(item) for item in mappings if str(item.get("source") or "")}
    catalog = build_source_catalog(rows.values(), extra_sources)
    values = {f"PRODUCT:{key}": value for key, value in product_values.items()}
    values.update({f"PIMCORE:{key}": value for key, value in pimcore_values.items()})
    values.update(dict(extra_values or {}))
    dependencies: dict[str, set[str]] = {}
    for source, row in rows.items():
        template = str(row.get("value_template") or "")
        dependencies[source] = {
            resolved.split(":", 1)[1]
            for resolved in (catalog.resolve(name) for name in placeholder_sources(template))
            if resolved.startswith("PIMCORE:") and resolved.split(":", 1)[1] in rows
        } if template else set()

    order, active, complete = [], [], set()
    def visit(source: str) -> None:
        if source in complete:
            return
        if source in active:
            cycle = active[active.index(source):] + [source]
            raise TemplateError("dependency_cycle", "Cykliczne pola: " + " -> ".join(cycle), 0)
        active.append(source)
        for dependency in dependencies[source]:
            visit(dependency)
        active.pop()
        complete.add(source)
        order.append(source)

    selected = set(targets or rows)
    for source in selected:
        if source not in rows:
            raise TemplateError("unknown_target", f"Nieznane pole docelowe {source}.", 0)
        visit(source)

    for source in order:
        template = str(rows[source].get("value_template") or "")
        if template:
            values[f"PIMCORE:{source}"] = render_template(template, lambda name: values.get(catalog.resolve(name), ""))
    return RenderedMappings(
        {source: values.get(f"PIMCORE:{source}", "") for source in rows},
        tuple(order),
    )


def _gtin13(seed: int) -> str:
    body = f"{seed % 10**12:012d}"
    total = sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(body))
    return body + str((-total) % 10)


def generate_test_values(mappings: Iterable[Mapping[str, object]]) -> dict[str, object]:
    token = f"{int(time.time() * 1000):x}{secrets.randbelow(0x10000):04x}"
    result = {}
    for index, mapping in enumerate(mappings, start=1):
        source = str(mapping.get("source") or "")
        parser = str(mapping.get("parser") or "text")
        element_type = str(mapping.get("type") or "input")
        if source.casefold() == "ean":
            value = _gtin13(int(time.time_ns()) + index)
        elif parser == "integer":
            value = str(1000 + index)
        elif parser == "decimal_comma":
            value = f"{1000 + index},{index % 10}"
        elif parser == "boolean" or element_type == "checkbox":
            value = "tak" if index % 2 else "nie"
        else:
            safe = re.sub(r"[^0-9A-Za-z]+", "_", source).strip("_") or f"FIELD_{index}"
            value = f"TEST_{safe}_{token}_{index}"
        result[source] = value
    return result
```

- [ ] **Step 4: Run source/sample tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_pimcore_templates.py -q
```

Expected: all template tests pass.

- [ ] **Step 5: Commit catalogue and sample support**

```powershell
git add picorgftp_sql/pimcore_templates.py tests/test_pimcore_templates.py
git commit -m "feat: resolve pimcore template sources"
```

## Task 3: Mapping Configuration And Empty URL Migration

**Files:**
- Modify: `picorgftp_sql/pimcore_config.py:20-216`
- Modify: `tests/test_pimcore_config.py:1-145`
- Modify: `tests/test_config.py:130-175`

- [ ] **Step 1: Write failing normalization and migration tests**

Add to `tests/test_pimcore_config.py`:

```python
def test_mapping_template_options_round_trip():
    result = normalize_pimcore_settings({
        "field_mappings": [{
            "source": "TITLE",
            "label": "Tytul",
            "pimcore_field": "title",
            "type": "input",
            "parser": "text",
            "value_template": "{NAZWA} - {TYP}",
            "translate": True,
            "target_language": "en",
        }]
    })
    mapping = result["field_mappings"][0]
    assert mapping["value_template"] == "{NAZWA} - {TYP}"
    assert mapping["translate"] is True
    assert mapping["target_language"] == "en"


def test_invalid_template_is_reported_by_mapping_validation():
    issues = field_mapping_issues([{
        "source": "TITLE",
        "pimcore_field": "title",
        "type": "input",
        "parser": "text",
        "value_template": "{NAZWA",
    }])
    assert issues == ["Mapowanie 1: Niezamkniety placeholder."]


def test_translation_requires_text_template_and_target_language():
    issues = field_mapping_issues([{
        "source": "TITLE",
        "pimcore_field": "title",
        "type": "input",
        "parser": "text",
        "value_template": "{NAZWA}",
        "translate": True,
        "target_language": "",
    }])
    assert issues == ["Mapowanie 1: wybierz jezyk docelowy tlumaczenia."]


def test_new_installation_has_empty_pimcore_url():
    assert normalize_pimcore_settings(None)["base_url"] == ""


def test_incomplete_legacy_default_url_is_cleared_but_configured_server_is_preserved():
    assert normalize_pimcore_settings({"base_url": "http://10.10.0.5"})["base_url"] == ""
    configured = normalize_pimcore_settings({
        "base_url": "http://10.10.0.5",
        "api_key": "secret",
        "class_name": "product",
        "parent_id": "6626",
    })
    assert configured["base_url"] == "http://10.10.0.5"
```

Update existing mapping equality assertions to include:

```python
"value_template": "",
"translate": False,
"target_language": None,
```

- [ ] **Step 2: Run config tests and verify RED**

Run:

```powershell
python -m pytest tests/test_pimcore_config.py tests/test_config.py -q
```

Expected: failures show the old URL default and missing mapping properties.

- [ ] **Step 3: Normalize templates and migrate only an unused old default**

In `picorgftp_sql/pimcore_config.py`, import the validation dependencies:

```python
from .pimcore_templates import (
    PRODUCT_SOURCES,
    TemplateError,
    build_source_catalog,
    generate_test_values,
    placeholder_sources,
    parse_template,
    render_mapping_templates,
)

OLD_EXAMPLE_BASE_URL = "http://10.10.0.5"
```

Replace the existing default dictionary entry with:

```python
"base_url": "",
```

Extend `normalize_field_mapping()` with values read from `raw`:

```python
"value_template": _text(raw.get("value_template")),
"translate": bool(raw.get("translate")),
"target_language": _text(raw.get("target_language")) or None,
```

Extend `infer_field_mapping()` with clean defaults:

```python
"value_template": "",
"translate": False,
"target_language": None,
```

In `normalize_pimcore_settings()` compute the URL before assigning it:

```python
raw_base_url = _text(source.get("base_url", settings["base_url"])).rstrip("/")
has_intentional_location = bool(
    _text(source.get(PIMCORE_API_KEY))
    or _text(source.get("class_id"))
    or _text(source.get("class_name"))
    or _text(source.get("parent_id"))
    or source.get("setup_complete") is True
)
settings["base_url"] = (
    "" if raw_base_url == OLD_EXAMPLE_BASE_URL and not has_intentional_location else raw_base_url
)
```

At the end of `field_mapping_issues()`, validate only non-empty templates and resolve every referenced source through the full mapping catalogue:

Inside the existing per-row structural loop, add:

```python
template = _text(raw.get("value_template"))
translate = bool(raw.get("translate"))
target_language = _text(raw.get("target_language"))
if template and element_type not in {"input", "textarea", "select"}:
    issues.append(f"Mapowanie {index}: szablon wymaga pola tekstowego.")
if translate and not template:
    issues.append(f"Mapowanie {index}: tlumaczenie wymaga szablonu wartosci.")
if translate and not target_language:
    issues.append(f"Mapowanie {index}: wybierz jezyk docelowy tlumaczenia.")
```

Then validate syntax, sources, and the dependency graph:

```python
try:
    catalog = build_source_catalog(raw_mappings)
    for index, raw in enumerate(raw_mappings, start=1):
        template = _text(raw.get("value_template")) if isinstance(raw, dict) else ""
        if not template:
            continue
        parse_template(template)
        for source in placeholder_sources(template):
            catalog.resolve(source)
    sample_values = generate_test_values(raw_mappings)
    render_mapping_templates(
        raw_mappings,
        product_values={key: "1" for key in PRODUCT_SOURCES},
        pimcore_values=sample_values,
    )
except TemplateError as exc:
    issues.append(f"Mapowanie {index}: {exc.message}")
```

Keep structural validation results ahead of template validation so existing error ordering stays stable.

- [ ] **Step 4: Run config tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_pimcore_config.py tests/test_config.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit mapping configuration**

```powershell
git add picorgftp_sql/pimcore_config.py tests/test_pimcore_config.py tests/test_config.py
git commit -m "feat: persist pimcore value templates"
```

## Task 4: Shared Translation Service With Non-Blocking Fallback

**Files:**
- Create: `picorgftp_sql/services/translation_service.py`
- Create: `tests/test_translation_service.py`

- [ ] **Step 1: Write failing provider and fallback tests**

Create `tests/test_translation_service.py`:

```python
import json
from unittest.mock import Mock

from picorgftp_sql.services.translation_service import translate_text


class Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.payload


def test_google_translation_returns_translated_text():
    opener = Mock(return_value=Response(json.dumps([[["White cabinet", "Biala szafka"]]]).encode()))
    result = translate_text(
        "Biala szafka",
        "en",
        {"provider": "google", "api_key": "", "api_url": ""},
        opener=opener,
    )
    assert result.text == "White cabinet"
    assert result.warning is None


def test_provider_failure_keeps_source_text_and_warning():
    opener = Mock(side_effect=TimeoutError("timeout"))
    result = translate_text(
        "Biala szafka",
        "en",
        {"provider": "google"},
        opener=opener,
    )
    assert result.text == "Biala szafka"
    assert result.warning["code"] == "translation_failed"
    assert "timeout" in result.warning["message"]


def test_deepl_without_key_keeps_source_without_network_call():
    opener = Mock()
    result = translate_text("Biala", "en", {"provider": "deepl", "api_key": ""}, opener=opener)
    assert result.text == "Biala"
    assert result.warning["code"] == "missing_translation_key"
    opener.assert_not_called()
```

- [ ] **Step 2: Run translation tests and verify RED**

Run:

```powershell
python -m pytest tests/test_translation_service.py -q
```

Expected: collection fails because `translation_service` does not exist.

- [ ] **Step 3: Implement provider-neutral translation**

Create `picorgftp_sql/services/translation_service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
import html
import json
import re
from typing import Callable, Mapping
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

from ..common import SSL_CONTEXT


@dataclass(frozen=True)
class TranslationResult:
    text: str
    warning: dict[str, str] | None = None


def _language(value: object, *, deepl: bool = False) -> str:
    code = {"ua": "uk"}.get(str(value or "").strip().lower(), str(value or "").strip().lower())
    return code.upper() if deepl else code


def _source_language(text: str) -> str:
    if re.search(r"[а-яіїєґ]", text.lower()):
        return "uk"
    if re.search(r"[ąćęłńóśźż]", text.lower()):
        return "pl"
    return "en"


def translate_text(
    text: object,
    target_language: object,
    settings: Mapping[str, object],
    *,
    opener: Callable = urlopen,
) -> TranslationResult:
    source = str(text or "")
    target = _language(target_language)
    if not source.strip() or not target:
        return TranslationResult(source)
    provider = str(settings.get("provider") or "google").strip().lower()
    api_key = str(settings.get("api_key") or "").strip()
    api_url = str(settings.get("api_url") or "").strip()
    if provider == "deepl" and not api_key:
        return TranslationResult(source, {"code": "missing_translation_key", "message": "Brak klucza API tlumaczen."})
    try:
        if provider == "deepl":
            endpoint = api_url or ("https://api-free.deepl.com/v2/translate" if api_key.endswith(":fx") else "https://api.deepl.com/v2/translate")
            request = Request(
                endpoint,
                data=urlencode({"auth_key": api_key, "text": source, "target_lang": _language(target, deepl=True)}).encode(),
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with opener(request, timeout=5, context=SSL_CONTEXT) as response:
                payload = json.loads(response.read().decode("utf-8"))
            translated = ((payload.get("translations") or [{}])[0].get("text") if isinstance(payload, dict) else "")
        elif provider == "mymemory":
            endpoint = "https://api.mymemory.translated.net/get" + f"?q={quote_plus(source)}&langpair={_source_language(source)}|{target}"
            with opener(Request(endpoint, headers={"User-Agent": "Mozilla/5.0"}), timeout=5, context=SSL_CONTEXT) as response:
                payload = json.loads(response.read().decode("utf-8"))
            translated = ((payload.get("responseData") or {}).get("translatedText") if isinstance(payload, dict) else "")
        else:
            endpoint = "https://translate.googleapis.com/translate_a/single" + f"?client=gtx&sl=auto&tl={target}&dt=t&q={quote_plus(source)}"
            with opener(Request(endpoint, headers={"User-Agent": "Mozilla/5.0"}), timeout=5, context=SSL_CONTEXT) as response:
                payload = json.loads(response.read().decode("utf-8"))
            translated = "".join(str(item[0]) for item in (payload[0] or []) if isinstance(item, list) and item)
        translated = html.unescape(str(translated or "")).strip()
        if not translated:
            raise ValueError("pusta odpowiedz")
        return TranslationResult(translated)
    except Exception as exc:
        return TranslationResult(source, {"code": "translation_failed", "message": f"Nie udalo sie przetlumaczyc tekstu: {exc}"})
```

- [ ] **Step 4: Run translation tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_translation_service.py -q
```

Expected: all translation tests pass without real network access.

- [ ] **Step 5: Commit translation service**

```powershell
git add picorgftp_sql/services/translation_service.py tests/test_translation_service.py
git commit -m "feat: translate generated pimcore values"
```

## Task 5: Backend Template Adapters, Routes, And Lookup Invariants

**Files:**
- Modify: `picorgftp_sql/services/pimcore_service.py:874-1030`
- Modify: `picorgftp_sql/web_data.py:1635-1765`
- Modify: `picorgftp_sql/web/app.py:4178-4410`
- Modify: `tests/test_pimcore_service.py:270-390`
- Modify: `tests/test_pimcore_web.py:360-525`

- [ ] **Step 1: Write failing service and route tests**

Add to `tests/test_pimcore_service.py`:

```python
def test_lookup_searches_whole_class_without_parent_filter():
    client = Mock()
    client.object_list.return_value = {"data": [{"id": 91, "fullPath": "/Other/5904"}]}
    found = find_product_by_ean(PRODUCT_CONFIG, "5904804578169", client=client)
    assert found["id"] == 91
    args, kwargs = client.object_list.call_args
    assert args == ({"EAN": "5904804578169"},)
    assert kwargs == {"object_class": "Product", "limit": 2}


@pytest.mark.parametrize("record", [{"id": "91"}, {"o_id": "91"}, {"objectId": "91"}])
def test_object_identity_accepts_known_id_variants(record):
    assert normalize_object_identity(record)["id"] == 91


def test_lookup_rejects_match_without_positive_object_id():
    client = Mock()
    client.object_list.return_value = {"data": [{"fullPath": "/Products/broken"}]}
    with pytest.raises(ValueError, match="ID"):
        find_product_by_ean(PRODUCT_CONFIG, "5904804578169", client=client)
```

Add route-level tests to `tests/test_pimcore_web.py`:

```python
def test_admin_can_preview_unsaved_template_but_user_cannot():
    client = TestClient(web_app.app)
    payload = {"mappings": [], "target_source": "TITLE", "product_values": {}, "values": {}}
    with patch.object(web_app, "_require_admin", return_value="admin"), patch.object(
        web_app, "preview_pimcore_template", return_value={"values": {"TITLE": "VIVO"}, "warnings": []}
    ):
        assert client.post("/api/settings/pimcore/template-preview", json=payload).status_code == 200


def test_admin_test_sample_route_returns_fresh_editable_values():
    client = TestClient(web_app.app)
    expected = {"form_schema": [{"source": "EAN"}], "values": {"EAN": "5904804578169"}, "warnings": []}
    with patch.object(web_app, "_require_admin", return_value="admin"), patch.object(
        web_app, "pimcore_test_sample", return_value=expected
    ):
        response = client.post("/api/settings/pimcore/test-sample")
    assert response.json() == expected


def test_logged_in_user_can_render_only_saved_templates():
    client = TestClient(web_app.app)
    expected = {"values": {"TITLE": "VIVO"}, "warnings": []}
    with patch.object(web_app, "_require_user", return_value="operator"), patch.object(
        web_app, "render_saved_pimcore_templates", return_value=expected
    ) as render:
        response = client.post("/api/pimcore/render-templates", json={
            "product_values": {"name": "Vivo"}, "values": {}, "targets": ["TITLE"]
        })
    assert response.json() == expected
    render.assert_called_once_with({"name": "Vivo"}, {}, ["TITLE"])
```

- [ ] **Step 2: Run focused backend tests and verify RED**

Run:

```powershell
python -m pytest tests/test_pimcore_service.py tests/test_pimcore_web.py -q
```

Expected: failures identify missing route adapters and unsupported identity variants.

- [ ] **Step 3: Harden identity and preserve class-wide lookup**

Change `normalize_object_identity()` in `picorgftp_sql/services/pimcore_service.py`:

```python
def normalize_object_identity(record: object) -> dict[str, object]:
    source = record if isinstance(record, dict) else {}
    raw_id = source.get("id") or source.get("o_id") or source.get("objectId")
    try:
        object_id = int(raw_id)
    except (TypeError, ValueError):
        object_id = 0
    return {
        "id": object_id,
        "key": str(source.get("key") or source.get("o_key") or ""),
        "path": str(source.get("fullPath") or source.get("path") or source.get("o_path") or ""),
    }
```

After normalizing a record in `find_product_by_ean()`, reject an invalid match:

```python
identity = normalize_object_identity(records[0]) if records else None
if identity is not None and int(identity["id"] or 0) <= 0:
    raise ValueError("Odpowiedz Pimcore zawiera produkt bez poprawnego ID.")
return identity
```

Retain the existing `object_list(build_ean_filter(...), object_class=..., limit=2)` call exactly; do not add `parent_id`, path, or folder conditions.

- [ ] **Step 4: Add web-data rendering adapters**

Import the template/translation services in `picorgftp_sql/web_data.py`, extend `_pimcore_runtime_form_schema()` with the three template properties, and add:

```python
def _product_template_values(raw: object) -> dict[str, object]:
    source = raw if isinstance(raw, dict) else {}
    return {
        "name": source.get("name", ""),
        "type": source.get("type", source.get("type_name", "")),
        "model": source.get("model", ""),
        "color1": source.get("color1", ""),
        "color2": source.get("color2", ""),
        "color3": source.get("color3", ""),
        "extra": source.get("extra", ""),
        "ean": source.get("ean", source.get("EAN", "")),
    }


def _render_templates(settings_payload, product_values, values, targets=None):
    rendered = render_mapping_templates(
        settings_payload["field_mappings"],
        product_values=_product_template_values(product_values),
        pimcore_values=values if isinstance(values, dict) else {},
        targets=targets,
    )
    output = dict(values) if isinstance(values, dict) else {}
    warnings = []
    translation_settings = config.CONFIG.get(TRANSLATION_SETTINGS_KEY, {}) or {}
    by_source = {item["source"]: item for item in settings_payload["field_mappings"]}
    for source in rendered.order:
        value = rendered.values[source]
        mapping = by_source[source]
        if mapping.get("value_template"):
            if mapping.get("translate"):
                translated = translate_text(value, mapping.get("target_language"), translation_settings)
                value = translated.text
                if translated.warning:
                    warnings.append({"source": source, **translated.warning})
            output[source] = value
    return {"values": output, "warnings": warnings}


def preview_pimcore_template(payload: object) -> dict[str, object]:
    source = payload if isinstance(payload, dict) else {}
    snapshot = normalize_pimcore_settings({"field_mappings": source.get("mappings", [])})
    target = str(source.get("target_source") or "")
    return _render_templates(snapshot, source.get("product_values"), source.get("values"), [target])


def pimcore_test_sample() -> dict[str, object]:
    settings_payload = _active_pimcore_runtime_settings()
    base = generate_test_values(settings_payload["field_mappings"])
    rendered = _render_templates(settings_payload, {}, base)
    return {"form_schema": _pimcore_runtime_form_schema(settings_payload), **rendered}


def render_saved_pimcore_templates(product_values: object, values: object, targets: object) -> dict[str, object]:
    settings_payload = _active_pimcore_runtime_settings()
    selected = [str(item) for item in targets] if isinstance(targets, list) else None
    return _render_templates(settings_payload, product_values, values, selected)
```

- [ ] **Step 5: Add thin FastAPI routes**

Import the three adapters and `TemplateError` in `picorgftp_sql/web/app.py`, then register:

```python
@app.post("/api/settings/pimcore/template-preview")
async def pimcore_template_preview_api(request: Request) -> JSONResponse:
    _require_admin(request)
    try:
        return JSONResponse(await run_in_threadpool(preview_pimcore_template, await request.json()))
    except (TemplateError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={
            "code": getattr(exc, "code", "invalid_template"),
            "message": str(exc),
            "position": getattr(exc, "position", 0),
        }) from exc


@app.post("/api/settings/pimcore/test-sample")
async def pimcore_test_sample_api(request: Request) -> JSONResponse:
    _require_admin(request)
    return JSONResponse(await run_in_threadpool(pimcore_test_sample))


@app.post("/api/pimcore/render-templates")
async def pimcore_render_templates_api(request: Request) -> JSONResponse:
    _require_user(request)
    payload = await request.json()
    source = payload if isinstance(payload, dict) else {}
    try:
        result = await run_in_threadpool(
            render_saved_pimcore_templates,
            source.get("product_values"),
            source.get("values"),
            source.get("targets"),
        )
    except (TemplateError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)
```

- [ ] **Step 6: Run backend tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_pimcore_templates.py tests/test_translation_service.py tests/test_pimcore_config.py tests/test_pimcore_service.py tests/test_pimcore_web.py -q
```

Expected: all focused backend tests pass.

- [ ] **Step 7: Commit backend integration**

```powershell
git add picorgftp_sql/services/pimcore_service.py picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_pimcore_service.py tests/test_pimcore_web.py
git commit -m "feat: expose pimcore template rendering"
```

## Task 6: Pimcore Settings Template Builder

**Files:**
- Modify: `picorgftp_sql/web/static/index.html:369-505`
- Modify: `picorgftp_sql/web/static/app.js:1-270,6374-6460,6950-7010,7607-7720`
- Modify: `picorgftp_sql/web/static/app.css:1870-2000,2270-2390`
- Modify: `tests/test_web_ui_integrity.py:570-690`
- Modify: `tests/test_source_integrity.py:430-510`

- [ ] **Step 1: Write failing UI integrity tests**

Add assertions that describe the builder without depending on browser internals:

```python
def test_pimcore_template_builder_has_sources_functions_preview_and_translation():
    root = Path(__file__).resolve().parents[1]
    html = (root / "picorgftp_sql/web/static/index.html").read_text(encoding="utf-8")
    js = (root / "picorgftp_sql/web/static/app.js").read_text(encoding="utf-8")
    assert 'id="pimcoreTemplateModal"' in html
    assert 'id="pimcoreTemplateText"' in html
    assert 'id="pimcoreTemplatePreview"' in html
    assert 'id="pimcoreTemplateTranslate"' in html
    assert 'id="pimcoreTemplateLanguage"' in html
    assert "openPimcoreTemplateBuilder" in js
    assert "previewPimcoreTemplate" in js
    assert "value_template" in js
    assert "target_language" in js


def test_pimcore_mapping_collects_template_metadata():
    source = (Path(__file__).resolve().parents[1] / "picorgftp_sql/web/static/app.js").read_text(encoding="utf-8")
    assert "row.dataset.valueTemplate" in source
    assert "row.dataset.translate" in source
    assert "row.dataset.targetLanguage" in source
```

- [ ] **Step 2: Run UI tests and verify RED**

Run:

```powershell
python -m pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py -q
```

Expected: failures show the missing builder modal and metadata.

- [ ] **Step 3: Add the template modal and DOM references**

Add this nested modal beside the existing Pimcore setup/test modals in `index.html`:

```html
<div id="pimcoreTemplateModal" class="modal-view nested-modal">
  <section class="manager-panel pimcore-template-panel">
    <div class="section-heading">
      <div><h1>Buduj tekst Pimcore</h1><span id="pimcoreTemplateTarget"></span></div>
      <button id="pimcoreTemplateCancelButton" type="button" class="ghost-button modal-close">Anuluj</button>
    </div>
    <div class="pimcore-template-layout">
      <aside>
        <input id="pimcoreTemplateSourceFilter" autocomplete="off" placeholder="Szukaj placeholdera">
        <div id="pimcoreTemplateSources" class="pimcore-template-palette"></div>
        <div id="pimcoreTemplateFunctions" class="pimcore-template-palette"></div>
      </aside>
      <section>
        <label>Szablon<textarea id="pimcoreTemplateText" rows="7"></textarea></label>
        <button id="pimcoreTemplateGroupButton" type="button" class="secondary-button">Dodaj grupe warunkowa</button>
        <label><input id="pimcoreTemplateTranslate" type="checkbox"> Tlumacz wynik</label>
        <label>Jezyk docelowy<input id="pimcoreTemplateLanguage" autocomplete="off"></label>
        <pre id="pimcoreTemplatePreview" class="result-output empty-state">Brak podgladu.</pre>
        <span id="pimcoreTemplateStatus" role="status"></span>
      </section>
    </div>
    <div class="heading-actions">
      <button id="pimcoreTemplateSaveButton" type="button">Zastosuj szablon</button>
    </div>
  </section>
</div>
```

Add state (`pimcoreTemplateEditor: null`) and DOM references at the top of `app.js`.

- [ ] **Step 4: Persist template metadata on mapping rows**

In both compact/setup mapping row constructors, assign:

```javascript
row.dataset.valueTemplate = mapping.value_template || "";
row.dataset.translate = mapping.translate === true ? "true" : "false";
row.dataset.targetLanguage = mapping.target_language || mapping.language || "";
```

Add a `Buduj tekst` button for supported `input`, `textarea`, and `select` fields. Its click handler collects the current mapping rows and calls `openPimcoreTemplateBuilder(row, mappings)`.

When collecting rows, include:

```javascript
value_template: row.dataset.valueTemplate || "",
translate: row.dataset.translate === "true",
target_language: row.dataset.targetLanguage || null,
```

- [ ] **Step 5: Implement builder editing and backend preview**

Add these browser contracts in `app.js`:

```javascript
function insertAtCursor(input, text) {
  const start = input.selectionStart ?? input.value.length;
  const end = input.selectionEnd ?? start;
  input.setRangeText(text, start, end, "end");
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.focus();
}

function currentProductTemplateValues() {
  return {
    name: productForm.elements.name?.value || "",
    type: productForm.elements.type_name?.value || "",
    model: productForm.elements.model?.value || "",
    color1: productForm.elements.color1?.value || "",
    color2: productForm.elements.color2?.value || "",
    color3: productForm.elements.color3?.value || "",
    extra: productForm.elements.extra?.value || "",
    ean: productForm.elements.ean?.value || "",
  };
}

function pimcoreTemplateSourceItems(mappings) {
  const products = [
    ["PRODUCT:NAME", "NAZWA"], ["PRODUCT:TYPE", "TYP"], ["PRODUCT:MODEL", "MODEL"],
    ["PRODUCT:COLOR1", "KOLOR 1"], ["PRODUCT:COLOR2", "KOLOR 2"],
    ["PRODUCT:COLOR3", "KOLOR 3"], ["PRODUCT:EXTRA", "DODATEK"], ["PRODUCT:EAN", "EAN"],
  ].map(([token, label]) => ({ token, label, provider: "Produkt" }));
  const pimcore = mappings
    .filter((item) => item.source)
    .map((item) => ({
      token: `PIMCORE:${item.source}`,
      label: item.label || item.source,
      provider: "Pimcore",
    }));
  return [...products, ...pimcore];
}

function openPimcoreTemplateBuilder(row, mappings) {
  state.pimcoreTemplateEditor = { row, mappings, sources: pimcoreTemplateSourceItems(mappings) };
  pimcoreTemplateTarget.textContent = row.querySelector('[name="mapping_label"]')?.value || row.dataset.source || "Pole";
  pimcoreTemplateText.value = row.dataset.valueTemplate || "";
  pimcoreTemplateTranslate.checked = row.dataset.translate === "true";
  pimcoreTemplateLanguage.value = row.dataset.targetLanguage || row.dataset.fieldLanguage || "";
  renderPimcoreTemplatePalette();
  pimcoreTemplateModal.classList.add("active");
  previewPimcoreTemplate();
}

function renderPimcoreTemplatePalette() {
  const editor = state.pimcoreTemplateEditor;
  const query = pimcoreTemplateSourceFilter.value.trim().toLowerCase();
  pimcoreTemplateSources.textContent = "";
  for (const item of editor?.sources || []) {
    const label = item.label || item.token || "";
    if (query && !label.toLowerCase().includes(query)) continue;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary-button";
    button.textContent = `${item.provider}: {${label}}`;
    button.addEventListener("click", () => insertAtCursor(pimcoreTemplateText, `{${item.token}}`));
    pimcoreTemplateSources.appendChild(button);
  }
  pimcoreTemplateFunctions.textContent = "";
  for (const name of ["keep", "trim", "normalize_spaces", "upper", "lower", "title", "capitalize", "replace:\"old\",\"new\"", "default:\"text\"", "substring:0,10", "truncate:30,\"...\"", "strip_diacritics", "slug", "number:2,\",\",\" \""]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary-button";
    button.textContent = name;
    button.addEventListener("click", () => insertAtCursor(pimcoreTemplateText, `|${name}`));
    pimcoreTemplateFunctions.appendChild(button);
  }
}

async function previewPimcoreTemplate() {
  const editor = state.pimcoreTemplateEditor;
  if (!editor) return;
  const mappings = editor.mappings.map((item) => ({ ...item }));
  const target = editor.row.querySelector('[name="mapping_source"]')?.value.trim() || editor.row.dataset.source;
  const selected = mappings.find((item) => item.source === target);
  if (selected) {
    selected.value_template = pimcoreTemplateText.value;
    selected.translate = pimcoreTemplateTranslate.checked;
    selected.target_language = pimcoreTemplateLanguage.value.trim() || null;
  }
  try {
    const result = await requestJson("/api/settings/pimcore/template-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mappings, target_source: target, product_values: currentProductTemplateValues(), values: {} }),
    });
    pimcoreTemplatePreview.className = "result-output";
    pimcoreTemplatePreview.textContent = result.values?.[target] ?? "";
    pimcoreTemplateStatus.textContent = (result.warnings || []).map((item) => item.message).join(" | ");
  } catch (error) {
    pimcoreTemplatePreview.className = "result-output empty-state";
    pimcoreTemplatePreview.textContent = "Brak poprawnego podgladu.";
    pimcoreTemplateStatus.textContent = error.message;
  }
}

let pimcoreTemplatePreviewTimer = 0;
function schedulePimcoreTemplatePreview() {
  window.clearTimeout(pimcoreTemplatePreviewTimer);
  pimcoreTemplatePreviewTimer = window.setTimeout(previewPimcoreTemplate, 250);
}

pimcoreTemplateSourceFilter?.addEventListener("input", renderPimcoreTemplatePalette);
pimcoreTemplateText?.addEventListener("input", schedulePimcoreTemplatePreview);
pimcoreTemplateTranslate?.addEventListener("change", schedulePimcoreTemplatePreview);
pimcoreTemplateLanguage?.addEventListener("input", schedulePimcoreTemplatePreview);
pimcoreTemplateGroupButton?.addEventListener("click", () => {
  const start = pimcoreTemplateText.selectionStart ?? 0;
  const end = pimcoreTemplateText.selectionEnd ?? start;
  const selected = pimcoreTemplateText.value.slice(start, end) || "{PLACEHOLDER}";
  pimcoreTemplateText.setRangeText(`(${selected})`, start, end, "select");
  schedulePimcoreTemplatePreview();
});
pimcoreTemplateSaveButton?.addEventListener("click", () => {
  const row = state.pimcoreTemplateEditor?.row;
  if (!row) return;
  row.dataset.valueTemplate = pimcoreTemplateText.value;
  row.dataset.translate = pimcoreTemplateTranslate.checked ? "true" : "false";
  row.dataset.targetLanguage = pimcoreTemplateLanguage.value.trim();
  pimcoreTemplateModal.classList.remove("active");
  state.pimcoreTemplateEditor = null;
});
pimcoreTemplateCancelButton?.addEventListener("click", () => {
  pimcoreTemplateModal.classList.remove("active");
  state.pimcoreTemplateEditor = null;
});
```

The event handlers debounce preview by 250 ms. Save copies the three values into row datasets and closes; cancel closes without mutation. Group insertion wraps the selected text or inserts `({PLACEHOLDER})` when no selection exists.

- [ ] **Step 6: Style the builder responsively**

Add:

```css
.pimcore-template-panel { width: min(1100px, calc(100vw - 32px)); }
.pimcore-template-layout { display: grid; grid-template-columns: minmax(220px, 320px) minmax(0, 1fr); gap: 16px; }
.pimcore-template-layout > aside,
.pimcore-template-layout > section { display: grid; align-content: start; gap: 10px; min-width: 0; }
.pimcore-template-palette { display: flex; flex-wrap: wrap; gap: 6px; max-height: 220px; overflow: auto; }
.pimcore-template-palette button { max-width: 100%; overflow-wrap: anywhere; }
#pimcoreTemplateText { width: 100%; min-height: 140px; font-family: Consolas, monospace; }
@media (max-width: 700px) { .pimcore-template-layout { grid-template-columns: 1fr; } }
```

- [ ] **Step 7: Run UI tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py -q
```

Expected: all UI integrity tests pass.

- [ ] **Step 8: Commit the settings builder**

```powershell
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py tests/test_source_integrity.py
git commit -m "feat: add pimcore template builder UI"
```

## Task 7: Runtime Samples, Create Rendering, Reliable Edit Modal, And Layout

**Files:**
- Modify: `picorgftp_sql/web/static/index.html:64-80,395-495`
- Modify: `picorgftp_sql/web/static/app.js:1-270,7170-7605,8067-8140,8375-8390`
- Modify: `picorgftp_sql/web/static/app.css:478-505,1950-1990,2290-2380`
- Modify: `tests/test_web_ui_integrity.py:570-720`
- Modify: `tests/test_source_integrity.py:430-530`

- [ ] **Step 1: Write failing runtime and layout integrity tests**

Add:

```python
def test_pimcore_test_form_loads_samples_and_can_regenerate():
    root = Path(__file__).resolve().parents[1]
    html = (root / "picorgftp_sql/web/static/index.html").read_text(encoding="utf-8")
    js = (root / "picorgftp_sql/web/static/app.js").read_text(encoding="utf-8")
    assert 'id="pimcoreTestRegenerateButton"' in html
    assert 'requestJson("/api/settings/pimcore/test-sample"' in js
    assert "populatePimcoreRuntimeForm" in js


def test_edit_modal_opens_before_fetch_and_guards_stale_responses():
    source = (Path(__file__).resolve().parents[1] / "picorgftp_sql/web/static/app.js").read_text(encoding="utf-8")
    start = source.index("async function openPimcoreEditModal")
    request = source.index("requestJson(`/api/pimcore/products/", start)
    opened = source.index('pimcoreEditModal.classList.add("active")', start)
    assert opened < request
    assert "pimcoreEditRequestId" in source[start:source.index("function closePimcoreEditModal", start)]
    assert "Przelicz pole" in source


def test_lookup_actions_wrap_without_fixed_edit_width():
    css = (Path(__file__).resolve().parents[1] / "picorgftp_sql/web/static/app.css").read_text(encoding="utf-8")
    block = re.search(r"(?s)\.lookup-actions\s*\{(.*?)\}", css).group(1)
    assert "flex-wrap: wrap" in block
    assert "grid-template-columns: repeat(3" not in block
    assert ".lookup-actions #pimcoreEditButton" not in css or "min-width: 170px" not in css


def test_pimcore_url_example_is_only_a_placeholder():
    source = (Path(__file__).resolve().parents[1] / "picorgftp_sql/web/static/app.js").read_text(encoding="utf-8")
    assert "http://10.10.0.5" not in source
    assert 'placeholder: "http://twoj-adres-pimcore.example"' in source
```

- [ ] **Step 2: Run runtime UI tests and verify RED**

Run:

```powershell
python -m pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py -q
```

Expected: failures show empty test-create, delayed modal opening, and fixed-width overflow CSS.

- [ ] **Step 3: Build reusable runtime fields and load test samples**

Add `pimcoreTestRegenerateButton` beside clear in `index.html`. Replace duplicated create/edit/test field construction with:

```javascript
function populatePimcoreRuntimeForm(form, schema, values, { readOnlyEan = false, recalculate = false } = {}) {
  form.textContent = "";
  for (const mapping of schema || []) {
    const label = document.createElement("label");
    const title = document.createElement("span");
    const row = document.createElement("span");
    const input = document.createElement("input");
    title.textContent = `${mapping.label || mapping.source}${mapping.required ? " *" : ""}`;
    input.name = mapping.source;
    input.value = values?.[mapping.source] ?? mapping.default ?? "";
    input.required = Boolean(mapping.required);
    input.autocomplete = "off";
    if (mapping.source === "EAN" && readOnlyEan) input.readOnly = true;
    row.className = "pimcore-runtime-input-row";
    row.appendChild(input);
    if (recalculate && mapping.value_template) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary-button";
      button.textContent = "Przelicz pole";
      button.addEventListener("click", () => recalculatePimcoreEditField(mapping.source));
      row.appendChild(button);
    }
    label.append(title, row);
    form.appendChild(label);
  }
}

async function loadPimcoreTestSample({ confirmReplace = false } = {}) {
  if (confirmReplace && state.pimcoreTestDirty && !window.confirm("Zastapic aktualne dane nowymi przykladami?")) return;
  pimcoreTestStatus.textContent = "Generowanie danych testowych...";
  const result = await requestJson("/api/settings/pimcore/test-sample", { method: "POST" });
  populatePimcoreRuntimeForm(pimcoreTestForm, result.form_schema, result.values);
  state.pimcoreTestDirty = false;
  pimcoreTestStatus.textContent = (result.warnings || []).map((item) => item.message).join(" | ");
}

async function openPimcoreWriteTest() {
  if (!pimcoreTestForm || !pimcoreTestModal) return;
  pimcoreTestModal.classList.add("active");
  pimcoreTestForm.textContent = "Generowanie danych testowych...";
  pimcoreTestModal.querySelectorAll('[name="pimcore_cleanup_policy"]').forEach((item) => {
    item.checked = false;
  });
  clearPimcoreLiveLog();
  pimcoreTestSubmitButton.disabled = true;
  pimcoreTestClearButton.disabled = true;
  try {
    await loadPimcoreTestSample();
    pimcoreTestSubmitButton.disabled = false;
    pimcoreTestClearButton.disabled = false;
  } catch (error) {
    pimcoreTestForm.textContent = "";
    pimcoreTestStatus.textContent = `Nie mozna wygenerowac danych: ${error.message}`;
  }
}

pimcoreTestForm?.addEventListener("input", () => {
  state.pimcoreTestDirty = true;
});
pimcoreTestRegenerateButton?.addEventListener("click", () => {
  loadPimcoreTestSample({ confirmReplace: true }).catch((error) => {
    pimcoreTestStatus.textContent = error.message;
  });
});
```

Add `pimcoreTestDirty: false` to state. The replacement opens immediately and loads values asynchronously. Regeneration confirms only after a user edit. Clear retains its current reset meaning.

- [ ] **Step 4: Render saved templates before showing create fields**

Reuse `currentProductTemplateValues()` from Task 6 and add:

```javascript
async function renderSavedPimcoreTemplates(values, targets = null) {
  return requestJson("/api/pimcore/render-templates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_values: currentProductTemplateValues(), values, targets }),
  });
}

async function openPimcoreCreateModal(ean) {
  if (!pimcoreCreateForm || !pimcoreCreateModal) return;
  const seeded = Object.fromEntries(
    (state.pimcoreCreateSchema || []).map((mapping) => [
      mapping.source,
      mapping.source === "EAN" ? ean : mapping.default || "",
    ])
  );
  pimcoreMissingModal?.classList.remove("active");
  pimcoreCreateModal.classList.add("active");
  pimcoreCreateForm.textContent = "Budowanie danych produktu...";
  pimcoreCreateSubmitButton.disabled = true;
  pimcoreCreateStatus.textContent = "";
  try {
    const rendered = await renderSavedPimcoreTemplates(seeded);
    populatePimcoreRuntimeForm(
      pimcoreCreateForm,
      state.pimcoreCreateSchema,
      rendered.values,
      { readOnlyEan: true }
    );
    pimcoreCreateStatus.textContent = (rendered.warnings || []).map((item) => item.message).join(" | ");
  } catch (error) {
    populatePimcoreRuntimeForm(
      pimcoreCreateForm,
      state.pimcoreCreateSchema,
      seeded,
      { readOnlyEan: true }
    );
    pimcoreCreateStatus.textContent = `Nie mozna zbudowac szablonow: ${error.message}`;
  } finally {
    pimcoreCreateSubmitButton.disabled = false;
  }
}
```

Replace the existing `openPimcoreCreateModal(ean)` with this asynchronous version. Translation warnings remain visible without disabling submit; a rendering failure falls back to editable defaults and EAN.

- [ ] **Step 5: Open edit immediately, guard stale requests, and recalculate explicitly**

Add `pimcoreEditRequestId: 0` to state. Replace `openPimcoreEditModal()` with the following flow:

```javascript
async function openPimcoreEditModal() {
  const objectId = Number(state.pimcoreExistingObject?.id || 0);
  if (objectId <= 0 || !pimcoreEditForm || !pimcoreEditModal) {
    formStatus.textContent = "Nie mozna edytowac produktu Pimcore bez poprawnego ID.";
    return;
  }
  const requestId = ++state.pimcoreEditRequestId;
  pimcoreEditModal.classList.add("active");
  pimcoreEditForm.textContent = "Ladowanie danych Pimcore...";
  pimcoreEditStatus.textContent = "";
  pimcoreEditSubmitButton.disabled = true;
  if (pimcoreEditButton) pimcoreEditButton.disabled = true;
  try {
    const payload = await requestJson(`/api/pimcore/products/${encodeURIComponent(objectId)}`);
    if (requestId !== state.pimcoreEditRequestId || !pimcoreEditModal.classList.contains("active")) return;
    state.pimcoreEditObjectId = Number(payload.object?.id || objectId);
    state.pimcoreEditMarker = String(payload.marker || "");
    state.pimcoreEditSchema = Array.isArray(payload.form_schema) ? payload.form_schema : [];
    populatePimcoreRuntimeForm(pimcoreEditForm, state.pimcoreEditSchema, payload.values, {
      readOnlyEan: true,
      recalculate: true,
    });
    pimcoreEditObjectInfo.textContent = [`ID ${state.pimcoreEditObjectId}`, payload.object?.path || ""].filter(Boolean).join(" - ");
    pimcoreEditSubmitButton.disabled = false;
  } catch (error) {
    if (requestId !== state.pimcoreEditRequestId) return;
    pimcoreEditForm.textContent = "";
    const retry = document.createElement("button");
    retry.type = "button";
    retry.textContent = "Sprobuj ponownie";
    retry.addEventListener("click", openPimcoreEditModal);
    pimcoreEditForm.appendChild(retry);
    pimcoreEditStatus.textContent = `Nie mozna pobrac danych Pimcore: ${error.message}`;
  } finally {
    if (requestId === state.pimcoreEditRequestId && pimcoreEditButton) {
      pimcoreEditButton.disabled = !state.pimcoreExistingObject?.id;
    }
  }
}

async function recalculatePimcoreEditField(source) {
  const values = Object.fromEntries(new FormData(pimcoreEditForm).entries());
  const result = await renderSavedPimcoreTemplates(values, [source]);
  const input = pimcoreEditForm.elements[source];
  if (input) input.value = result.values?.[source] ?? input.value;
  pimcoreEditStatus.textContent = (result.warnings || []).map((item) => item.message).join(" | ");
}
```

Increment `state.pimcoreEditRequestId` in `closePimcoreEditModal()` and whenever EAN/product state resets. In `checkPimcoreProductStatus()`, enable edit only when `Number(payload.object?.id || 0) > 0`; otherwise show a malformed-response error.

- [ ] **Step 6: Replace overflowing action CSS**

Use:

```css
.lookup-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.lookup-actions > button {
  flex: 1 1 140px;
  min-width: 0;
  max-width: 100%;
}

.pimcore-runtime-input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.pimcore-runtime-input-row input { flex: 1 1 auto; min-width: 0; }
.pimcore-runtime-input-row button { flex: 0 0 auto; }
```

Delete the existing `.lookup-actions #pimcoreEditButton { min-width: 170px; }` rule. At `max-width: 540px`, set `.lookup-actions > button { flex-basis: 100%; width: 100%; }`.

- [ ] **Step 7: Remove UI URL value fallbacks**

Before changing cache versions, remove both UI value fallbacks. Extend `pimcoreSetupInput()` with an optional placeholder:

```javascript
function pimcoreSetupInput(name, labelText, value = "", type = "text", placeholder = "") {
  const label = document.createElement("label");
  const title = document.createElement("span");
  const input = document.createElement("input");
  title.textContent = labelText;
  input.name = name;
  input.type = type;
  input.value = value || "";
  input.placeholder = placeholder;
  input.autocomplete = type === "password" ? "new-password" : "off";
  label.append(title, input);
  return label;
}
```

Render the setup and compact controls with an empty value plus a display-only example:

```javascript
pimcoreSetupInput(
  "base_url",
  "Adres Pimcore",
  setup.settings.base_url || "",
  "text",
  "http://twoj-adres-pimcore.example"
)

inputField("base_url", "Adres Pimcore", pimcore.base_url || "", {
  placeholder: "http://twoj-adres-pimcore.example",
})
```

Confirm that no JavaScript fallback contains `http://10.10.0.5`.

- [ ] **Step 8: Update cache-busting versions**

Change both static asset query strings in `index.html` from `20260702-pimcore-setup` to `20260703-pimcore-templates` so deployed browsers load the new JS/CSS.

- [ ] **Step 9: Run runtime UI and backend tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_pimcore_web.py tests/test_web_ui_integrity.py tests/test_source_integrity.py -q
```

Expected: all focused runtime/UI tests pass.

- [ ] **Step 10: Commit runtime UX fixes**

```powershell
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py tests/test_source_integrity.py
git commit -m "fix: make pimcore runtime forms reliable"
```

## Task 8: Documentation And Full Regression Verification

**Files:**
- Modify: `README.md:13-40`
- Modify: any existing Pimcore test fixture whose exact normalized mapping assertion requires the three new backward-compatible keys.

- [ ] **Step 1: Update user-facing Pimcore documentation**

Add concise examples to `README.md`:

```markdown
### Szablony wartości Pimcore

W mapowaniu tekstowego pola wybierz `Buduj tekst`. Szablon może łączyć tekst i dane produktu, np. `{NAZWA} - {TYP} {KOLOR 1}(/{KOLOR 2})`. Fragment w nawiasach znika razem z separatorami, gdy jego placeholder jest pusty. Dostępne są kontrolowane funkcje, np. `{MODEL|trim|replace:"_"," "|upper}`.

Testowe dodawanie generuje przy każdym otwarciu nowe edytowalne przykłady. Tworzenie produktu przelicza zapisane szablony automatycznie; edycja istniejącego produktu robi to tylko po `Przelicz pole`. Opcjonalne tłumaczenie pozostawia tekst źródłowy i ostrzeżenie, gdy provider jest niedostępny.

Wyszukiwanie EAN obejmuje całą wybraną klasę Pimcore. Folder wskazany w ustawieniach służy wyłącznie jako parent nowo tworzonych obiektów.
```

- [ ] **Step 2: Run focused tests**

Run:

```powershell
python -m pytest tests/test_pimcore_templates.py tests/test_translation_service.py tests/test_pimcore_config.py tests/test_pimcore_operations.py tests/test_pimcore_service.py tests/test_pimcore_web.py tests/test_web_ui_integrity.py tests/test_source_integrity.py -q
```

Expected: exit code 0 and no failures.

- [ ] **Step 3: Run the complete test suite**

Run:

```powershell
python -m pytest -q
```

Expected: exit code 0 and no failures.

- [ ] **Step 4: Run syntax and whitespace checks**

Run:

```powershell
python -m compileall -q picorgftp_sql
git diff --check
```

Expected: both commands exit 0 with no output.

- [ ] **Step 5: Perform browser smoke verification**

Run the web application with its existing launcher and verify these exact scenarios in a desktop browser and a viewport below 540 px:

1. `Edytuj dane Pimcore` stays inside `Produkt` and never overlaps `Sloty`.
2. Clicking edit immediately opens a loading modal; a forced fetch failure appears inside it with retry.
3. Test-create opens with fresh values in every field, allows edits, and regenerates only after confirmation.
4. The agreed color template includes `/` only when color 2 exists.
5. Create applies templates automatically; edit changes nothing until `Przelicz pole` is pressed.
6. A simulated translation failure leaves the source text editable with a warning.
7. Empty Pimcore settings show `http://twoj-adres-pimcore.example` only as a placeholder.

Expected: every scenario behaves as listed with no console errors or horizontal page overflow.

- [ ] **Step 6: Commit documentation and final fixture adjustments**

```powershell
git add README.md tests/test_pimcore_config.py tests/test_pimcore_service.py tests/test_pimcore_web.py tests/test_web_ui_integrity.py tests/test_source_integrity.py
git commit -m "docs: describe pimcore value templates"
```

- [ ] **Step 7: Confirm final repository state**

Run:

```powershell
git status --short
git log -8 --oneline
```

Expected: no unintended working-tree changes; the task commits are visible in order.
