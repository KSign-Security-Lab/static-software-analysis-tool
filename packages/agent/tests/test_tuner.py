"""The return path: config identity, proposals, and the gate on applying one.

The tests that matter here are the ones about what the tuner *cannot* do. A
proposal engine that produces good suggestions and can also apply them is not
safer than one that produces bad ones.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent import harness, replay, tuner
from agent.config import AgentConfig
from agent.schema import Finding, Report, RunStats, Span


def _config(**over: Any) -> AgentConfig:
    base = {"model": "fake", "lenses": ("injection", "memory"), "enable_tools": False}
    return AgentConfig(**{**base, **over})


# -- identity ----------------------------------------------------------------


def test_the_same_settings_hash_the_same() -> None:
    assert harness.fingerprint(_config()) == harness.fingerprint(_config())


def test_settings_that_change_the_answer_change_the_hash() -> None:
    assert harness.fingerprint(_config()) != harness.fingerprint(_config(lenses=("injection",)))
    assert harness.fingerprint(_config()) != harness.fingerprint(_config(triage=False))
    assert harness.fingerprint(_config()) != harness.fingerprint(_config(context_char_budget=999))


def test_settings_that_only_change_speed_do_not() -> None:
    """The line the hash draws.

    Folding a timeout into it would make two identical analyses look like two
    different experiments every time somebody moved a port, and every comparison
    afterwards would be against a config nobody had actually changed.
    """
    same = harness.fingerprint(_config())
    assert harness.fingerprint(_config(request_timeout=999)) == same
    assert harness.fingerprint(_config(max_concurrency=1)) == same
    assert harness.fingerprint(_config(api_key="another")) == same


def test_a_recorded_config_can_be_read_back() -> None:
    digest = harness.record(_config(), label="under test")
    found = harness.load(digest)
    assert found is not None
    assert found.knobs["lenses"] == ["injection", "memory"]
    assert found.pinned is False


def test_recording_twice_writes_one_row() -> None:
    """The hash is the key, so a thousand runs alike are one experiment."""
    first = harness.record(_config())
    second = harness.record(_config())
    assert first == second
    assert len([c for c in harness.all_configs() if c.config_hash == first]) == 1


def test_a_run_records_the_config_that_produced_it(tmp_path) -> None:
    """Traceability, end to end: a result points at its settings.

    Everything in `tuner.py` rests on this one property, which is why the tuner
    was not written until it held.
    """
    from agent.graph.build import run_inspection
    from agent.index import ChunkStore, build_index
    from agent.runs import Run, new_run
    from conftest import read_tree
    from test_graph import ScriptedCaller

    root = tmp_path / "src"
    root.mkdir()
    (root / "app.c").write_text("#include <stdio.h>\nvoid f(void) { puts(\"x\"); }\n", encoding="utf-8")
    store = ChunkStore(new_run().run_id)
    build_index(read_tree(root), store)

    settings = _config()
    run_inspection(
        run_id=store.run_id,
        files=read_tree(root),
        store=store,
        config=settings,
        caller=ScriptedCaller(),  # type: ignore[arg-type]
    )

    recorded = Run(store.run_id).read_meta().get("config_hash")
    assert recorded == harness.fingerprint(settings)
    assert harness.load(recorded) is not None


# -- what the tuner may not do ----------------------------------------------


def test_the_tuner_is_never_in_the_request_path() -> None:
    """Asserted rather than intended.

    A tuner reachable from a request is a harness that can change while it is
    being measured, and every number produced afterwards is about a moving
    target. The import graph is the only place that can be enforced, so this
    reads the source of everything a run touches and refuses to find it.
    """
    from pathlib import Path

    package = Path(tuner.__file__).parent
    hot = [
        package / "graph" / "build.py",
        package / "graph" / "nodes.py",
        package / "graph" / "session.py",
        package / "graph" / "plan.py",
        package / "llm.py",
        package / "mcp" / "server.py",
    ]
    for path in hot:
        source = path.read_text(encoding="utf-8")
        assert "import tuner" not in source and "from .tuner" not in source, f"{path.name} imports the tuner"
        assert "import replay" not in source and "from .replay" not in source, f"{path.name} imports replay"


def test_the_tuner_may_not_tune_the_tuner() -> None:
    """`planning` is off limits, and so is anything the gate depends on.

    A system that can widen its own approval criteria will, and the first thing
    it widens is whatever is stopping it.
    """
    assert "planning" in tuner.OFF_LIMITS

    digest = harness.record(_config())
    proposal = tuner.Proposal(
        id="p-offlimits",
        base_hash=digest,
        changes={"planning": "advisory"},
        evidence=tuner.Evidence(runs=["r1"], note="would like the wheel"),
        metric="confirmed",
    )
    with pytest.raises(ValueError, match="changes nothing the tuner may touch"):
        tuner.save(proposal)


def test_a_pinned_config_is_never_argued_with() -> None:
    """Checked when proposing, so a pinned baseline never acquires a proposal
    for somebody to have to ignore."""
    digest = harness.record(_config(max_chunk_chars=4321), label="baseline")
    harness.pin(digest)

    assert tuner.propose(digest) == []
    assert harness.load(digest).pinned is True  # type: ignore[union-attr]


def test_a_proposal_carries_the_evidence_that_motivated_it() -> None:
    digest = harness.record(_config(wave_width=2))
    seen = {"runs": ["r1", "r2", "r3"], "totals": {"runs": 3, "budget_hits": 3}}
    made = tuner._propose_visit_budget({"wave_width": 2}, seen, digest, None)

    assert made is not None
    assert made.changes == {"wave_width": 4}
    assert made.evidence.runs == ["r1", "r2", "r3"]
    assert made.evidence.observations["runs_short_of_queue"] == 3
    assert made.metric and made.direction == "up"


def test_a_proposal_names_two_configs_that_exist() -> None:
    """So a replay always has something to replay *against*."""
    digest = harness.record(_config(wave_width=2))
    made = tuner._propose_visit_budget(
        {"wave_width": 2}, {"runs": ["r1"], "totals": {"runs": 3, "budget_hits": 3}}, digest, None
    )
    assert made is not None
    tuner.save(made)

    stored = [p for p in tuner.proposals() if p["id"] == made.id][0]
    assert harness.load(stored["base_hash"]) is not None
    assert harness.load(stored["proposed_hash"]) is not None
    assert stored["status"] == "proposed"


# -- the gate ----------------------------------------------------------------


def _saved_proposal() -> str:
    digest = harness.record(_config(wave_width=2))
    made = tuner._propose_visit_budget(
        {"wave_width": 2}, {"runs": ["r1"], "totals": {"runs": 3, "budget_hits": 3}}, digest, None
    )
    assert made is not None
    return tuner.save(made)


def test_applying_without_a_replay_is_refused() -> None:
    """The guardrail, in code rather than in a docstring.

    Evidence is about runs that happened; the change is a claim about runs that
    have not. Only a replay connects them, so this is the one place that can
    tell the difference and it is not permitted to be polite about it.
    """
    proposal_id = _saved_proposal()
    with pytest.raises(tuner.NotReplayed, match="no A/B replay"):
        tuner.apply(proposal_id)


def test_applying_after_a_failed_replay_is_refused() -> None:
    proposal_id = _saved_proposal()
    tuner.attach_replay(
        proposal_id,
        {"metric": "chunks_inspected", "direction": "up", "before": 10.0, "after": 9.0, "improved": False},
    )
    assert [p for p in tuner.proposals() if p["id"] == proposal_id][0]["status"] == "rejected"

    with pytest.raises(tuner.NotReplayed, match="did not move"):
        tuner.apply(proposal_id)


def test_a_passing_replay_is_what_lets_it_through() -> None:
    proposal_id = _saved_proposal()
    tuner.attach_replay(
        proposal_id,
        {"metric": "chunks_inspected", "direction": "up", "before": 9.0, "after": 14.0, "improved": True},
    )
    applied = tuner.apply(proposal_id)

    assert applied["config_hash"]
    assert harness.load(applied["config_hash"]) is not None
    assert [p for p in tuner.proposals() if p["id"] == proposal_id][0]["status"] == "applied"


def test_the_superseded_config_is_still_there() -> None:
    """Never delete, only archive. A hash that resolves to nothing is a result
    with no provenance."""
    proposal_id = _saved_proposal()
    before = [p for p in tuner.proposals() if p["id"] == proposal_id][0]["base_hash"]
    tuner.attach_replay(proposal_id, {"metric": "chunks_inspected", "direction": "up", "improved": True})
    tuner.apply(proposal_id)

    assert harness.load(before) is not None


# -- the replay itself -------------------------------------------------------


def _report(confirmed: int, inspected: int) -> Report:
    findings = [
        Finding(
            id=f"f{i}",
            chunk_id="c",
            severity="high",
            confidence=0.9,
            title=f"finding {i}",
            primary=Span(file="a.c", start_line=1, end_line=1, start_column=0, end_column=1, excerpt="x"),
            explanation="",
            remediation={"summary": "s", "detail": "d"},
            verified=True,
        )
        for i in range(confirmed)
    ]
    return Report(run_id="r", findings=findings, stats=RunStats(chunks_inspected=inspected))


def test_the_metric_and_direction_are_fixed_before_the_replay_runs() -> None:
    """A replay that could pick its own metric afterwards would approve
    everything, because some number always moves."""
    assert replay.improved(1.0, 2.0, "up") is True
    assert replay.improved(2.0, 1.0, "up") is False
    assert replay.improved(2.0, 1.0, "down") is True
    # A tie is a failure: a change with no measurable effect has no argument.
    assert replay.improved(1.0, 1.0, "up") is False
    assert replay.improved(1.0, 1.0, "down") is False


def test_an_unknown_metric_is_refused_rather_than_scored_as_zero() -> None:
    with pytest.raises(ValueError, match="unknown metric"):
        replay.measure(_report(1, 1), "vibes")


def test_a_replay_runs_both_arms_over_one_corpus() -> None:
    """Pinned corpus, same files to both arms.

    Against whatever happened to be lying around, a replay measures the corpus
    as much as the config, and two configs judged on different trees are not
    being compared at all.
    """
    base = harness.record(_config(wave_width=2))
    proposed = harness.record(_config(wave_width=4))

    saw: list[tuple[int, str]] = []

    def arm(config: AgentConfig, corpus: str) -> Report:
        saw.append((config.wave_width, corpus))
        return _report(confirmed=3, inspected=10) if config.wave_width == 2 else _report(confirmed=3, inspected=18)

    out = replay.compare(
        base_hash=base,
        proposed_hash=proposed,
        metric="chunks_inspected",
        direction="up",
        run_arm=arm,
        corpus="fixtures/sample",
    )

    assert [corpus for _, corpus in saw] == ["fixtures/sample", "fixtures/sample"]
    assert out["before"] == 10.0 and out["after"] == 18.0
    assert out["improved"] is True
    assert out["base_stats"]["chunks_inspected"] == 10


def test_a_replay_that_finds_less_does_not_pass() -> None:
    """The failure the default metric exists to catch: a cheaper config that
    finds fewer real things."""
    base = harness.record(_config(lenses=("injection", "memory")))
    proposed = harness.record(_config(lenses=("injection",)))

    def arm(config: AgentConfig, corpus: str) -> Report:
        return _report(confirmed=4, inspected=10) if len(config.lenses) == 2 else _report(confirmed=1, inspected=10)

    out = replay.compare(
        base_hash=base,
        proposed_hash=proposed,
        metric="confirmed_per_call",
        direction="up",
        run_arm=arm,
        corpus="fixtures/sample",
    )
    assert out["improved"] is False
