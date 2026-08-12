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
#
# These descriptions are not documentation. They are handed to the endpoint as
# part of the JSON schema and sit beside the field while it is being decoded,
# which makes them the closest instruction to the tokens being produced -- so
# the ones asking for prose ask in the language that prose has to be in, and the
# example is in it too. An English exemplar next to `title` was most of why a
# fully Korean prompt still came back in English.
#
# The field *names* stay English: they are the schema's, not the reader's.


class CandidateEvidence(BaseModel):
    """One step of the argument, as the model states it."""

    role: EvidenceRole = Field(description="What this evidence contributes to the argument.")
    file: str = Field(description="Path of the file this evidence is in, exactly as given in the context.")
    anchor_text: str = Field(
        description="근거가 가리키는 원문을 코드에서 글자 그대로 복사한 것. 번역하지 마십시오. "
        "'NNN| ' 줄 번호 접두사는 빼십시오."
    )
    note: str = Field(description="이 단계가 왜 중요한지 한국어 한 문장.")


class CandidateRemediation(BaseModel):
    """The fix, as the model proposes it. Never applied automatically."""

    summary: str = Field(description="무엇을 고칠지 한국어 한 줄. 예: '셸을 거치지 말고 인자를 배열로 넘기기'.")
    detail: str = Field(description="어떻게 고치고 그것이 왜 문제를 닫는지, 한국어로.")


class CandidateFinding(BaseModel):
    """One suspected vulnerability, before the server resolves or verifies it."""

    title: str = Field(
        # Deliberately not a shape a real finding is likely to land on: an
        # example close to the answer gets copied instead of read.
        description="짧은 한국어 명사구. 영어 용어를 품더라도 구 전체는 한국어입니다. "
        "예: '설정 파일 이름을 통한 path traversal', '세션 검사를 건너뛴 권한 상승'."
    )
    severity: Severity
    cwe: str | None = Field(default=None, description="CWE identifier like 'CWE-78', or null if none applies.")
    anchor_text: str = Field(
        description="밑줄 그을 원문 -- 가장 문제가 되는 표현식 또는 문장 하나를, 코드에서 글자 그대로 "
        "복사한 것. 번역하지 마십시오. 'NNN| ' 줄 번호 접두사와 바깥 따옴표는 빼십시오."
    )
    explanation: str = Field(description="왜 악용 가능한지 한국어로. 구체적으로, 일반론이 아니라.")
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
        description="Written in English, for the model that analyses a caller -- not for a reader. "
        "One or two sentences: what this unit does to its inputs, what it returns, and whether "
        "either is attacker-influenced. Empty if unremarkable.",
    )


class Verdict(BaseModel):
    """The refute pass. Defaults are hostile to the finding on purpose."""

    refuted: bool = Field(description="True if the finding does not hold up. Default to true when uncertain.")
    reason: str = Field(description="성립하는지 아닌지, 그 이유를 한국어로.")
    confidence: float = Field(ge=0.0, le=1.0, description="0-1 confidence that the finding is real.")


#: The specialists. One generalist prompt asked to hold every vulnerability
#: class in mind at once skims all of them; four narrow ones, run concurrently,
#: each have room to be thorough about their own.
Lens = Literal["memory", "injection", "access", "logic"]

LENSES: tuple[Lens, ...] = get_args(Lens)


class Region(BaseModel):
    """One stretch of a unit worth reading closely."""

    start_line: int = Field(description="시작 줄 번호. 코드 앞에 붙은 'NNN| ' 의 숫자 그대로.")
    end_line: int = Field(description="끝 줄 번호, 포함. 판단에 필요한 선언과 대입까지 넣으십시오.")
    why: str = Field(description="여기를 자세히 볼 이유, 한국어 한 문장.")


class Scout(BaseModel):
    """Where in a unit is worth a specialist's close attention.

    Not findings -- candidates. The mirror of :class:`Triage` one level down:
    triage prunes units, this prunes the parts of a unit, and both exist so the
    expensive pass behind them reads less and reads it better.
    """

    regions: list[Region] = Field(
        default_factory=list,
        description="자세히 볼 구간들. 없으면 빈 목록. 확신이 없으면 넣는 쪽으로.",
    )


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
    reason: str = Field(default="", description="한국어 한 문장. 살펴볼 값어치가 있다고/없다고 본 이유.")


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
    #: Stretches the specialists were pointed at. Equal to the units inspected
    #: when nothing needed narrowing, and above it when something did.
    regions: int = 0
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
