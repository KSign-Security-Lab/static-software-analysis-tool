"""JSON file utilities."""

import json
import os
from pathlib import Path
from typing import Any, List


def list_json_files(dir_path: str) -> List[str]:
    """
    Recursively collects all .json file paths under a directory.

    Args:
        dir_path: Root directory to scan.

    Returns:
        Array of full file paths to .json files.
    """
    paths: List[str] = []
    dir_path_obj = Path(dir_path)

    if not dir_path_obj.exists():
        return paths

    for entry in dir_path_obj.rglob("*.json"):
        if entry.is_file():
            paths.append(str(entry.absolute()))

    return paths


def read_long_json_files(file_path: str) -> Any:
    """
    Reads a single JSON file from `file_path` and deserializes it.

    Note: Python version doesn't use V8 serialization like Node.js.
    This function reads standard JSON files.

    Args:
        file_path: Full path to a JSON file.

    Returns:
        The deserialized value.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_files(data_array: List[Any], file_paths: List[str]) -> List[str]:
    """
    Writes each item in `data_array` as a JSON file to the corresponding path in `file_paths`.

    Args:
        data_array: Array of JSON-serializable values.
        file_paths: Array of full file paths (same length as `data_array`).

    Returns:
        An array of full file paths that were written.

    Raises:
        ValueError: If data_array and file_paths have different lengths.
    """
    if len(data_array) != len(file_paths):
        raise ValueError("Length of data_array and file_paths must match.")

    output_paths: List[str] = []

    for item, target_path in zip(data_array, file_paths):
        target_path_clean = target_path.strip()
        dir_path = os.path.dirname(target_path_clean)

        os.makedirs(dir_path, exist_ok=True)

        with open(target_path_clean, "w", encoding="utf-8") as f:
            json.dump(item, f, indent=2)

        output_paths.append(target_path_clean)

    return output_paths


def write_long_json_files(data: Any, file_path: str) -> str:
    """
    Serializes `data` as JSON and writes it to `file_path`. Creates directories as needed.

    Note: Python version uses standard JSON instead of V8 binary format.
    For very large files, consider using a streaming JSON writer.

    Args:
        data: Any JSON-serializable value (object, array, etc.).
        file_path: Full path (including filename) where the JSON will be written.

    Returns:
        The same `file_path` string, for convenience.
    """
    dir_path = os.path.dirname(file_path)
    os.makedirs(dir_path, exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return file_path

