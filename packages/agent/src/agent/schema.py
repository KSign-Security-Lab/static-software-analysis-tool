"""The contract between the model, the server and the web page.

Two schemas, kept apart. Model-facing (:class:`ChunkAnalysis`, :class:`Triage`,
:class:`Verdict`) is what guided decoding constrains the LLM to: analysis only.
Wire (:class:`Finding`, :class:`Report`) adds what the server owns -- the id, the
resolved span, the excerpt read from disk, the verification state.
"""

from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel, Field

# Bumped when a field is removed or changes meaning; adding an optional one is
# fine. Typed as the literal so the defaults below stay assignable.
SCHEMA_VERSION: Literal["1"] = "1"

Severity = Literal["critical", "high", "medium", "low", "info"]

EvidenceRole = Literal["source", "propagation", "sink", "missing_check", "context"]

SEVERITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


# --------------------------------------------------------------------------
# Model-facing: what guided decoding constrains the LLM to produce.
# --------------------------------------------------------------------------


class CandidateEvidence(BaseModel):
    """One step of the argument, as the model states it."""

    role: EvidenceRole = Field(description="What this evidence contributes to the argument.")
    file: str = Field(description="Path of the file this evidence is in, exactly as given in the context.")
    anchor_text: str = Field(
        description="The exact source text this evidence refers to, copied verbatim from the code. "
        "Do NOT include the 'NNN| ' line-number prefix."
    )
    note: str = Field(description="One sentence on why this step matters.")


class CandidateRemediation(BaseModel):
    """The fix, as the model proposes it. Never applied automatically."""

    summary: str = Field(description="One line: what to change.")
    detail: str = Field(description="How to change it, and why that closes the issue.")


class CandidateFinding(BaseModel):
    """One suspected vulnerability, before the server resolves or verifies it."""

    title: str = Field(description="Short noun phrase, e.g. 'Command injection via firmware URL'.")
    severity: Severity
    cwe: str | None = Field(default=None, description="CWE identifier like 'CWE-78', or null if none applies.")
    anchor_text: str = Field(
        description="The exact source text to underline -- the single most offending expression or statement, "
        "copied verbatim from the code WITHOUT the 'NNN| ' line-number prefix and without surrounding quotes."
    )
    explanation: str = Field(description="Why this is exploitable. Concrete, not generic advice.")
    evidence: list[CandidateEvidence] = Field(default_factory=list)
    remediation: CandidateRemediation


class ChunkAnalysis(BaseModel):
    """The model's output for one chunk.

    ``note`` is the cross-chunk metadata: stored here, injected into every
    caller's context. That is how taint crosses a chunk boundary.
    """

    findings: list[CandidateFinding] = Field(default_factory=list)
    note: str = Field(
        default="",
        description="One or two sentences for this unit's callers: what it does to its inputs, "
        "what it returns, and whether either is attacker-influenced. Empty if unremarkable.",
    )


class Verdict(BaseModel):
    """The refute pass. Defaults are hostile to the finding on purpose."""

    refuted: bool = Field(description="True if the finding does not hold up. Default to true when uncertain.")
    reason: str = Field(description="Why it holds or does not.")
    confidence: float = Field(ge=0.0, le=1.0, description="0-1 confidence that the finding is real.")


#: The specialists. One generalist prompt asked to hold every vulnerability
#: class in mind at once skims all of them; four narrow ones, run concurrently,
#: each have room to be thorough about their own.
Lens = Literal["memory", "injection", "access", "logic"]

LENSES: tuple[Lens, ...] = get_args(Lens)


class Triage(BaseModel):
    """The screening pass: is this unit worth a specialist's time, and whose?

    The mirror of :class:`Verdict`, and deliberately so. Verification defaults
    against the finding because a false positive wastes a reader's afternoon.
    Triage defaults *for* the unit, because a false negative here is a
    vulnerability nobody ever hears about.
    """

    worth_analysing: bool = Field(
        description="True unless this unit plainly cannot contain a vulnerability. When in doubt, true."
    )
    lenses: list[Lens] = Field(
        default_factory=list,
        description="Which specialists should look at it. Empty means all of them.",
    )
    reason: str = Field(default="", description="One sentence. What made this worth a look, or not.")


# --------------------------------------------------------------------------
# Wire: what the web consumes.
# --------------------------------------------------------------------------


class Span(BaseModel):
    """A resolved source range, 1-based and inclusive."""

    file: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    excerpt: str = Field(description="The text actually at this range, read from disk -- never from the model.")


class Evidence(BaseModel):
    """A step of the argument, with its location resolved."""

    role: EvidenceRole
    span: Span
    note: str


class Remediation(BaseModel):
    """Display-only. ``diff`` is never applied -- there is no write endpoint;
    it is the seam a future "fix now" attaches to."""

    summary: str
    detail: str
    diff: str | None = None


class Finding(BaseModel):
    """One verified vulnerability, ready to render as a lint marker."""

    schema_version: Literal["1"] = SCHEMA_VERSION
    id: str = Field(description="Content-derived and stable across runs, so two reports can be diffed.")
    chunk_id: str
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    title: str
    cwe: str | None = None
    primary: Span = Field(description="The span that gets the squiggle.")
    explanation: str
    evidence: list[Evidence] = Field(default_factory=list)
    remediation: Remediation
    verified: bool = Field(description="Survived the adversarial refute pass.")

    def sort_key(self) -> tuple[int, str, int, str]:
        """Most severe first, then position. Stable report order."""
        return (SEVERITY_ORDER.get(self.severity, 99), self.primary.file, self.primary.start_line, self.id)


class RunStats(BaseModel):
    """Counts kept separate rather than merged into one score."""

    files_indexed: int = 0
    files_skipped: int = 0
    chunks_total: int = 0
    chunks_inspected: int = 0
    chunks_cached: int = 0
    #: Screened out before any specialist looked at them.
    triaged_out: int = 0
    candidates: int = 0
    dropped_unlocatable: int = 0
    refuted: int = 0


class Report(BaseModel):
    """A complete inspection result."""

    schema_version: Literal["1"] = SCHEMA_VERSION
    run_id: str
    findings: list[Finding] = Field(default_factory=list)
    stats: RunStats = Field(default_factory=RunStats)

    def sorted_findings(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: f.sort_key())


class FindingDiff(BaseModel):
    """Two runs compared, by content-derived id."""

    new: list[Finding] = Field(default_factory=list)
    fixed: list[Finding] = Field(default_factory=list)
    unchanged: list[Finding] = Field(default_factory=list)


EXPORTED_MODELS: tuple[type[BaseModel], ...] = (
    Span,
    Evidence,
    Remediation,
    Finding,
    RunStats,
    Report,
    FindingDiff,
)
