from __future__ import annotations

from typing import Any

import pytest

from agent import harness, replay, tuner
from agent.config import AgentConfig
from agent.schema import Finding, Report, RunStats, Span


def _config(**over: Any) -> AgentConfig:
    base = {"model": "fake", "lenses": ("injection", "memory"), "enable_tools": False}
    return AgentConfig(**{**base, **over})


def test_the_same_settings_hash_the_same() -> None:
    assert harness.fingerprint(_config()) == harness.fingerprint(_config())


def test_settings_that_change_the_answer_change_the_hash() -> None:
    assert harness.fingerprint(_config()) != harness.fingerprint(_config(lenses=("injection",)))
    assert harness.fingerprint(_config()) != harness.fingerprint(_config(triage=False))
    assert harness.fingerprint(_config()) != harness.fingerprint(_config(context_char_budget=999))


def test_settings_that_only_change_speed_do_not() -> None:
    same = harness.fingerprint(_config())
    assert harness.fingerprint(_config(request_timeout=999)) == same
    assert harness.fingerprint(_config(max_concurrency=1)) == same
    assert harness.fingerprint(_config(max_inflight=1)) == same
    assert harness.fingerprint(_config(api_key="another")) == same


def test_a_recorded_config_can_be_read_back() -> None:
    digest = harness.record(_config(), label="under test")
    found = harness.load(digest)
    assert found is not None
    assert found.knobs["lenses"] == ["injection", "memory"]
    assert found.pinned is False


def test_recording_twice_writes_one_row() -> None:
    first = harness.record(_config())
    second = harness.record(_config())
    assert first == second
    assert len([c for c in harness.all_configs() if c.config_hash == first]) == 1


def test_a_run_records_the_config_that_produced_it(tmp_path) -> None:
    from agent.graph.build import run_inspection
    from agent.index import ChunkStore, build_index
    from agent.runs import Run, new_run
    from conftest import read_tree
    from test_graph import ScriptedCaller

    root = tmp_path / "src"
    root.mkdir()
    (root / "app.c").write_text('#include <stdio.h>\nvoid f(void) { puts("x"); }\n', encoding="utf-8")
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


def test_the_tuner_is_never_in_the_request_path() -> None:
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


def _saved_proposal() -> str:
    digest = harness.record(_config(wave_width=2))
    made = tuner._propose_visit_budget(
        {"wave_width": 2}, {"runs": ["r1"], "totals": {"runs": 3, "budget_hits": 3}}, digest, None
    )
    assert made is not None
    return tuner.save(made)


def test_applying_without_a_replay_is_refused() -> None:
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
    proposal_id = _saved_proposal()
    before = [p for p in tuner.proposals() if p["id"] == proposal_id][0]["base_hash"]
    tuner.attach_replay(proposal_id, {"metric": "chunks_inspected", "direction": "up", "improved": True})
    tuner.apply(proposal_id)

    assert harness.load(before) is not None


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
    assert replay.improved(1.0, 2.0, "up") is True
    assert replay.improved(2.0, 1.0, "up") is False
    assert replay.improved(2.0, 1.0, "down") is True
    assert replay.improved(1.0, 1.0, "up") is False
    assert replay.improved(1.0, 1.0, "down") is False


def test_an_unknown_metric_is_refused_rather_than_scored_as_zero() -> None:
    with pytest.raises(ValueError, match="unknown metric"):
        replay.measure(_report(1, 1), "vibes")


def test_a_replay_runs_both_arms_over_one_corpus() -> None:
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


def test_a_lens_whose_every_claim_was_refuted_is_the_signal() -> None:
    per_lens = {
        "memory": {"calls": 20, "raised": 12, "confirmed": 0},
        "injection": {"calls": 20, "raised": 6, "confirmed": 4},
        "access": {"calls": 0, "raised": 0, "confirmed": 0},
        "crypto": {"calls": 0, "raised": 0, "confirmed": 0},
        "logic": {"calls": 0, "raised": 0, "confirmed": 0},
    }
    made = _propose_with_lenses(("memory", "injection"), per_lens)

    assert made is not None
    assert made.changes == {"lenses": ["injection"]}
    assert made.evidence.observations["refuted_throughout"] == ["memory"]
    assert "raised 12 and had none confirmed" in made.evidence.note


def test_a_lens_that_is_working_is_left_alone() -> None:
    per_lens = {
        "memory": {"calls": 20, "raised": 12, "confirmed": 5},
        "injection": {"calls": 20, "raised": 6, "confirmed": 4},
        "access": {"calls": 0, "raised": 0, "confirmed": 0},
        "crypto": {"calls": 0, "raised": 0, "confirmed": 0},
        "logic": {"calls": 0, "raised": 0, "confirmed": 0},
    }
    assert _propose_with_lenses(("memory", "injection"), per_lens) is None


def test_the_lens_set_is_never_emptied() -> None:
    per_lens = {lens: {"calls": 20, "raised": 0, "confirmed": 0} for lens in ("memory", "injection")}
    per_lens.update({lens: {"calls": 0, "raised": 0, "confirmed": 0} for lens in ("access", "crypto", "logic")})
    assert _propose_with_lenses(("memory", "injection"), per_lens) is None


def _propose_with_lenses(active: tuple[str, ...], per_lens: dict[str, dict[str, int]]):
    import agent.tuner as module

    original = module._lens_record
    module._lens_record = lambda *_a, **_k: per_lens  # type: ignore[assignment]
    try:
        return module._propose_idle_lens(
            {"lenses": list(active)},
            {"runs": ["r1", "r2", "r3"], "totals": {"runs": 3, "confirmed": 4}},
            "cfg",
            None,
        )
    finally:
        module._lens_record = original  # type: ignore[assignment]


def test_a_retrieval_budget_nobody_spends_is_proposed_away() -> None:
    import agent.tuner as module

    original = module._tool_record
    module._tool_record = lambda *_a, **_k: {"read_source": 4}
    try:
        made = module._propose_tool_budget(
            {"max_lens_tool_calls": 2, "lens_tools": True},
            {"runs": ["r1", "r2", "r3"], "totals": {"runs": 3, "confirmed": 5}},
            "cfg",
            None,
        )
    finally:
        module._tool_record = original

    assert made is not None
    assert made.changes == {"max_lens_tool_calls": 0, "lens_tools": False}
    assert "took none" in made.evidence.note


def test_no_confirmed_findings_means_the_retrieval_signal_says_nothing() -> None:
    import agent.tuner as module

    original = module._tool_record
    module._tool_record = lambda *_a, **_k: {}
    try:
        made = module._propose_tool_budget(
            {"max_lens_tool_calls": 2, "lens_tools": True},
            {"runs": ["r1"], "totals": {"runs": 3, "confirmed": 0}},
            "cfg",
            None,
        )
    finally:
        module._tool_record = original
    assert made is None


def test_a_finding_records_the_specialist_that_raised_it(tmp_path) -> None:
    from agent.graph.build import run_inspection
    from agent.index import ChunkStore, build_index
    from agent.runs import new_run
    from conftest import read_tree
    from test_graph import ScriptedCaller, _finding
    from agent.schema import ChunkAnalysis

    root = tmp_path / "src"
    root.mkdir()
    (root / "app.c").write_text(
        '#include <stdlib.h>\nvoid run(const char *a) { char c[64]; sprintf(c, "%s", a); system(c); }\n',
        encoding="utf-8",
    )
    store = ChunkStore(new_run().run_id)
    build_index(read_tree(root), store)

    report = run_inspection(
        run_id=store.run_id,
        files=read_tree(root),
        store=store,
        config=_config(lenses=("injection",)),
        caller=ScriptedCaller(analyses={"run": ChunkAnalysis(findings=[_finding("system(c);")])}),  # type: ignore[arg-type]
    )

    assert report.findings, "the fixture should have produced a finding"
    assert report.findings[0].lens == "injection"


def test_the_schema_is_built_by_the_run_rather_than_by_the_tests() -> None:
    from sqlalchemy import inspect as sqla_inspect

    from agent.db import ensure
    from agent.db.session import engine

    ensure()
    tables = set(sqla_inspect(engine()).get_table_names())
    assert {"harness_configs", "config_proposals", "plan_items", "plan_events"} <= tables


def test_a_replay_arm_is_not_evidence_about_the_config_it_tested() -> None:
    from agent.runs import Run, new_run

    digest = harness.record(_config(max_callee_notes=7))
    ordinary = new_run()
    ordinary.write_meta(status="done", config_hash=digest, report={"findings": [], "stats": {}})
    arm = new_run()
    arm.write_meta(status="done", config_hash=digest, replay=True, report={"findings": [], "stats": {}})

    counted = {row.id for row in tuner._completed(digest, None)}
    assert ordinary.run_id in counted
    assert arm.run_id not in counted, "an A/B arm must not be evidence about the config it tested"
    assert Run(arm.run_id).read_meta()["status"] == "done", "and it should still say it finished"


def test_the_token_settings_are_part_of_a_result_s_identity() -> None:
    from agent.cache import recipe_of

    base = dict(model="m", lenses=("memory",), prompts={"analyse": "a"})
    default = recipe_of(**base, reasoning_effort="low", max_tokens=4096)

    assert recipe_of(**base, reasoning_effort="medium", max_tokens=4096) != default
    assert recipe_of(**base, reasoning_effort="low", max_tokens=8192) != default
    assert recipe_of(**base, reasoning_effort="low", max_tokens=4096) == default


def test_reasoning_effort_is_a_knob_that_changes_the_answer() -> None:
    from agent.config import AgentConfig
    from agent.harness import TUNABLE, fingerprint

    assert "reasoning_effort" in TUNABLE

    low = AgentConfig(model="m")
    low.reasoning_effort = "low"
    high = AgentConfig(model="m")
    high.reasoning_effort = "high"
    assert fingerprint(low) != fingerprint(high)


def test_results_cached_before_the_retry_worked_are_not_reused() -> None:
    from agent.cache import FORMAT

    assert FORMAT != "1", "bump this when a fix changes what a cached result means"
