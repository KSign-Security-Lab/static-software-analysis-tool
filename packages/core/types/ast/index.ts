interface IASTFeature {
  node_type_id: number;
  train_mask: number;
  in_loop: number;
  is_loop: number;
  ctx_guard_strength: number;
  ctx_upper_bound_norm: number;
  is_buffer_decl: number;
  buffer_size_state: number;
  buffer_size_norm: number;
  call_sem_cat_id: number;
  call_flag_danger_unbounded: number;
  call_flag_len_linked_to_dst: number;
  call_flag_sizeof_non_dst: number;
  call_flag_has_varargs: number;
  call_dst_is_field: number;
  call_size_kind: number;
  call_len_linked_to_dst_extended: number;
  call_size_is_sizeof_base_struct: number;
  call_size_mismatch_field: number;
  alloc_sizeof_state: number;
}

interface IASTNode {
  sid: number;
  node_type: string;
  code: string;
  orig_id: number;
  feat: IASTFeature;
}

type EdgeASTPC = [number, number, number];
type EdgeASTSB = [number, number, number];

interface EdgeASTGuard {
  src: number;
  dst: number;
  edge_type: number;
  guard_kind: number;
  guard_branch: number;
}

export interface IASTResult {
  nodes: IASTNode[];
  edges_ast_pc: EdgeASTPC[];
  edges_ast_sb: EdgeASTSB[];
  edges_ast_guard: EdgeASTGuard[];
}
