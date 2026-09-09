from __future__ import annotations

from typing import List, Optional

from .graph import CPGModel
from .models import MappingEvidence

HANDLER_CALL = "HANDLER_CALL"


def at(
    cpg: CPGModel,
    kind: str,
    *,
    value: str,
    node: Optional[int],
    method: Optional[int] = None,
) -> MappingEvidence:
    owner = method if method is not None else cpg.method_of(node)
    return MappingEvidence(type=kind, value=value, file=cpg.method_filename(owner), line=cpg.line(node))


def code_at(cpg: CPGModel, kind: str, node: Optional[int], *, method: Optional[int] = None) -> MappingEvidence:
    return at(cpg, kind, value=cpg.code(node), node=node, method=method)


def method_ref(cpg: CPGModel, kind: str, method: Optional[int]) -> MappingEvidence:
    return at(cpg, kind, value=cpg.name(method), node=method, method=method)


def dispatch_to_handler(
    cpg: CPGModel,
    dispatch_kind: str,
    *,
    dispatch_value: str,
    dispatch_node: Optional[int],
    handler_call: Optional[int],
    method: Optional[int] = None,
) -> List[MappingEvidence]:
    return [
        at(cpg, dispatch_kind, value=dispatch_value, node=dispatch_node, method=method),
        code_at(cpg, HANDLER_CALL, handler_call, method=method),
    ]
