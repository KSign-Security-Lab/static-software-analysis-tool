from typing import List, Literal, NotRequired, Tuple, TypedDict

# --- Enumerations ---

ASTNodeType = Literal[
    "FunctionEntry",
    "ParameterDeclaration",
    "IfStatement",
    "VariableDeclaration",
    "AssignmentExpression",
    "UserDefinedCall",
    "StandardLibCall",
]

# If you have a closed set for edge kinds, narrow these:
ASTEdgeGuardKind = Literal[0, 1]  # seen: 1
ASTEdgeTypeKind = Literal[0, 1, 2]  # seen: 2 in edges_ast_guard; 0/1 used in *_pc/*_sb


# --- ASTNode feature payload ---


class ASTNodeFeat(TypedDict):
    node_type_id: int
    train_mask: int
    in_loop: int
    is_loop: int
    ctx_guard_strength: int
    ctx_upper_bound_norm: float
    is_buffer_decl: int
    buffer_size_state: int
    buffer_size_norm: float
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


class ASTNodeDebug(TypedDict, total=False):
    origin: str  # present for some ParameterDeclaration nodes


class ASTNode(TypedDict):
    sid: int
    node_type: ASTNodeType
    code: str
    orig_id: int
    feat: ASTNodeFeat
    debug: NotRequired[ASTNodeDebug]


# --- Edge payloads ---

# Program counter edges: (src_sid, dst_sid, edge_type_int)
AstPcEdge = Tuple[int, int, int]

# Sibling/sequence edges: (src_sid, dst_sid, edge_type_int)
AstSbEdge = Tuple[int, int, int]


class AstGuardEdge(TypedDict):
    src: int
    dst: int
    edge_type: ASTEdgeTypeKind  # e.g., 2
    guard_kind: ASTEdgeGuardKind  # e.g., 1
    guard_branch: int  # e.g., 0 or 1


# --- ASTGraph and dataset ---


class ASTGraph(TypedDict):
    nodes: List[ASTNode]
    edges_ast_pc: List[AstPcEdge]
    edges_ast_sb: List[AstSbEdge]
    edges_ast_guard: List[AstGuardEdge]


AST = List[ASTGraph]
