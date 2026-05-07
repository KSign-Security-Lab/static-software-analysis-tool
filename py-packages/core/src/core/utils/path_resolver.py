"""Robust Path Resolution Utility for Python."""

from pathlib import Path
from typing import Dict

# Get the repository root
def get_repo_root() -> Path:
    """Get the absolute path to the repository root."""
    # Get the directory of this file
    current_file = Path(__file__)
    # Navigate up: py-packages/core/src/core/utils -> py-packages/core/src/core -> 
    # py-packages/core/src -> py-packages/core -> py-packages -> repo root
    return current_file.parent.parent.parent.parent.parent.parent


def get_packages_dir() -> Path:
    """Get the absolute path to the packages directory."""
    return get_repo_root() / "packages"


def get_py_packages_dir() -> Path:
    """Get the absolute path to the py-packages directory."""
    return get_repo_root() / "py-packages"


def get_core_dir() -> Path:
    """Get the absolute path to the core package directory."""
    return get_py_packages_dir() / "core"


# Predefined paths
PATHS: Dict[str, Path] = {
    "AST_EXTRACTOR": get_core_dir() / "src" / "core" / "ast" / "extractor.py",
    "DFG_EXTRACTOR": get_core_dir() / "src" / "core" / "dfg" / "python" / "DFGExtractor.py",
}


def get_path(key: str) -> str:
    """Get a path without validation."""
    return str(PATHS.get(key, Path("")))


async def get_validated_path(key: str) -> str:
    """Get a validated path for a commonly used file."""
    path = PATHS.get(key)
    if path is None:
        raise ValueError(f"Unknown path key: {key}")
    if not path.exists():
        raise FileNotFoundError(f"{key.replace('_', ' ').lower()} not found at: {path}")
    return str(path)


