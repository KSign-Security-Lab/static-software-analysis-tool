from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Sequence


class UnsupportedSchema(ValueError):
    pass


_PRIMITIVES = {"string": "string", "integer": "number", "number": "number", "boolean": "boolean", "null": "null"}


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _type_of(schema: Mapping[str, Any]) -> str:
    if "$ref" in schema:
        return _ref_name(schema["$ref"])

    if "const" in schema:
        return json.dumps(schema["const"])

    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])

    if "anyOf" in schema:
        return " | ".join(_type_of(option) for option in schema["anyOf"])

    kind = schema.get("type")
    if kind == "array":
        return f"{_type_of(schema.get('items', {}))}[]"
    if isinstance(kind, str) and kind in _PRIMITIVES:
        return _PRIMITIVES[kind]
    if isinstance(kind, list):
        return " | ".join(_PRIMITIVES[k] for k in kind)

    raise UnsupportedSchema(f"unsupported schema node, refusing to emit `any`: {schema!r}")


def _interface(name: str, schema: Mapping[str, Any], all_present: bool) -> str:
    required = set(schema.get("required", []))
    lines = [f"export interface {name} {{"]
    for field, definition in schema.get("properties", {}).items():
        description = definition.get("description")
        if description:
            lines.append(f"  /** {description} */")
        optional = "" if all_present or field in required else "?"
        lines.append(f"  {field}{optional}: {_type_of(definition)};")
    lines.append("}")
    return "\n".join(lines)


def render(
    roots: Sequence[tuple[str, Mapping[str, Any]]],
    header: str,
    extras: str | None = None,
    all_present: bool = False,
) -> str:
    definitions: dict[str, Mapping[str, Any]] = {}
    tops: list[tuple[str, Mapping[str, Any]]] = []

    for name, schema in roots:
        body = dict(schema)
        for defined, definition in body.pop("$defs", {}).items():
            definitions.setdefault(defined, definition)
        tops.append((name, body))

    emitted: set[str] = set()
    blocks: list[str] = []

    for name, definition in sorted(definitions.items()):
        if name not in emitted:
            emitted.add(name)
            blocks.append(_interface(name, definition, all_present))
    for name, definition in tops:
        if name not in emitted:
            emitted.add(name)
            blocks.append(_interface(name, definition, all_present))

    if extras:
        blocks.append(extras)
    return header + "\n" + "\n\n".join(blocks) + "\n"


def schemas_of(models: Iterable[Any]) -> list[tuple[str, Mapping[str, Any]]]:
    return [(model.__name__, model.model_json_schema(ref_template="#/$defs/{model}")) for model in models]
