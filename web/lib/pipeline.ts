// Turn the SSAT pipeline's per-function artifacts into the same GraphView shape
// the CPG views use, so <GraphView> can render both without knowing which is
// which.
//
// These are NOT the CPG views in lib/views.ts. Those project Joern's own graph
// by edge label. These are the statement-level AST and def-use DFG that the
// Python pipeline computes from the Template — a different object that happens
// to share the words "AST" and "DFG".

import type {
  GraphView,
  PipelineAst,
  PipelineFunction,
  ViewEdge,
  ViewNode,
} from "./types";

/** Guard-edge kinds, as emitted by the AST extractor. */
const GUARD_KIND_LABEL: Record<number, string> = {
  1: "lower",
  2: "upper",
  4: "switch",
};

/** DFG edge flow ids (see ssat.dfg.extractor FLOW_ID). */
const FLOW_LABEL: Record<number, string> = {
  1: "value",
  2: "index",
  3: "size",
  4: "base",
};

function astNodes(ast: PipelineAst): ViewNode[] {
  return ast.nodes.map((n) => ({
    id: String(n.sid),
    label: n.node_type_id || "Statement",
    name: "",
    code: n.code ?? "",
    line: "",
    props: { sid: n.sid, orig_id: n.orig_id, ...(n.feat ?? {}), ...(n.debug ?? {}) },
  }));
}

export function pipelineAstView(fn: PipelineFunction): GraphView {
  const edges: ViewEdge[] = [];

  for (const [parent, child] of fn.ast.edges_ast_pc ?? []) {
    edges.push({ id: `pc-${parent}-${child}`, source: String(parent), target: String(child), label: "" });
  }
  for (const [prev, next] of fn.ast.edges_ast_sb ?? []) {
    edges.push({ id: `sb-${prev}-${next}`, source: String(prev), target: String(next), label: "next" });
  }
  for (const g of fn.ast.edges_ast_guard ?? []) {
    edges.push({
      id: `guard-${g.src}-${g.dst}`,
      source: String(g.src),
      target: String(g.dst),
      label: GUARD_KIND_LABEL[g.guard_kind] ?? "guard",
    });
  }

  return {
    key: "pipeline-ast",
    title: "AST (pipeline)",
    description:
      "Statement-level tree built by the SSAT extractor: parent/child, statement order, and guard edges.",
    nodes: astNodes(fn.ast),
    edges,
  };
}

export function pipelineDfgView(fn: PipelineFunction): GraphView {
  // DFG nodes carry only sids; borrow the AST's code for readable labels.
  const codeBySid = new Map(fn.ast.nodes.map((n) => [n.sid, n.code ?? ""]));
  const typeBySid = new Map(fn.ast.nodes.map((n) => [n.sid, n.node_type_id ?? ""]));

  const nodes: ViewNode[] = (fn.dfg.nodes ?? []).map((n) => ({
    id: String(n.sid),
    label: n.node_type_id || typeBySid.get(n.sid) || "Statement",
    name: "",
    code: codeBySid.get(n.sid) ?? "",
    line: "",
    props: { sid: n.sid, ...(n.feat ?? {}), ...(n.debug ?? {}) },
  }));

  const edges: ViewEdge[] = (fn.dfg.edges_dfg ?? []).map(([src, dst, attrs], i) => {
    const varKey = String((attrs?.debug as { var_key?: string } | undefined)?.var_key ?? "");
    const flowId = Number((attrs?.feat as { flow_id?: number } | undefined)?.flow_id ?? 0);
    const flow = FLOW_LABEL[flowId];
    const label = varKey || flow || "";
    return { id: `dfg-${src}-${dst}-${i}`, source: String(src), target: String(dst), label };
  });

  return {
    key: "pipeline-dfg",
    title: "DFG (pipeline)",
    description:
      "Def-use data flow: which statement's write reaches which statement's read, with the variable on each edge.",
    nodes,
    edges,
  };
}

/** Functions that actually produced something worth drawing. */
export function nonEmptyFunctions(functions: PipelineFunction[]): PipelineFunction[] {
  return functions.filter((f) => (f.ast?.nodes?.length ?? 0) > 0);
}
