"""The inspection loop, driven by a scripted model.

A fake :class:`StructuredCaller` makes the loop's behaviour testable as
behaviour rather than as vibes: whether notes really reach callers, whether an
unlocatable finding is really dropped, whether refutation really removes things,
whether a second run really skips work. None of that is observable against a
live model, because a live model answers differently every time.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from agent.config import AgentConfig
from agent.graph.build import run_inspection
from agent.index import ChunkStore, build_index
from agent.prompts import LENS_SYSTEM
from agent.trace import SpanStore
from agent.schema import (
    CandidateEvidence,
    CandidateFinding,
    CandidateRemediation,
    ChunkAnalysis,
    Triage,
    Verdict,
)

VULNERABLE = """\
#include <stdlib.h>
#include <stdio.h>

char *taint_source(void) {
    return getenv("USER_INPUT");
}

void run_command(const char *arg) {
    char cmd[128];
    sprintf(cmd, "echo %s", arg);
    system(cmd);
}

void handler(void) {
    run_command(taint_source());
}
"""


class ScriptedCaller:
    """Stands in for the model. Records what it was asked."""

    def __init__(
        self,
        analyses: dict[str, ChunkAnalysis] | None = None,
        verdict: Verdict | None = None,
        default_analysis: ChunkAnalysis | None = None,
        triage: Triage | None = None,
    ) -> None:
        self.analyses = analyses or {}
        self.verdict = verdict if verdict is not None else Verdict(refuted=False, reason="holds", confidence=0.9)
        self.default_analysis = default_analysis or ChunkAnalysis()
        # Everything through, by default: a screening pass that changed the
        # answer would make every other test in this file about triage.
        self.triage = triage if triage is not None else Triage(worth_analysing=True, lenses=[], reason="")
        self.prompts: list[tuple[str, str]] = []
        # The system prompt is what tells one specialist from another, so the
        # tests that are about the specialists have to be able to see it.
        self.systems: list[tuple[str, str]] = []
        self.gather_calls: list[tuple[Any, int]] = []
        self.traces: list[Any] = []

    #: Set by tests that want the gather step to return something.
    gathered: str = ""

    def gather(self, system: str, user: str, session: Any, budget: int, trace: Any = None) -> str:
        self.prompts.append(("gather", user))
        self.gather_calls.append((session, budget))
        self.traces.append(trace)
        return self.gathered

    def call(self, schema: type[BaseModel], system: str, user: str, trace: Any = None) -> Any:
        self.prompts.append((schema.__name__, user))
        self.systems.append((schema.__name__, system))
        self.traces.append(trace)
        if schema is ChunkAnalysis:
            for symbol, analysis in self.analyses.items():
                if f":: {symbol} " in user:
                    return analysis
            return self.default_analysis
        if schema is Verdict:
            return self.verdict
        if schema is Triage:
            return self.triage
        return None

    def prompts_for(self, schema_name: str) -> list[str]:
        return [text for name, text in self.prompts if name == schema_name]


def _finding(anchor: str, *, title: str = "Command injection", cwe: str = "CWE-78") -> CandidateFinding:
    return CandidateFinding(
        title=title,
        severity="high",
        cwe=cwe,
        anchor_text=anchor,
        explanation="Untrusted input reaches a shell.",
        evidence=[CandidateEvidence(role="sink", file="app.c", anchor_text=anchor, note="the sink")],
        remediation=CandidateRemediation(summary="Use execve", detail="Avoid the shell entirely."),
    )


@pytest.fixture
def indexed(tmp_path: Path) -> tuple[Path, ChunkStore]:
    root = tmp_path / "src"
    root.mkdir()
    (root / "app.c").write_text(VULNERABLE, encoding="utf-8")
    store = ChunkStore(tmp_path / "index.db")
    build_index(root, store)
    return root, store


def _run(
    root: Path,
    store: ChunkStore,
    caller: ScriptedCaller,
    tools: Any = None,
    **config_kwargs: Any,
):
    # enable_tools defaults False here so the suite never spawns an MCP
    # subprocess unless a test is specifically about tools.
    #
    # One lens by default, for the same kind of reason: with four, every count
    # in this file would be four times what the pipeline actually did, and a
    # test about dropping an anchor would read as a test about arithmetic. The
    # tests that are about the specialists ask for them by name.
    config_kwargs.setdefault("lenses", ("injection",))
    config = AgentConfig(model="fake", enable_tools=False, **config_kwargs)
    return run_inspection(
        run_id="test",
        root=root,
        store=store,
        config=config,
        caller=caller,  # type: ignore[arg-type]
        tools=tools,
    )


class FakeToolSession:
    """Stands in for the MCP session; records what verification asked for."""

    def __init__(self, replies: dict[str, str] | None = None) -> None:
        self.replies = replies or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.tools: list[Any] = []

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        self.calls.append((name, arguments))
        return self.replies.get(name, "")


def test_a_located_and_unrefuted_finding_reaches_the_report(indexed) -> None:
    root, store = indexed
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})

    report = _run(root, store, caller)

    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.primary.file == "app.c"
    assert finding.primary.excerpt == "system(cmd);"
    assert finding.verified is True
    assert finding.confidence == pytest.approx(0.9)
    store.close()


def test_reported_span_really_is_where_the_text_is(indexed) -> None:
    """Location integrity, end to end: the coordinates must select the excerpt.

    This is the property that makes a marker trustworthy, checked on a whole
    report rather than on a single call to ``locate_anchor``.
    """
    root, store = indexed
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("sprintf(cmd,")])})

    report = _run(root, store, caller)

    assert report.findings
    for finding in report.findings:
        for span in [finding.primary, *(e.span for e in finding.evidence)]:
            line = (root / span.file).read_text(encoding="utf-8").splitlines()[span.start_line - 1]
            assert line[span.start_column - 1 :].startswith(span.excerpt.splitlines()[0])
    store.close()


def test_unlocatable_findings_are_dropped_and_counted(indexed) -> None:
    """A hallucinated anchor must produce no marker at all."""
    root, store = indexed
    caller = ScriptedCaller(
        analyses={"run_command": ChunkAnalysis(findings=[_finding("strcpy(dst, src); /* not in the file */")])}
    )

    report = _run(root, store, caller)

    assert report.findings == []
    assert report.stats.candidates == 1
    assert report.stats.dropped_unlocatable == 1
    store.close()


def test_refuted_findings_do_not_reach_the_report(indexed) -> None:
    root, store = indexed
    caller = ScriptedCaller(
        analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])},
        verdict=Verdict(refuted=True, reason="arg is a constant", confidence=0.1),
    )

    report = _run(root, store, caller)

    assert report.findings == []
    assert report.stats.refuted == 1
    store.close()


def test_a_missing_verdict_counts_against_the_finding(indexed) -> None:
    """No answer is not a pass. Uncertainty must not become a marker."""
    root, store = indexed

    class NoVerdict(ScriptedCaller):
        def call(self, schema: type[BaseModel], system: str, user: str, trace: Any = None) -> Any:
            if schema is Verdict:
                return None
            return super().call(schema, system, user, trace)

    caller = NoVerdict(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})
    report = _run(root, store, caller)

    assert report.findings == []
    assert report.stats.refuted == 1
    store.close()


def test_callee_notes_are_injected_into_caller_context(indexed) -> None:
    """The cross-chunk mechanism, observed directly.

    ``handler`` calls ``run_command``. Because callees are analysed first, the
    note written while analysing ``run_command`` must appear in the prompt used
    for ``handler`` -- that is how taint crosses the boundary without putting
    the whole tree in one prompt.
    """
    root, store = indexed
    note = "builds a shell command from its argument with no validation"
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[], note=note)})

    _run(root, store, caller)

    handler_prompts = [p for p in caller.prompts_for("ChunkAnalysis") if ":: handler " in p]
    assert handler_prompts, "handler was never analysed"
    assert note in handler_prompts[0], "the callee's note did not reach its caller"
    assert "이 단위가 부르는 것들이 하는 일" in handler_prompts[0]
    store.close()


def test_notes_are_persisted_even_with_no_findings(indexed) -> None:
    root, store = indexed
    caller = ScriptedCaller(analyses={"taint_source": ChunkAnalysis(findings=[], note="returns attacker data")})

    _run(root, store, caller)

    source_chunk = next(c for c in store.chunks() if c.symbol == "taint_source")
    assert store.note(source_chunk.chunk_id) == "returns attacker data"
    store.close()


def test_chunks_are_analysed_callees_first(indexed) -> None:
    root, store = indexed
    caller = ScriptedCaller()

    _run(root, store, caller)

    analysed = [p for p in caller.prompts_for("ChunkAnalysis")]
    order = [
        next(sym for sym in ("taint_source", "run_command", "handler") if f":: {sym} " in prompt)
        for prompt in analysed
        if any(f":: {sym} " in prompt for sym in ("taint_source", "run_command", "handler"))
    ]
    assert order.index("run_command") < order.index("handler")
    store.close()


def test_a_second_run_skips_already_inspected_chunks(indexed) -> None:
    """Incremental re-inspection: content-derived chunk ids make this free."""
    root, store = indexed
    first = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})
    first_report = _run(root, store, first)
    assert first_report.stats.chunks_inspected > 0

    second = ScriptedCaller()
    second_report = _run(root, store, second)

    assert second.prompts == [], "the model was called again for unchanged chunks"
    assert second_report.stats.chunks_cached == second_report.stats.chunks_total
    assert len(second_report.findings) == len(first_report.findings), (
        "a cached run must still report everything known about the tree"
    )
    store.close()


def test_editing_one_function_reanalyses_only_that_chunk(indexed) -> None:
    root, store = indexed
    _run(root, store, ScriptedCaller())

    edited = VULNERABLE.replace('sprintf(cmd, "echo %s", arg);', 'snprintf(cmd, sizeof(cmd), "echo %s", arg);')
    (root / "app.c").write_text(edited, encoding="utf-8")
    build_index(root, store)

    caller = ScriptedCaller()
    _run(root, store, caller)

    analysed = caller.prompts_for("ChunkAnalysis")
    assert len(analysed) == 1, f"expected only the edited chunk to be re-analysed, got {len(analysed)}"
    assert ":: run_command " in analysed[0]
    store.close()


def test_verification_cap_marks_rather_than_hides(indexed) -> None:
    """Past the cap a finding is kept but flagged unverified.

    Silently dropping it would hide real findings; silently blessing it would
    launder unverified ones. Saying so is the only honest option.
    """
    root, store = indexed
    findings = [
        _finding("system(cmd);", cwe="CWE-78"),
        _finding("sprintf(cmd,", cwe="CWE-787"),
        _finding("char cmd[128];", cwe="CWE-121"),
    ]
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=findings)})

    report = _run(root, store, caller, max_verify_per_chunk=1)

    assert len(report.findings) == 3
    verified = [f for f in report.findings if f.verified]
    unverified = [f for f in report.findings if not f.verified]
    assert len(verified) == 1
    assert len(unverified) == 2
    assert all(f.confidence < 0.5 for f in unverified)
    store.close()


def test_model_supplied_cwe_and_title_are_normalised_before_the_wire(indexed) -> None:
    """Observed from a real run: the model returned a markdown paragraph with
    two CWE references and mitre.org links in the ``cwe`` field, which the
    editor then rendered as the marker's source label."""
    root, store = indexed
    messy = CandidateFinding(
        title="  Command\n   Injection  ",
        severity="high",
        cwe="[CWE-78](https://cwe.mitre.org/data/definitions/77.html) (OS Command Injection) or [CWE-94]",
        anchor_text="system(cmd);",
        explanation="Untrusted input reaches a shell.",
        evidence=[],
        remediation=CandidateRemediation(summary="Use execve", detail="Avoid the shell."),
    )
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[messy])})

    report = _run(root, store, caller)

    assert len(report.findings) == 1
    assert report.findings[0].cwe == "CWE-78"
    assert report.findings[0].title == "Command Injection"
    store.close()


def test_an_overlong_title_is_bounded(indexed) -> None:
    root, store = indexed
    finding = _finding("system(cmd);")
    finding.title = "x" * 500
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[finding])})

    report = _run(root, store, caller)

    assert len(report.findings[0].title) <= 120
    store.close()


def test_verification_gathers_evidence_with_tools_before_ruling(indexed) -> None:
    """A claim gets checked, not just argued about.

    Whether ``run_command``'s argument is attacker controlled is decided in its
    caller, so a verdict made from the chunk alone is a guess. With tools the
    verifier can go and look.
    """
    root, store = indexed
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})
    caller.gathered = "$ find_callers(run_command)\nhandler passes taint_source() straight in"
    session = FakeToolSession()

    report = _run(root, store, caller, tools=session)

    assert caller.gather_calls, "verification never offered the tools"
    _, budget = caller.gather_calls[0]
    assert budget == AgentConfig().max_tool_calls

    verdict_prompts = caller.prompts_for("Verdict")
    assert verdict_prompts, "no verdict was requested"
    assert "도구가 돌려준 것" in verdict_prompts[0]
    assert "handler passes taint_source" in verdict_prompts[0]
    assert report.findings
    store.close()


def test_verification_works_without_tools(indexed) -> None:
    """Context-only is a supported mode, not a degraded one -- most claims are
    decidable from the pack."""
    root, store = indexed
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})

    report = _run(root, store, caller, tools=None)

    assert caller.gather_calls == []
    assert len(report.findings) == 1
    assert "도구가 돌려준 것" not in caller.prompts_for("Verdict")[0]
    store.close()


def test_an_empty_gather_does_not_pollute_the_verdict_prompt(indexed) -> None:
    """If the model decides it needs nothing, the prompt should not gain an
    empty section implying it looked and found nothing."""
    root, store = indexed
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})
    caller.gathered = "   "
    session = FakeToolSession()

    _run(root, store, caller, tools=session)

    assert "도구가 돌려준 것" not in caller.prompts_for("Verdict")[0]
    store.close()


def test_tools_are_offered_only_during_verification(indexed) -> None:
    """Analysis is deterministic-context by design; letting it browse would make
    two runs over the same tree incomparable."""
    root, store = indexed
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})
    session = FakeToolSession()

    _run(root, store, caller, tools=session)

    assert len(caller.gather_calls) == 1, "gather should run once per finding, not per chunk"
    assert len(caller.prompts_for("ChunkAnalysis")) > 1, "analysis still ran for every chunk"


def test_findings_are_deduplicated_by_stable_id(indexed) -> None:
    """The same finding reported twice is one finding."""
    root, store = indexed
    duplicate = _finding("system(cmd);")
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[duplicate, duplicate])})

    report = _run(root, store, caller)

    assert len(report.findings) == 1
    store.close()


def test_empty_analysis_produces_an_empty_report(indexed) -> None:
    """Finding nothing is a valid outcome, not an error."""
    root, store = indexed
    report = _run(root, store, ScriptedCaller())

    assert report.findings == []
    assert report.stats.chunks_inspected == report.stats.chunks_total
    assert report.stats.candidates == 0
    store.close()


def test_a_run_records_its_own_trace(indexed, tmp_path: Path) -> None:
    """The local trace is what the debug view reads; LangSmith is optional."""
    root, store = indexed
    spans = SpanStore(tmp_path / "trace.db")
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})

    config = AgentConfig(model="fake", enable_tools=False, lenses=("injection",))
    run_inspection(
        run_id="test",
        root=root,
        store=store,
        config=config,
        caller=caller,  # type: ignore[arg-type]
        spans=spans,
    )

    recorded = spans.spans()
    names = {span.name for span in recorded}
    assert {"plan", "context", "triage", "injection", "locate", "verify", "reduce"} <= names
    assert all(span.status == "ok" for span in recorded), "every span should have been closed"

    # A tree, not a flat list: the node spans hang off the graph's root span.
    ids = {span.id for span in recorded}
    parents = {span.parent_id for span in recorded if span.parent_id}
    assert parents and parents <= ids

    spans.close()
    store.close()


def test_the_graph_shape_is_readable_without_a_run(tmp_path: Path) -> None:
    """The structure is a property of the code, so the UI can draw it before
    anything has been inspected."""
    from agent.graph.build import graph_shape

    shape = graph_shape()

    assert set(shape["nodes"]) == {
        "__start__",
        "plan",
        "context",
        "triage",
        "scout",
        "memory",
        "injection",
        "access",
        "crypto",
        "logic",
        "skip",
        "locate",
        "gather",
        "verify",
        "reduce",
        "__end__",
    }
    edges = {(e["source"], e["target"]) for e in shape["edges"]}
    assert ("context", "triage") in edges
    assert ("reduce", "plan") in edges, "the loop back to plan is the whole shape"
    # Every specialist joins at `locate`. That is what makes the fan-out a
    # fan-out rather than four separate runs.
    assert {(lens, "locate") for lens in ("memory", "injection", "access", "logic")} <= edges

    conditional = {(e["source"], e["target"]) for e in shape["edges"] if e["conditional"]}
    assert ("plan", "__end__") in conditional
    assert ("scout", "memory") in conditional, "a Send is invisible unless the edge declares it"
    assert ("triage", "scout") in conditional
    # `gather` routes itself, with a Send inside a Command rather than a router.
    # It has to declare its destination for the same reason.
    assert ("gather", "verify") in conditional


def test_a_run_checkpoints_every_super_step(indexed, tmp_path: Path) -> None:
    """Each node's state is kept, so a finished run can be stepped through."""
    from agent.graph.checkpoints import read_history

    root, store = indexed
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})
    db = tmp_path / "checkpoints.db"

    run_inspection(
        run_id="test",
        root=root,
        store=store,
        config=AgentConfig(model="fake", enable_tools=False, lenses=("injection",)),
        caller=caller,  # type: ignore[arg-type]
        checkpoints=db,
    )

    history = read_history(db, "test")
    assert len(history) > 1

    # Oldest first: reading a run as a sequence of steps is the point, and
    # LangGraph yields them newest first.
    steps = [h["step"] for h in history if h["step"] is not None]
    assert steps == sorted(steps)

    # Nothing records which node wrote a state, so it is read off the parent
    # checkpoint's queue: what was about to run there is what wrote this.
    assert {h["node"] for h in history} >= {"plan", "context", "triage", "injection", "locate", "verify", "reduce"}

    # The parent pointer is what makes the history a tree rather than a list,
    # and it is the only thing a branch can be reconstructed from.
    by_id = {h["checkpoint_id"]: h for h in history}
    parented = [h for h in history if h["parent_checkpoint_id"]]
    assert parented, "every step after the first has a parent"
    assert all(h["parent_checkpoint_id"] in by_id for h in parented)

    # Bulky lists are counted, not copied: a snapshot says where the run was,
    # it is not a second copy of the findings.
    values = history[-1]["values"]
    assert set(values["pending"]) == {"remaining", "next"}
    assert set(values["candidates"]) == {"count"}
    store.close()


def test_history_of_a_run_that_was_never_checkpointed_is_empty(tmp_path: Path) -> None:
    from agent.graph.checkpoints import read_history

    assert read_history(tmp_path / "missing.db", "test") == []


# -- the studio: watching a run, stopping it, and steering it -----------------


def _session(indexed, tmp_path: Path, **kwargs):
    """A session over the scripted caller, with checkpoints on.

    One chunk per wave unless a test asks otherwise: stepping, stopping and
    editing are all about one node at a time, and a fan-out would make every
    assertion below about how many tasks a wave happened to hold. The tests
    that are about waves set the width themselves.
    """
    from agent.graph.session import InspectionSession

    root, store = indexed
    caller = kwargs.pop("caller", None) or ScriptedCaller(
        analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])}
    )
    config = kwargs.pop("config", None) or AgentConfig(
        model="fake", enable_tools=False, lenses=("injection",), wave_width=1
    )
    return InspectionSession(
        run_id="test",
        root=root,
        store=store,
        config=config,
        caller=caller,
        checkpoints=tmp_path / "checkpoints.db",
        **kwargs,
    )


def test_a_run_reports_every_node_as_it_starts_and_finishes(indexed, tmp_path: Path) -> None:
    """The live graph is driven by these events, so they have to be ordered.

    A poll cannot say which node is running *now*; only the stream can.
    """
    seen: list[tuple[str, Any]] = []

    with _session(indexed, tmp_path, emit=lambda event, payload: seen.append((event, payload))) as session:
        session.start()

    started = [p["node"] for e, p in seen if e == "node_started"]
    finished = [p["node"] for e, p in seen if e == "node_finished"]
    assert started[:6] == ["plan", "context", "triage", "scout", "injection", "locate"]
    assert sorted(started) == sorted(finished), "a node that started and did not finish would hang the view"

    # Checkpoints arrive with the id the state endpoints are addressed by.
    checkpoints = [p for e, p in seen if e == "checkpoint"]
    assert checkpoints and all(p["checkpoint_id"] for p in checkpoints)

    # Bulky writes are counted, not shipped: this is a progress event.
    wrote = [p["updates"]["candidates"] for e, p in seen if e == "node_finished" and "candidates" in p["updates"]]
    assert wrote
    assert all(set(u) in ({"count"}, {"cleared"}) for u in wrote), wrote
    assert {"count"} in [set(u) for u in wrote], "a specialist's findings should be counted"


def test_a_breakpoint_stops_the_run_before_that_node(indexed, tmp_path: Path) -> None:
    """Stopping is the whole basis of stepping and of editing state mid-run."""
    with _session(indexed, tmp_path, breakpoints=["injection"]) as session:
        session.start()

        assert session.interrupted
        assert session.next_nodes == ["injection"]
        # Stopped *before* the node, so nothing it would have written is there.
        assert not session.values.get("candidates")

        session.resume()
        # It stops again at the next chunk: one breakpoint, hit repeatedly.
        assert session.interrupted

        # Resuming with an edit is the point of stopping: the person looks at
        # what the graph is about to do and changes it.
        session.resume(values={"pending": []})

    assert not session.interrupted
    assert session.values["pending"] == []


def test_resuming_with_an_edit_does_not_repeat_the_node_that_just_ran(indexed, tmp_path: Path) -> None:
    """LangGraph has to be told whose write an edit stands in for.

    Left to infer, it attributes the write to the step before the one that just
    finished, and the run redoes a node it had already done -- which for
    `analyse` means paying for the same model call twice.
    """
    seen: list[str] = []

    def watch(event: str, payload: Any) -> None:
        if event == "node_started" and payload.get("node"):
            seen.append(payload["node"])

    with _session(indexed, tmp_path, breakpoints=["injection"], emit=watch) as session:
        session.start()
        assert session.interrupted and session.next_nodes == ["injection"]
        before = list(seen)

        session.resume(values={"pending": []})

    ran = seen[len(before) :]
    assert ran and ran[0] == "injection", f"expected to carry on into the specialist, went to {ran[:2]}"


def test_a_breakpoint_needs_somewhere_to_stop(indexed, tmp_path: Path) -> None:
    """Without a checkpointer there is nowhere to save, so it cannot interrupt.

    Dropped rather than raised: a run with no history is still a valid run.
    """
    from agent.graph.session import InspectionSession

    root, store = indexed
    session = InspectionSession(
        run_id="test",
        root=root,
        store=store,
        config=AgentConfig(model="fake", enable_tools=False, lenses=("injection",)),
        caller=ScriptedCaller(),
        breakpoints=["injection"],
    )
    assert session.breakpoints == []
    session.close()


def test_a_misspelled_breakpoint_is_refused(indexed, tmp_path: Path) -> None:
    """Otherwise it is a breakpoint that silently never fires."""
    with pytest.raises(ValueError, match="analyze"):
        _session(indexed, tmp_path, breakpoints=["analyze"])


def test_state_can_be_read_in_full_and_edited(indexed, tmp_path: Path) -> None:
    """Editing needs the real values: a count cannot be edited back into a list."""
    from agent.graph.checkpoints import read_state, write_state

    db = tmp_path / "checkpoints.db"
    with _session(indexed, tmp_path, breakpoints=["context"]) as session:
        session.start()
        assert session.interrupted

        state = read_state(db, "test")
        assert state is not None
        assert isinstance(state["values"]["pending"], list), "summarised state cannot be edited"
        assert state["next"] == ["context"]

        # Drain the queue by hand: what the run does next is now our decision.
        write_state(db, "test", {"pending": []}, state["checkpoint_id"])
        session.resume()

    assert not session.interrupted
    assert session.values["pending"] == []


def test_writing_over_an_old_checkpoint_branches_rather_than_overwrites(indexed, tmp_path: Path) -> None:
    """The course already recorded has to survive being second-guessed."""
    from agent.graph.checkpoints import read_history, write_state

    root, store = indexed
    db = tmp_path / "checkpoints.db"
    run_inspection(
        run_id="test",
        root=root,
        store=store,
        config=AgentConfig(model="fake", enable_tools=False, lenses=("injection",)),
        caller=ScriptedCaller(),  # type: ignore[arg-type]
        checkpoints=db,
    )

    before = read_history(db, "test")
    target = next(h for h in before if h["node"] == "plan" and h["next"])
    branched = write_state(db, "test", {"pending": ["nothing-real"]}, target["checkpoint_id"])

    after = read_history(db, "test")
    assert branched and branched not in {h["checkpoint_id"] for h in before}
    assert len(after) == len(before) + 1, "the original line is still there"

    # The branch hangs off the point it was made against, which is what lets a
    # history with two courses in it be drawn as a tree.
    child = next(h for h in after if h["checkpoint_id"] == branched)
    assert child["parent_checkpoint_id"] == target["checkpoint_id"]
    assert child["values"]["pending"] == {"remaining": 1, "next": ["nothing-real"]}
    store.close()


def test_state_of_a_run_that_never_ran_is_nothing(tmp_path: Path) -> None:
    from agent.graph.checkpoints import read_state

    assert read_state(tmp_path / "missing.db", "test") is None


def test_a_run_can_be_started_with_a_narrowed_queue(indexed, tmp_path: Path) -> None:
    """The studio's input pane submits this: try one chunk, not the whole tree."""
    with _session(indexed, tmp_path) as session:
        every = session.initial()
        assert len(every["pending"]) > 1

        session.start(values={"pending": every["pending"][:1]})

    assert session.values["stats"]["chunks_inspected"] == 1


def test_starting_with_an_override_keeps_the_rest_of_the_state(indexed, tmp_path: Path) -> None:
    """Merged, not replaced: naming one field must not drop the tallies the
    other nodes read, which would make the run fail well after the mistake."""
    with _session(indexed, tmp_path) as session:
        session.start(values={"pending": []})

    assert session.values["stats"]["chunks_total"] > 0
    assert session.values["stats"]["chunks_inspected"] == 0


def test_a_breakpoint_after_a_node_stops_once_it_has_written(indexed, tmp_path: Path) -> None:
    """Before and after answer different questions: what is it about to be given,
    and what did it just produce."""
    with _session(indexed, tmp_path, breakpoints_after=["plan"]) as session:
        session.start()

        assert session.interrupted
        # `plan` has run -- it chose a chunk -- and `context` has not yet.
        assert session.values["current"] is not None
        assert session.next_nodes == ["context"]

        while session.interrupted:
            session.resume()

    assert not session.interrupted


def test_a_misspelled_breakpoint_after_is_refused_too(indexed, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="planne"):
        _session(indexed, tmp_path, breakpoints_after=["planne"])


# -- the specialists, the wave, and the screening pass ------------------------


def test_every_selected_lens_analyses_the_chunk(indexed) -> None:
    """Four narrow briefs, not one broad one. Each has to actually be sent."""
    root, store = indexed
    caller = ScriptedCaller()

    _run(root, store, caller, lenses=("memory", "injection", "access", "logic"))

    systems = [system for name, system in caller.systems if name == "ChunkAnalysis"]
    # Against the prompts themselves rather than a phrase out of one. The brief
    # is prose and gets re-tuned; which brief was sent is the claim being made.
    for lens in ("memory", "injection", "access", "logic"):
        assert LENS_SYSTEM[lens] in systems, f"{lens} was never asked"


def test_two_lenses_reporting_one_anchor_make_one_finding(indexed) -> None:
    """Agreement between specialists is agreement, not two vulnerabilities."""
    root, store = indexed
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})

    report = _run(root, store, caller, lenses=("memory", "injection"))

    assert len(report.findings) == 1, "the same anchor came back from both lenses"
    assert report.stats.candidates == 2, "both were counted; only one survived the merge"


def test_a_chunk_screened_out_costs_no_specialist(indexed) -> None:
    root, store = indexed
    caller = ScriptedCaller(triage=Triage(worth_analysing=False, lenses=[], reason="pure getter"))

    report = _run(root, store, caller)

    assert caller.prompts_for("ChunkAnalysis") == [], "nothing should have been analysed"
    assert report.stats.triaged_out == report.stats.chunks_inspected > 0
    # Still inspected: a screened-out chunk is a decided chunk, and a re-run
    # must not pay for the screening again.
    assert all(store.is_inspected(chunk_id) for chunk_id in store.order())


def test_triage_picks_which_specialists_run(indexed) -> None:
    root, store = indexed
    caller = ScriptedCaller(triage=Triage(worth_analysing=True, lenses=["memory"], reason="buffers"))

    _run(root, store, caller, lenses=("memory", "injection", "access", "logic"))

    systems = [system for name, system in caller.systems if name == "ChunkAnalysis"]
    assert systems, "the chosen lens should still have run"
    assert all(s == LENS_SYSTEM["memory"] for s in systems), "only the chosen lens should run"


def test_a_lens_switched_off_stays_off_whatever_triage_says(indexed) -> None:
    """The config is the ceiling. A model cannot talk its way into a specialist
    the deployment has turned off."""
    root, store = indexed
    caller = ScriptedCaller(triage=Triage(worth_analysing=True, lenses=["memory", "injection"], reason=""))

    _run(root, store, caller, lenses=("injection",))

    systems = [system for name, system in caller.systems if name == "ChunkAnalysis"]
    assert systems and all(s == LENS_SYSTEM["injection"] for s in systems)


def test_screening_that_fails_analyses_anyway(indexed) -> None:
    """A false negative in triage is a vulnerability nobody hears about, so an
    unanswered screening call must not be read as "skip it"."""

    class NoTriage(ScriptedCaller):
        def call(self, schema: type[BaseModel], system: str, user: str, trace: Any = None) -> Any:
            if schema is Triage:
                self.prompts.append((schema.__name__, user))
                return None
            return super().call(schema, system, user, trace)

    root, store = indexed
    caller = NoTriage(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})

    report = _run(root, store, caller)

    assert caller.prompts_for("ChunkAnalysis"), "a failed screening must not skip the chunk"
    assert len(report.findings) == 1


def test_a_wave_inspects_several_chunks_at_once(indexed) -> None:
    """The fixture's three level-zero chunks have no calls between them, so
    they go together; `handler` calls two of them and must wait."""
    root, store = indexed
    waves: list[list[str]] = []
    caller = ScriptedCaller()

    config = AgentConfig(model="fake", enable_tools=False, lenses=("injection",), wave_width=4)
    run_inspection(
        run_id="test",
        root=root,
        store=store,
        config=config,
        caller=caller,  # type: ignore[arg-type]
        emit=lambda event, payload: waves.append(list(payload["chunks"])) if event == "wave_started" else None,
    )

    assert len(waves) == 2, f"expected one wave per call depth, got {waves}"
    assert len(waves[0]) == 3, "the three independent chunks should go together"
    assert len(waves[1]) == 1, "the caller waits for its callees"
    assert sum(len(w) for w in waves) == len(store.order())


def test_a_started_chunk_says_which_file_it_is_in(indexed) -> None:
    """A chunk id names nothing a reader has seen.

    The client shows the tree of files being inspected, and a chunk id on its
    own leaves it unable to say which of them is being read right now --
    `chunk_finished` has carried the file since it was written, and the start of
    the work is exactly when saying so is worth anything.
    """
    root, store = indexed
    started: list[dict] = []

    run_inspection(
        run_id="test",
        root=root,
        store=store,
        config=AgentConfig(model="fake", enable_tools=False, lenses=("injection",), wave_width=4),
        caller=ScriptedCaller(),  # type: ignore[arg-type]
        emit=lambda event, payload: started.append(payload) if event == "chunk_started" else None,
    )

    assert started, "every chunk that runs announces itself"
    for payload in started:
        chunk = store.chunk(payload["chunk_id"])
        assert payload["file"] == chunk.file
        assert payload["symbol"] == chunk.symbol


def test_a_wave_still_gets_its_callees_notes(indexed) -> None:
    """The invariant waves are allowed to exist under. `handler` is in a later
    wave than `run_command`, so it still sees what `run_command` concluded."""
    root, store = indexed
    note = "runs its argument through a shell"
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[], note=note)})

    _run(root, store, caller, wave_width=4)

    handler_prompts = [p for p in caller.prompts_for("ChunkAnalysis") if ":: handler " in p]
    assert handler_prompts, "handler was never analysed"
    assert note in handler_prompts[0], "the callee's note did not reach its caller"


def test_a_run_is_the_same_however_the_endpoint_answers(indexed, tmp_path: Path) -> None:
    """Four specialists finishing in four different orders must still produce
    one report, in one order. Otherwise no two runs are comparable."""
    import random

    def report_for(seed: int) -> str:
        root = tmp_path / f"src{seed}"
        root.mkdir()
        (root / "app.c").write_text(VULNERABLE, encoding="utf-8")
        store = ChunkStore(tmp_path / f"index{seed}.db")
        build_index(root, store)

        rng = random.Random(seed)

        class Jittered(ScriptedCaller):
            """Answers in an order the run must not depend on."""

            def call(self, schema: type[BaseModel], system: str, user: str, trace: Any = None) -> Any:
                time.sleep(rng.random() / 500)
                return super().call(schema, system, user, trace)

        caller = Jittered(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})
        # No cache: this asks whether two *runs* agree, and a second run served
        # from the first one's results would agree by not running.
        report = _run(
            root,
            store,
            caller,
            wave_width=4,
            lenses=("memory", "injection", "access", "logic"),
            cache_results=False,
        )
        store.close()
        return report.model_dump_json(exclude={"run_id"})

    assert report_for(1) == report_for(2)


def test_a_breakpoint_stops_every_task_of_a_fanned_out_step(indexed, tmp_path: Path) -> None:
    """One breakpoint, three chunks in flight: all three stop, or the pause is
    a lie about what the run is doing."""
    config = AgentConfig(model="fake", enable_tools=False, lenses=("injection",), wave_width=4)

    with _session(indexed, tmp_path, config=config, breakpoints=["injection"]) as session:
        session.start()
        assert session.interrupted
        assert session.next_nodes == ["injection"] * 3, session.next_nodes


def test_a_run_can_be_stopped_where_it_goes_looking(indexed, tmp_path: Path) -> None:
    """The point of `gather` being a node.

    Retrieval is the step whose cost the prompt does not bound -- it is the only
    one holding tools -- and until it had a node of its own there was nowhere to
    stop and see what the agent was about to go and read.
    """
    config = AgentConfig(model="fake", enable_tools=False, lenses=("injection",))

    with _session(
        indexed,
        tmp_path,
        config=config,
        caller=ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])}),
        breakpoints=["gather"],
    ) as session:
        session.start()
        assert session.interrupted
        assert session.next_nodes == ["gather"], session.next_nodes


def test_what_gather_turned_up_reaches_the_verifier(indexed, tmp_path: Path) -> None:
    """The hand-off the split had to preserve.

    The claim and the transcript travel in the `Send`, not in graph state. A
    plain edge between the two nodes would make `verify` a join with no claim in
    front of it -- and `reduce` reads a missing verdict as a refutation, so the
    report would come back empty with nothing raised anywhere.
    """
    root, store = indexed
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})
    caller.gathered = "find_callers(run_command) -> handler passes taint straight in"

    report = _run(root, store, caller, tools=FakeToolSession())

    assert len(caller.gather_calls) == 1, "one investigation per claim, not per wave"
    verdict_prompts = caller.prompts_for("Verdict")
    assert len(verdict_prompts) == 1, "the claim reached exactly one verifier"
    assert caller.gathered in verdict_prompts[0], "what gather read never reached the ruling"
    assert report.findings and report.findings[0].verified is True
    store.close()


def test_editing_state_at_a_fanned_out_step_is_refused(indexed, tmp_path: Path) -> None:
    """There is no single node the edit stands in for, and guessing one decides
    where the run goes next. Better to say so than to be quietly wrong."""
    from agent.graph.session import ParallelStep

    config = AgentConfig(model="fake", enable_tools=False, lenses=("injection",), wave_width=4)

    with _session(indexed, tmp_path, config=config, breakpoints=["injection"]) as session:
        session.start()
        with pytest.raises(ParallelStep, match="joins them"):
            session.resume(values={"pending": []})

        # Carrying on without an edit is still fine: nothing has to be
        # attributed to anyone. It stops again at the next wave, which is one
        # breakpoint doing its job rather than the refusal biting twice.
        session.resume()
        assert session.next_nodes == ["injection"]
        session.resume()
        assert not session.interrupted


def test_a_wave_closes_exactly_once_when_a_chunk_is_screened_out(indexed) -> None:
    """The bug this pins was silent and total: a screened-out chunk routed
    straight to the join, which fired it while the specialists were still
    running. That closed the wave early, cleared the state under them, and the
    run finished having thrown away everything they found."""
    root, store = indexed
    only_run_command = {"run_command"}

    class Selective(ScriptedCaller):
        """Screens out everything except one chunk, so a wave contains both."""

        def call(self, schema: type[BaseModel], system: str, user: str, trace: Any = None) -> Any:
            if schema is Triage:
                self.prompts.append((schema.__name__, user))
                worth = any(f":: {name} " in user for name in only_run_command)
                return Triage(worth_analysing=worth, lenses=[], reason="")
            return super().call(schema, system, user, trace)

    caller = Selective(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})
    finished: list[str] = []

    config = AgentConfig(model="fake", enable_tools=False, lenses=("injection",), wave_width=4)
    report = run_inspection(
        run_id="test",
        root=root,
        store=store,
        config=config,
        caller=caller,  # type: ignore[arg-type]
        emit=lambda event, payload: finished.append(payload["chunk_id"]) if event == "chunk_finished" else None,
    )

    assert len(finished) == len(set(finished)) == len(store.order()), f"a chunk was closed twice: {finished}"
    assert report.stats.chunks_inspected == report.stats.chunks_total
    assert len(report.findings) == 1, "the surviving specialist's finding was lost"
    store.close()


def test_the_verifier_is_told_which_specialist_raised_the_claim() -> None:
    """The one edge in the run that used to leave no record.

    `locate` knows which lens produced each candidate and `claims` dropped it, so
    a trace could show a claim being refuted without showing who had made it.
    """
    from agent.graph.nodes import claims

    state = {
        "located": [
            {"chunk_id": "c1", "lens": "injection", "finding": {"id": "f1"}},
            {"chunk_id": "c1", "lens": "memory", "finding": {"id": "f2"}, "over_cap": True},
        ]
    }
    sends = claims(state)

    assert [send.arg["lens"] for send in sends] == ["injection"], "capped claims are not verified at all"
    assert sends[0].arg["finding"] == {"id": "f1"}


def test_call_config_carries_the_lens_into_the_trace() -> None:
    from agent.tracing import call_config

    config = call_config(step="verify", subject="CWE-78 net.c:12", lens="injection")
    assert config["metadata"]["lens"] == "injection"
    # Absent rather than null where the notion does not apply -- triage and the
    # specialists are not about anybody else's claim.
    assert "lens" not in call_config(step="triage")["metadata"]


def test_every_verifier_call_is_told_which_specialist_it_is_arguing_with(indexed) -> None:
    """Through the real graph, on the config the model call is actually given.

    The hand-off from analysis to verification was the one edge in the run that
    left no record: a reader could see a claim investigated and refuted without
    seeing who had made it. `locate` knew and `claims` dropped it. Asserted on the
    `RunnableConfig` each call receives, because that is what carries the metadata
    into the trace -- a scripted caller never reaches LangChain, so there is no
    span to read here.
    """
    root, store = indexed
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})

    _run(root, store, caller, tools=FakeToolSession())

    lens_of = {trace["metadata"]["step"]: trace["metadata"].get("lens") for trace in caller.traces if trace is not None}
    assert lens_of["gather"] == "injection", "gathering evidence is about somebody's claim"
    assert lens_of["verify"] == "injection"
    # Absent on the calls that are nobody else's claim.
    assert lens_of.get("triage") is None
    assert lens_of.get("lens:injection") is None


# -- results kept across runs -------------------------------------------------


def _tree_at(tmp_path: Path, name: str, source: str) -> tuple[Path, ChunkStore]:
    root = tmp_path / name
    root.mkdir()
    (root / "app.c").write_text(source, encoding="utf-8")
    store = ChunkStore(tmp_path / f"{name}.db")
    build_index(root, store)
    return root, store


def test_a_second_run_over_unchanged_code_costs_nothing(tmp_path: Path) -> None:
    """The whole point of content-derived chunk ids, finally spent.

    Within a run that already bought something; across runs it bought nothing,
    so uploading the same tree twice paid full price for every unit that had not
    moved -- on a real codebase, almost all of them.
    """
    first_root, first_store = _tree_at(tmp_path, "first", VULNERABLE)
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})
    first = _run(first_root, first_store, caller)
    calls = len(caller.prompts)
    assert first.findings and calls > 0
    first_store.close()

    # A different run over identical code: same ids, nothing to do.
    second_root, second_store = _tree_at(tmp_path, "second", VULNERABLE)
    again = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})
    second = _run(second_root, second_store, again)

    assert again.prompts == [], "the model was asked about code already analysed"
    assert second.stats.chunks_cached == second.stats.chunks_total
    assert [f.id for f in second.findings] == [f.id for f in first.findings], "reuse must be faithful"
    second_store.close()


def test_changed_code_is_analysed_again(tmp_path: Path) -> None:
    """A chunk id is derived from the body, so an edited function is a new unit
    and the cache cannot answer for it."""
    first_root, first_store = _tree_at(tmp_path, "before", VULNERABLE)
    _run(first_root, first_store, ScriptedCaller())
    first_store.close()

    edited = VULNERABLE.replace('sprintf(cmd, "echo %s", arg);', 'snprintf(cmd, sizeof(cmd), "echo %s", arg);')
    second_root, second_store = _tree_at(tmp_path, "after", edited)
    caller = ScriptedCaller()
    report = _run(second_root, second_store, caller)

    assert caller.prompts, "the edited unit must be looked at again"
    assert report.stats.chunks_cached < report.stats.chunks_total
    second_store.close()


def test_a_different_recipe_does_not_reuse_another_one_s_answers(tmp_path: Path) -> None:
    """Serving a result produced by a narrower configuration is a false negative
    that looks like a cache hit -- the worst failure this tool has."""
    first_root, first_store = _tree_at(tmp_path, "narrow", VULNERABLE)
    _run(first_root, first_store, ScriptedCaller(), lenses=("injection",))
    first_store.close()

    second_root, second_store = _tree_at(tmp_path, "wide", VULNERABLE)
    caller = ScriptedCaller()
    report = _run(second_root, second_store, caller, lenses=("injection", "memory"))

    assert caller.prompts, "a run with more specialists must not inherit a narrower run's results"
    assert report.stats.chunks_cached == 0
    second_store.close()


def test_the_cache_can_be_turned_off(tmp_path: Path) -> None:
    first_root, first_store = _tree_at(tmp_path, "one", VULNERABLE)
    _run(first_root, first_store, ScriptedCaller())
    first_store.close()

    second_root, second_store = _tree_at(tmp_path, "two", VULNERABLE)
    caller = ScriptedCaller()
    _run(second_root, second_store, caller, cache_results=False)
    assert caller.prompts, "AGENT_CACHE=0 means analyse it again"
    second_store.close()
