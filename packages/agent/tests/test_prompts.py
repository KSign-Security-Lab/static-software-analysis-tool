"""Tuned prompts: stored beside the runs, read at run time, revertible.

The point of the override store is that tuning a prompt against a real trace
changes what later runs do, without editing tracked source and without a bad
save being a code change.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent import promptstore
from agent.promptstore import DEFAULTS, NAMES, UnknownPrompt


def test_nothing_saved_means_the_shipped_prompts(tmp_path: Path) -> None:
    path = tmp_path / "prompts.json"

    assert promptstore.load(path) == {}
    assert promptstore.resolve(path) == DEFAULTS
    # Never written just by being read: an unconfigured install stays clean.
    assert not path.exists()


def test_a_saved_prompt_shadows_the_default(tmp_path: Path) -> None:
    path = tmp_path / "prompts.json"
    promptstore.save(path, "lens:memory", "Only report memory errors.")

    resolved = promptstore.resolve(path)
    assert resolved["lens:memory"] == "Only report memory errors."
    # The others are untouched, so tuning one call does not disturb the rest.
    assert resolved["verify"] == DEFAULTS["verify"]
    assert resolved["gather"] == DEFAULTS["gather"]


def test_clearing_puts_the_default_back(tmp_path: Path) -> None:
    path = tmp_path / "prompts.json"
    promptstore.save(path, "verify", "Refute everything.")
    promptstore.clear(path, "verify")

    assert promptstore.resolve(path)["verify"] == DEFAULTS["verify"]
    assert promptstore.load(path) == {}


def test_clearing_a_prompt_that_was_never_tuned_is_fine(tmp_path: Path) -> None:
    path = tmp_path / "prompts.json"
    promptstore.clear(path, "lens:memory")

    assert promptstore.resolve(path) == DEFAULTS


def test_an_empty_prompt_is_refused(tmp_path: Path) -> None:
    """Far likelier a cleared textarea than an instruction to say nothing, and
    the run it would produce could not be explained."""
    path = tmp_path / "prompts.json"

    with pytest.raises(ValueError):
        promptstore.save(path, "lens:memory", "   \n ")
    assert promptstore.resolve(path) == DEFAULTS


@pytest.mark.parametrize("name", ["analyze", "", "ANALYSE", "system"])
def test_an_unknown_prompt_name_is_refused(tmp_path: Path, name: str) -> None:
    """Saving under a typo would be a silent no-op that looks like it worked."""
    with pytest.raises(UnknownPrompt):
        promptstore.save(tmp_path / "prompts.json", name, "text")
    with pytest.raises(UnknownPrompt):
        promptstore.clear(tmp_path / "prompts.json", name)


def test_a_corrupt_store_falls_back_rather_than_failing_the_run(tmp_path: Path) -> None:
    """A run that behaves as shipped is a far better failure than one that
    refuses to start because a JSON file was hand-edited."""
    path = tmp_path / "prompts.json"
    path.write_text("{not json at all", encoding="utf-8")

    assert promptstore.load(path) == {}
    assert promptstore.resolve(path) == DEFAULTS


def test_junk_entries_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "prompts.json"
    path.write_text('{"lens:memory": "kept", "nope": "x", "verify": 12, "gather": "  "}', encoding="utf-8")

    resolved = promptstore.resolve(path)
    assert resolved["lens:memory"] == "kept"
    assert resolved["verify"] == DEFAULTS["verify"]
    assert resolved["gather"] == DEFAULTS["gather"]
    assert "nope" not in resolved


def test_describe_carries_both_the_default_and_the_tuning(tmp_path: Path) -> None:
    """The editor needs both to offer a revert and to show what changed."""
    path = tmp_path / "prompts.json"
    promptstore.save(path, "lens:memory", "tuned")

    described = {row["name"]: row for row in promptstore.describe(path)}
    assert set(described) == set(NAMES)
    assert described["lens:memory"]["override"] == "tuned"
    assert described["lens:memory"]["in_use"] == "tuned"
    assert described["lens:memory"]["default"] == DEFAULTS["lens:memory"]
    assert described["verify"]["override"] is None
    assert described["verify"]["in_use"] == DEFAULTS["verify"]


def test_a_run_uses_the_tuned_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point: what is saved here is what the next run is given."""
    from agent.config import ENV_PROMPTS_FILE, AgentConfig
    from agent.graph.session import InspectionSession
    from agent.index import ChunkStore, build_index

    path = tmp_path / "prompts.json"
    monkeypatch.setenv(ENV_PROMPTS_FILE, str(path))
    promptstore.save(path, "lens:memory", "Report only command injection.")

    root = tmp_path / "src"
    root.mkdir()
    (root / "a.c").write_text("void f(void) { }\n", encoding="utf-8")
    store = ChunkStore(tmp_path / "index.db")
    build_index(root, store)

    class Recording:
        def __init__(self) -> None:
            self.systems: list[str] = []

        def call(self, schema, system, user, trace=None):  # noqa: ANN001
            self.systems.append(system)
            return None

        def gather(self, system, user, session, budget, trace=None):  # noqa: ANN001
            return ""

    caller = Recording()
    with InspectionSession(
        run_id="test",
        root=root,
        store=store,
        # One specialist and no screening, so every call this run makes is the
        # call under test rather than a mixture of four prompts and a screener.
        config=AgentConfig(model="fake", enable_tools=False, lenses=("memory",), triage=False),
        caller=caller,  # type: ignore[arg-type]
    ) as session:
        assert session.prompts["lens:memory"] == "Report only command injection."
        session.start()

    assert caller.systems, "the run made no model call to check"
    assert all(system == "Report only command injection." for system in caller.systems)
    store.close()
