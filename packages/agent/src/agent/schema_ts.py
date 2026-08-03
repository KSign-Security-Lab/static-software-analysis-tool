"""Generate the TypeScript view of the wire schema from the pydantic models.

The schema is defined once, in :mod:`agent.schema`. Hand-writing the matching
TypeScript would create a second definition that drifts the first time a field
is added -- silently, because a missing optional field in TS is not a type
error. So the TS is generated, checked in, and a test asserts the checked-in
file still matches. Regenerate with::

    python -m agent.schema_ts --write

Only the subset of JSON Schema the wire models actually use is handled --
objects, ``$ref``, arrays, string/number/boolean/null, enums and
``anyOf`` nullables. Anything else raises rather than emitting ``any``, because
an ``any`` here is exactly the drift this file exists to prevent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .schema import EXPORTED_MODELS

HEADER = """\
// GENERATED FILE -- DO NOT EDIT.
//
// The wire schema is defined in packages/agent/src/agent/schema.py. This file
// is generated from it by `python -m agent.schema_ts --write`, and
// packages/agent/tests/test_schema.py fails if the two drift apart.
"""

#: Where the generated file lands, relative to the repo root.
OUTPUT_PATH = Path("web") / "lib" / "agent-schema.ts"

_PRIMITIVES = {"string": "string", "integer": "number", "number": "number", "boolean": "boolean", "null": "null"}


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _type_of(schema: dict[str, Any]) -> str:
    """One JSON-Schema node as a TypeScript type expression."""
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

    raise ValueError(f"unsupported schema node, refusing to emit `any`: {schema!r}")


def _interface(name: str, schema: dict[str, Any]) -> str:
    required = set(schema.get("required", []))
    lines = [f"export interface {name} {{"]
    for field, definition in schema.get("properties", {}).items():
        description = definition.get("description")
        if description:
            lines.append(f"  /** {description} */")
        optional = "" if field in required else "?"
        lines.append(f"  {field}{optional}: {_type_of(definition)};")
    lines.append("}")
    return "\n".join(lines)


def _severity_helpers() -> str:
    """Hand-maintained extras that are genuinely UI concerns, not schema."""
    return """\
export const SEVERITIES = ["critical", "high", "medium", "low", "info"] as const;

export type SeverityName = (typeof SEVERITIES)[number];

/** Rank for sorting: lower is more severe. Mirrors SEVERITY_ORDER in schema.py. */
export const SEVERITY_RANK: Record<SeverityName, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};
"""


def render() -> str:
    """The full generated TypeScript source."""
    definitions: dict[str, dict[str, Any]] = {}
    roots: list[tuple[str, dict[str, Any]]] = []

    for model in EXPORTED_MODELS:
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        for name, definition in schema.pop("$defs", {}).items():
            definitions.setdefault(name, definition)
        roots.append((model.__name__, schema))

    emitted: set[str] = set()
    blocks: list[str] = []

    # Dependencies first, so the file reads top-down.
    for name, definition in sorted(definitions.items()):
        if name not in emitted:
            emitted.add(name)
            blocks.append(_interface(name, definition))
    for name, definition in roots:
        if name not in emitted:
            emitted.add(name)
            blocks.append(_interface(name, definition))

    blocks.append(_severity_helpers())
    return HEADER + "\n" + "\n\n".join(blocks) + "\n"


def repo_root() -> Path:
    """Walk up to the directory holding the workspace pyproject."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists() and (parent / "web").is_dir():
            return parent
    raise RuntimeError("could not locate the repo root")


def output_path() -> Path:
    return repo_root() / OUTPUT_PATH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent.schema_ts", description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write the file rather than printing it")
    args = parser.parse_args(argv)

    rendered = render()
    if not args.write:
        print(rendered, end="")
        return 0

    destination = output_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8")
    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
