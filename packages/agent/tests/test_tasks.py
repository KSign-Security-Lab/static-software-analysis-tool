"""The task index in pyproject.toml, and the script that reads it.

``scripts/ssat.sh`` parses ``[tool.tasks]`` with awk, because it has to work
before any venv exists and the system interpreter here predates ``tomllib``.
Awk is not a TOML parser, so the thing worth testing is that it agrees with one:
a quoting edge case that silently dropped a task would leave the listing
claiming something that cannot be run.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
MANIFEST = REPO / "pyproject.toml"
RUNNER = REPO / "scripts" / "ssat.sh"

ANSI = re.compile(r"\033\[[0-9;]*m")


def declared_tasks() -> dict[str, str]:
    with MANIFEST.open("rb") as handle:
        return dict(tomllib.load(handle).get("tool", {}).get("tasks", {}))


def run_script(*args: str, manifest: Path | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    if not RUNNER.exists() or shutil.which("bash") is None:
        pytest.skip("scripts/ssat.sh or bash is unavailable")
    env = None
    if manifest is not None:
        env = {**os.environ, "SSAT_MANIFEST": str(manifest)}
    return subprocess.run(
        ["bash", str(RUNNER), *args],
        cwd=cwd or REPO,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


@pytest.fixture(scope="module")
def parsed() -> dict[str, str]:
    """What the awk parser sees: name -> description."""
    result = run_script("--list-tasks")
    assert result.returncode == 0, result.stderr
    rows = [line.split("\t", 1) for line in result.stdout.splitlines() if line.strip()]
    return {name: (rest[0] if rest else "") for name, *rest in rows}


def test_the_manifest_declares_tasks() -> None:
    assert declared_tasks(), "[tool.tasks] is empty or missing"


def test_awk_and_tomllib_agree_on_the_task_names(parsed: dict[str, str]) -> None:
    """The awk parser must neither skip an entry nor invent one."""
    assert set(parsed) == set(declared_tasks())


def test_every_task_has_a_description(parsed: dict[str, str]) -> None:
    """The comment above an entry is its description; a missing one shows as a
    blank column and makes the listing useless."""
    for name, desc in parsed.items():
        assert len(desc.strip()) > 5, f"{name} has no description in {MANIFEST.name}"


def test_the_listing_shows_every_task_and_every_stack_action() -> None:
    """The menu is how these are found, so nothing runnable may be missing."""
    result = run_script("--help")
    assert result.returncode == 0, result.stderr
    listing = ANSI.sub("", result.stdout)
    for name in declared_tasks():
        assert re.search(rf"^  {re.escape(name)}\s", listing, re.M), f"{name} is not in the listing"
    for action in ("up", "down", "delete", "status", "logs"):
        assert re.search(rf"^  {action}\s", listing, re.M), f"stack action {action} is not in the listing"


def test_an_unknown_task_fails_loudly() -> None:
    result = run_script("definitely-not-a-task")
    assert result.returncode != 0
    assert "unknown task" in result.stderr


def test_the_script_holds_no_task_definitions_of_its_own(tmp_path: Path) -> None:
    """One source of truth. Pointed at a manifest it has never seen, the script
    must list and run whatever that manifest declares -- which it cannot do if
    the commands are baked into the dispatcher."""
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[tool.tasks]\n# an invented task, declared nowhere else\nfabricated = "echo made-up-output"\n')

    listed = run_script("--list-tasks", manifest=manifest)
    assert listed.stdout.strip() == "fabricated\tan invented task, declared nowhere else"

    ran = run_script("fabricated", manifest=manifest)
    assert ran.returncode == 0, ran.stderr
    assert "made-up-output" in ran.stdout


def test_referenced_scripts_exist() -> None:
    """A task pointing at a missing file is a listing that lies."""
    for name, command in declared_tasks().items():
        for token in command.split():
            if token.startswith("scripts/") and token.endswith(".sh"):
                assert (REPO / token).exists(), f"task {name} references missing {token}"
