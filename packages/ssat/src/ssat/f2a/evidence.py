"""Builders for the reviewable evidence F2-A attaches to its findings.

Every piece of evidence answers the same two questions -- *what* was seen and
*where* -- and the "where" is always the file of some enclosing method plus the
line of some node. Thirteen construction sites spelled that out, several of them
guarding ``method_filename`` against ``None`` even though it already returns ``""``
for ``None``.
"""

from __future__ import annotations

from typing import List, Optional

from .graph import CPGModel
from .models import MappingEvidence

#: The evidence type paired with every dispatch site: the call it dispatches to.
HANDLER_CALL = "HANDLER_CALL"


def at(
    cpg: CPGModel,
    kind: str,
    *,
    value: str,
    node: Optional[int],
    method: Optional[int] = None,
) -> MappingEvidence:
    """Evidence of ``kind`` reading ``value``, located at ``node``.

    The file comes from ``method`` when given, otherwise from whichever method
    encloses ``node``.
    """
    owner = method if method is not None else cpg.method_of(node)
    return MappingEvidence(type=kind, value=value, file=cpg.method_filename(owner), line=cpg.line(node))


def code_at(cpg: CPGModel, kind: str, node: Optional[int], *, method: Optional[int] = None) -> MappingEvidence:
    """Evidence whose value is the node's own source text."""
    return at(cpg, kind, value=cpg.code(node), node=node, method=method)


def method_ref(cpg: CPGModel, kind: str, method: Optional[int]) -> MappingEvidence:
    """Evidence naming a method -- its name, its file, its line."""
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
    """The two-part mapping every dispatch extractor produces.

    First where the action was recognised, then the call that hands off to the
    handler. Both are located in the same method.
    """
    return [
        at(cpg, dispatch_kind, value=dispatch_value, node=dispatch_node, method=method),
        code_at(cpg, HANDLER_CALL, handler_call, method=method),
    ]
