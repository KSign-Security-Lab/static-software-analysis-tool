"""The F2-A pipeline: seven steps that collect source-code evidence from a CPG.

Each step "collects" one kind of evidence, exactly as the implementation deck
frames it (``docs/v2/f2a_deck_v7_implementation.html``):

1. handler discovery      — AST string literal + CG call → which function handles the action
2. source binding         — AST field access + DFG def → the variable to track
3. source→sink flow       — DFG (REACHING_DEF) + CG arg→param bridge → the value's path
4. sink mapping           — AST call symbol matched to the KB danger list → sink + domain
5. check detection        — AST/DFG relevance + CFG dominance → observed defensive checks
6. expected matching      — KB expected vs observed → missing / weak / negative checks
7. evidence package       — assemble everything, score connection quality, hand off to F6

F2-A never confirms a vulnerability; it produces a reviewable *candidate*.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple, cast

from .graph import ASSIGNMENT_OPS, FIELD_ACCESS_OPS, CPGModel
from .kb import CheckPattern, FieldProfile, KnowledgeBase, default_knowledge_base
from .models import (
    BindingEvidence,
    CandidateFragment,
    CheckEvidence,
    CheckStrength,
    CodeEvidence,
    CodeLocation,
    ConfidenceBreakdown,
    EvidencePackage,
    ExpectedCheckMatching,
    F2AResult,
    FieldBinding,
    FieldBindingDetail,
    FlowCandidate,
    FlowStep,
    HandlerMap,
    HandlerRef,
    MappingEvidence,
    MatchingResult,
    MatchingStatus,
    MissingCheckCandidateSet,
    MissingCheckItem,
    MissingCheckSummary,
    NegativeCheckEvidence,
    ObservedCheck,
    OcppContext,
    PrimaryLocation,
    SecurityInterpretation,
    SinkInfo,
    SinkMapping,
    SourceRef,
    Traceability,
    WeakCheckItem,
)

# §14.2 static-confidence weights (connection quality, NOT severity).
CONFIDENCE_WEIGHTS = {
    "handler_mapping": 0.15,
    "field_binding": 0.20,
    "semantic_binding": 0.15,
    "source_sink_flow": 0.25,
    "sink_mapping": 0.10,
    "check_detection": 0.10,
    "traceability": 0.05,
}

STANDARD_LIMITATIONS = [
    "Static analysis cannot confirm runtime exploitability.",
    "Missing checks are candidates, not confirmed absence of runtime controls.",
    "Checks enforced outside this CPG (gateway, policy server, config) are not visible here.",
]


def _strip_quotes(text: str) -> str:
    text = (text or "").strip()
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
        return text[1:-1]
    return text


class _Ids:
    """Deterministic per-run id generator (no wall clock / randomness)."""

    def __init__(self) -> None:
        self._counters: Dict[str, int] = {}

    def next(self, prefix: str) -> str:
        n = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = n
        return f"{prefix}-{n:04d}"


class FlowTrace:
    """Result of the interprocedural forward taint walk (step 3)."""

    def __init__(self) -> None:
        self.reached: bool = False
        self.sink_call: Optional[int] = None
        self.sink_arg: Optional[int] = None
        self.steps: List[FlowStep] = []
        self.visited: Set[int] = set()
        self.tracked_names: Set[str] = set()
        self.tracked_decls: Set[int] = set()
        self.methods_on_path: List[int] = []
        self.bridge_call_in_method: Dict[int, int] = {}  # method -> outgoing call node
        # All reached sinks: (sink_call_id, tainted_arg_id). Parent pointers let us
        # reconstruct the flow to each one.
        self.sinks: List[Tuple[int, int]] = []
        self.parent: Dict[int, Tuple[Optional[int], str]] = {}


class F2AAnalyzer:
    """Runs the seven F2-A steps over one CPG."""

    def __init__(self, cpg: CPGModel, kb: Optional[KnowledgeBase] = None):
        self.cpg = cpg
        self.kb = kb or default_knowledge_base()
        self.ids = _Ids()
        self._sink_apis = set(self.kb.sink_apis())

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def analyze(self, source_cpg: str = "") -> F2AResult:
        result = F2AResult(source_cpg=source_cpg)

        for action in self.kb.all_actions():
            handler_map = self._step1_discover_handler(action)
            if handler_map is None:
                result.limitations.append(
                    f"No handler found for action '{action}' in this CPG "
                    f"(dispatch may be dynamic / in another translation unit)."
                )
                continue
            result.handler_maps.append(handler_map)
            handler_method = self._handler_method_id.get(action)

            for field_prof in self.kb.fields_for_action(action):
                binding = self._step2_bind_source(action, field_prof, handler_method)
                if binding is None:
                    result.limitations.append(
                        f"Field '{field_prof.field_name}' of '{action}' not bound to a "
                        f"variable in this CPG."
                    )
                    continue
                result.field_bindings.append(binding)

                trace = self._step3_flow(binding)
                if not trace.reached:
                    result.limitations.append(
                        f"Source '{binding.binding.bound_variable}' did not reach a known "
                        f"sink within this CPG (flow may leave this translation unit)."
                    )
                    continue

                # One evidence package per relevant sink the source reaches.
                for sink_call, sink_arg in self._select_sinks(trace, field_prof):
                    trace.sink_call = sink_call
                    trace.sink_arg = sink_arg
                    trace.steps = self._reconstruct_flow(trace.parent, sink_arg, sink_call)

                    sink_mapping = self._step4_map_sink(trace)
                    result.sink_mappings.append(sink_mapping)

                    observed, negatives = self._step5_detect_checks(
                        action, field_prof, trace
                    )

                    matching, missing_set = self._step6_match_expected(
                        action, field_prof, trace, observed, negatives
                    )
                    result.expected_check_matchings.append(matching)
                    result.missing_check_candidate_sets.append(missing_set)

                    package, fragment, flow_candidate = self._step7_assemble(
                        action,
                        field_prof,
                        handler_map,
                        binding,
                        trace,
                        sink_mapping,
                        observed,
                        matching,
                        missing_set,
                    )
                    result.evidence_packages.append(package)
                    result.candidate_fragments.append(fragment)
                    result.flow_candidates.append(flow_candidate)

        return result

    def _select_sinks(
        self, trace: "FlowTrace", field_prof: FieldProfile
    ) -> List[Tuple[int, int]]:
        """Choose which reached sinks to report.

        Prefer sinks whose domain is one the KB flags as dangerous for this field
        (e.g. ``location`` → COMMAND_EXECUTION); fall back to every reached sink.
        Deduplicate by sink call so a sink reached via several args is reported once.
        """
        wanted = set(field_prof.dangerous_sink_domain or [])
        seen_calls: Set[int] = set()
        preferred: List[Tuple[int, int]] = []
        fallback: List[Tuple[int, int]] = []
        for call, arg in trace.sinks:
            if call in seen_calls:
                continue
            seen_calls.add(call)
            prof = self.kb.sink_for_api(self.cpg.name(call))
            domain = prof.sink_domain if prof else "UNKNOWN_SINK"
            (preferred if domain in wanted else fallback).append((call, arg))
        return preferred or fallback

    # ------------------------------------------------------------------
    # Step 1 · Handler discovery  (AST literal + CG call)
    # ------------------------------------------------------------------

    def _step1_discover_handler(self, action: str) -> Optional[HandlerMap]:
        cpg = self.cpg
        if not hasattr(self, "_handler_method_id"):
            self._handler_method_id: Dict[str, int] = {}

        # AST: find the action string literal.
        literal_id = None
        for v in cpg.vertices:
            if v.get("label") != "LITERAL":
                continue
            vid = cpg_id(v)
            if _strip_quotes(cpg.code(vid)) == action:
                literal_id = vid
                break
        if literal_id is None:
            return None

        dispatcher = cpg.method_of(literal_id)
        if dispatcher is None:
            return None

        # CG: the internal function called in the same branch as the literal.
        handler_call = self._handler_call_near(dispatcher, literal_id)
        if handler_call is None:
            return None
        callee = cpg.call_target(handler_call)
        if callee is None:
            return None

        self._handler_method_id[action] = callee
        handler_ref = HandlerRef(
            file=cpg.method_filename(callee),
            function=cpg.name(callee),
            line=cpg.line(callee),
            language="c",
        )
        evidence = [
            MappingEvidence(
                type="DISPATCH_STRING_MATCH",
                value=action,
                file=cpg.method_filename(dispatcher),
                line=cpg.line(literal_id),
            ),
            MappingEvidence(
                type="HANDLER_CALL",
                value=cpg.code(handler_call),
                file=cpg.method_filename(dispatcher),
                line=cpg.line(handler_call),
            ),
        ]
        return HandlerMap(
            handler_map_id=self.ids.next("OCPP-HMAP"),
            action=action,
            handler=handler_ref,
            mapping_evidence=evidence,
            confidence=0.9,
        )

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
                if self._is_internal_call(node):
                    return node
        # Fallback: any internal call in the dispatcher.
        for node in cpg.calls_in_method(dispatcher):
            if self._is_internal_call(node):
                return node
        return None

    def _is_internal_call(self, call_id: int) -> bool:
        cpg = self.cpg
        callee = cpg.call_target(call_id)
        if callee is None:
            return False
        nm = cpg.name(callee)
        if nm.startswith("<operator>") or nm.startswith("<global>"):
            return False
        return cpg.scalar(callee, "IS_EXTERNAL") is not True

    # ------------------------------------------------------------------
    # Step 2 · Source binding  (AST field access + DFG def)
    # ------------------------------------------------------------------

    def _step2_bind_source(
        self, action: str, field_prof: FieldProfile, handler_method: Optional[int]
    ) -> Optional[FieldBinding]:
        cpg = self.cpg
        aliases = {a.lower() for a in (field_prof.field_source_aliases or [])}
        aliases.add(field_prof.field_name.lower())

        candidate = self._find_field_access(field_prof, handler_method)
        if candidate is None:
            return None
        access_call, source_expr, seed_nodes, loc_node = candidate

        # DFG: the variable the field value is assigned into (the def).
        bound_variable, target_ident, assign_node = self._assignment_target(access_call)
        if target_ident is not None:
            seed_nodes.append(target_ident)
        binding_node = assign_node if assign_node is not None else access_call
        method = cpg.method_of(binding_node)

        self._seed_nodes = seed_nodes  # consumed by step 3
        detail = FieldBindingDetail(
            source_type="OCPP_PAYLOAD_FIELD",
            source_expression=source_expr,
            bound_variable=bound_variable or cpg.code(access_call),
            file=cpg.method_filename(method) if method is not None else "",
            function=cpg.name(method) if method is not None else "",
            line=cpg.line(binding_node),
        )
        return FieldBinding(
            field_binding_id=self.ids.next("OCPP-FBIND"),
            action=action,
            field=field_prof.field_name,
            field_semantic=field_prof.semantic_type,
            binding=detail,
            binding_evidence=[
                BindingEvidence(
                    type="STRUCT_FIELD_ASSIGNMENT",
                    expression=cpg.code(binding_node),
                )
            ],
            confidence=0.85,
        )

    def _find_field_access(
        self, field_prof: FieldProfile, handler_method: Optional[int]
    ) -> Optional[Tuple[int, str, List[int], int]]:
        """Locate ``req->location`` / ``json_get(...,"location")`` style access.

        Returns ``(access_call, source_expression, seed_nodes, loc_node)``.
        """
        cpg = self.cpg
        aliases = {a.lower() for a in (field_prof.field_source_aliases or [])}
        aliases.add(field_prof.field_name.lower())

        def search_methods() -> List[int]:
            methods = cpg.internal_methods()
            if handler_method is not None and handler_method in methods:
                # Prefer the handler method first.
                return [handler_method] + [m for m in methods if m != handler_method]
            return methods

        for method in search_methods():
            for call in cpg.calls_in_method(method):
                nm = cpg.name(call)
                # (a) direct struct/pointer field access
                if nm in FIELD_ACCESS_OPS:
                    for _idx, arg in cpg.call_args(call):
                        if cpg.label(arg) == "FIELD_IDENTIFIER":
                            if cpg.field_name(arg).lower() in aliases:
                                return call, cpg.code(call), [call], call
                # (b) accessor call with the field name as a string literal arg
                else:
                    for _idx, arg in cpg.call_args(call):
                        if cpg.label(arg) == "LITERAL":
                            if _strip_quotes(cpg.code(arg)).lower() in aliases:
                                return call, cpg.code(call), [call], call
        return None

    def _assignment_target(
        self, access_call: int
    ) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        """If the field access is the RHS of an assignment, return its LHS."""
        cpg = self.cpg
        for call_id, _idx in cpg.argument_of(access_call):
            if cpg.name(call_id) in ASSIGNMENT_OPS:
                args = cpg.call_args(call_id)
                if args:
                    target = args[0][1]
                    return cpg.name(target) or cpg.code(target), target, call_id
        return None, None, None

    # ------------------------------------------------------------------
    # Step 3 · Source→sink flow  (DFG + CG bridge)
    # ------------------------------------------------------------------

    def _step3_flow(self, binding: FieldBinding) -> FlowTrace:
        cpg = self.cpg
        trace = FlowTrace()
        seeds = list(getattr(self, "_seed_nodes", []))
        if not seeds:
            return trace

        parent = trace.parent
        queue: "deque[int]" = deque()
        for s in seeds:
            if s not in trace.visited:
                trace.visited.add(s)
                parent[s] = (None, "source")
                queue.append(s)

        sinks: List[Tuple[int, int]] = []
        seen_sinks: Set[Tuple[int, int]] = set()

        while queue:
            cur = queue.popleft()
            self._record_tracked(cur, trace)

            # Sink detection + CG bridge via argument position.
            for call_id, idx in cpg.argument_of(cur):
                api = cpg.name(call_id).lower()
                if api in self._sink_apis:
                    if (call_id, cur) not in seen_sinks:
                        seen_sinks.add((call_id, cur))
                        sinks.append((call_id, cur))
                    continue  # do not descend into the sink itself
                callee = cpg.call_target(call_id)
                if callee is not None and self._is_internal_call(call_id):
                    method_of_cur = cpg.method_of(cur)
                    if method_of_cur is not None:
                        trace.bridge_call_in_method[method_of_cur] = call_id
                    param = cpg.params_of_method(callee).get(idx)
                    if param is not None and param not in trace.visited:
                        trace.visited.add(param)
                        parent[param] = (cur, f"parameter_bind→{cpg.name(callee)}")
                        queue.append(param)

            # DFG successors (intraprocedural REACHING_DEF).
            for nxt in cpg.reaching_out(cur):
                if nxt not in trace.visited:
                    trace.visited.add(nxt)
                    parent[nxt] = (cur, "propagate")
                    queue.append(nxt)

        trace.sinks = sinks
        trace.reached = bool(sinks)
        # Every internal method the tainted value passed through — the search
        # space for observed checks (step 5).
        touched = {
            m
            for n in trace.visited
            for m in [cpg.method_of(n)]
            if m is not None and cpg.name(m) and not cpg.name(m).startswith("<")
        }
        trace.methods_on_path = sorted(touched)
        return trace

    def _record_tracked(self, node: int, trace: FlowTrace) -> None:
        cpg = self.cpg
        lbl = cpg.label(node)
        if lbl in ("IDENTIFIER", "METHOD_PARAMETER_IN", "LOCAL"):
            nm = cpg.name(node)
            if nm and nm.upper() not in ("NULL", "NULLPTR"):
                trace.tracked_names.add(nm)
            decl = cpg.ref_decl(node) if lbl == "IDENTIFIER" else node
            if decl is not None:
                trace.tracked_decls.add(decl)

    def _reconstruct_flow(
        self,
        parent: Dict[int, Tuple[Optional[int], str]],
        sink_arg: int,
        sink_call: int,
    ) -> List[FlowStep]:
        cpg = self.cpg
        # Walk back from the sink argument to the source seed.
        chain: List[int] = []
        cur: Optional[int] = sink_arg
        seen = set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            cur = parent.get(cur, (None, ""))[0]
        chain.reverse()

        steps: List[FlowStep] = []
        last_key = None
        for node in chain:
            op_raw = parent.get(node, (None, ""))[1]
            method = cpg.method_of(node)
            fn = cpg.name(method) if method is not None else ""
            file = cpg.method_filename(method) if method is not None else ""
            ln = cpg.line(node)
            operation = self._operation_label(node, op_raw)
            if operation is None:
                continue
            key = (fn, str(ln), operation)
            if key == last_key:
                continue
            last_key = key
            steps.append(
                FlowStep(step=len(steps) + 1, function=fn, file=file, line=ln, operation=operation)
            )

        # Always end at the sink call itself.
        sink_method = cpg.method_of(sink_call)
        steps.append(
            FlowStep(
                step=len(steps) + 1,
                function=cpg.name(sink_method) if sink_method is not None else "",
                file=cpg.method_filename(sink_method) if sink_method is not None else "",
                line=cpg.line(sink_call),
                operation=f"sink:{cpg.name(sink_call)}",
            )
        )
        return steps

    def _operation_label(self, node: int, op_raw: str) -> Optional[str]:
        cpg = self.cpg
        lbl = cpg.label(node)
        if op_raw == "source":
            return "source_binding"
        if op_raw.startswith("parameter_bind"):
            return "argument_pass " + op_raw.replace("parameter_bind→", "→ ")
        if lbl == "CALL":
            nm = cpg.name(node)
            if nm.startswith("<operator>"):
                return None
            if nm.lower() in {"sprintf", "snprintf", "strcpy", "strcat", "strncpy"}:
                return f"string_build:{nm}"
            return None
        if lbl in ("IDENTIFIER", "METHOD_PARAMETER_IN"):
            return None  # collapsed into surrounding operations
        return None

    # ------------------------------------------------------------------
    # Step 4 · Sink mapping  (AST symbol → KB danger list)
    # ------------------------------------------------------------------

    def _step4_map_sink(self, trace: FlowTrace) -> SinkMapping:
        cpg = self.cpg
        api = cpg.name(trace.sink_call)
        prof = self.kb.sink_for_api(api)
        method = cpg.method_of(trace.sink_call)
        return SinkMapping(
            sink_mapping_id=self.ids.next("OCPP-SINK"),
            sink=CodeLocation(
                file=cpg.method_filename(method) if method is not None else "",
                function=cpg.name(method) if method is not None else "",
                line=cpg.line(trace.sink_call),
            ),
            api=api,
            sink_domain=prof.sink_domain if prof else "UNKNOWN_SINK",
            related_cwe=prof.related_cwe if prof else [],
            severity_hint=prof.severity if prof else "",
            mapping_evidence=[cpg.code(trace.sink_call)],
        )

    # ------------------------------------------------------------------
    # Step 5 · Check detection  (AST/DFG relevance + CFG dominance)
    # ------------------------------------------------------------------

    def _step5_detect_checks(
        self, action: str, field_prof: FieldProfile, trace: FlowTrace
    ) -> Tuple[List[ObservedCheck], List[NegativeCheckEvidence]]:
        cpg = self.cpg
        observed: List[ObservedCheck] = []
        seen_evidence: Set[Tuple[str, str]] = set()

        for method in trace.methods_on_path:
            departure = trace.bridge_call_in_method.get(method)
            if departure is None and cpg.method_of(trace.sink_call) == method:
                departure = trace.sink_call

            # (a) conditional checks reading a tracked variable
            for cs in cpg.control_structures_in(method):
                cond = cpg.condition_of(cs)
                if cond is None:
                    continue
                if not self._references_tracked(cond, trace):
                    continue
                pattern = self._classify_condition(cond)
                if pattern is None:
                    continue
                ordered = self._ordered_before(cond, cs, departure, method)
                strength: CheckStrength = cast(
                    CheckStrength, pattern.default_strength if ordered else "PARTIAL"
                )
                ev = cpg.code(cs) or cpg.code(cond)
                key = (pattern.check_type, cpg.name(method))
                if key in seen_evidence:
                    continue
                seen_evidence.add(key)
                observed.append(
                    ObservedCheck(
                        observed_check_id=self.ids.next("OCPP-OBS-CHK"),
                        detection_method="RULE_BASED",
                        check_type=pattern.check_type,
                        action=action,
                        field=field_prof.field_name,
                        applies_to=sorted(trace.tracked_names)[:4],
                        file=cpg.method_filename(method),
                        function=cpg.name(method),
                        line=cpg.line(cs),
                        evidence=ev,
                        check_strength=strength,
                        matched_expected_check=pattern.matched_expected_check,
                        confidence=0.95 if pattern.check_type == "NULL_CHECK" else 0.85,
                    )
                )

            # (b) explicit check-function calls on a tracked variable
            for call in cpg.calls_in_method(method):
                nm = cpg.name(call)
                if nm.startswith("<operator>"):
                    continue
                pattern = self._classify_call(nm)
                if pattern is None:
                    continue
                if not self._call_references_tracked(call, trace):
                    continue
                ev = cpg.code(call)
                key = (pattern.check_type, cpg.name(method))
                if key in seen_evidence:
                    continue
                seen_evidence.add(key)
                observed.append(
                    ObservedCheck(
                        observed_check_id=self.ids.next("OCPP-OBS-CHK"),
                        detection_method="RULE_BASED",
                        check_type=pattern.check_type,
                        action=action,
                        field=field_prof.field_name,
                        applies_to=sorted(trace.tracked_names)[:4],
                        file=cpg.method_filename(method),
                        function=cpg.name(method),
                        line=cpg.line(call),
                        evidence=ev,
                        check_strength=cast(CheckStrength, pattern.default_strength),
                        matched_expected_check=pattern.matched_expected_check,
                        confidence=0.85,
                    )
                )

        negatives = self._detect_negative_evidence(field_prof, trace)
        return observed, negatives

    def _references_tracked(self, node: int, trace: FlowTrace) -> bool:
        cpg = self.cpg
        for d in [node, *cpg.ast_descendants(node)]:
            if cpg.label(d) == "IDENTIFIER":
                if cpg.name(d) in trace.tracked_names:
                    return True
                decl = cpg.ref_decl(d)
                if decl is not None and decl in trace.tracked_decls:
                    return True
        return False

    def _call_references_tracked(self, call: int, trace: FlowTrace) -> bool:
        cpg = self.cpg
        for _idx, arg in cpg.call_args(call):
            if self._references_tracked(arg, trace) or (
                cpg.label(arg) == "IDENTIFIER" and cpg.name(arg) in trace.tracked_names
            ):
                return True
        return False

    def _classify_condition(self, cond: int) -> Optional[CheckPattern]:
        """Classify a condition by its *shape*, using AST node kinds + symbols.

        No regex over source text: we look at the operator NAME symbols, the
        helper-call NAME symbols, and the operand nodes' kinds/values (an
        IDENTIFIER named ``NULL``, a string LITERAL starting ``http``).
        """
        cpg = self.cpg
        subtree = [cond, *cpg.ast_descendants(cond)]
        operators = {
            cpg.name(d)
            for d in subtree
            if cpg.label(d) == "CALL" and cpg.name(d).startswith("<operator>")
        }
        helper_calls = {
            cpg.name(d).lower()
            for d in subtree
            if cpg.label(d) == "CALL" and not cpg.name(d).startswith("<operator>")
        }
        operand_idents = {
            cpg.name(d).lower() for d in subtree if cpg.label(d) == "IDENTIFIER"
        }
        operand_literals = [
            _strip_quotes(cpg.code(d)).lower()
            for d in subtree
            if cpg.label(d) == "LITERAL"
        ]

        # A named helper call is the strongest, unambiguous signal.
        for pat in self.kb.check_patterns:
            if pat.call_names and helper_calls & {c.lower() for c in pat.call_names}:
                return pat

        # Otherwise classify by operator symbol + operand constraint.
        for pat in self.kb.check_patterns:
            if pat.standalone_operators and operators & set(pat.standalone_operators):
                return pat
            if not (pat.operators and operators & set(pat.operators)):
                continue
            if pat.operand_identifiers and operand_idents & {
                i.lower() for i in pat.operand_identifiers
            }:
                return pat
            if pat.operand_literal_prefixes and any(
                lit.startswith(p.lower())
                for lit in operand_literals
                for p in pat.operand_literal_prefixes
            ):
                return pat
            if not pat.operand_identifiers and not pat.operand_literal_prefixes:
                return pat  # operator alone is sufficient for this pattern
        return None

    def _classify_call(self, name: str) -> Optional[CheckPattern]:
        low = name.lower()
        for pat in self.kb.check_patterns:
            if low in {c.lower() for c in pat.call_names}:
                return pat
        return None

    def _ordered_before(
        self, cond: int, cs: int, departure: Optional[int], method: int
    ) -> bool:
        """CFG: does the check dominate the flow's departure toward the sink?"""
        cpg = self.cpg
        if departure is None:
            return True  # nothing downstream in this method to order against
        if cpg.dominates(cond, departure) or cpg.dominates(cs, departure):
            return True
        # Fall back to intra-method source order.
        cl, dl = cpg.line(cs), cpg.line(departure)
        return isinstance(cl, int) and isinstance(dl, int) and cl <= dl

    def _detect_negative_evidence(
        self, field_prof: FieldProfile, trace: FlowTrace
    ) -> List[NegativeCheckEvidence]:
        """Structural negative evidence: the tainted value reached a sink whose
        *domain* disproves a required safe-API check (e.g. a COMMAND_EXECUTION
        sink disproves SAFE_DOWNLOAD_API_NO_SHELL).

        This reuses the same sink symbol→domain mapping as step 4 — no regex and
        no re-scanning of source text.
        """
        cpg = self.cpg
        negatives: List[NegativeCheckEvidence] = []

        # Domain of every sink the tainted value actually reached (by symbol).
        reached = []
        for call, _arg in trace.sinks:
            prof = self.kb.sink_for_api(cpg.name(call))
            if prof is not None:
                reached.append((call, prof.sink_domain))

        for check_id in field_prof.expected_checks:
            neg_domains = set(self.kb.negative_sink_domains_for(check_id))
            if not neg_domains:
                continue
            for call, domain in reached:
                if domain not in neg_domains:
                    continue
                owner = cpg.method_of(call)
                negatives.append(
                    NegativeCheckEvidence(
                        evidence_id=self.ids.next("OCPP-NEG-CHK"),
                        related_expected_check=check_id,
                        reason=(
                            f"tainted value reaches a {domain} sink "
                            f"'{cpg.name(call)}' instead of a safe {check_id}."
                        ),
                        file=cpg.method_filename(owner) if owner is not None else "",
                        function=cpg.name(owner) if owner is not None else "",
                        line=cpg.line(call),
                        confidence=0.94,
                    )
                )
                break  # one negative-evidence record per expected check
        return negatives
        return negatives

    # ------------------------------------------------------------------
    # Step 6 · Expected matching  (KB expected vs observed)
    # ------------------------------------------------------------------

    def _step6_match_expected(
        self,
        action: str,
        field_prof: FieldProfile,
        trace: FlowTrace,
        observed: List[ObservedCheck],
        negatives: List[NegativeCheckEvidence],
    ) -> Tuple[ExpectedCheckMatching, MissingCheckCandidateSet]:
        candidate_id = self.ids.next("OCPP-FLOW")
        self._current_candidate_id = candidate_id

        neg_by_check = {n.related_expected_check: n for n in negatives}
        obs_by_expected: Dict[str, List[ObservedCheck]] = {}
        for o in observed:
            if o.matched_expected_check:
                obs_by_expected.setdefault(o.matched_expected_check, []).append(o)

        results: List[MatchingResult] = []
        summary = MissingCheckSummary()
        missing_items: List[MissingCheckItem] = []
        weak_items: List[WeakCheckItem] = []
        review_items: List[MissingCheckItem] = []

        for check_id in field_prof.expected_checks:
            matches = obs_by_expected.get(check_id, [])
            negative = neg_by_check.get(check_id)

            if negative is not None:
                status = "NEGATIVE_EVIDENCE_FOUND"
                results.append(
                    MatchingResult(
                        expected_check=check_id,
                        matching_status=cast(MatchingStatus, status),
                        basis=["negative_evidence"],
                        confidence=negative.confidence,
                        limitations=["Negative evidence indicates the safe control is bypassed, not that exploitation is confirmed."],
                    )
                )
                summary.missing_check_candidates.append(check_id)
                missing_items.append(
                    MissingCheckItem(
                        check_id=check_id,
                        basis="NEGATIVE_EVIDENCE_FOUND",
                        confidence=negative.confidence,
                        reason=negative.reason,
                    )
                )
                continue

            if matches:
                strongest = max(matches, key=lambda m: _strength_rank(m.check_strength))
                if strongest.check_strength == "STRONG":
                    status = "SATISFIED"
                    summary.satisfied_checks.append(check_id)
                elif strongest.check_strength in ("PARTIAL",):
                    status = "PARTIALLY_SATISFIED"
                    summary.partially_satisfied_checks.append(check_id)
                    weak_items.append(
                        WeakCheckItem(
                            check_id=strongest.check_type,
                            related_expected_check=check_id,
                            reason="Related check found but only partially satisfies the requirement.",
                        )
                    )
                else:  # WEAK / UNKNOWN
                    status = "WEAKLY_RELATED"
                    summary.weakly_related_checks.append(check_id)
                    summary.missing_check_candidates.append(check_id)
                    weak_items.append(
                        WeakCheckItem(
                            check_id=strongest.check_type,
                            related_expected_check=check_id,
                            reason="A weak/related check exists but does not satisfy the expected check.",
                        )
                    )
                    missing_items.append(
                        MissingCheckItem(
                            check_id=check_id,
                            basis="WEAKLY_RELATED",
                            confidence=0.7,
                            reason="Only a weak/related check was observed.",
                        )
                    )
                results.append(
                    MatchingResult(
                        expected_check=check_id,
                        matching_status=cast(MatchingStatus, status),
                        matched_observed_check=strongest.observed_check_id,
                        check_strength=strongest.check_strength,
                        basis=["semantic_match" if status != "WEAKLY_RELATED" else "weak_match"],
                        confidence=strongest.confidence,
                        limitations=[] if status == "SATISFIED" else ["Check semantics judged statically; runtime effect not confirmed."],
                    )
                )
                continue

            # No observed evidence either way.
            status = "UNVERIFIED"
            summary.missing_check_candidates.append(check_id)
            results.append(
                MatchingResult(
                    expected_check=check_id,
                    matching_status=cast(MatchingStatus, status),
                    basis=["no_observed_check"],
                    confidence=0.75,
                    limitations=["Expected check not found on the analyzed path; it may be enforced elsewhere."],
                )
            )
            missing_items.append(
                MissingCheckItem(
                    check_id=check_id,
                    basis="UNVERIFIED",
                    confidence=0.75,
                    reason="No corresponding check observed on the source→sink path within this CPG.",
                )
            )

        matching = ExpectedCheckMatching(
            expected_check_matching_id=self.ids.next("OCPP-ECM"),
            candidate_id=candidate_id,
            action=action,
            field=field_prof.field_name,
            field_semantic=field_prof.semantic_type,
            expected_checks=list(field_prof.expected_checks),
            observed_check_references=[o.observed_check_id for o in observed],
            matching_results=results,
            missing_check_summary=summary,
        )
        missing_set = MissingCheckCandidateSet(
            missing_check_candidate_id=self.ids.next("OCPP-MCHK"),
            candidate_id=candidate_id,
            action=action,
            field=field_prof.field_name,
            missing_check_candidates=missing_items,
            weak_or_partial_check_candidates=weak_items,
            review_required_missing_check_candidates=review_items,
            limitations=["'missing' means 'not statically verifiable here', not 'absent at runtime'."],
        )
        return matching, missing_set

    # ------------------------------------------------------------------
    # Step 7 · Evidence package assembly
    # ------------------------------------------------------------------

    def _step7_assemble(
        self,
        action: str,
        field_prof: FieldProfile,
        handler_map: HandlerMap,
        binding: FieldBinding,
        trace: FlowTrace,
        sink_mapping: SinkMapping,
        observed: List[ObservedCheck],
        matching: ExpectedCheckMatching,
        missing_set: MissingCheckCandidateSet,
    ) -> Tuple[EvidencePackage, CandidateFragment, FlowCandidate]:
        candidate_id = self._current_candidate_id

        source_ref = SourceRef(
            source_type="OCPP_PAYLOAD_FIELD",
            binding=binding.binding.bound_variable,
            file=binding.binding.file,
            function=binding.binding.function,
            line=binding.binding.line,
        )
        sink_info = SinkInfo(
            sink_domain=sink_mapping.sink_domain,
            api=sink_mapping.api,
            file=sink_mapping.sink.file,
            function=sink_mapping.sink.function,
            line=sink_mapping.sink.line,
        )
        code_evidence = CodeEvidence(source=source_ref, flow=trace.steps, sink=sink_info)

        missing_ids = missing_set.missing_check_candidates
        related_cwe = sorted(set(field_prof.related_cwe) | set(sink_mapping.related_cwe))
        root_causes = self.kb.root_cause_for(
            sink_mapping.sink_domain, [m.check_id for m in missing_ids]
        )

        confidence = self._score(handler_map, binding, trace, sink_mapping, observed, matching)

        traceability = Traceability(
            files=sorted({s.file for s in trace.steps if s.file}),
            functions=sorted({s.function for s in trace.steps if s.function}),
            primary_locations=[
                PrimaryLocation(file=source_ref.file, line=source_ref.line, evidence=binding.binding.source_expression),
                PrimaryLocation(file=sink_info.file, line=sink_info.line, evidence=sink_mapping.mapping_evidence[0] if sink_mapping.mapping_evidence else ""),
            ],
        )

        limitations = list(STANDARD_LIMITATIONS)
        if any(s.operation.startswith("argument_pass") for s in trace.steps):
            limitations.append("Interprocedural flow was bridged via the call graph; deep alias/async paths are not modeled.")

        semantic_summary = (
            f"Untrusted OCPP field '{action}.{field_prof.field_name}' "
            f"({field_prof.semantic_type}) reaches {sink_mapping.sink_domain} sink "
            f"'{sink_mapping.api}' with only {self._observed_summary(observed)} on the path."
        )

        ocpp_ctx = OcppContext(
            ocpp_version=self.kb.actions[action].protocol_version,
            action=action,
            field=field_prof.field_name,
            field_semantic=field_prof.semantic_type,
            trust_level=field_prof.trust_level,
        )
        component_type = self.kb.actions[action].component_type

        package = EvidencePackage(
            evidence_id=self.ids.next("OCPP-EVID"),
            language="c",
            component_type=component_type,
            ocpp_context=ocpp_ctx,
            code_evidence=code_evidence,
            check_evidence=CheckEvidence(
                expected_checks=list(field_prof.expected_checks),
                observed_checks=observed,
                missing_check_candidates=missing_ids,
            ),
            traceability=traceability,
            security_interpretation=SecurityInterpretation(
                summary=semantic_summary,
                root_cause_candidates=root_causes,
                related_cwe=related_cwe,
            ),
            root_cause_candidates=root_causes,
            related_cwe=related_cwe,
            confidence=confidence,
            static_confidence=confidence.overall_static_confidence,
            limitations=limitations,
        )

        fragment = CandidateFragment(
            candidate_id=candidate_id,
            language="c",
            component_type=component_type,
            ocpp_context=ocpp_ctx,
            code_evidence=code_evidence,
            expected_checks=list(field_prof.expected_checks),
            observed_checks=observed,
            missing_check_candidates=missing_ids,
            root_cause_candidates=root_causes,
            related_cwe=related_cwe,
            static_confidence=confidence.overall_static_confidence,
            lifecycle_state_hint="STATIC_SUSPECT_HVVD",
            limitations=limitations,
        )

        flow_candidate = FlowCandidate(
            candidate_id=candidate_id,
            component_type=component_type,
            ocpp_version=ocpp_ctx.ocpp_version,
            action=action,
            field=field_prof.field_name,
            field_semantic=field_prof.semantic_type,
            source=source_ref,
            flow=trace.steps,
            sink=sink_info,
            observed_checks=[o.observed_check_id for o in observed],
            expected_checks=list(field_prof.expected_checks),
            missing_check_candidates=[m.check_id for m in missing_ids],
            static_confidence=confidence.overall_static_confidence,
            limitations=limitations,
        )
        return package, fragment, flow_candidate

    def _observed_summary(self, observed: List[ObservedCheck]) -> str:
        if not observed:
            return "no checks"
        return ", ".join(f"{o.check_type}({o.check_strength})" for o in observed)

    def _score(
        self,
        handler_map: HandlerMap,
        binding: FieldBinding,
        trace: FlowTrace,
        sink_mapping: SinkMapping,
        observed: List[ObservedCheck],
        matching: ExpectedCheckMatching,
    ) -> ConfidenceBreakdown:
        components = {
            "handler_mapping": handler_map.confidence,
            "field_binding": binding.confidence,
            "semantic_binding": 1.0 if binding.field_semantic else 0.5,
            "source_sink_flow": 0.8 if any(
                s.operation.startswith("argument_pass") for s in trace.steps
            ) else 0.95,
            "sink_mapping": 1.0 if sink_mapping.sink_domain != "UNKNOWN_SINK" else 0.4,
            "check_detection": 0.75 if observed else 0.6,
            "traceability": 1.0,
        }
        overall = round(sum(CONFIDENCE_WEIGHTS[k] * v for k, v in components.items()), 3)
        return ConfidenceBreakdown(overall_static_confidence=overall, **components)


def _strength_rank(strength: Optional[str]) -> int:
    order = {"CONFLICTED": 0, "UNKNOWN": 1, "WEAK": 2, "PARTIAL": 3, "STRONG": 4}
    return order.get(strength or "UNKNOWN", 1)


def cpg_id(vertex: Dict[str, Any]) -> int:
    from .graph import _unwrap

    return cast(int, _unwrap(vertex.get("id")))
