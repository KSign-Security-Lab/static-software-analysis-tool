import type { CPGGraphData, CPGRoot, EdgeGeneric, EdgeLabel, GraphSON, GraphSONValue, NodeInfo, VertexGeneric, VertexProperty } from "../types/cpg";

export class CPGFilter {
  private readonly cpg: CPGGraphData;

  constructor(cpg: CPGRoot) {
    this.cpg = cpg.export["@value"];
  }

  public filterAST(): { edges: EdgeGeneric[]; vertices: NodeInfo[] } {
    const astEdges = this.filterEdgesByLabel(["AST"]);
    const astVertices = this.filterVertexByEdges(astEdges);
    const astVerticesWithProperties = astVertices.map((vertex) => this.decorateVertexWithProperties(vertex));

    return {
      edges: astEdges,
      vertices: astVerticesWithProperties,
    };
  }

  public filterDFG(): { edges: EdgeGeneric[]; vertices: NodeInfo[] } {
    const dfgEdges = this.filterEdgesByLabel(["CFG", "CDG"]);
    const dfgVertices = this.filterVertexByEdges(dfgEdges);
    const dfgVerticesWithProperties = dfgVertices.map((vertex) => this.decorateVertexWithProperties(vertex));

    return {
      edges: dfgEdges,
      vertices: dfgVerticesWithProperties,
    };
  }

  private filterEdgesByLabel(label: EdgeLabel[]): EdgeGeneric[] {
    return this.cpg.edges.filter((edge) => label.includes(edge.label));
  }

  private filterVertexByEdges(edges: EdgeGeneric[]): VertexGeneric[] {
    const outIds = new Set(edges.map((e) => e.outV["@value"]));
    const inIds = new Set(edges.map((e) => e.inV["@value"]));
    return this.cpg.vertices.filter((v) => outIds.has(v.id["@value"]) || inIds.has(v.id["@value"]));
  }

  private decorateVertexWithProperties(node: VertexGeneric): NodeInfo {
    // id
    const idVal = String(node.id["@value"]);

    // label
    const labelVal = node.label;

    // name (unwrap GraphSON or VertexProperty -> GraphSON)
    let nameVal = "";
    const rawName = this.getProp(node, "NAME");
    const unwrappedName = this.unwrapValue(rawName);
    if (unwrappedName !== undefined) nameVal = String(unwrappedName);

    // code
    let codeVal = "";
    const rawCode = this.getProp(node, "CODE");
    const unwrappedCode = this.unwrapValue(rawCode);
    if (unwrappedCode !== undefined) codeVal = String(unwrappedCode);

    // line number
    let lineNoVal: number | string = "";
    const rawLine = this.getProp(node, "LINE_NUMBER");
    const unwrappedLine = this.unwrapValue(rawLine);
    if (unwrappedLine !== undefined) lineNoVal = unwrappedLine;

    return {
      id: idVal,
      label: labelVal,
      name: nameVal,
      code: codeVal,
      line_no: lineNoVal,
      properties: node.properties as unknown as Record<string, unknown>,
    };
  }

  private getProp(node: VertexGeneric, key: "NAME" | "CODE" | "LINE_NUMBER"): GraphSON<GraphSONValue> | VertexProperty<GraphSONValue> | undefined {
    const props = node.properties as unknown as Record<string, unknown>;
    const val = props[key];
    if (this.isGraphSON(val)) return val;
    if (this.isVertexProperty(val)) return val;
    return undefined;
  }

  private isGraphSON(x: unknown): x is GraphSON<GraphSONValue> {
    if (typeof x !== "object" || x === null) return false;
    const obj = x as Record<string, unknown>;
    const inner = obj["@value"] as Record<string, unknown> | undefined;
    return !!(inner && typeof inner === "object" && "@value" in inner);
  }

  private isVertexProperty<T = GraphSONValue>(x: unknown): x is VertexProperty<T> {
    if (typeof x !== "object" || x === null) return false;
    const obj = x as Record<string, unknown>;
    return obj["@type"] === "g:VertexProperty" && "@value" in obj && "id" in obj;
  }

  private unwrapValue(x: GraphSON<GraphSONValue> | VertexProperty<GraphSONValue> | string | number | undefined): number | string | undefined {
    if (x == null) return undefined;
    if (typeof x === "string" || typeof x === "number") return x;

    // VertexProperty -> delegate to contained GraphSON
    if (this.isVertexProperty(x)) return this.unwrapValue(x["@value"]);

    // GraphSON
    if (this.isGraphSON(x)) {
      const inner = x["@value"]["@value"];
      if (typeof inner === "string" || typeof inner === "number") return inner;
      if (Array.isArray(inner)) {
        for (const v of inner) {
          if (typeof v === "string" || typeof v === "number") return v;
        }
        return undefined;
      }
      return undefined;
    }
    return undefined;
  }
}
