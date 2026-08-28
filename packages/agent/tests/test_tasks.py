"""The task index in pyproject.toml, and the script that reads it.

``scripts/run.sh`` parses ``[tool.tasks]`` with awk, because it has to work
before any venv exists and the system interpreter here predates ``tomllib``.
Awk is not a TOML parser, so the thing worth testing is that it agrees with one:
a quoting edge case that silently dropped a task would leave the listing
claiming something that cannot be run.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
MANIFEST = REPO / "pyproject.toml"
RUNNER = REPO / "scripts" / "run.sh"


def declared_tasks() -> dict[str, str]:
    with MANIFEST.open("rb") as handle:
        return dict(tomllib.load(handle).get("tool", {}).get("tasks", {}))


@pytest.fixture(scope="module")
def listing() -> str:
    if not RUNNER.exists() or shutil.which("bash") is None:
        pytest.skip("scripts/run.sh or bash is unavailable")
    result = subprocess.run(["bash", str(RUNNER)], cwd=REPO, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_the_manifest_declares_tasks() -> None:
    assert declared_tasks(), "[tool.tasks] is empty or missing"


def test_the_listing_shows_every_declared_task(listing: str) -> None:
    """The awk parser must not silently skip an entry."""
    missing = [name for name in declared_tasks() if name not in listing]
    assert missing == [], f"declared but not listed by scripts/run.sh: {missing}"


def test_the_listing_invents_nothing(listing: str) -> None:
    """And must not show a task that cannot be run."""
    body = listing.split("tasks", 1)[-1]
    shown = {
        line.strip().split()[0].replace("\033[36m", "").strip()
        for line in body.splitlines()
        if line.startswith("  ") and line.strip()
    }
    shown = {name for name in shown if name.isidentifier() or "-" in name}
    unknown = shown - set(declared_tasks()) - {"Web-only"}
    assert unknown == set(), f"listed but not declared: {unknown}"


def test_every_task_has_a_description(listing: str) -> None:
    """The comment above an entry is its description; a missing one shows as a
    blank column and makes the listing useless."""
    for name in declared_tasks():
        row = next((line for line in listing.splitlines() if f"{name} " in line and line.startswith("  ")), "")
        assert row, f"{name} is not in the listing"
        remainder = row.split(name, 1)[-1].replace("\033[0m", "").strip()
        assert len(remainder) > 5, f"{name} has no description in [tool.tasks]"


def test_an_unknown_task_fails_loudly() -> None:
    result = subprocess.run(
        ["bash", str(RUNNER), "definitely-not-a-task"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "unknown task" in result.stderr


def test_the_runner_holds_no_task_definitions_of_its_own() -> None:
    """One source of truth. If commands creep back into the script, the manifest
    stops being the list."""
    source = RUNNER.read_text(encoding="utf-8")
    body = source.split("main() {", 1)[0]
    for name, command in declared_tasks().items():
        first_word = command.split()[0]
        assert f'"{name}"' not in body.replace('"$wanted"', ""), f"{name} looks hard-coded in run.sh"
        assert first_word not in body or first_word in {"cd", "uv"}, (
            f"the command for {name} appears in run.sh; it belongs in {MANIFEST.name}"
        )


def test_referenced_scripts_exist() -> None:
    """A task pointing at a missing file is a listing that lies."""
    for name, command in declared_tasks().items():
        for token in command.split():
            if token.startswith("scripts/") and token.endswith(".sh"):
                assert (REPO / token).exists(), f"task {name} references missing {token}"
