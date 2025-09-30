# SSAT CLI

This package provides the command-line interface to generate and transform artifacts in the Static Software Analysis Tool (SSAT).

## Commands

- `cpg` — Generate Code Property Graph from C source.
- `template` — Generate Template artifacts from CPG JSON.
- `ast` — Generate AST results from Template (per function in the input Template).
- `dfg` — Generate DFG results using CPG + AST.
- `template-functions` — NEW: Extract and save each function node from the Template by recursively scanning the Template tree.

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

## Notes

- Directory mode preserves relative subdirectory structure under `--output`.
- Single-file mode writes alongside the corresponding relative path under `--output`.
- No index files are produced; filenames are deterministic and discoverable by listing the output directory.
