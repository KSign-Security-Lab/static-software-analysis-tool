from typing import Any, Dict, List, Set, Tuple

from dfg.constants import FLOW_ID, KEYWORDS
from dfg.processors.AssignmentAnalysisProcessor import AssignmentAnalysisProcessor
from dfg.processors.GuardMapProcessor import GuardMapProcessor
from dfg.processors.InitializationProcessor import InitializationProcessor
from dfg.processors.OutputProcessor import OutputProcessor
from dfg.processors.StatementProcessor import StatementProcessor
from dfg.utils import DFGUtils


class DFGExtractor(DFGUtils):
    def __init__(
        self,
        ast_json: Dict[str, Any],
        ast_result: Dict[str, Any],
        sink_mode: str = "k1",
    ):
        # Initialize processors
        self.initialization_processor = InitializationProcessor(self)
        self.output_processor = OutputProcessor(self)
        self.assignment_analysis_processor = AssignmentAnalysisProcessor(self)

        # Initialize DFG using the initialization processor
        self.initialization_processor.initialize_dfg(ast_json, ast_result, sink_mode)

        # Initialize additional attributes that are set by the initialization processor
        self.nodes = getattr(self, "nodes", [])
        self.sid2flat = getattr(self, "sid2flat", {})
        self.id2orig = getattr(self, "id2orig", {})

    # ------------------------------
    # Public: build edges + finalize node features
    # ------------------------------
    def run(self) -> Dict[str, Any]:
        """Main processing method - delegates to specialized processors."""
        # Build guard map
        self.guard_map = self._build_guard_map()

        # Initialize edge storage
        self.edges_defuse = []

        # Create and use statement processor
        processor = StatementProcessor(self)
        processor.process_all_statements(self.nodes)

        # Get processing state
        state = processor.get_processing_state()

        # Calculate degrees using output processor
        deg_in, deg_out = self.output_processor.calculate_degrees()

        # Build final output using output processor
        return self.output_processor.build_final_output(state, deg_in, deg_out)

    def _build_guard_map(self):
        """Build guard map for DFG processing."""
        guard_map_processor = GuardMapProcessor(self)
        return guard_map_processor.build_guard_map()

    # ------------------------------
    # AST helpers / schema-based visitors
    # ------------------------------
    def _find_ast_row_by_sid(self, sid: int) -> Dict[str, Any] | None:
        """Return flattened AST row by sid (has orig_id/id/code/node_type_id)."""
        try:
            s = int(sid)
        except Exception:
            return None
        return self.sid2flat.get(s)

    def _orig_for_stmt(self, flat_row: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if not isinstance(flat_row, dict):
            return None
        orig_id = (
            flat_row.get("orig_id")
            if isinstance(flat_row.get("orig_id"), int)
            else None
        )
        if orig_id is None:
            # 일부 파이프라인은 평탄화 row에도 id를 보존할 수 있음
            alt = flat_row.get("id")
            orig_id = alt if isinstance(alt, int) else None
        return self.id2orig.get(orig_id) if orig_id is not None else None

    # ------------------------------
    # Delegation methods to processors
    # ------------------------------
    def _is_decl_init_trick(
        self, sid: int, name: str, assign_node: Dict[str, Any]
    ) -> bool:
        """Delegate to AssignmentAnalysisProcessor."""
        return self.assignment_analysis_processor.is_decl_init_trick(
            sid, name, assign_node
        )

    def _assignment_by_ast(
        self, assign_node: Dict[str, Any], cur_sid: int
    ) -> Tuple[List[str], List[Tuple[str, str]], int, int]:
        """Delegate to AssignmentAnalysisProcessor."""
        return self.assignment_analysis_processor.assignment_by_ast(
            assign_node, cur_sid
        )

    def _array_decl_by_ast(
        self, decl: Dict[str, Any]
    ) -> Tuple[List[str], List[Tuple[str, str]]]:
        """Delegate to AssignmentAnalysisProcessor."""
        return self.assignment_analysis_processor.array_decl_by_ast(decl)

    # ------------------------------
    # Helper methods for run() method
    # ------------------------------
    def _ensure_feat(
        self,
        sid: int,
        node_type_id: str,
        node_feat: Dict[int, Dict[str, Any]],
        node_debug: Dict[int, Dict[str, Any]],
    ):
        """Ensure feature and debug containers exist for a node."""
        if sid not in node_feat:
            node_feat[sid] = {
                "node_type_id": node_type_id,
                "in_degree_dfg": 0,
                "out_degree_dfg": 0,
                # counts
                "def_count": 0,
                "use_count": 0,
                # buffer/sink
                "is_buffer_access": 0,
                "is_sink_assign": 0,
                "is_sink_call_unbounded": 0,
                "is_sink_call_bounded": 0,
                "call_dst_indexed": 0,
                "call_len_linked_to_dst": 0,
                "call_size_nonconst": 0,
                "call_danger_unbounded": 0,
            }
        if sid not in node_debug:
            node_debug[sid] = {"code": "", "def_vars": [], "use_vars": []}

    def _add_use_edge(
        self,
        var: str,
        role: str,
        dst_sid: int,
        last_def: Dict[str, int],
        seen_edges: Set[Tuple[int, int, str, int]],
        use_vars_by_sid: Dict[int, Set[str]],
    ):
        """
        USE 기록 및 Def→Use 에지 생성.
        - base 역할은 use_vars 카운트에서 제외(그래프 에지로만 표현)
        - 가드 주입은 변수별 → '*' → '__agg__' 를 병합한다:
            lower/upper는 OR, upper_const는 max,
            kind는 var > * > __agg__ 우선순위로 첫 비-0 선택
        - 에지는 flat dict로 저장하고, 마지막에 feat/debug로 래핑
        """
        if not var or var in KEYWORDS:
            return

        # 디버그/카운트용 USE: base는 제외
        if role != "base":
            use_vars_by_sid[dst_sid].add(var)

        # Def→Use 에지는 마지막 DEF가 있을 때만 생성
        if var not in last_def:
            return
        src = last_def[var]

        # flow_id 결정 (value=1, index=2, size=3, base=4)
        fid = FLOW_ID.get(role or "value", FLOW_ID["value"])

        key = (src, dst_sid, var, fid)
        if key in seen_edges:
            return
        seen_edges.add(key)

        # Get guard information for this statement
        dst_guards = self.guard_map.get(dst_sid, {})
        g_var = dst_guards.get(var) or {}
        g_all = dst_guards.get("*") or {}
        g_agg = dst_guards.get("__agg__") or {}

        # kind: var > * > __agg__ 우선순위
        kind = self._pick_kind(g_var, g_all, g_agg)

        has_lower = (
            self._as_int(g_var.get("lower", 0))
            | self._as_int(g_all.get("lower", 0))
            | self._as_int(g_agg.get("lower", 0))
        )
        has_upper = (
            self._as_int(g_var.get("upper", 0))
            | self._as_int(g_all.get("upper", 0))
            | self._as_int(g_agg.get("upper", 0))
        )
        upper_norm = max(
            self._as_float(g_var.get("upper_const", 0.0)),
            self._as_float(g_all.get("upper_const", 0.0)),
            self._as_float(g_agg.get("upper_const", 0.0)),
        )

        if getattr(self, "DEBUG_GUARD", False) and dst_sid in (40,):
            print(
                f"[DBG][edge] {src}->{dst_sid} var={var} role={role} fid={fid} "
                f"guard=({kind},{has_lower},{has_upper},{upper_norm})"
            )

        # ---- 에지 페이로드 저장 (flat; 최종 변환부에서 래핑) ----
        self.edges_defuse.append(
            (
                src,
                dst_sid,
                {
                    "var_key": f"{var}@{src}",
                    "flow_id": fid,
                    "guard_kind": kind,
                    "has_lower_guard": has_lower,
                    "has_upper_guard": has_upper,
                    "upper_guard_norm": upper_norm,
                },
            )
        )
