"""The contract between the model, the server and the web page.

Two schemas, deliberately kept apart.

**Model-facing** (:class:`ChunkAnalysis` and friends) is what the LLM is
constrained to emit under guided decoding. It contains analysis only -- no ids,
no resolved coordinates, no verification state. Every field is something a
reader of the source could plausibly produce.

**Wire** (:class:`Finding`, :class:`Report`) is what the web consumes. It adds
everything the *server* owns: the stable id, the resolved span, the excerpt read
back from disk, whether the finding survived verification.

Conflating the two is how stable ids and guided decoding both get harder than
they need to be. The model cannot be trusted to compute an id, and the client
should never have to.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: Bumped when a field is removed or its meaning changes. Adding an optional
#: field does not require a bump; the web tolerates unknown keys.
#:
#: Typed as the literal rather than ``str`` so the field defaults below stay
#: assignable and a bump has to be made in both places deliberately.
SCHEMA_VERSION: Literal["1"] = "1"

Severity = Literal["critical", "high", "medium", "low", "info"]

#: What a piece of evidence is doing in the argument. ``source`` is where
#: untrusted data enters, ``sink`` is where it does damage, ``propagation`` is
#: the path between them, and ``missing_check`` is the validation that should
#: have been there and is not.
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
    """The model's complete output for one chunk.

    ``note`` is the cross-chunk metadata. It is stored against this chunk and
    injected into every caller's context, which is how taint crosses a chunk
    boundary without the whole tree entering one prompt. It should describe
    what this unit does to data passing through it -- not restate the findings.
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


# --------------------------------------------------------------------------
# Wire: what the web consumes.
# --------------------------------------------------------------------------


class Span(BaseModel):
    """A resolved source range. 1-based and inclusive, as editors count."""

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
    """The proposed fix. Display-only.

    ``diff`` may hold a unified diff, but nothing applies it: there is no write
    endpoint. It is the seam a future "fix now" would attach to.
    """

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
        """Most severe first, then by position, so report order is stable."""
        return (SEVERITY_ORDER.get(self.severity, 99), self.primary.file, self.primary.start_line, self.id)


class RunStats(BaseModel):
    """What the run did, for the progress UI and for honest reporting."""

    files_indexed: int = 0
    files_skipped: int = 0
    chunks_total: int = 0
    chunks_inspected: int = 0
    chunks_cached: int = 0
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
    """Two runs compared. Content-derived ids are what make this possible."""

    new: list[Finding] = Field(default_factory=list)
    fixed: list[Finding] = Field(default_factory=list)
    unchanged: list[Finding] = Field(default_factory=list)


#: Models exported to TypeScript. Order matters only for readability of the
#: generated file; dependencies are emitted before dependents.
EXPORTED_MODELS: tuple[type[BaseModel], ...] = (
    Span,
    Evidence,
    Remediation,
    Finding,
    RunStats,
    Report,
    FindingDiff,
)
