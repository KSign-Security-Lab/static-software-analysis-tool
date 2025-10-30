# @ssat/cli — Command Line Interface

Developer-focused CLI to run the SSAT pipeline and related utilities from the terminal. It wraps `@ssat/core` functionality and provides consistent file/directory processing with progress and structured outputs.

## What It Does

- Generate CPG, Template, AST, and DFG artifacts from C code and intermediate JSONs
- Process single files or entire directories while preserving structure
- Save per-function outputs for AST/Template where useful
- Provide predictable filenames without intermediate index files

## Environment Setup

- Node.js >= 18.17 < 23
- Joern 4.0.361+ available when running full C→CPG
- Python 3.x (used by core via subprocess for AST/DFG steps; no HTTP server)
Install at repo root:

```bash
yarn install
```

Optional: start Joern via Docker (from repo root):

```bash
yarn docker:up     # Ensure Joern container is ready
```

## Commands

- `cpg` — Generate Code Property Graph from C source
- `template` — Generate Template from CPG JSON
- `ast` — Generate AST per function from Template JSON
- `dfg` — Generate DFG using CPG + AST
- `template-functions` — Extract and save each function node from Template JSON
## Recent Changes

### 1) Per‑Function Outputs (without index files)

- For `ast`:
  - Each function’s AST result is saved as `<base>_<functionName>_ast.json`.
  - Function name is derived from the first node’s `code` formatted as `<entry:NAME>`. Fallback: `func_<index>`.
- For `template-functions`:
  - Each Template function node is saved as `<base>_<functionName>_template.json`.
  - Function name comes from the node’s `name` field. Fallback: `func_<index>`.
- Index files are NO LONGER written.

### 2) Unified Single-File Processing

- Introduced a common helper `processSingleFile(...)` used for both directory and single-file modes.
- All mode branching (cpg/template/ast/dfg/template-functions) and writing is handled in one place.

### 3) Robust Path Resolution (Core)

- The CLI uses core’s endpoint APIs which internally rely on a robust path resolver for Python tools and data.
- This avoids failures when the current working directory changes.

## Usage Examples

Generate AST per function:

```bash
yarn generate:ast --data <template_dir_or_file> --output <out_dir>
```

Outputs:

```
<out_dir>/<subdirs>/<base>_<functionName>_ast.json
```

Extract Template functions (recursively):

```bash
yarn template-functions --data <template_dir_or_file> --output <out_dir>
```

Outputs:

```
<out_dir>/<subdirs>/<base>_<functionName>_template.json
```

Generate DFG:

```bash
yarn generate:dfg --data <cpg_dir_or_file> --output <out_dir>
```

## Typical Pipelines (step-by-step)

```bash
# 1) End-to-end from C sources or precomputed CPG JSON
#    - If you pass .c files: the CLI generates CPG via Docker Joern
#    - If you pass .json files: they must be CPG JSON (not Template JSON)
yarn generate:full --data path/to/input --output result/full_out

# 2) Manual step-through to inspect intermediates
yarn generate:cpg --data path/to/c/sources --output result/cpg_out
yarn generate:template --data result/cpg_out --output result/template_out
yarn generate:ast --data result/template_out --output result/ast_out
yarn generate:dfg --data result/template_out --output result/dfg_out

# 3) Extract per-function Template or AST files
yarn template-functions --data result/template_out --output result/template_funcs
yarn generate:ast --data result/template_out --output result/ast_per_fn
```

Notes:
- Output paths are created if missing; relative subfolders are preserved

Generate CPG end-to-end from C sources:

```bash
yarn generate:cpg --data path/to/src --output result/cpg_out
```

Run the full pipeline (C→CPG→Template→AST→DFG):

```bash
yarn generate:full --data path/to/src --output result/full_out
```

## Architecture

- Thin CLI layer (Commander) calls into `@ssat/core/endpoint` functions
- Shared path resolution in `@ssat/core/utils/pathResolver` avoids CWD issues
- Directory traversal preserves relative structure under `--output`

## Tips

- Use `--workers` for parallelism when supported
- Use `--keep-intermediate` to inspect intermediate artifacts

## Scripts

```bash
# From repo root (recommended):
yarn generate:cpg
yarn generate:template
yarn generate:template:functions
yarn generate:ast
yarn generate:dfg
yarn generate:full

# Or directly in the workspace:
yarn workspace @ssat/cli generate:cpg
yarn workspace @ssat/cli generate:template
yarn workspace @ssat/cli generate:template:functions
yarn workspace @ssat/cli generate:ast
yarn workspace @ssat/cli generate:dfg
yarn workspace @ssat/cli generate:full

# Discover CLI scripts with descriptions:
yarn workspace @ssat/cli scripts:help
```

## Notes

- Directory mode preserves relative subdirectory structure under `--output`.
- Single-file mode writes alongside the corresponding relative path under `--output`.
- No index files are produced; filenames are deterministic and discoverable by listing the output directory.
