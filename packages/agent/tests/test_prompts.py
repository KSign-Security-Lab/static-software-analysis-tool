from __future__ import annotations

from pathlib import Path

import pytest

from agent.llm import Outcome

from agent import promptstore
from agent.promptstore import DEFAULTS, NAMES, UnknownPrompt


def test_triage_offers_every_lens_that_exists() -> None:
    from agent.prompts import TRIAGE_SYSTEM
    from agent.schema import LENSES

    missing = [lens for lens in LENSES if f"- {lens}:" not in TRIAGE_SYSTEM]
    assert not missing, f"triage never offers: {missing}"


def test_nothing_saved_means_the_shipped_prompts(tmp_path: Path) -> None:
    path = tmp_path / "prompts.json"

    assert promptstore.load(path) == {}
    assert promptstore.resolve(path) == DEFAULTS
    assert not path.exists()


def test_a_saved_prompt_shadows_the_default(tmp_path: Path) -> None:
    path = tmp_path / "prompts.json"
    promptstore.save(path, "lens:memory", "Only report memory errors.")

    resolved = promptstore.resolve(path)
    assert resolved["lens:memory"] == "Only report memory errors."
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
    path = tmp_path / "prompts.json"

    with pytest.raises(ValueError):
        promptstore.save(path, "lens:memory", "   \n ")
    assert promptstore.resolve(path) == DEFAULTS


@pytest.mark.parametrize("name", ["analyze", "", "ANALYSE", "system"])
def test_an_unknown_prompt_name_is_refused(tmp_path: Path, name: str) -> None:
    with pytest.raises(UnknownPrompt):
        promptstore.save(tmp_path / "prompts.json", name, "text")
    with pytest.raises(UnknownPrompt):
        promptstore.clear(tmp_path / "prompts.json", name)


def test_a_corrupt_store_falls_back_rather_than_failing_the_run(tmp_path: Path) -> None:
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
    from agent.config import ENV_PROMPTS_FILE, AgentConfig
    from agent.graph.session import InspectionSession
    from agent.runs import new_run
    from conftest import read_tree
    from agent.index import ChunkStore, build_index

    path = tmp_path / "prompts.json"
    monkeypatch.setenv(ENV_PROMPTS_FILE, str(path))
    promptstore.save(path, "lens:memory", "Report only command injection.")

    root = tmp_path / "src"
    root.mkdir()
    (root / "a.c").write_text("void f(void) { }\n", encoding="utf-8")
    store = ChunkStore(new_run().run_id)
    build_index(read_tree(root), store)

    class Recording:
        def __init__(self) -> None:
            self.systems: list[str] = []

        def call(self, schema, system, user, trace=None):  # noqa: ANN001
            self.systems.append(system)
            return Outcome.failed("refused")

        def gather(self, system, user, session, budget, trace=None, allowed=None, cancelled=None):  # noqa: ANN001
            return ""

    caller = Recording()
    with InspectionSession(
        run_id="test",
        files=read_tree(root),
        store=store,
        config=AgentConfig(model="fake", enable_tools=False, lenses=("memory",), triage=False),
        caller=caller,  # type: ignore[arg-type]
    ) as session:
        assert session.prompts["lens:memory"] == "Report only command injection."
        session.start()

    assert caller.systems, "the run made no model call to check"
    assert all(system == "Report only command injection." for system in caller.systems)
    store.close()
