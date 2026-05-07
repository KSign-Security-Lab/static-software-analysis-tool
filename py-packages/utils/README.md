# utils — Shared Python Utilities

Utility functions used by Python packages in this repo (e.g., `packages/graph`). Provides simple JSON IO, directory walking, Template function discovery, and lightweight multiprocessing helpers.

## What It Does

- `multiprocess(func, args, num_processes)` — Map a function across inputs with `multiprocessing.Pool`
- `read_json(path)` — Load JSON file into Python dict
- `recursvely_get_json_files(dir)` — Find all `.json` files under a directory
- `recursivelyGetFunctionsFromTemplate(template)` — Extract function nodes from Template structures

## Environment Setup (uv only)

- Python >= 3.14
- Managed with `pyproject.toml` (uv build backend)

```bash
cd packages/utils
uv sync
```

## Usage

Example usage inside another package:

```python
from utils import recursvely_get_json_files, read_json

files = recursvely_get_json_files("data/templates")
obj = read_json(files[0])
```

## Notes

- The function discovery assumes a KAST-style Template with `nodeType` and `children` fields.
