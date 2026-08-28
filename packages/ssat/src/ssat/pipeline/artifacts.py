"""Write per-function analysis results to disk.

Ported from the old ``ssat.graph`` package, which mixed this file-walking and
output-formatting with its own argparse CLI. The CLI lives in :mod:`ssat.cli`;
this module is just the writer, so both the CLI and library callers can use it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from . import FunctionGraphs, analyze_template, training_record

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str, fallback: str, max_len: int = 120) -> str:
    """Make a filesystem-safe path component."""
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", name or "").strip("._-")
    if not cleaned:
        cleaned = _UNSAFE_FILENAME_CHARS.sub("_", fallback or "fn")
    return cleaned[:max_len]


def to_markdown(code: str, ast_obj: Any, dfg_obj: Any) -> str:
    """Render a Notion-friendly markdown section: code, AST, DFG."""
    code_str = code if isinstance(code, str) else ""
    ast_json = json.dumps(ast_obj, ensure_ascii=False, indent=2)
    dfg_json = json.dumps(dfg_obj, ensure_ascii=False, indent=2)
    return f"""### Code
```c
{code_str}
```

### AST
```json
{ast_json}
```

### DFG
```json
{dfg_json}
```
"""


def write_function_artifacts(
    graphs: List[FunctionGraphs],
    out_dir: Path,
    stem: str,
    *,
    emit_md: bool = False,
    keep_name: bool = False,
) -> List[Path]:
    """Write one JSON (and optionally one .md) per function. Returns paths written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    name_counts: Dict[str, int] = {}

    for index, fn in enumerate(graphs):
        safe_fn = sanitize_filename(fn.name, fallback=f"function_{index}")
        seen = name_counts.get(safe_fn, 0)
        name_counts[safe_fn] = seen + 1
        suffix = f"_{seen}" if seen else ""

        base = out_dir / (f"{stem}{suffix}" if keep_name else f"{stem}__{safe_fn}{suffix}")

        out_json = base.with_suffix(".dfg.json")
        out_json.write_text(
            json.dumps(training_record(fn), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        written.append(out_json)

        if emit_md:
            out_md = base.with_suffix(".md")
            out_md.write_text(to_markdown(fn.code, fn.ast, fn.dfg), encoding="utf-8")
            written.append(out_md)

    return written


def process_template_file(
    template_path: Path,
    data_root: Path,
    save_root: Path,
    *,
    emit_md: bool = False,
    keep_name: bool = False,
) -> List[Path]:
    """Analyse one template JSON file and write per-function artifacts."""
    template_json = json.loads(template_path.read_text(encoding="utf-8"))
    template = template_json if isinstance(template_json, list) else [template_json]

    relative = template_path.relative_to(data_root)
    graphs = analyze_template(template, source=str(relative))

    return write_function_artifacts(
        graphs,
        save_root / relative.parent,
        template_path.stem,
        emit_md=emit_md,
        keep_name=keep_name,
    )
