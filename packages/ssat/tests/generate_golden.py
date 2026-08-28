"""Regenerate the legacy-chain golden snapshots.

    python packages/ssat/tests/generate_golden.py

Run this only when a behaviour change is *intended*, and review the resulting
diff -- these files are the safety net for the refactor.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from legacy_chain import (  # noqa: E402
    GOLDEN_DIR,
    all_fixtures,
    build_graphs,
    dump,
    golden_path,
)


def main() -> int:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for fixture in all_fixtures():
        snapshot = build_graphs(fixture)
        out = golden_path(fixture)
        out.write_text(dump(snapshot), encoding="utf-8")
        functions = snapshot["functions"]
        ast_nodes = sum(len(f["ast"]["nodes"]) for f in functions)
        dfg_edges = sum(len(f["dfg"].get("edges_dfg", [])) for f in functions)
        print(f"{out.name:<50} {len(functions):>2} fn  {ast_nodes:>4} ast nodes  {dfg_edges:>4} dfg edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
