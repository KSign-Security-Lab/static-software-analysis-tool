"""Mutable bookkeeping for one def-use extraction pass.

``DFGExtractor.run()`` used to hold all of this in local variables of an
826-line function, with three closures over them. The state is the same; it just
has a name now, so the statement handlers can be separate methods instead of
sections of one loop body.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

#: Tokens that are never variables.
KEYWORDS = {"if", "for", "while", "switch", "case", "return", "int", "char", "void", "NULL", "sizeof", "stdin", "else"}

#: Which kind of flow an edge carries.
FLOW_ID = {"value": 1, "index": 2, "size": 3, "base": 4}

#: Zeroed feature vector for a DFG node.
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

#: Feature bits that describe a *call*, cleared on nodes that are not one.
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
    """Tokens a call within the current statement has already accounted for.

    Both sets exist to stop one variable being counted twice for one statement:
    ``excluded`` is what a call wrote (so it is not also a token USE), and
    ``used_by_call`` is what a call already read as an argument.
    """

    excluded: Set[str] = field(default_factory=set)
    used_by_call: Set[str] = field(default_factory=set)

    def skips(self, token: str) -> bool:
        return token in self.excluded or token in self.used_by_call


@dataclass
class AssignmentTarget:
    """What an assignment's left-hand side names, and how the write reaches it.

    The two flags are not opposites and both can be false -- a left-hand side
    this pass does not recognise names nothing and gets neither treatment.

    * ``is_object_base`` -- the write lands on the named thing (``x``, ``s.f``,
      ``buf[i]``), so it is a definition of that name.
    * ``is_pointer_base`` -- the write goes *through* the name (``*p``,
      ``p[i]`` where p is a dereference), so the name is read, not defined.
    """

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
    """Collects DEF/USE facts and def-use edges as statements are walked."""

    def __init__(self, guard_map: Dict[int, Dict[str, Dict[str, Any]]], *, debug_guard: bool = False):
        self.guard_map = guard_map
        self.debug_guard = debug_guard

        #: variable -> sid of the statement that last defined it
        self.last_def: Dict[str, int] = {}
        #: (src, dst, var, flow_id) already emitted
        self.seen_edges: Set[Tuple[int, int, str, int]] = set()

        self.use_vars_by_sid: Dict[int, Set[str]] = defaultdict(set)
        self.def_vars_by_sid: Dict[int, Set[str]] = defaultdict(set)
        self.buffer_access_by_sid: Dict[int, int] = defaultdict(int)
        self.sink_assign_by_sid: Dict[int, int] = defaultdict(int)

        self.node_feat: Dict[int, Dict[str, Any]] = {}
        self.node_debug: Dict[int, Dict[str, Any]] = {}

        #: (src_sid, dst_sid, attributes) -- flat until :meth:`finalize` wraps them
        self.edges: List[Tuple[int, int, Dict[str, Any]]] = []

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def ensure_node(self, sid: int, node_type_id: str) -> None:
        """Create the feature and debug records for ``sid`` if absent."""
        if sid not in self.node_feat:
            self.node_feat[sid] = {"node_type_id": node_type_id, **ZERO_FEAT}
        if sid not in self.node_debug:
            self.node_debug[sid] = {"code": "", "def_vars": [], "use_vars": []}

    def raise_feat(self, sid: int, key: str, value: int) -> None:
        """Keep the larger of the current and given value for a feature bit."""
        self.node_feat[sid][key] = max(self.node_feat[sid][key], value)

    def clear_call_feats(self, sid: int) -> None:
        for key in CALL_FEAT_KEYS:
            self.node_feat[sid][key] = 0

    # ------------------------------------------------------------------
    # Definitions and uses
    # ------------------------------------------------------------------

    def define(self, var: str, sid: int) -> None:
        """Record that ``sid`` defines ``var``, making it the reaching definition."""
        if not var or var in KEYWORDS:
            return
        self.last_def[var] = sid
        self.def_vars_by_sid[sid].add(var)

    def seed_parameter(self, name: str) -> None:
        """A parameter arrives already defined, by the function entry node (sid 0)."""
        if name and name != "<empty>":
            self.last_def[name] = 0
            self.def_vars_by_sid[0].add(name)

    def add_use_edge(self, var: str, role: str, dst_sid: int) -> None:
        """Record a USE of ``var`` at ``dst_sid`` and edge it to the reaching definition.

        The ``base`` role is left out of the USE counts: a container write like
        ``buf[i] = x`` reads ``buf`` only in the sense of locating it, which the
        graph says with a flow_id=4 edge rather than a use count.

        Guard evidence is merged over three keys, most specific first: the
        variable's own, ``*``, then ``__agg__``. lower/upper OR together,
        upper_const takes the max, and kind takes the first non-zero.
        """
        if not var or var in KEYWORDS:
            return

        if role != "base":
            self.use_vars_by_sid[dst_sid].add(var)

        # An edge needs a definition to start from.
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
        # OR, not max: the sources only ever set 0 or 1, but this is what the
        # original did and the two differ the moment a value exceeds 1.
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
        """Edge the value a call returns to the assignment that consumes it.

        Note the shape: this is the one edge built with nested ``feat``/``debug``
        dicts rather than the flat keys every other edge uses. :meth:`emitted_edges`
        reads the flat keys, so the guard values computed here are dropped and the
        emitted edge carries defaults -- flow_id 1 (which happens to be right) and
        zeroed guards. Preserved as-is because correcting it would change output;
        recorded here so the next reader does not take the nested dict at face
        value.
        """
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

    # ------------------------------------------------------------------
    # Degrees
    # ------------------------------------------------------------------

    def degrees(self, sids: List[int]) -> Tuple[Dict[int, int], Dict[int, int]]:
        """In- and out-degree per sid, counting only edges between known nodes."""
        deg_in = {sid: 0 for sid in sids}
        deg_out = {sid: 0 for sid in sids}
        for src, dst, _attr in self.edges:
            if src in deg_out:
                deg_out[src] += 1
            if dst in deg_in:
                deg_in[dst] += 1
        return deg_in, deg_out

    def emitted_edges(self) -> List[List[Any]]:
        """The edge list in output shape, features split from debug fields."""
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
