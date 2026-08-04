// Parse a Joern CPG GraphSON document into a normalized, queryable model.
//
// Mirrors the edge/property semantics that ssat.f2a.graph.CPGModel relies on
// (verified against real exports):
//   - property value = VertexProperty -> List -> [value]  (single-element)
//   - AST edge: outV = parent, inV = child
//   - CALL edge: outV = call-site, inV = callee METHOD
//   - REACHING_DEF: outV = def, inV = use (variable in edge property)
//   - REF: outV = IDENTIFIER, inV = declaration
//   - CFG / DOMINATE: control-flow / dominance edges

import type { CpgDocument, CpgEdge, CpgNode, ParsedCpg, RawEdge, RawGraph, RawVertex } from "./types";

/** Recursively strip GraphSON `@value` wrappers. */
export function unwrap(value: unknown): unknown {
  if (value !== null && typeof value === "object") {
    if ("@value" in (value as Record<string, unknown>)) {
      return unwrap((value as Record<string, unknown>)["@value"]);
    }
    if (Array.isArray(value)) {
      return value.map((v) => unwrap(v));
    }
  }
  return value;
}

/** A single scalar from an unwrapped value that may be a one-element array. */
function scalarize(value: unknown): unknown {
  const u = unwrap(value);
  if (Array.isArray(u)) {
    return u.length === 1 ? u[0] : u.length ? u : undefined;
  }
  return u;
}

function toId(value: unknown): string {
  const u = unwrap(value);
  return typeof u === "object" ? JSON.stringify(u) : String(u);
}

/** Find the {vertices, edges} object inside any accepted document shape. */
/**
 * Unwrap a CPG file to the bare GraphSON the API and the viewers expect.
 *
 * `ssat cpg` and the API disagree about the wrapper: the pipeline reads
 * `{"export": ...}` while /analyze returns the GraphSON directly. Accept both
 * rather than making the user know which one they have.
 */
export function unwrapCpgDocument(raw: unknown): unknown {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const o = raw as Record<string, unknown>;
    if ("export" in o) return o.export;
  }
  return raw;
}

/** Whether a parsed JSON file has vertices we can draw. */
export function looksLikeCpg(raw: unknown): boolean {
  const { vertices } = extractGraph(unwrapCpgDocument(raw) as CpgDocument);
  return vertices.length > 0;
}

export function extractGraph(doc: CpgDocument): RawGraph {
  const vertices: RawVertex[] = [];
  const edges: RawEdge[] = [];

  const absorb = (obj: unknown): boolean => {
    if (obj && typeof obj === "object") {
      const o = obj as Record<string, unknown>;
      if ("vertices" in o && "edges" in o) {
        vertices.push(...((o.vertices as RawVertex[]) ?? []));
        edges.push(...((o.edges as RawEdge[]) ?? []));
        return true;
      }
      if ("@value" in o) return absorb(o["@value"]);
    }
    return false;
  };

  if (Array.isArray(doc)) doc.forEach((item) => absorb(item));
  else absorb(doc);

  return { vertices, edges };
}

function nodeProps(v: RawVertex): { props: Record<string, unknown>; name: string; code: string; line: string | number } {
  const props: Record<string, unknown> = {};
  const raw = v.properties ?? {};
  for (const [key, val] of Object.entries(raw)) {
    props[key] = scalarize(val);
  }
  const name = props.NAME != null ? String(props.NAME) : "";
  const code = props.CODE != null ? String(props.CODE) : "";
  const lineVal = props.LINE_NUMBER;
  const line = typeof lineVal === "number" || typeof lineVal === "string" ? lineVal : "";
  const canonical = props.CANONICAL_NAME != null ? String(props.CANONICAL_NAME) : "";
  return { props, name: name || canonical, code, line };
}

function edgeVariable(e: RawEdge): string | undefined {
  const raw = e.properties ?? {};
  for (const val of Object.values(raw)) {
    const s = scalarize(val);
    if (typeof s === "string" && s.length) return s;
  }
  return undefined;
}

export function parseCpg(doc: CpgDocument): ParsedCpg {
  const { vertices, edges: rawEdges } = extractGraph(doc);

  const nodes = new Map<string, CpgNode>();
  const labelCounts: Record<string, number> = {};
  for (const v of vertices) {
    const id = toId(v.id);
    const { props, name, code, line } = nodeProps(v);
    nodes.set(id, { id, label: v.label, name, code, line, props });
    labelCounts[v.label] = (labelCounts[v.label] ?? 0) + 1;
  }

  const edges: CpgEdge[] = [];
  const edgesByLabel = new Map<string, CpgEdge[]>();
  const edgeLabelCounts: Record<string, number> = {};
  const astParent = new Map<string, string>(); // child -> parent

  rawEdges.forEach((e, idx) => {
    const source = toId(e.outV);
    const target = toId(e.inV);
    const edge: CpgEdge = {
      id: `e${idx}`,
      label: e.label,
      source,
      target,
      variable: e.label === "REACHING_DEF" ? edgeVariable(e) : undefined,
    };
    edges.push(edge);
    if (!edgesByLabel.has(e.label)) edgesByLabel.set(e.label, []);
    edgesByLabel.get(e.label)!.push(edge);
    edgeLabelCounts[e.label] = (edgeLabelCounts[e.label] ?? 0) + 1;
    if (e.label === "AST") astParent.set(target, source);
  });

  const methodCache = new Map<string, string | undefined>();
  const methodOf = (nodeId: string): string | undefined => {
    if (methodCache.has(nodeId)) return methodCache.get(nodeId);
    const seen = new Set<string>();
    let cur: string | undefined = nodeId;
    while (cur !== undefined && !seen.has(cur)) {
      seen.add(cur);
      if (nodes.get(cur)?.label === "METHOD") {
        methodCache.set(nodeId, cur);
        return cur;
      }
      cur = astParent.get(cur);
    }
    methodCache.set(nodeId, undefined);
    return undefined;
  };

  return { nodes, edges, edgesByLabel, labelCounts, edgeLabelCounts, methodOf };
}
