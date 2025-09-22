import { z } from "zod";

import type { IASTGraph, IASTResult } from "../types/ast";

// Feature schema
export const zIASTFeature = z.object({
  node_type_id: z.number(),
  train_mask: z.number(),
  in_loop: z.number(),
  is_loop: z.number(),
  ctx_guard_strength: z.number(),
  ctx_upper_bound_norm: z.number(),
  is_buffer_decl: z.number(),
  buffer_size_state: z.number(),
  buffer_size_norm: z.number(),
  call_sem_cat_id: z.number(),
  call_flag_danger_unbounded: z.number(),
  call_flag_len_linked_to_dst: z.number(),
  call_flag_sizeof_non_dst: z.number(),
  call_flag_has_varargs: z.number(),
  call_dst_is_field: z.number(),
  call_size_kind: z.number(),
  call_len_linked_to_dst_extended: z.number(),
  call_size_is_sizeof_base_struct: z.number(),
  call_size_mismatch_field: z.number(),
  alloc_sizeof_state: z.number(),
});

// Node schema
export const zIASTNode = z.object({
  sid: z.number(),
  node_type: z.string(),
  code: z.string(),
  orig_id: z.number(),
  feat: zIASTFeature,
});

// Edge schemas
export const zEdgeASTPC = z.tuple([z.number(), z.number(), z.number()]);
export const zEdgeASTSB = z.tuple([z.number(), z.number(), z.number()]);
export const zEdgeASTGuard = z.object({
  src: z.number(),
  dst: z.number(),
  edge_type: z.number(),
  guard_kind: z.number(),
  guard_branch: z.number(),
});

// Result schema
export const zIASTResult = z.object({
  nodes: z.array(zIASTNode),
  edges_ast_pc: z.array(zEdgeASTPC),
  edges_ast_sb: z.array(zEdgeASTSB),
  edges_ast_guard: z.array(zEdgeASTGuard),
});

// Graph schema
export const zIASTGraph = z.object({
  file: z.string(),
  label: z.number(),
  ast_result: z.array(zIASTResult),
});

export function validateIASTGraph(value: unknown): IASTGraph {
  return zIASTGraph.parse(value);
}

export function validateIASTResults(value: unknown): IASTResult[] {
  return z.array(zIASTResult).parse(value);
}
