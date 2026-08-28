"""Generate the TypeScript view of the wire schema from the pydantic models.

The schema is defined once, in :mod:`agent.schema`. Hand-writing the matching
TypeScript would create a second definition that drifts the first time a field
is added -- silently, because a missing optional field in TS is not a type
error. So the TS is generated, checked in, and a test asserts the checked-in
file still matches. Regenerate with::

    python -m agent.schema_ts --write

The rendering itself lives in :mod:`schemagen`, because ``ssat`` needs the same
thing for the F2-A models and ``agent`` may not import ``ssat`` or the reverse.
This module is the part that is specific to this schema: which models, which
header, and the two UI helpers that are not schema at all.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from schemagen import render as render_ts, schemas_of

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

EXTRAS = """\
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
    """The full generated TypeScript source.

    ``all_present`` is deliberately left off here: these are read *and*
    written by the client, and the drift test pins this output byte for byte.
    """
    return render_ts(schemas_of(EXPORTED_MODELS), HEADER, EXTRAS)


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
