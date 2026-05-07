"""Utility functions for SSAT.

Merges utilities from core/utils and the standalone utils package.
"""

import json
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Callable, Dict, List

# Re-export submodule utilities
from .path_resolver import get_path, get_validated_path
from .tree_to_text import TreeToText


def multiprocess(func: Callable[[Any], Any], args: List[Any], num_processes: int) -> List[Any]:
    """Run a function in parallel across multiple processes."""
    with Pool(num_processes) as p:
        return p.map(func, args)


def read_json(file_path: str | Path) -> Dict[str, Any]:
    """Read a JSON file and return its contents as a dictionary."""
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def recursively_get_json_files(directory: str | Path) -> List[Path]:
    """Recursively find all JSON files in a directory."""
    return list(Path(directory).rglob("*.json"))


def get_functions_from_template(template: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Recursively extract function definitions from template nodes.

    Args:
        template: List of template nodes to search.

    Returns:
        List of function definition nodes.
    """
    functions: List[Dict[str, Any]] = []
    for node in template:
        node_type = node.get("nodeType")
        if node_type in ("FunctionDefinition", "FunctionDeclaration"):
            functions.append(node)

        children = node.get("children")
        if isinstance(children, list) and children:
            functions.extend(get_functions_from_template(children))

    return functions
