"""Pytest configuration and fixtures."""

import json
import os
from pathlib import Path
from typing import Any, Dict

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def c_sources_dir(fixtures_dir: Path) -> Path:
    """Return path to C sources directory."""
    return fixtures_dir / "c_sources"


@pytest.fixture
def cpg_dir(fixtures_dir: Path) -> Path:
    """Return path to CPG fixtures directory."""
    return fixtures_dir / "cpg"


@pytest.fixture
def expected_dir(fixtures_dir: Path) -> Path:
    """Return path to expected outputs directory."""
    return fixtures_dir / "expected"


@pytest.fixture
def monorepo_root() -> Path:
    """Find and return monorepo root."""
    current = Path(__file__).parent
    while current != current.parent:
        if (current / "package.json").exists():
            return current
        current = current.parent
    return Path.cwd()


@pytest.fixture
def nodejs_core_path(monorepo_root: Path) -> Path:
    """Return path to Node.js core package."""
    return monorepo_root / "packages" / "core"


@pytest.fixture
def python_core_path(monorepo_root: Path) -> Path:
    """Return path to Python core package."""
    return monorepo_root / "py-packages" / "core"


def load_json_file(file_path: Path) -> Any:
    """Load JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_file(data: Any, file_path: Path) -> None:
    """Save data as JSON file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

