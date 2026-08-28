"""The step roster: what the API can say about a step before anything has run."""

from __future__ import annotations

from agent.config import AgentConfig
from agent.promptstore import NAMES, lens_prompt
from agent.schema import LENSES
from agent.steps import DETERMINISTIC, NODE_NOTES, STEP_NODE, STEP_ORDER, describe_nodes, describe_steps


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
    # `fix` last of the per-chunk steps: it is the only one that runs *after* a
    # claim is known to have survived, which is what stops it spending calls on
    # findings nobody reads.
    #
    # `replan` sits behind all of them because it is not a step a chunk passes
    # through at all -- it runs once a whole wave is finished, and only when
    # planning is advisory.
    assert STEP_ORDER[-4:] == ("gather", "verify", "fix", "replan")


def test_the_steps_that_read_something_new_are_the_ones_with_tools() -> None:
    """A specialist looks things up;  may also go and read. Screening,
    narrowing and the ruling itself read nothing they were not handed."""
    described = _by_step()
    holders = [entry["step"] for entry in described.values() if entry["tools"]]
    assert "gather" in holders
    assert all(step.startswith("lens:") or step == "gather" for step in holders), holders

    names = [tool["name"] for tool in described["gather"]["tools"]]
    assert "read_source" in names and "search_semantic" in names
    # Described, not just named: a list of bare identifiers does not tell anyone
    # what the verifier was able to go and check.
    assert all(tool["summary"] for tool in described["gather"]["tools"])
    assert "path" in dict(zip(names, described["gather"]["tools"]))["read_source"]["parameters"]


def test_gathering_evidence_is_a_node_of_its_own() -> None:
    """The one step that goes and reads things is the one worth stopping at.

    It used to be the first half of `verify`, which meant the drawing of the
    agent had no box for retrieval at all -- the run went and looked things up
    inside a node named after the ruling it made afterwards.
    """
    described = _by_step()
    assert described["gather"]["node"] == "gather"
    assert described["verify"]["node"] == "verify"
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


# -- the graph's own nodes ----------------------------------------------------


def test_every_node_is_classified() -> None:
    """Adding a node to the graph has to say which kind it is.

    The web tags a box `agent` or `code` from this. A node that calls a model but is
    missing from `STEP_NODE` would be drawn as plain Python -- a wrong answer, which
    is worse than no answer -- and nothing else would notice.
    """
    from agent.graph.build import NODES

    classified = set(STEP_NODE.values()) | set(DETERMINISTIC)
    assert classified == set(NODES), (
        "a node is either an agent (named by a step) or deterministic (named in "
        "DETERMINISTIC); this one is neither or both"
    )
    assert not (set(STEP_NODE.values()) & set(DETERMINISTIC)), "a node cannot be both"


def test_every_deterministic_node_says_what_it_does() -> None:
    assert set(NODE_NOTES) == set(DETERMINISTIC)
    for name, notes in NODE_NOTES.items():
        assert notes["does"], name
        assert notes["rule"], f"{name} must say how it decides where to go next"


def test_a_node_reads_and_writes_real_channels() -> None:
    """The channel names are declared, so they are the part that can drift."""
    from agent.graph.state import InspectionState

    channels = set(InspectionState.__annotations__)
    for name, notes in NODE_NOTES.items():
        for channel in [*notes["reads"], *notes["writes"]]:
            assert channel in channels, f"{name} names a channel the state does not have: {channel}"


def test_routing_comes_off_the_compiled_graph() -> None:
    """Not from the table, so it cannot disagree with the graph it describes."""
    from agent.graph.build import graph_shape

    edges = graph_shape()["edges"]
    expected = {
        name: sorted({e["target"] for e in edges if e["source"] == name}) for name in {e["source"] for e in edges}
    }
    for node in describe_nodes():
        assert node["routes"] == expected.get(node["node"], []), node["node"]


def test_an_agent_node_is_one_because_a_step_names_it() -> None:
    by_node = {node["node"]: node for node in describe_nodes()}

    assert by_node["plan"]["agent"] is False
    assert by_node["plan"]["calls"] == 0
    assert by_node["triage"]["agent"] is True
    # One step each, and the tools belong to the one that goes looking.
    assert by_node["gather"] == {
        **by_node["gather"],
        "agent": True,
        "steps": ["gather"],
        "calls": 1,
        "tools": 11,
    }
    # Two steps in the one node: the ruling, and the fix that follows a claim
    # surviving it. `lens:memory` in node `memory` is the same shape.
    assert by_node["verify"] == {
        **by_node["verify"],
        "agent": True,
        "steps": ["verify", "fix"],
        "calls": 2,
        "tools": 0,
    }
    # The deterministic ones carry the explanation instead.
    assert by_node["locate"]["does"]
    assert by_node["triage"]["does"] is None, "an agent explains itself through its prompt"
