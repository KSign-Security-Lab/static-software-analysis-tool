"""AST validation using Pydantic."""

from typing import Any, Dict, List, cast

from pydantic import BaseModel

from ..types.ast import IASTResult


class IASTFeatureModel(BaseModel):
    """AST feature model."""

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


class IASTNodeModel(BaseModel):
    """AST node model."""

    sid: int
    node_type: str
    code: str
    orig_id: int
    feat: IASTFeatureModel
    debug: Dict[str, Any] = {}


class EdgeASTGuardModel(BaseModel):
    """AST guard edge model."""

    src: int
    dst: int
    edge_type: int
    guard_kind: int
    guard_branch: int


def validate_ast_results(value: Any) -> List[IASTResult]:
    """Validate AST results."""
    if not isinstance(value, list):
        raise ValueError("AST results must be a list")

    results: List[IASTResult] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each AST result must be a dictionary")

        # Validate nodes
        nodes = []
        for node_data in item.get("nodes", []):
            node_model = IASTNodeModel.model_validate(node_data)
            nodes.append(
                {
                    "sid": node_model.sid,
                    "node_type": node_model.node_type,
                    "code": node_model.code,
                    "orig_id": node_model.orig_id,
                    "feat": node_model.feat.model_dump(),
                    "debug": node_model.debug,
                }
            )

        # Validate edges
        edges_ast_pc = [tuple(e) for e in item.get("edges_ast_pc", []) if isinstance(e, (list, tuple)) and len(e) == 3]
        edges_ast_sb = [tuple(e) for e in item.get("edges_ast_sb", []) if isinstance(e, (list, tuple)) and len(e) == 3]
        edges_ast_guard = [EdgeASTGuardModel.model_validate(e).model_dump() for e in item.get("edges_ast_guard", [])]

        results.append(
            cast(
                IASTResult,
                {
                    "nodes": nodes,
                    "edges_ast_pc": edges_ast_pc,
                    "edges_ast_sb": edges_ast_sb,
                    "edges_ast_guard": edges_ast_guard,
                },
            )
        )

    return results
