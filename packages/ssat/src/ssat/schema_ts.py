"""Generate the TypeScript view of the F2-A result models.

The web app used to mirror these by hand. It had already drifted: ``F2AResult``
was missing four of its eleven fields, so ``flow_candidates``,
``sink_mappings``, ``expected_check_matchings`` and
``missing_check_candidate_sets`` were simply invisible to the UI -- and
invisible in a way TypeScript cannot report, because a field absent from an
interface is not a type error at the point it is read.

Regenerate with::

    python -m ssat.schema_ts --write

Unlike the agent schema, this one is generated with ``all_present``: it is a
response the server only ever writes, every field carries a pydantic default,
and without the flag every property renders optional and every read downstream
needs a ``?? []`` -- across five hundred lines of decision.ts, for values that
are always serialised.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from schemagen import render as render_ts, schemas_of

from .f2a.models import F2AResult

HEADER = """\
// GENERATED FILE -- DO NOT EDIT.
//
// The F2-A result models are defined in packages/ssat/src/ssat/f2a/models.py.
// This file is generated from them by `python -m ssat.schema_ts --write`, and
// packages/ssat/tests/test_schema_ts.py fails if the two drift apart.
"""

#: Where the generated file lands, relative to the repo root.
OUTPUT_PATH = Path("web") / "lib" / "f2a-schema.ts"


def render() -> str:
    """The full generated TypeScript source."""
    return render_ts(schemas_of([F2AResult]), HEADER, all_present=True)


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
    parser = argparse.ArgumentParser(prog="ssat.schema_ts", description=__doc__)
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
