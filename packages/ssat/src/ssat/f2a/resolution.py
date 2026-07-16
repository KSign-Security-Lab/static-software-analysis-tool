"""Handler-resolution model for F2-A step 1.

Discovery is three separated concerns:

    extractors (per syntax) -> ResolutionEvidence[]
                            -> group by callback -> HandlerCandidate[]
                            -> selection stage   -> SelectionResult

This module holds the data model plus the *pure* (CPG-free) pieces — action-id
consistency and the selection function — so they are unit-testable without a
graph. The extractors themselves live in ``pipeline.py`` because they traverse
the CPG.

Phase 1 wires the existing four strategies in as evidence producers and uses
``select_cascade`` (most-precise-first), which reproduces the historical cascade
behaviour exactly. Corroboration / contradiction is a later, opt-in policy
(``select_corroborate``, not implemented here yet).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class MatchStrength(Enum):
    """How well an observed ActionIdentifier matched a KB profile.

    Ordinal — higher is stronger. A numeric constant resolved from a symbol is
    deliberately ranked above a heuristic substring match.
    """

    EXACT_IDENTIFIER = 4      # symbol / protocol string / numeric id matched a KB field verbatim
    RESOLVED_VALUE = 3        # a symbol/macro resolved to a constant that matched a KB numeric id
    NORMALIZED_NAME = 2       # matched the normalized (UPPER_SNAKE / canonical) action name
    HEURISTIC_SUBSTRING = 1   # a KB token appears as a substring of an observed token
    NONE = 0


class ConsistencyState(Enum):
    CONSISTENT = "CONSISTENT"      # >=2 independent fields agree on one identity
    CONFLICTING = "CONFLICTING"    # populated fields disagree
    PARTIAL = "PARTIAL"            # <2 cross-checkable fields — nothing to corroborate


class ResolutionStatus(Enum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


class UnresolvedReason(Enum):
    NO_EVIDENCE = "NO_EVIDENCE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    UNSUPPORTED_REGISTRAR_CALL = "UNSUPPORTED_REGISTRAR_CALL"
    UNRESOLVED_INDIRECT_CALL = "UNRESOLVED_INDIRECT_CALL"
    EXTERNAL_DEFINITION = "EXTERNAL_DEFINITION"
    DYNAMIC_ACTION_ID = "DYNAMIC_ACTION_ID"
    MISSING_POINTSTO = "MISSING_POINTSTO"
    GENERATED_CODE_UNAVAILABLE = "GENERATED_CODE_UNAVAILABLE"
    REGISTRATION_OUT_OF_TU = "REGISTRATION_OUT_OF_TU"


# Evidence kinds (open set of string constants).
STRING_DISPATCH = "STRING_DISPATCH"
ENUM_CASE = "ENUM_CASE"
REGISTRATION_INIT = "REGISTRATION_INIT"
REGISTRATION_ASSIGN = "REGISTRATION_ASSIGN"
REGISTRAR_CALL = "REGISTRAR_CALL"
NAME_MATCH = "NAME_MATCH"
DISPATCH_SITE = "DISPATCH_SITE"

# Per-kind prior reliability == the historical hard-coded strategy confidences.
KIND_WEIGHT: Dict[str, float] = {
    STRING_DISPATCH: 0.90,
    ENUM_CASE: 0.85,
    REGISTRATION_INIT: 0.80,
    REGISTRATION_ASSIGN: 0.80,
    REGISTRAR_CALL: 0.70,
    NAME_MATCH: 0.70,       # pattern; token fallback overrides to 0.65 at emit time
    DISPATCH_SITE: 0.00,
}

# Tie-break order for equal-weight candidates (mirrors the old cascade order).
KIND_RANK: Dict[str, int] = {
    STRING_DISPATCH: 5,
    ENUM_CASE: 4,
    REGISTRATION_INIT: 3,
    REGISTRATION_ASSIGN: 3,
    REGISTRAR_CALL: 2,
    NAME_MATCH: 1,
    DISPATCH_SITE: 0,
}

# Explicit ordinal rank for MatchStrength — used by the dedup survivor rule so it
# never relies on the enum's incidental value ordering (tested directly).
MATCH_STRENGTH_RANK: Dict[MatchStrength, int] = {
    MatchStrength.EXACT_IDENTIFIER: 4,
    MatchStrength.RESOLVED_VALUE: 3,
    MatchStrength.NORMALIZED_NAME: 2,
    MatchStrength.HEURISTIC_SUBSTRING: 1,
    MatchStrength.NONE: 0,
}

# Score multiplier per match strength (the Q3 granularity feeding the calculus).
MATCH_MULTIPLIER: Dict[MatchStrength, float] = {
    MatchStrength.EXACT_IDENTIFIER: 1.00,
    MatchStrength.RESOLVED_VALUE: 0.95,
    MatchStrength.NORMALIZED_NAME: 0.85,
    MatchStrength.HEURISTIC_SUBSTRING: 0.70,
    MatchStrength.NONE: 0.00,
}

STRONG_BASIS = (MatchStrength.EXACT_IDENTIFIER, MatchStrength.RESOLVED_VALUE)


@dataclass
class CalculusConfig:
    """Tunable Phase-2 policy constants (kept out of the aggregation code so they
    can be retuned without touching the algorithm)."""

    weak_only_cap: float = 0.85
    global_cap: float = 0.99
    min_confidence: float = 0.50
    ambiguity_margin: float = 0.15
    conflict_multiplier_cap: float = 0.70   # CONFLICTING identifier caps M here
    conflict_scale: float = 0.5             # ...then scales the evidence score
    # Documented-but-disabled hook (see spec §4): widen the margin when the top
    # two candidates both own a strong-basis group. Off by default.
    strong_competitor_hardening: bool = False


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass
class ActionIdentifier:
    """Several representations of one action identity, kept side by side.

    The fields are individual *observations*; they are not silently merged. Use
    :meth:`consistency` to classify whether the populated fields agree.
    """

    protocol_string: Optional[str] = None      # wire name / string literal ("RemoteStartTransaction")
    symbol: Optional[str] = None               # enum/macro constant ("ACTION_REMOTE_START")
    numeric_id: Optional[int] = None           # integer id as written (15)
    normalized_name: Optional[str] = None      # KB canonical action_name this maps to
    raw_expression: Optional[str] = None       # raw CPG code of the id node
    resolved_value: Optional[Union[int, str]] = None  # constant a symbol/macro resolves to
    node: Optional[int] = None                 # provenance: CPG node the id was read from

    def _numeric_values(self) -> Set[int]:
        vals: Set[int] = set()
        if self.numeric_id is not None:
            vals.add(self.numeric_id)
        if isinstance(self.resolved_value, int):
            vals.add(self.resolved_value)
        return vals

    def consistency(self, kb: Any = None) -> ConsistencyState:
        """Classify the internal agreement of the populated fields.

        Kb-free, a mismatch between ``numeric_id`` and an integer
        ``resolved_value`` is always CONFLICTING. With a knowledge base, each
        populated field group is resolved to the set of KB actions it could
        denote; disjoint groups are CONFLICTING, agreeing groups CONSISTENT, and
        fewer than two cross-checkable groups PARTIAL.
        """
        # Hard, KB-free contradiction: two different concrete numeric values.
        if len(self._numeric_values()) >= 2:
            return ConsistencyState.CONFLICTING

        if kb is None:
            groups = sum(
                x is not None
                for x in (self.protocol_string, self.symbol, self.numeric_id, self.normalized_name)
            )
            # Without a KB we cannot cross-check symbolic fields against each
            # other, so anything past the numeric check is reported PARTIAL.
            return ConsistencyState.PARTIAL if groups <= 1 else ConsistencyState.PARTIAL

        implied: List[Set[str]] = []
        if self.protocol_string is not None:
            implied.append(_kb_actions_for_name(kb, self.protocol_string))
        if self.normalized_name is not None:
            implied.append(_kb_actions_for_name(kb, self.normalized_name))
        if self.symbol is not None:
            implied.append(_kb_actions_for_symbol(kb, self.symbol))
        num = self.numeric_id
        if num is None and isinstance(self.resolved_value, int):
            num = self.resolved_value
        if num is not None:
            implied.append(_kb_actions_for_numeric(kb, num))

        implied = [s for s in implied if s]  # drop fields that denote no known action
        if len(implied) < 2:
            return ConsistencyState.PARTIAL
        inter: Set[str] = set(implied[0])
        for s in implied[1:]:
            inter &= s
        return ConsistencyState.CONSISTENT if inter else ConsistencyState.CONFLICTING


def _kb_actions_for_symbol(kb: Any, symbol: str) -> Set[str]:
    return {
        name for name, p in kb.actions.items() if symbol in getattr(p, "action_symbols", [])
    }


def _kb_actions_for_numeric(kb: Any, value: int) -> Set[str]:
    return {
        name for name, p in kb.actions.items() if value in getattr(p, "numeric_ids", [])
    }


def _kb_actions_for_name(kb: Any, name: str) -> Set[str]:
    return {a for a in kb.actions if a == name}


@dataclass
class ResolutionEvidence:
    """One observation linking an action id (and/or dispatch site) to a callback."""

    kind: str
    action_id: ActionIdentifier
    weight: float
    match_strength: MatchStrength
    callback: Optional[int] = None          # METHOD node id (None for a bare dispatch site)
    dispatch_site: Optional[int] = None
    nodes: List[int] = field(default_factory=list)
    provenance_group: Optional[str] = None  # correlated-evidence key (used by corroboration, not cascade)
    extractor: str = ""
    mapping_evidence: List[Any] = field(default_factory=list)  # human-facing MappingEvidence for the HandlerMap
    score: float = 0.0                       # post-policy score (W*M, after any consistency penalty)
    score_pre_penalty: float = 0.0           # W*M before the consistency penalty (diagnostic)


@dataclass
class HandlerCandidate:
    """All evidence that agrees on one callback."""

    callback: int
    evidence: List[ResolutionEvidence]
    confidence: float = 0.0


@dataclass
class ConflictReport:
    competing: List[Dict[str, Any]]
    margin: float
    note: str


@dataclass
class UnresolvedReport:
    reason: UnresolvedReason
    dispatch_site: Optional[int] = None
    attempted_extractors: List[str] = field(default_factory=list)
    available_evidence: List[ResolutionEvidence] = field(default_factory=list)
    secondary: Optional[UnresolvedReason] = None


@dataclass
class SelectionResult:
    status: ResolutionStatus
    chosen: Optional[HandlerCandidate] = None
    candidates: List[HandlerCandidate] = field(default_factory=list)
    conflict: Optional[ConflictReport] = None
    unresolved: Optional[UnresolvedReport] = None


# ---------------------------------------------------------------------------
# Selection (pure)
# ---------------------------------------------------------------------------


def _best_evidence(cand: HandlerCandidate) -> ResolutionEvidence:
    return max(cand.evidence, key=lambda e: (e.weight, KIND_RANK.get(e.kind, 0)))


def _conflict_report(ranked: List[HandlerCandidate]) -> Optional[ConflictReport]:
    if len(ranked) <= 1:
        return None
    margin = round(ranked[0].confidence - ranked[1].confidence, 6)
    return ConflictReport(
        competing=[
            {
                "callback": c.callback,
                "confidence": c.confidence,
                "evidence_kinds": sorted({e.kind for e in c.evidence}),
            }
            for c in ranked[:3]
        ],
        margin=margin,
        note="competing callbacks; margin between top two",
    )


# --- exact deduplication (spec §1) -----------------------------------------


def _dedup_key(e: ResolutionEvidence) -> Any:
    return (
        e.kind,
        e.callback,
        e.dispatch_site if e.dispatch_site is not None else -1,
        tuple(sorted(e.nodes)),
    )


def _survivor(a: ResolutionEvidence, b: ResolutionEvidence) -> ResolutionEvidence:
    """Deterministic winner between two exact-duplicate evidences that differ
    only in metadata: higher match-strength rank, then higher weight, then the
    lexicographically smaller extractor name."""
    ka = (MATCH_STRENGTH_RANK[a.match_strength], a.weight)
    kb = (MATCH_STRENGTH_RANK[b.match_strength], b.weight)
    if ka != kb:
        return a if ka > kb else b
    return a if a.extractor <= b.extractor else b


def dedupe_evidence(evidences: List[ResolutionEvidence]) -> List[ResolutionEvidence]:
    """Collapse literally-identical observations (§1). Extractor identity is NOT
    part of the key, so the same fact seen by two extractors becomes one."""
    best: Dict[Any, ResolutionEvidence] = {}
    for e in evidences:
        key = _dedup_key(e)
        cur = best.get(key)
        best[key] = e if cur is None else _survivor(cur, e)
    return [best[k] for k in sorted(best, key=lambda k: (str(k[0]), k[1] if k[1] is not None else -1, k[2], k[3]))]


def select_cascade(candidates: List[HandlerCandidate]) -> SelectionResult:
    """Cascade-compatible selection: the candidate owning the single
    highest-weight evidence wins, reproducing the historical most-precise-first
    cascade. Competitors are *recorded* in a ConflictReport but never downgrade
    the status — corroboration and contradiction are a separate (later) policy.

    Contract for downstream ordering: ``chosen`` is the selected candidate and
    ``candidate.confidence`` is the post-policy score. The public projection
    orders candidates as *selection order* (chosen first, then by that score with
    a function/file/line tie-break), so a future policy that selects a
    non-max-confidence candidate still serialises chosen-first.
    """
    if not candidates:
        return SelectionResult(
            status=ResolutionStatus.UNRESOLVED,
            unresolved=UnresolvedReport(reason=UnresolvedReason.NO_EVIDENCE),
        )

    for c in candidates:
        c.confidence = max(e.weight for e in c.evidence)

    def sort_key(c: HandlerCandidate) -> Any:
        best = _best_evidence(c)
        return (c.confidence, KIND_RANK.get(best.kind, 0), -c.callback)

    ranked = sorted(candidates, key=sort_key, reverse=True)
    return SelectionResult(
        status=ResolutionStatus.RESOLVED,
        chosen=ranked[0],
        candidates=ranked,
        conflict=_conflict_report(ranked),
    )


# --- Phase 2 policy: corroborate + contradict (spec) ------------------------


def _score_evidence(e: ResolutionEvidence, kb: Any, cfg: CalculusConfig) -> None:
    """Set e.score_pre_penalty and e.score per the calculus (spec §3.1–3.2)."""
    m = MATCH_MULTIPLIER[e.match_strength]
    pre = e.weight * m
    e.score_pre_penalty = round(pre, 6)
    if e.action_id.consistency(kb) is ConsistencyState.CONFLICTING:
        m_eff = min(m, cfg.conflict_multiplier_cap)
        e.score = round(e.weight * m_eff * cfg.conflict_scale, 6)
    else:
        e.score = e.score_pre_penalty


def select_corroborate(
    candidates: List[HandlerCandidate], kb: Any = None, cfg: Optional[CalculusConfig] = None
) -> SelectionResult:
    """Phase-2 selection: per-evidence scoring + consistency penalty, max within
    a provenance group, noisy-OR across groups, caps, then margin-based status.

    Aggregation order is fixed: penalty (per-evidence) -> group-max -> noisy-OR
    -> caps. Contradiction is a competing-callback margin; identifier conflict is
    a per-evidence penalty only and never forces AMBIGUOUS on its own.
    """
    cfg = cfg or CalculusConfig()
    if not candidates:
        return SelectionResult(
            status=ResolutionStatus.UNRESOLVED,
            unresolved=UnresolvedReport(reason=UnresolvedReason.NO_EVIDENCE),
        )

    for c in candidates:
        groups: Dict[str, float] = {}
        for e in c.evidence:
            _score_evidence(e, kb, cfg)
            key = e.provenance_group or f"nogroup:{id(e)}"
            groups[key] = max(groups.get(key, 0.0), e.score)
        doubt = 1.0
        for g in groups.values():
            doubt *= (1.0 - g)
        conf = min(cfg.global_cap, 1.0 - doubt)
        if not any(e.match_strength in STRONG_BASIS for e in c.evidence):
            conf = min(conf, cfg.weak_only_cap)
        c.confidence = round(conf, 6)

    ranked = sorted(
        candidates,
        key=lambda c: (c.confidence, KIND_RANK.get(_best_evidence(c).kind, 0), -c.callback),
        reverse=True,
    )
    conflict = _conflict_report(ranked)

    # min-confidence: never bind below the floor; retain candidates for review.
    if ranked[0].confidence < cfg.min_confidence:
        return SelectionResult(
            status=ResolutionStatus.UNRESOLVED,
            chosen=None,
            candidates=ranked,
            conflict=conflict,
            unresolved=UnresolvedReport(
                reason=UnresolvedReason.LOW_CONFIDENCE,
                available_evidence=[e for c in ranked for e in c.evidence],
            ),
        )

    if len(ranked) > 1 and (ranked[0].confidence - ranked[1].confidence) < cfg.ambiguity_margin:
        return SelectionResult(
            status=ResolutionStatus.AMBIGUOUS,
            chosen=None,
            candidates=ranked,
            conflict=conflict,
        )

    return SelectionResult(
        status=ResolutionStatus.RESOLVED,
        chosen=ranked[0],
        candidates=ranked,
        conflict=conflict,
    )
