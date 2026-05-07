"""Comparison utilities for test outputs."""

import json
from typing import Any, Dict, List, Optional, Tuple

from deepdiff import DeepDiff


def normalize_json(data: Any) -> Any:
    """
    Normalize JSON data for comparison.

    - Sorts lists of dictionaries by a stable key if possible
    - Removes None values
    - Normalizes numeric types
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            normalized = normalize_json(value)
            if normalized is not None:
                result[key] = normalized
        return result
    elif isinstance(data, list):
        normalized_list = [normalize_json(item) for item in data if normalize_json(item) is not None]
        # Try to sort if all items are dicts with a common key
        if normalized_list and all(isinstance(item, dict) for item in normalized_list):
            # Try common sort keys
            for sort_key in ["id", "sid", "name", "code"]:
                if all(sort_key in item for item in normalized_list):
                    normalized_list = sorted(normalized_list, key=lambda x: (x.get(sort_key), json.dumps(x, sort_keys=True)))
                    break
        return normalized_list
    elif isinstance(data, (int, float)):
        # Normalize to int if it's a whole number
        if isinstance(data, float) and data.is_integer():
            return int(data)
        return data
    else:
        return data


def compare_outputs(
    nodejs_output: Any,
    python_output: Any,
    tolerance: float = 1e-6,
    ignore_order: bool = True,
) -> Tuple[bool, List[str]]:
    """
    Compare Node.js and Python outputs.

    Args:
        nodejs_output: Output from Node.js version
        python_output: Output from Python version
        tolerance: Numeric tolerance for comparison
        ignore_order: Whether to ignore order in lists

    Returns:
        Tuple of (is_equal, list_of_differences)
    """
    # Normalize both outputs
    norm_nodejs = normalize_json(nodejs_output)
    norm_python = normalize_json(python_output)

    # Use DeepDiff for comparison
    diff = DeepDiff(
        norm_nodejs,
        norm_python,
        ignore_order=ignore_order,
        ignore_numeric_type_changes=True,
        significant_digits=6,
        verbose_level=2,
    )

    if not diff:
        return True, []

    # Format differences
    differences: List[str] = []
    for change_type, changes in diff.items():
        if change_type == "dictionary_item_added":
            for item in changes:
                differences.append(f"Added in Python: {item}")
        elif change_type == "dictionary_item_removed":
            for item in changes:
                differences.append(f"Removed in Python: {item}")
        elif change_type == "values_changed":
            for path, change in changes.items():
                differences.append(f"Value changed at {path}: {change.get('old_value')} -> {change.get('new_value')}")
        elif change_type == "iterable_item_added":
            for item in changes:
                differences.append(f"Item added in Python: {item}")
        elif change_type == "iterable_item_removed":
            for item in changes:
                differences.append(f"Item removed in Python: {item}")
        else:
            differences.append(f"{change_type}: {changes}")

    return False, differences


def compare_graphs(
    nodejs_graph: Dict[str, Any],
    python_graph: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """
    Compare graph structures (nodes and edges).

    Args:
        nodejs_graph: Graph from Node.js
        python_graph: Graph from Python

    Returns:
        Tuple of (is_equal, list_of_differences)
    """
    differences: List[str] = []

    # Compare node counts
    nodejs_nodes = nodejs_graph.get("nodes", [])
    python_nodes = python_graph.get("nodes", [])
    if len(nodejs_nodes) != len(python_nodes):
        differences.append(f"Node count mismatch: Node.js={len(nodejs_nodes)}, Python={len(python_nodes)}")

    # Compare edge counts
    nodejs_edges = nodejs_graph.get("edges", [])
    python_edges = python_graph.get("edges", [])
    if len(nodejs_edges) != len(python_edges):
        differences.append(f"Edge count mismatch: Node.js={len(nodejs_edges)}, Python={len(python_edges)}")

    # Compare structure
    is_equal, struct_diffs = compare_outputs(nodejs_graph, python_graph, ignore_order=True)
    differences.extend(struct_diffs)

    return is_equal and len(differences) == 0, differences

