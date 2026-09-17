from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)
KEYWORDS = {"if", "for", "while", "switch", "case", "return", "int", "char", "void", "NULL", "sizeof", "stdin", "else"}
FLOW_ID = {"value": 1, "index": 2, "size": 3, "base": 4}
ZERO_FEAT = {
    "in_degree_dfg": 0,
    "out_degree_dfg": 0,
    "def_count": 0,
    "use_count": 0,
    "is_buffer_access": 0,
    "is_sink_assign": 0,
    "is_sink_call_unbounded": 0,
    "is_sink_call_bounded": 0,
    "call_dst_indexed": 0,
    "call_len_linked_to_dst": 0,
    "call_size_nonconst": 0,
    "call_danger_unbounded": 0,
}

CALL_FEAT_KEYS = (
    "is_sink_call_unbounded",
    "is_sink_call_bounded",
    "call_dst_indexed",
    "call_len_linked_to_dst",
    "call_size_nonconst",
    "call_danger_unbounded",
)


@dataclass
class StatementScope:
    excluded: Set[str] = field(default_factory=set)
    used_by_call: Set[str] = field(default_factory=set)

    def skips(self, token: str) -> bool:
        return token in self.excluded or token in self.used_by_call


@dataclass
class AssignmentTarget:
    name: str = ""
    node_type: Optional[str] = None
    is_pointer_base: bool = False
    is_object_base: bool = False


def _as_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _as_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


class DefUseAccumulator:
    def __init__(self, guard_map: Dict[int, Dict[str, Dict[str, Any]]], *, debug_guard: bool = False):
        self.guard_map = guard_map
        self.debug_guard = debug_guard

        self.last_def: Dict[str, int] = {}
        self.seen_edges: Set[Tuple[int, int, str, int]] = set()

        self.use_vars_by_sid: Dict[int, Set[str]] = defaultdict(set)
        self.def_vars_by_sid: Dict[int, Set[str]] = defaultdict(set)
        self.buffer_access_by_sid: Dict[int, int] = defaultdict(int)
        self.sink_assign_by_sid: Dict[int, int] = defaultdict(int)

        self.node_feat: Dict[int, Dict[str, Any]] = {}
        self.node_debug: Dict[int, Dict[str, Any]] = {}

        self.edges: List[Tuple[int, int, Dict[str, Any]]] = []

    def ensure_node(self, sid: int, node_type_id: str) -> None:
        if sid not in self.node_feat:
            self.node_feat[sid] = {"node_type_id": node_type_id, **ZERO_FEAT}
        if sid not in self.node_debug:
            self.node_debug[sid] = {"code": "", "def_vars": [], "use_vars": []}

    def raise_feat(self, sid: int, key: str, value: int) -> None:
        self.node_feat[sid][key] = max(self.node_feat[sid][key], value)

    def clear_call_feats(self, sid: int) -> None:
        for key in CALL_FEAT_KEYS:
            self.node_feat[sid][key] = 0

    def define(self, var: str, sid: int) -> None:
        if not var or var in KEYWORDS:
            return
        self.last_def[var] = sid
        self.def_vars_by_sid[sid].add(var)

    def seed_parameter(self, name: str) -> None:
        if name and name != "<empty>":
            self.last_def[name] = 0
            self.def_vars_by_sid[0].add(name)

    def add_use_edge(self, var: str, role: str, dst_sid: int) -> None:
        if not var or var in KEYWORDS:
            return

        if role != "base":
            self.use_vars_by_sid[dst_sid].add(var)

        if var not in self.last_def:
            return
        src = self.last_def[var]
        fid = FLOW_ID.get(role or "value", FLOW_ID["value"])
        key = (src, dst_sid, var, fid)
        if key in self.seen_edges:
            return
        self.seen_edges.add(key)

        guards = self.guard_map.get(dst_sid, {}) or {}
        candidates = [guards.get(var) or {}, guards.get("*") or {}, guards.get("__agg__") or {}]
        kind = next((k for k in (_as_int(g.get("kind", 0)) for g in candidates) if k), 0)
        has_lower = _as_int(candidates[0].get("lower", 0))
        has_upper = _as_int(candidates[0].get("upper", 0))
        for g in candidates[1:]:
            has_lower |= _as_int(g.get("lower", 0))
            has_upper |= _as_int(g.get("upper", 0))
        upper_norm = max(_as_float(g.get("upper_const", 0.0)) for g in candidates)

        if self.debug_guard:
            logger.debug(
                "[edge] %s->%s var=%s role=%s fid=%s guard=(%s,%s,%s,%s)",
                src,
                dst_sid,
                var,
                role,
                fid,
                kind,
                has_lower,
                has_upper,
                upper_norm,
            )

        self.edges.append(
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

    def add_return_value_edge(self, call_sid: int, assign_sid: int) -> None:
        agg = (self.guard_map.get(assign_sid) or {}).get("__agg__", {})
        var_key = f"$ret@{call_sid}"
        self.edges.append(
            (
                call_sid,
                assign_sid,
                {
                    "var_key": var_key,
                    "feat": {
                        "flow_id": FLOW_ID["value"],
                        "guard_kind": _as_int(agg.get("kind", 0)),
                        "has_lower_guard": _as_int(agg.get("lower", 0)),
                        "has_upper_guard": _as_int(agg.get("upper", 0)),
                        "upper_guard_norm": _as_float(agg.get("upper_const", 0.0)),
                    },
                    "debug": {"var_key": var_key},
                },
            )
        )

    def degrees(self, sids: List[int]) -> Tuple[Dict[int, int], Dict[int, int]]:
        deg_in = {sid: 0 for sid in sids}
        deg_out = {sid: 0 for sid in sids}
        for src, dst, _attr in self.edges:
            if src in deg_out:
                deg_out[src] += 1
            if dst in deg_in:
                deg_in[dst] += 1
        return deg_in, deg_out

    def emitted_edges(self) -> List[List[Any]]:
        return [
            [
                src,
                dst,
                {
                    "feat": {
                        "flow_id": attr.get("flow_id", 1),
                        "guard_kind": attr.get("guard_kind", 0),
                        "has_lower_guard": attr.get("has_lower_guard", 0),
                        "has_upper_guard": attr.get("has_upper_guard", 0),
                        "upper_guard_norm": attr.get("upper_guard_norm", 0.0),
                    },
                    "debug": {"var_key": attr.get("var_key", "")},
                },
            ]
            for src, dst, attr in self.edges
        ]
