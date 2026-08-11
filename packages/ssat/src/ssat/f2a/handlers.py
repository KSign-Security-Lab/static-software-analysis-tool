"""Which function handles an OCPP action, and the evidence for saying so.

F2-A step 1. Five extractors look for the handler in five different ways -- an
action string literal next to a call, a switch case on an action enum, a
registration table, a registrar helper, and finally a name match -- and the
selection policy in :mod:`ssat.f2a.resolution` decides between them.

Split out of ``pipeline.py``, where these 22 methods shared one class with the
six flow-analysis steps and touched none of their state. The only overlap was two
CPG queries, which now live on :class:`~ssat.f2a.graph.CPGModel` where the rest
of the graph vocabulary is.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .evidence import at, code_at, dispatch_to_handler, method_ref
from .graph import CPGModel, cpg_id
from .kb import KnowledgeBase, default_knowledge_base
from .models import (
    ActionIdentifierView,
    CompetingCandidateView,
    ConflictReportView,
    EvidenceRecord,
    HandlerRef,
    HandlerResolution,
    HandlerResolutionCandidate,
    HandlerResolutionEvidence,
    MappingEvidence,
    UnresolvedDispatchSite,
    UnresolvedReportView,
)
from .resolution import (
    ENUM_CASE,
    ActionIdentifier,
    NAME_MATCH,
    REGISTRAR_CALL,
    REGISTRATION_ASSIGN,
    REGISTRATION_INIT,
    STRING_DISPATCH,
    CalculusConfig,
    ConsistencyState,
    HandlerCandidate,
    MatchStrength,
    ResolutionEvidence,
    ResolutionStatus,
    SelectionResult,
    UnresolvedReason,
    UnresolvedReport,
    dedupe_evidence,
    select_cascade,
    select_corroborate,
)


def _strip_quotes(text: str) -> str:
    """Drop the surrounding quotes from a string literal's source text."""
    t = (text or "").strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        return t[1:-1]
    return t


@dataclass
class HandlerRegistration:
    """Shape-agnostic 'action id is bound to this callback here' fact.

    One extractor recovers it from each registration syntax (aggregate
    initializer, indexed assignment, and — in future — DFG-correlated field
    stores or registrar calls); handler discovery consumes the list uniformly.
    """

    action_id_symbols: Set[str]  # upper-cased id tokens co-located with the ref
    action_id_literals: Set[str]  # numeric/string literal ids co-located with the ref
    callback_method: int  # METHOD node of the handler
    mechanism: str  # AGGREGATE_INIT | INDEXED_ASSIGN | ...
    evidence_node: int  # the initializer/assignment node proving the pairing
    ref_node: int  # the METHOD_REF node
    site_key: str = ""  # the enclosing table/array (shared by entries of one table)
    id_sites: List[int] = field(default_factory=list)  # sibling `.action = id` store(s), for the trail
    slot: str = ""  # receiver/slot code (e.g. `handlers[0]`), for the trail


#: Joern comparison operators, for spotting `if (id == ACTION)` style dispatch.
CMP_OPS = frozenset(
    {
        "<operator>.equals",
        "<operator>.notEquals",
        "<operator>.lessThan",
        "<operator>.greaterThan",
        "<operator>.lessEqualsThan",
        "<operator>.greaterEqualsThan",
    }
)


class HandlerResolver:
    """Resolves an OCPP action to the function that handles it.

    Holds no pipeline state: give it a CPG and a knowledge base and ask it about
    an action. Results are memoised per action in :attr:`selections`.
    """

    def __init__(
        self,
        cpg: CPGModel,
        kb: Optional[KnowledgeBase] = None,
        selection: str = "corroborate",
        calculus: Optional[CalculusConfig] = None,
    ):
        self.cpg = cpg
        self.kb = kb or default_knowledge_base()
        # "corroborate" (Phase 2, default) or "cascade" (Phase 1, most-precise-first).
        self.selection = selection
        self.calculus = calculus or CalculusConfig()
        #: action -> the selection made for it, for inspection and tests
        self.selections: Dict[str, SelectionResult] = {}
        self._registration_cache: Optional[List[HandlerRegistration]] = None

    @staticmethod
    def _upper_snake(name: str) -> str:
        """DataTransfer -> DATA_TRANSFER (for matching enum/case symbols)."""
        out = []
        for i, ch in enumerate(name):
            if ch.isupper() and i > 0 and not name[i - 1].isupper():
                out.append("_")
            out.append(ch.upper())
        return "".join(out)

    def _action_symbol_tokens(self, action: str) -> Set[str]:
        prof = self.kb.actions.get(action)
        toks = {self._upper_snake(action)}
        for s in prof.action_symbols if prof else []:
            toks.add(s.upper())
        return toks

    def resolve(self, action: str) -> SelectionResult:
        """Which function handles ``action``, and why.

        Runs all five extractors, groups their evidence by candidate callback and
        applies the selection policy. The result is recorded in :attr:`selections`,
        which the pipeline reads to report one outcome per requested action --
        resolved, ambiguous or unresolved alike.
        """
        sel = self._select(action)
        self.selections[action] = sel
        return sel

    def _select(self, action: str) -> SelectionResult:
        evidences: List[ResolutionEvidence] = []
        for extractor in (
            self._handler_by_string,
            self._handler_by_enum_case,
            self._handler_by_registration,
            self._handler_by_registrar_call,
            self._handler_by_name,
        ):
            evidences.extend(extractor(action))

        evidences = dedupe_evidence(evidences)  # spec §1: collapse identical observations

        by_callback: Dict[int, List[ResolutionEvidence]] = {}
        for ev in evidences:
            if ev.callback is None:
                continue
            by_callback.setdefault(ev.callback, []).append(ev)
        candidates = [HandlerCandidate(callback=cb, evidence=evs) for cb, evs in by_callback.items()]

        if self.selection == "cascade":
            sel = select_cascade(candidates)
        else:
            sel = select_corroborate(candidates, self.kb, self.calculus)

        # Only synthesize a dispatch-based unresolved reason when nothing bound at
        # all; a below-floor candidate keeps its LOW_CONFIDENCE report + candidates.
        if sel.status is ResolutionStatus.UNRESOLVED and not sel.candidates:
            sel.unresolved = self._diagnose_unresolved(action, evidences)
        return sel

    def limitation_for(self, action: str, sel: Optional[SelectionResult]) -> str:
        """Compatibility limitation string, derived from the structured selection
        result (conflict / unresolved report) so it cannot drift from
        ``handler_resolutions``."""
        if sel is not None and sel.status is ResolutionStatus.AMBIGUOUS:
            # Handlers WERE found; the selector declined to choose. Derive from
            # the competing candidates rather than claiming none was found.
            fns = ", ".join(self.cpg.name(c.callback) for c in sel.candidates)
            return (
                f"Multiple competing handlers found for action '{action}' "
                f"({len(sel.candidates)} candidates: {fns}); no handler selected. "
                f"[compat: see handler_resolutions]"
            )
        if sel is not None and sel.unresolved is not None:
            msg = f"No handler resolved for action '{action}': {sel.unresolved.reason.value}"
            if sel.unresolved.secondary is not None:
                msg += f" ({sel.unresolved.secondary.value})"
            return msg + " [compat: see handler_resolutions]"
        return (
            f"No handler found for action '{action}' in this CPG "
            f"(dispatch may be dynamic / in another translation unit). "
            f"[compat: see handler_resolutions]"
        )

    def selection_to_resolution(self, action: str, sel: SelectionResult) -> HandlerResolution:
        """Project the internal SelectionResult (CPG node ids) onto the public,
        serializable HandlerResolution (functions / files / lines). ``chosen`` is
        taken *only* from ``status == RESOLVED`` — assembly never re-picks a
        winner."""
        cpg = self.cpg

        def _consistency(cand: HandlerCandidate) -> str:
            states = [e.action_id.consistency(self.kb) for e in cand.evidence]
            if any(s is ConsistencyState.CONFLICTING for s in states):
                return "CONFLICTING"
            if any(s is ConsistencyState.CONSISTENT for s in states):
                return "CONSISTENT"
            return "PARTIAL"

        def _ev_view(e: ResolutionEvidence) -> HandlerResolutionEvidence:
            aid = e.action_id
            site = None
            if e.dispatch_site is not None:
                owner = cpg.method_of(e.dispatch_site)
                site = UnresolvedDispatchSite(
                    file=cpg.method_filename(owner) if owner is not None else "",
                    line=cpg.line(e.dispatch_site),
                    code=cpg.code(e.dispatch_site),
                )
            return HandlerResolutionEvidence(
                kind=e.kind,
                extractor=e.extractor,
                match_strength=e.match_strength.name,
                action_id_consistency=aid.consistency(self.kb).value,
                provenance_group=e.provenance_group or "",
                weight=e.weight,
                score=e.score,
                score_pre_penalty=e.score_pre_penalty,
                action_id=ActionIdentifierView(
                    protocol_string=aid.protocol_string,
                    symbol=aid.symbol,
                    numeric_id=aid.numeric_id,
                    normalized_name=aid.normalized_name,
                    raw_expression=aid.raw_expression,
                    resolved_value=aid.resolved_value,
                ),
                dispatch_site=site,
                records=[
                    EvidenceRecord(type=m.type, value=m.value, file=m.file, line=m.line) for m in e.mapping_evidence
                ],
            )

        def _view(cand: HandlerCandidate) -> HandlerResolutionCandidate:
            cb = cand.callback
            return HandlerResolutionCandidate(
                function=cpg.name(cb),
                file=cpg.method_filename(cb),
                line=cpg.line(cb),
                confidence=cand.confidence,
                evidence_kinds=sorted({e.kind for e in cand.evidence}),
                action_id_consistency=_consistency(cand),
                evidence=[_ev_view(e) for e in cand.evidence],
            )

        # Candidate order is *selection order*, not raw-confidence order:
        #   1. the selected candidate (sel.chosen) is always first, and
        #   2. the remainder is ordered by the selection policy — represented by
        #      the post-policy `confidence` score — with a documented tie-break
        #      of (function, file, line) for stability.
        # Under the cascade policy chosen == max-confidence, but this holds even
        # if a future policy selects a non-max-confidence candidate.
        ordered = sorted(
            sel.candidates,
            key=lambda c: (
                -c.confidence,
                cpg.name(c.callback),
                cpg.method_filename(c.callback),
                str(cpg.line(c.callback)),
            ),
        )
        chosen_ref: Optional[HandlerRef] = None
        if sel.status is ResolutionStatus.RESOLVED and sel.chosen is not None:
            chosen = sel.chosen
            ordered = [c for c in ordered if c is chosen] + [c for c in ordered if c is not chosen]
            cb = chosen.callback
            chosen_ref = HandlerRef(
                file=cpg.method_filename(cb),
                function=cpg.name(cb),
                line=cpg.line(cb),
            )

        conflict_view: Optional[ConflictReportView] = None
        if sel.conflict is not None:
            conflict_view = ConflictReportView(
                competing=[
                    CompetingCandidateView(
                        function=cpg.name(c["callback"]),
                        confidence=c["confidence"],
                        evidence_kinds=list(c["evidence_kinds"]),
                    )
                    for c in sel.conflict.competing
                ],
                margin=sel.conflict.margin,
                note=sel.conflict.note,
            )

        unresolved_view: Optional[UnresolvedReportView] = None
        if sel.unresolved is not None:
            u = sel.unresolved
            site = None
            if u.dispatch_site is not None:
                owner = cpg.method_of(u.dispatch_site)
                site = UnresolvedDispatchSite(
                    file=cpg.method_filename(owner) if owner is not None else "",
                    line=cpg.line(u.dispatch_site),
                    code=cpg.code(u.dispatch_site),
                )
            unresolved_view = UnresolvedReportView(
                reason=u.reason.value,
                secondary=u.secondary.value if u.secondary else None,
                dispatch_site=site,
                attempted_extractors=list(u.attempted_extractors),
            )

        return HandlerResolution(
            action=action,
            status=sel.status.value,
            chosen=chosen_ref,
            candidates=[_view(c) for c in ordered],
            conflict=conflict_view,
            unresolved=unresolved_view,
        )

    def _diagnose_unresolved(self, action: str, evidences: List[ResolutionEvidence]) -> UnresolvedReport:
        """Explain *why* no handler resolved, primary reason first — so the
        result is actionable (e.g. 'registrar-style call unsupported' rather than
        the generic 'indirect call unresolved')."""
        cpg = self.cpg
        tokens = {t for t in self._action_symbol_tokens(action) if t}
        prof = self.kb.actions.get(action)
        numeric = {str(n) for n in (prof.numeric_ids if prof else [])}

        dispatch_site: Optional[int] = None
        registrar = False
        for v in cpg.vertices:
            label = v.get("label")
            if label == "CALL" and cpg.name(cpg_id(v)) == "<operator>.pointerCall":
                if dispatch_site is None:
                    dispatch_site = cpg_id(v)
                continue
            if label != "METHOD_REF" or registrar:
                continue
            ref = cpg_id(v)
            parent = self.cpg.ast_parent(ref)
            if parent is None or cpg.label(parent) != "CALL":
                continue
            if cpg.name(parent) in ("<operator>.arrayInitializer", "<operator>.assignment"):
                continue  # handled by the AST registration extractor
            # A registrar-style call: an internal METHOD_REF passed alongside an
            # id token / numeric that matches this action.
            for d in cpg.ast_descendants(parent):
                code_u = str(cpg.code(d) or "").upper()
                if any(t in code_u for t in tokens):
                    registrar = True
                    break
                if cpg.label(d) == "LITERAL" and _strip_quotes(cpg.code(d)) in numeric:
                    registrar = True
                    break

        if registrar:
            # Producer 2 tried a resolved registrar call but did not reach the
            # terminal store -> a more precise reason than "unsupported". When the
            # miss was classified as a runtime search-then-write registrar, name
            # that idiom specifically (most actionable).
            if getattr(self, "_registrar_store_miss", False):
                reason = getattr(self, "_registrar_miss_reason", None) or (UnresolvedReason.REGISTRAR_STORE_NOT_REACHED)
            else:
                reason = UnresolvedReason.UNSUPPORTED_REGISTRAR_CALL
            secondary = UnresolvedReason.UNRESOLVED_INDIRECT_CALL if dispatch_site else None
        elif dispatch_site is not None:
            reason = UnresolvedReason.UNRESOLVED_INDIRECT_CALL
            secondary = None
        else:
            reason = UnresolvedReason.NO_EVIDENCE
            secondary = None

        return UnresolvedReport(
            reason=reason,
            dispatch_site=dispatch_site,
            attempted_extractors=[
                "string_dispatch",
                "enum_case",
                "registration_ast",
                "name_match",
            ],
            available_evidence=list(evidences),
            secondary=secondary,
        )

    def _handler_by_string(self, action: str) -> List[ResolutionEvidence]:
        """Extractor — action string literal + the call in its branch."""
        cpg = self.cpg
        literal_id = None
        for v in cpg.vertices:
            if v.get("label") != "LITERAL":
                continue
            vid = cpg_id(v)
            if _strip_quotes(cpg.code(vid)) == action:
                literal_id = vid
                break
        if literal_id is None:
            return []
        dispatcher = cpg.method_of(literal_id)
        if dispatcher is None:
            return []
        handler_call = self._handler_call_near(dispatcher, literal_id)
        if handler_call is None:
            return []
        callee = cpg.call_target(handler_call)
        if callee is None:
            return []
        mapping = dispatch_to_handler(
            cpg,
            "DISPATCH_STRING_MATCH",
            dispatch_value=action,
            dispatch_node=literal_id,
            handler_call=handler_call,
            method=dispatcher,
        )
        return [
            ResolutionEvidence(
                kind=STRING_DISPATCH,
                action_id=ActionIdentifier(
                    protocol_string=action,
                    normalized_name=action,
                    raw_expression=_strip_quotes(cpg.code(literal_id)),
                    node=literal_id,
                ),
                weight=0.9,
                match_strength=MatchStrength.EXACT_IDENTIFIER,
                callback=callee,
                nodes=[literal_id, handler_call],
                provenance_group=f"site:string:{dispatcher}",
                extractor="string_dispatch",
                mapping_evidence=mapping,
                score=0.9,
            )
        ]

    def _handler_by_enum_case(self, action: str) -> List[ResolutionEvidence]:
        """Extractor — enum/switch: a `case <SYMBOL>:` whose symbol matches the
        action, then the internal call reachable from that case via CFG."""
        cpg = self.cpg
        tokens = self._action_symbol_tokens(action)
        prof = self.kb.actions.get(action)
        for v in cpg.vertices:
            if v.get("label") != "JUMP_TARGET":
                continue
            jt = cpg_id(v)
            code = str(cpg.code(jt) or "").upper()
            if not any(t in code for t in tokens):
                continue
            call = self._first_internal_call_via_cfg(jt)
            if call is None:
                continue
            callee = cpg.call_target(call)
            if callee is None:
                continue
            method = cpg.method_of(jt)
            matched_symbol = next((s for s in (prof.action_symbols if prof else []) if s.upper() in code), None)
            if matched_symbol is not None:
                strength = MatchStrength.EXACT_IDENTIFIER
                group = f"site:switch:{method}"
            elif self._upper_snake(action) in code:
                strength = MatchStrength.NORMALIZED_NAME
                group = f"token:{action}"
            else:
                strength = MatchStrength.HEURISTIC_SUBSTRING
                group = f"token:{action}"
            mapping = dispatch_to_handler(
                cpg,
                "DISPATCH_ENUM_CASE",
                dispatch_value=cpg.code(jt),
                dispatch_node=jt,
                handler_call=call,
                method=method,
            )
            return [
                ResolutionEvidence(
                    kind=ENUM_CASE,
                    action_id=ActionIdentifier(
                        symbol=matched_symbol,
                        normalized_name=action,
                        raw_expression=cpg.code(jt),
                        node=jt,
                    ),
                    weight=0.85,
                    match_strength=strength,
                    callback=callee,
                    dispatch_site=jt,
                    nodes=[jt, call],
                    provenance_group=group,
                    extractor="enum_case",
                    mapping_evidence=mapping,
                    score=0.85,
                )
            ]
        return []

    def _handler_by_name(self, action: str) -> List[ResolutionEvidence]:
        """Extractor (fallback) — an internal function whose name matches the KB
        handler patterns, or contains the normalized action token."""
        cpg = self.cpg
        prof = self.kb.actions.get(action)
        patterns = {p.lower() for p in (prof.handler_patterns if prof else [])}
        snake = self._upper_snake(action).lower()  # data_transfer
        fallback: Optional[int] = None
        for m in cpg.internal_methods():
            nm = cpg.name(m).lower()
            if nm in patterns:
                return [
                    ResolutionEvidence(
                        kind=NAME_MATCH,
                        action_id=ActionIdentifier(normalized_name=action, raw_expression=cpg.name(m), node=m),
                        weight=0.7,
                        match_strength=MatchStrength.NORMALIZED_NAME,
                        callback=m,
                        nodes=[m],
                        provenance_group=f"token:{action}",
                        extractor="name_pattern",
                        mapping_evidence=[method_ref(cpg, "HANDLER_NAME_PATTERN", m)],
                        score=0.7,
                    )
                ]
            if fallback is None and snake and snake in nm:
                fallback = m
        if fallback is not None:
            return [
                ResolutionEvidence(
                    kind=NAME_MATCH,
                    action_id=ActionIdentifier(
                        normalized_name=action, raw_expression=cpg.name(fallback), node=fallback
                    ),
                    weight=0.65,
                    match_strength=MatchStrength.HEURISTIC_SUBSTRING,
                    callback=fallback,
                    nodes=[fallback],
                    provenance_group=f"token:{action}",
                    extractor="name_token",
                    mapping_evidence=[method_ref(cpg, "HANDLER_NAME_MATCH", fallback)],
                    score=0.65,
                )
            ]
        return []

    def _first_internal_call_via_cfg(self, start: int) -> Optional[int]:
        """First internal CALL reachable from `start` over CFG edges, without
        crossing into another case label (JUMP_TARGET)."""
        cpg = self.cpg
        seen: Set[int] = set()
        queue: "deque[int]" = deque([start])
        while queue:
            cur = queue.popleft()
            if cur in seen:
                continue
            seen.add(cur)
            if cur != start and cpg.label(cur) == "JUMP_TARGET":
                continue  # next case — stop this branch
            if cpg.label(cur) == "CALL" and self.cpg.is_internal_call(cur):
                return cur
            for nxt in cpg.out_ids(cur, "CFG"):
                if nxt not in seen:
                    queue.append(nxt)
        return None

    def _handler_by_registration(self, action: str) -> List[ResolutionEvidence]:
        """Extractor — handler *registrations*, e.g.

            static HandlerEntry g_table[] = {
                { MSG_SET_PROFILE, process_configuration },   // aggregate init
            };
            g_handlers[ACTION_REMOTE_START] = process_request; // indexed assign

        Emits **all** matching registrations, not just the first: two
        registrations for the same callback become two evidences on one
        candidate; registrations for different callbacks become competing
        candidates. Candidate selection is the selection layer's job, not the
        extractor's.
        """
        cpg = self.cpg
        tokens = {t for t in self._action_symbol_tokens(action) if t}
        prof = self.kb.actions.get(action)
        numeric = {str(n) for n in (prof.numeric_ids if prof else [])}
        symbols = set(prof.action_symbols) if prof else set()

        out: List[ResolutionEvidence] = []
        for reg in self._handler_registrations():
            symbol_hit = any(any(t in s for s in reg.action_id_symbols) for t in tokens)
            numeric_hit = numeric & reg.action_id_literals
            if not (symbol_hit or numeric_hit):
                continue

            matched_symbol = next((s for s in symbols if s.upper() in reg.action_id_symbols), None)
            matched_numeric = int(next(iter(numeric_hit))) if numeric_hit else None
            if matched_numeric is not None or matched_symbol is not None:
                strength = MatchStrength.EXACT_IDENTIFIER
                group = f"site:reg:{reg.site_key}"
            else:
                strength = MatchStrength.HEURISTIC_SUBSTRING
                group = f"token:{action}"
            kind = REGISTRATION_INIT if reg.mechanism == "AGGREGATE_INIT" else REGISTRATION_ASSIGN

            fn_file = cpg.method_filename(cpg.method_of(reg.evidence_node))
            mapping = [
                at(
                    cpg,
                    "DISPATCH_HANDLER_TABLE",
                    value=cpg.code(reg.evidence_node),
                    node=reg.ref_node,
                    method=reg.callback_method,
                ),
            ]
            # Correlated field stores: show the paired `.action = id` write(s) and
            # the shared slot, so the pairing is auditable in the trail.
            for id_site in reg.id_sites:
                mapping.append(
                    MappingEvidence(type="ACTION_STORE", value=cpg.code(id_site), file=fn_file, line=cpg.line(id_site))
                )
            if reg.slot:
                mapping.append(MappingEvidence(type="SLOT", value=reg.slot, file=fn_file, line=""))
            mapping.append(method_ref(cpg, "HANDLER_REF", reg.callback_method))
            out.append(
                ResolutionEvidence(
                    kind=kind,
                    action_id=ActionIdentifier(
                        symbol=matched_symbol,
                        numeric_id=matched_numeric,
                        raw_expression=cpg.code(reg.evidence_node),
                        node=reg.ref_node,
                    ),
                    weight=0.8,
                    match_strength=strength,
                    callback=reg.callback_method,
                    nodes=[reg.evidence_node, reg.ref_node],
                    provenance_group=group,
                    extractor="registration_ast",
                    mapping_evidence=mapping,
                    score=0.8,
                )
            )
        return out

    def _handler_by_registrar_call(self, action: str) -> List[ResolutionEvidence]:
        """Extractor — a registration performed through a registrar function:

            register_handler(ACTION, fn);   // fn stored into a table by the callee

        A call site *qualifies as a registrar* by observable behavior, not by
        name: it has a resolved internal call target, one arg is a METHOD_REF to
        an internal function (the callback), another arg is an action id matching
        the KB, and — following resolved call targets with arg->param substitution
        (bounded by ``registrar_depth``, default 2) — the callback parameter is
        stored into a table slot paired with the id parameter (Producer 1's
        slot-pairing, reused). If the terminal store is not reached, NO evidence
        is emitted (the miss is reported via _diagnose_unresolved).
        """
        cpg = self.cpg
        tokens = {t for t in self._action_symbol_tokens(action) if t}
        prof = self.kb.actions.get(action)
        numeric = {str(n) for n in (prof.numeric_ids if prof else [])}
        symbols = {s.upper() for s in (prof.action_symbols if prof else [])}
        by_name: Dict[str, int] = {}
        for m in cpg.internal_methods():
            by_name.setdefault(cpg.name(m), m)

        out: List[ResolutionEvidence] = []
        self._registrar_store_miss = False  # reset per action; read by _diagnose_unresolved
        self._registrar_miss_reason: Optional[UnresolvedReason] = None  # specific miss cause
        internal_methods = set(by_name.values())
        for v in cpg.vertices:
            if v.get("label") != "CALL":
                continue
            call = cpg_id(v)
            if cpg.name(call).startswith("<operator>"):
                continue
            target = cpg.call_target(call)
            if target is None or target not in internal_methods:
                continue
            args = cpg.call_args(call)

            cb_arg = next(
                (
                    (idx, a)
                    for idx, a in args
                    if cpg.label(a) == "METHOD_REF" and by_name.get(_strip_quotes(cpg.code(a)))
                ),
                None,
            )
            if cb_arg is None:
                continue
            callback = by_name[_strip_quotes(cpg.code(cb_arg[1]))]

            id_arg = None
            id_exact = False
            for idx, a in args:
                code_u = str(cpg.code(a) or "").upper()
                if cpg.label(a) == "LITERAL" and _strip_quotes(cpg.code(a)) in numeric:
                    id_arg, id_exact = (idx, a), True
                    break
                if any(t in code_u for t in tokens):
                    id_arg = (idx, a)
                    id_exact = code_u in symbols or code_u in {n for n in numeric}
            if id_arg is None:
                continue

            params = cpg.params_of_method(target)
            cb_param = params.get(cb_arg[0])
            id_param = params.get(id_arg[0])
            if cb_param is None or id_param is None:
                continue

            depth = self.calculus.registrar_depth
            trace = self._registrar_trace(target, cpg.name(id_param), cpg.name(cb_param), depth)
            if trace is None:
                self._registrar_store_miss = True  # for _diagnose_unresolved
                # Refine the miss: a runtime search-then-write registrar is a
                # distinct, more actionable cause than a generic store miss.
                # Prefer the specific reason if any qualifying call exhibits it.
                if self._registrar_miss_reason is None and self._registrar_uses_search(
                    target, cpg.name(id_param), cpg.name(cb_param)
                ):
                    self._registrar_miss_reason = UnresolvedReason.REGISTRAR_SEARCH_THEN_WRITE
                continue

            strength = MatchStrength.EXACT_IDENTIFIER if id_exact else MatchStrength.HEURISTIC_SUBSTRING
            mapping = [
                code_at(cpg, "DISPATCH_REGISTRAR_CALL", call),
                *trace,
                method_ref(cpg, "HANDLER_REF", callback),
            ]
            out.append(
                ResolutionEvidence(
                    kind=REGISTRAR_CALL,
                    action_id=ActionIdentifier(
                        symbol=(_strip_quotes(cpg.code(id_arg[1])) if not id_exact or not id_arg[1] else None),
                        numeric_id=(
                            int(_strip_quotes(cpg.code(id_arg[1])))
                            if cpg.label(id_arg[1]) == "LITERAL"
                            and _strip_quotes(cpg.code(id_arg[1])).lstrip("-").isdigit()
                            else None
                        ),
                        raw_expression=cpg.code(id_arg[1]),
                        node=call,
                    ),
                    weight=0.7,
                    match_strength=strength,
                    callback=callback,
                    dispatch_site=call,
                    nodes=[call, cb_arg[1]],
                    provenance_group=f"site:registrar:{call}",
                    extractor="registrar_call",
                    mapping_evidence=mapping,
                    score=0.7,
                )
            )
        return out

    def _registrar_trace(self, method: int, id_name: str, cb_name: str, depth: int) -> Optional[List[MappingEvidence]]:
        """If `method` stores its `cb_name` parameter into a table slot paired
        with its `id_name` parameter — directly, or by delegating to a resolved
        callee (arg->param substitution) within `depth` hops — return the ordered
        chain (delegate calls + the terminal paired field stores) as evidence
        records; else None. Reuses Producer 1's receiver-identity slot pairing."""
        cpg = self.cpg

        def rhs_names(assign: int) -> Set[str]:
            a = cpg.call_args(assign)
            if len(a) < 2:
                return set()
            rhs = a[1][1]
            names: Set[str] = set()
            for d in [rhs, *cpg.ast_descendants(rhs)]:
                if cpg.label(d) in ("IDENTIFIER", "METHOD_REF"):
                    names.add(cpg.name(d) or _strip_quotes(cpg.code(d)))
            return names

        assigns = [c for c in cpg.calls_in_method(method) if cpg.name(c) == "<operator>.assignment"]
        # direct: cb-param stored into a slot whose sibling stores the id-param
        for ca in assigns:
            if cb_name not in rhs_names(ca):
                continue
            slot = self._store_receiver(cpg.call_args(ca)[0][1])
            for other in assigns:
                if other is ca:
                    continue
                if self._store_receiver(cpg.call_args(other)[0][1]) == slot and id_name in rhs_names(other):
                    return [
                        code_at(cpg, "CHAIN_STORE", other, method=method),
                        code_at(cpg, "CHAIN_STORE", ca, method=method),
                    ]
        if depth <= 0:
            return None
        # delegate: a resolved callee receiving both params by position
        for c in cpg.calls_in_method(method):
            if cpg.name(c).startswith("<operator>"):
                continue
            t = cpg.call_target(c)
            if t is None:
                continue
            cb_idx = id_idx = None
            for idx, a in cpg.call_args(c):
                anames = {cpg.name(a)} | {cpg.name(d) for d in cpg.ast_descendants(a)}
                if cb_name in anames:
                    cb_idx = idx
                if id_name in anames:
                    id_idx = idx
            if cb_idx is None or id_idx is None:
                continue
            params = cpg.params_of_method(t)
            cb2, id2 = params.get(cb_idx), params.get(id_idx)
            if cb2 is None or id2 is None:
                continue
            sub = self._registrar_trace(t, cpg.name(id2), cpg.name(cb2), depth - 1)
            if sub is not None:
                return [code_at(cpg, "CHAIN_CALL", c, method=method), *sub]
        return None

    def _registrar_uses_search(self, method: int, id_name: str, cb_name: str) -> bool:
        """Classify a store-miss registrar as *search-then-write*: it locates the
        slot at runtime (a loop) by *comparing* the action id (a predicate) and
        then writes only the callback — e.g.::

            for (i ...) if (table[i].action == a) { table[i].handler = cb; }

        The defining trait is that the id parameter is *compared*, not co-stored
        with the callback. That plus a loop is what puts the action->slot
        correlation outside the paired-store baseline. Detected structurally so
        the diagnosis names the idiom instead of the generic 'store not reached'.
        """
        cpg = self.cpg
        id_compared = any(
            cpg.name(c) in CMP_OPS and id_name in {cpg.name(d) for d in cpg.ast_descendants(c)}
            for c in cpg.calls_in_method(method)
        )
        if not id_compared:
            return False
        # Corroborate with a loop and a variable-indexed callback store, so a
        # plain `if (a == X) t.handler = cb;` (no runtime slot search) is not
        # mislabeled.
        has_loop = any(
            str(cpg.scalar(cs, "CONTROL_STRUCTURE_TYPE") or "").upper() in ("FOR", "WHILE", "DO")
            for cs in cpg.control_structures_in(method)
        )
        var_index_store = any(
            cpg.name(ca) == "<operator>.assignment"
            and cb_name in {cpg.name(d) for d in cpg.ast_descendants(ca)}
            and self._store_slot_has_variable_index(cpg.call_args(ca)[0][1])
            for ca in cpg.calls_in_method(method)
        )
        return has_loop or var_index_store

    def _store_slot_has_variable_index(self, lhs: int) -> bool:
        """True if the store LHS selects its slot with a non-constant index
        (``t[i].fn`` / ``t[i]``), i.e. the slot is chosen at runtime."""
        cpg = self.cpg
        target = lhs
        if cpg.label(lhs) == "CALL" and cpg.name(lhs) in (
            "<operator>.fieldAccess",
            "<operator>.indirectFieldAccess",
        ):
            kids = cpg.out_ids(lhs, "AST")
            if kids:
                target = kids[0]
        if cpg.label(target) == "CALL" and cpg.name(target) in (
            "<operator>.indirectIndexAccess",
            "<operator>.indexAccess",
        ):
            idx = cpg.out_ids(target, "AST")
            return len(idx) > 1 and cpg.label(idx[1]) != "LITERAL"
        return False

    def _handler_registrations(self) -> List["HandlerRegistration"]:
        if self._registration_cache is None:
            self._registration_cache = self._extract_registrations_ast()
        return self._registration_cache

    def _store_receiver(self, lhs: int) -> str:
        """Slot identity of an assignment LHS: the receiver sub-expression of a
        field access (`t[i].fn` -> `t[i]`), else the LHS code itself
        (`handlers[id]`). Probe 1 confirmed this is a stable correlation key."""
        cpg = self.cpg
        if cpg.label(lhs) == "CALL" and cpg.name(lhs) in (
            "<operator>.fieldAccess",
            "<operator>.indirectFieldAccess",
        ):
            kids = cpg.out_ids(lhs, "AST")
            if kids:
                return cpg.code(kids[0])
        return cpg.code(lhs)

    def _enclosing_struct_init(self, assign: int) -> Optional[int]:
        """If ``assign`` is a *designated field initializer* (``.field = value``,
        whose LHS is a bare field-name IDENTIFIER) inside a struct aggregate,
        return the enclosing ``<operator>.arrayInitializer``; else None.

        c2cpg lowers ``{ .action = X, .fn = f }`` to an arrayInitializer whose
        members are the designated ``.field = value`` assignments, each wrapped in
        a synthetic BLOCK — so we climb past at most a couple of BLOCK levels. A
        real field store (``t[i].fn = f``) or indexed assign (``h[id] = f``) has a
        fieldAccess/indexAccess LHS, not a bare IDENTIFIER, so it returns None and
        keeps flowing through the existing FIELD_ASSIGN path unchanged."""
        cpg = self.cpg
        args = cpg.call_args(assign)
        if not args or cpg.label(args[0][1]) != "IDENTIFIER":
            return None
        cur = self.cpg.ast_parent(assign)
        hops = 0
        while cur is not None and hops < 3:
            if cpg.label(cur) == "CALL" and cpg.name(cur) == "<operator>.arrayInitializer":
                return cur
            if cpg.label(cur) != "BLOCK":
                return None
            cur = self.cpg.ast_parent(cur)
            hops += 1
        return None

    def _designated_fields(self, struct_init: int) -> List[int]:
        """The ``.field = value`` assignment nodes that are direct members of one
        struct aggregate initializer (each wrapped in a synthetic BLOCK). Used to
        find the sibling that carries the action id, correlated purely by shared
        enclosing initializer — order-independent, no cross-initializer leakage."""
        cpg = self.cpg
        out: List[int] = []
        for child in cpg.out_ids(struct_init, "AST"):
            candidates = cpg.out_ids(child, "AST") if cpg.label(child) == "BLOCK" else [child]
            for n in candidates:
                if cpg.label(n) == "CALL" and cpg.name(n) == "<operator>.assignment":
                    a = cpg.call_args(n)
                    if a and cpg.label(a[0][1]) == "IDENTIFIER":
                        out.append(n)
        return out

    def _collect_ids(self, node: int, symbols: Set[str], literals: Set[str]) -> None:
        cpg = self.cpg
        for d in [node, *cpg.ast_descendants(node)]:
            code_u = str(cpg.code(d) or "").upper()
            name_u = str(cpg.name(d) or "").upper()
            if code_u:
                symbols.add(code_u)
            if name_u:
                symbols.add(name_u)
            if cpg.label(d) == "LITERAL":
                literals.add(_strip_quotes(cpg.code(d)))

    def _extract_registrations_ast(self) -> List["HandlerRegistration"]:
        """AST + symbol-resolution extractor for handler registrations:

        * ``{ id, fn }`` aggregate initializers (Producer 0);
        * ``handlers[id] = fn`` indexed assignments (id in the LHS);
        * ``t[i].action = id; t[i].fn = fn`` correlated field stores (Producer 1)
          — the id is recovered from a *sibling* assignment writing the same slot,
          keyed by receiver identity (probe 1).

        Purely AST + symbol resolution; DFG is an escalation (variable-index
        soundness / alias→slot) handled elsewhere, not part of this baseline.
        """
        cpg = self.cpg
        by_name: Dict[str, int] = {}
        for m in cpg.internal_methods():
            by_name.setdefault(cpg.name(m), m)

        regs: List[HandlerRegistration] = []
        for v in cpg.vertices:
            if v.get("label") != "METHOD_REF":
                continue
            ref = cpg_id(v)
            entry = self.cpg.ast_parent(ref)
            if entry is None or cpg.label(entry) != "CALL":
                continue
            op = cpg.name(entry)
            if op not in ("<operator>.arrayInitializer", "<operator>.assignment"):
                continue
            callback = by_name.get(_strip_quotes(cpg.code(ref)))
            if callback is None:
                continue

            symbols: Set[str] = set()
            literals: Set[str] = set()
            slot = ""
            id_sites: List[int] = []
            evidence_node = entry

            # A designated field initializer (`.fn = f`) reaches the METHOD_REF via
            # an <operator>.assignment; recognize when it belongs to a struct
            # aggregate so it is handled as an aggregate init, not a field store.
            struct_init = self._enclosing_struct_init(entry) if op == "<operator>.assignment" else None

            if op == "<operator>.arrayInitializer":
                # Positional aggregate `{ ID, fn }`: the id is a sibling element.
                mechanism = "AGGREGATE_INIT"
                for child in cpg.out_ids(entry, "AST"):
                    if child == ref:
                        continue
                    self._collect_ids(child, symbols, literals)
                # All entries of one table literal share the outer initializer.
                table = self.cpg.ast_parent(entry)
                site_key = str(table if table is not None else entry)
            elif struct_init is not None:
                # Designated aggregate `{ .action = ID, .fn = fn }`: the id lives in
                # a *sibling designated field* of the same struct initializer. Same
                # semantic evidence as positional (REGISTRATION_INIT); correlation
                # is by shared enclosing init only (order-independent, no field-name
                # guessing, no cross-initializer leakage). The struct init is the
                # evidence node so the trail shows the whole `{ ... }` entry.
                mechanism = "AGGREGATE_INIT"
                evidence_node = struct_init
                site_key = f"designated:{struct_init}"
                for fld in self._designated_fields(struct_init):
                    if fld == entry:  # skip the callback field itself
                        continue
                    fargs = cpg.call_args(fld)
                    if len(fargs) < 2:
                        continue
                    before = (len(symbols), len(literals))
                    self._collect_ids(fargs[1][1], symbols, literals)
                    if (len(symbols), len(literals)) != before:
                        id_sites.append(fld)  # the `.action = id` field, for the trail
            else:  # <operator>.assignment field store
                mechanism = "FIELD_ASSIGN"
                # ids spelled in the entry node itself (indexed LHS `handlers[id]=fn`).
                for child in cpg.out_ids(entry, "AST"):
                    if child == ref:
                        continue
                    self._collect_ids(child, symbols, literals)
                args = cpg.call_args(entry)
                lhs = args[0][1] if args else entry
                slot = self._store_receiver(lhs)
                method = cpg.method_of(entry)
                site_key = f"assign:{method}:{slot}"
                # Producer 1: pull the id from a sibling store to the SAME slot,
                # and remember that store so the trail can show the pairing.
                for other in cpg.calls_in_method(method) if method is not None else []:
                    if other == entry or cpg.name(other) != "<operator>.assignment":
                        continue
                    oargs = cpg.call_args(other)
                    if len(oargs) < 2:
                        continue
                    if self._store_receiver(oargs[0][1]) != slot:
                        continue
                    before = (len(symbols), len(literals))
                    self._collect_ids(oargs[1][1], symbols, literals)
                    if (len(symbols), len(literals)) != before:
                        id_sites.append(other)  # this sibling contributed the id

            regs.append(
                HandlerRegistration(
                    action_id_symbols=symbols,
                    action_id_literals=literals,
                    callback_method=callback,
                    mechanism=mechanism,
                    evidence_node=evidence_node,
                    ref_node=ref,
                    site_key=site_key,
                    id_sites=id_sites,
                    slot=slot,
                )
            )
        return regs

    def _handler_call_near(self, dispatcher: int, literal_id: int) -> Optional[int]:
        cpg = self.cpg
        # Prefer the control structure whose subtree holds the literal.
        for cs in cpg.control_structures_in(dispatcher):
            subtree = set(cpg.ast_descendants(cs))
            if literal_id not in subtree:
                continue
            cond = cpg.condition_of(cs)
            cond_subtree = set(cpg.ast_descendants(cond)) if cond is not None else set()
            for node in subtree:
                if node in cond_subtree or cpg.label(node) != "CALL":
                    continue
                if self.cpg.is_internal_call(node):
                    return node
        # Fallback: any internal call in the dispatcher.
        for node in cpg.calls_in_method(dispatcher):
            if self.cpg.is_internal_call(node):
                return node
        return None
