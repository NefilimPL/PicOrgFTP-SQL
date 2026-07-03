from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import csv
import io
import re
import unicodedata
from typing import Callable, Iterable


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
    parts: list[str] = []
    current: list[str] = []
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
        row = next(
            csv.reader(
                io.StringIO(value),
                skipinitialspace=True,
                escapechar="\\",
            )
        )
    except (csv.Error, StopIteration) as exc:
        raise TemplateError(
            "invalid_arguments",
            "Niepoprawne argumenty funkcji.",
            position,
        ) from exc
    return tuple(row)


def _placeholder(content: str, position: int) -> PlaceholderNode:
    parts = _split_quoted(content, "|")
    source = parts[0].strip()
    if not source:
        raise TemplateError(
            "empty_placeholder",
            "Placeholder nie ma zrodla.",
            position,
        )
    functions: list[FunctionCall] = []
    for raw in parts[1:]:
        name = _split_quoted(raw, ":")[0].strip().lower()
        argument_text = raw[len(name) + 1 :] if ":" in raw else ""
        functions.append(FunctionCall(name, _arguments(argument_text, position)))
    return PlaceholderNode(source, tuple(functions), position)


class _Parser:
    def __init__(self, template: str):
        if len(template) > MAX_TEMPLATE_LENGTH:
            raise TemplateError(
                "template_too_long",
                "Szablon jest za dlugi.",
                MAX_TEMPLATE_LENGTH,
            )
        self.template = template
        self.index = 0

    def parse(self) -> tuple[object, ...]:
        nodes = self._sequence("", 0)
        if self.index != len(self.template):
            raise TemplateError(
                "unexpected_closing",
                "Nieoczekiwany znak zamykajacy.",
                self.index,
            )
        return nodes

    def _sequence(self, closing: str, depth: int) -> tuple[object, ...]:
        if depth > MAX_TEMPLATE_DEPTH:
            raise TemplateError(
                "nesting_too_deep",
                "Za duzo zagniezdzonych grup.",
                self.index,
            )
        nodes: list[object] = []
        literal: list[str] = []
        while self.index < len(self.template):
            char = self.template[self.index]
            if closing and char == closing:
                break
            if char == "\\":
                self.index += 1
                if self.index >= len(self.template):
                    raise TemplateError(
                        "dangling_escape",
                        "Pusty znak ucieczki.",
                        self.index - 1,
                    )
                literal.append(self.template[self.index])
                self.index += 1
                continue
            if char == "{":
                if literal:
                    nodes.append(LiteralNode("".join(literal)))
                    literal = []
                nodes.append(self._read_placeholder())
                continue
            if char == "(":
                if literal:
                    nodes.append(LiteralNode("".join(literal)))
                    literal = []
                start = self.index
                self.index += 1
                children = self._sequence(")", depth + 1)
                if self.index >= len(self.template):
                    raise TemplateError(
                        "unclosed_group",
                        "Niezamknieta grupa warunkowa.",
                        start,
                    )
                self.index += 1
                if not any(
                    isinstance(node, (PlaceholderNode, GroupNode))
                    for node in children
                ):
                    raise TemplateError(
                        "condition_without_placeholder",
                        "Grupa nie zawiera placeholdera.",
                        start,
                    )
                nodes.append(GroupNode(children, start))
                continue
            if char in ")}":
                raise TemplateError(
                    "unexpected_closing",
                    "Nieoczekiwany znak zamykajacy.",
                    self.index,
                )
            literal.append(char)
            self.index += 1
        if literal:
            nodes.append(LiteralNode("".join(literal)))
        return tuple(nodes)

    def _read_placeholder(self) -> PlaceholderNode:
        start = self.index
        self.index += 1
        content: list[str] = []
        quote = ""
        escaped = False
        while self.index < len(self.template):
            char = self.template[self.index]
            if escaped:
                content.append(char)
                escaped = False
            elif char == "\\":
                content.append(char)
                escaped = True
            elif quote:
                content.append(char)
                if char == quote:
                    quote = ""
            elif char in {'"', "'"}:
                content.append(char)
                quote = char
            elif char == "}":
                self.index += 1
                return _placeholder("".join(content), start)
            else:
                content.append(char)
            self.index += 1
        raise TemplateError(
            "unclosed_placeholder",
            "Niezamkniety placeholder.",
            start,
        )


def parse_template(template: object) -> tuple[object, ...]:
    return _Parser(str(template or "")).parse()


def _case_shortcut(source: str, calls: Iterable[FunctionCall]) -> str:
    if any(
        call.name in {"keep", "upper", "lower", "title", "capitalize"}
        for call in calls
    ):
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
    known = {
        "keep",
        "trim",
        "normalize_spaces",
        "upper",
        "lower",
        "title",
        "capitalize",
        "replace",
        "default",
        "substring",
        "truncate",
        "strip_diacritics",
        "slug",
        "number",
    }
    if name not in known:
        raise TemplateError(
            "unknown_function",
            f"Nieznana funkcja {name}.",
            position,
        )
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
            if len(args) == 1:
                return value[start:]
            return value[start : start + int(args[1])]
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
            return (
                rendered.replace(",", "\x00")
                .replace(".", decimal_separator)
                .replace("\x00", group_separator)
            )
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise TemplateError(
            "invalid_arguments",
            f"Niepoprawne argumenty funkcji {name}.",
            position,
        ) from exc
    raise TemplateError(
        "invalid_arguments",
        f"Niepoprawne argumenty funkcji {name}.",
        position,
    )


def render_template(template: object, resolver: Callable[[str], object]) -> str:
    def render_nodes(nodes: tuple[object, ...]) -> tuple[str, list[str]]:
        output: list[str] = []
        resolved: list[str] = []
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
                value, group_values = render_nodes(node.children)
                output.append(
                    value if group_values and all(item.strip() for item in group_values) else ""
                )
                resolved.extend(group_values)
        text = "".join(output)
        if len(text) > MAX_OUTPUT_LENGTH:
            raise TemplateError(
                "output_too_long",
                "Wynik szablonu jest za dlugi.",
                MAX_OUTPUT_LENGTH,
            )
        return text, resolved

    return render_nodes(parse_template(template))[0]


def placeholder_sources(template: object) -> tuple[str, ...]:
    sources: list[str] = []

    def visit(nodes: tuple[object, ...]) -> None:
        for node in nodes:
            if isinstance(node, PlaceholderNode) and node.source not in sources:
                sources.append(node.source)
            elif isinstance(node, GroupNode):
                visit(node.children)

    visit(parse_template(template))
    return tuple(sources)
