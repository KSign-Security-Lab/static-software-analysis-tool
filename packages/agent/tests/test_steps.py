"""The step roster: what the API can say about a step before anything has run."""

from __future__ import annotations

from agent.config import AgentConfig
from agent.promptstore import NAMES, lens_prompt
from agent.schema import LENSES
from agent.steps import STEP_ORDER, describe_steps


def _by_step(config: AgentConfig | None = None) -> dict[str, dict]:
    return {entry["step"]: entry for entry in describe_steps(config)}


def test_every_step_names_a_prompt_that_exists() -> None:
    """The roster and the prompt store are joined by this key -- it is what lets
    a call in the trace be traced back to the prompt that produced it."""
    assert {entry["prompt"] for entry in describe_steps()} == set(NAMES)


def test_every_lens_appears_without_the_roster_being_edited() -> None:
    described = _by_step()
    for lens in LENSES:
        assert lens_prompt(lens) in described
        assert described[lens_prompt(lens)]["node"] == lens


def test_the_order_is_the_order_a_chunk_passes_through() -> None:
    assert [entry["step"] for entry in describe_steps()] == list(STEP_ORDER)
    assert STEP_ORDER[0] == "triage"
    assert STEP_ORDER[-2:] == ("gather", "verify")


def test_only_gather_holds_tools_and_it_holds_them_all() -> None:
    described = _by_step()
    assert [entry["step"] for entry in described.values() if entry["tools"]] == ["gather"]

    names = [tool["name"] for tool in described["gather"]["tools"]]
    assert "read_source" in names and "run_in_sandbox" in names
    # Described, not just named: a list of bare identifiers does not tell anyone
    # what the verifier was able to go and check.
    assert all(tool["summary"] for tool in described["gather"]["tools"])
    assert "path" in dict(zip(names, described["gather"]["tools"]))["read_source"]["parameters"]


def test_gather_and_verify_are_two_steps_of_one_node() -> None:
    """The reason a node name was never enough to say what a call was for."""
    described = _by_step()
    assert described["gather"]["node"] == described["verify"]["node"] == "verify"
    assert described["gather"]["schema"] is None, "a tool-calling loop returning prose"
    assert described["verify"]["schema"] == "Verdict"
    assert "refuted" in described["verify"]["schema_fields"]


def test_a_step_switched_off_says_so() -> None:
    config = AgentConfig(triage=False, lenses=("injection",), enable_tools=False)
    described = _by_step(config)

    assert described["triage"]["enabled"] is False
    assert described["lens:injection"]["enabled"] is True
    assert described["lens:memory"]["enabled"] is False
    # Still listed with its tools, because that is what the code offers -- but
    # this endpoint cannot call them, and a roster that hid that would be a lie.
    assert described["gather"]["tools"]
    assert described["gather"]["tools_enabled"] is False
