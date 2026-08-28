"""AST type definitions."""

from typing import Any, Dict, List, TypedDict


class IASTFeature(TypedDict):
    """AST node feature structure."""

    node_type_id: int
    train_mask: int
    in_loop: int
    is_loop: int
    ctx_guard_strength: int
    ctx_upper_bound_norm: int
    is_buffer_decl: int
    buffer_size_state: int
    buffer_size_norm: int
    call_sem_cat_id: int
    call_flag_danger_unbounded: int
    call_flag_len_linked_to_dst: int
    call_flag_sizeof_non_dst: int
    call_flag_has_varargs: int
    call_dst_is_field: int
    call_size_kind: int
    call_len_linked_to_dst_extended: int
    call_size_is_sizeof_base_struct: int
    call_size_mismatch_field: int
    alloc_sizeof_state: int


class IASTNode(TypedDict):
    """AST node structure."""

    sid: int
    node_type: str
    code: str
    orig_id: int
    feat: IASTFeature
    debug: Dict[str, Any]


EdgeASTPC = tuple[int, int, int]
EdgeASTSB = tuple[int, int, int]


class EdgeASTGuard(TypedDict):
    """AST guard edge structure."""

    src: int
    dst: int
    edge_type: int
    guard_kind: int
    guard_branch: int


class IASTResult(TypedDict):
    """AST result structure."""

    nodes: List[IASTNode]
    edges_ast_pc: List[EdgeASTPC]
    edges_ast_sb: List[EdgeASTSB]
    edges_ast_guard: List[EdgeASTGuard]


__all__ = [
    "IASTFeature",
    "IASTNode",
    "EdgeASTPC",
    "EdgeASTSB",
    "EdgeASTGuard",
    "IASTResult",
]
