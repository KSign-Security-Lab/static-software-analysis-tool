"""The inspection loop, driven by a scripted model.

A fake :class:`StructuredCaller` makes the loop's behaviour testable as
behaviour rather than as vibes: whether notes really reach callers, whether an
unlocatable finding is really dropped, whether refutation really removes things,
whether a second run really skips work. None of that is observable against a
live model, because a live model answers differently every time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from agent.config import AgentConfig
from agent.graph.build import run_inspection
from agent.index import ChunkStore, build_index
from agent.schema import (
    CandidateEvidence,
    CandidateFinding,
    CandidateRemediation,
    ChunkAnalysis,
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
    ) -> None:
        self.analyses = analyses or {}
        self.verdict = verdict if verdict is not None else Verdict(refuted=False, reason="holds", confidence=0.9)
        self.default_analysis = default_analysis or ChunkAnalysis()
        self.prompts: list[tuple[str, str]] = []
        self.gather_calls: list[tuple[Any, int]] = []

    #: Set by tests that want the gather step to return something.
    gathered: str = ""

    def gather(self, system: str, user: str, session: Any, budget: int) -> str:
        self.prompts.append(("gather", user))
        self.gather_calls.append((session, budget))
        return self.gathered

    def call(self, schema: type[BaseModel], system: str, user: str) -> Any:
        self.prompts.append((schema.__name__, user))
        if schema is ChunkAnalysis:
            for symbol, analysis in self.analyses.items():
                if f":: {symbol} " in user:
                    return analysis
            return self.default_analysis
        if schema is Verdict:
            return self.verdict
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
        def call(self, schema: type[BaseModel], system: str, user: str) -> Any:
            if schema is Verdict:
                return None
            return super().call(schema, system, user)

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
    assert "WHAT THIS UNIT'S CALLEES DO" in handler_prompts[0]
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
    assert "WHAT THE TOOLS RETURNED" in verdict_prompts[0]
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
    assert "WHAT THE TOOLS RETURNED" not in caller.prompts_for("Verdict")[0]
    store.close()


def test_an_empty_gather_does_not_pollute_the_verdict_prompt(indexed) -> None:
    """If the model decides it needs nothing, the prompt should not gain an
    empty section implying it looked and found nothing."""
    root, store = indexed
    caller = ScriptedCaller(analyses={"run_command": ChunkAnalysis(findings=[_finding("system(cmd);")])})
    caller.gathered = "   "
    session = FakeToolSession()

    _run(root, store, caller, tools=session)

    assert "WHAT THE TOOLS RETURNED" not in caller.prompts_for("Verdict")[0]
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
