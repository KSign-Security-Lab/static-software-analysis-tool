# graph — Function-level AST/DFG Extractor (Python)

Generates per-function AST and DFG artifacts from Template JSON inputs. Preserves input directory structure and can emit Notion-friendly Markdown alongside JSON.

## What It Does

- Recursively finds functions in Template graphs and extracts:
  - AST via `ASTExtractorV1_12`
  - DFG via `DFGExtractorV1_12`
- Writes one output per function with stable filenames
- Optional Markdown emission with code + AST + DFG blocks

## Environment Setup (uv only)

- Python >= 3.14
- Managed with `pyproject.toml` (uv build backend)
- Depends on the `utils` workspace package

```bash
cd packages/graph
uv sync
```

## Usage

CLI entrypoint (defined in `pyproject.toml`):

```bash
# From repo root or the package directory
uv run dfg --data path/to/template_jsons --save results --emit-md
```

Key options:

- `--data`     Directory with Template JSON files (required)
- `--save`     Output directory (default: `results`)
- `--emit-md`  Also emit a `.md` file per function (optional)
- `--keep-name` Keep original filename without appending function name

Outputs (per input file and function):

- `<base>__<function>.dfg.json` with fields: `code`, `ast`, `dfg`, `template`
- Optional `<base>__<function>.md` with code/AST/DFG sections

## Architecture

- `graph/__init__.py` — CLI, file walking, per-function processing
- `graph/ast.py`       — ASTExtractorV1_12 wrapper
- `graph/dfg.py`       — DFGExtractorV1_12 wrapper
- `utils` workspace    — JSON IO, recursive Template scanning, multiprocessing

## Notes

- Skips the `main` function by default
- Ensures filenames are sanitized and de-duplicated when repeated

## Scripts

```bash
# Exposed by pyproject.toml
uv run dfg --data <template_dir> --save <output_dir> [--emit-md] [--keep-name]
```
