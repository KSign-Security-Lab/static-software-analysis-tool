import { EdgeGeneric, ICPGRootExport, NodeInfo, TreeNode } from "../types/cpg";

interface EdgeInfo {
  edge: EdgeGeneric;
  inV_node: NodeInfo | null;
  outV_node: NodeInfo | null;
}

export class TemplateExtractor {
  public getTemplateTree(cpg: unknown): TreeNode[] {
    if (typeof cpg !== "object" || cpg === null || !("@value" in (cpg as Record<string, unknown>))) {
      return [];
    }
    const data = cpg as ICPGRootExport;
    const inner = data["@value"];
    if (typeof inner !== "object" || !Array.isArray(inner.edges) || !Array.isArray(inner.vertices)) {
      return [];
    }

    const edges = inner.edges;
    const nodes = inner.vertices;

    const astEdges = edges.filter((e) => e.label === "AST");

    const nodeDict: Record<string, NodeInfo> = {};
    for (const n of nodes) {
      if (this.isValueWrapper(n.id) && (typeof n.id["@value"] === "string" || typeof n.id["@value"] === "number")) {
        const key = String(n.id["@value"]);
        nodeDict[key] = n as unknown as NodeInfo;
      }
    }

    const astData: EdgeInfo[] = astEdges.map((edge) => {
      let outNode: NodeInfo | null = null;
      let inNode: NodeInfo | null = null;

      if (this.isValueWrapper(edge.outV)) {
        const outIdRaw = edge.outV["@value"];
        const outIdUnwrapped = this.unwrapValue(outIdRaw);
        const outIdStr = outIdUnwrapped !== undefined ? String(outIdUnwrapped) : "";
        outNode = nodeDict[outIdStr] ?? null;
      }
      if (this.isValueWrapper(edge.inV)) {
        const inIdRaw = edge.inV["@value"];
        const inIdUnwrapped = this.unwrapValue(inIdRaw);
        const inIdStr = inIdUnwrapped !== undefined ? String(inIdUnwrapped) : "";
        inNode = nodeDict[inIdStr] ?? null;
      }
      return {
        edge,
        inV_node: inNode,
        outV_node: outNode,
      };
    });

    const nodeInfoMap: Record<string, NodeInfo> = {};
    const childrenMap: Record<string, string[]> = {};

    for (const item of astData) {
      const edge = item.edge;

      if (this.isValueWrapper(edge.outV) && this.isValueWrapper(edge.inV)) {
        const outId = String(this.unwrapValue(edge.outV["@value"]));
        let inId = "";
        if (typeof edge.inV["@value"] === "string" || typeof edge.inV["@value"] === "number") {
          inId = String(edge.inV["@value"]);
        } else {
          // fallback: try to unwrap value if it's a value wrapper
          inId = this.unwrapValue(edge.inV["@value"]) !== undefined ? String(this.unwrapValue(edge.inV["@value"])) : "";
        }

        if (!(outId in nodeInfoMap)) {
          nodeInfoMap[outId] = this.extractNodeInfo(item.outV_node);
        }
        if (!(inId in nodeInfoMap)) {
          nodeInfoMap[inId] = this.extractNodeInfo(item.inV_node);
        }

        if (!(outId in childrenMap)) {
          childrenMap[outId] = [];
        }
        childrenMap[outId].push(inId);
      }
    }

    const allIds = new Set<string>(Object.keys(nodeInfoMap));
    const childIds = new Set<string>();
    for (const childArr of Object.values(childrenMap)) {
      for (const cid of childArr) {
        childIds.add(cid);
      }
    }
    const rootIds = Array.from(allIds).filter((id) => !childIds.has(id));

    function buildTree(nodeId: string): TreeNode {
      const info = nodeInfoMap[nodeId];

      const node: TreeNode = {
        id: info.id,
        label: info.label,
        name: info.name,
        code: info.code,
        line_no: info.line_no,
        properties: info.properties,
        children: [],
      };

      const childs = childrenMap[nodeId] ?? [];
      for (const cid of childs) {
        node.children.push(buildTree(cid));
      }
      return node;
    }

    return rootIds.map((rid) => buildTree(rid));
  }
  private extractNodeInfo(node: NodeInfo | null): NodeInfo {
    if (node === null) {
      throw new Error("Node cannot be null in extractNodeInfo");
    }

    let idVal = "";
    if (this.isValueWrapper(node.id) && (typeof node.id["@value"] === "string" || typeof node.id["@value"] === "number")) {
      idVal = String(node.id["@value"]);
    }

    const labelVal = node.label;

    let nameVal = "";
    if ("NAME" in node.properties) {
      const rawName = node.properties.NAME;
      const unwrappedName = this.unwrapValue(rawName);
      if (unwrappedName !== undefined) {
        nameVal = String(unwrappedName);
      }
    }

    let codeVal = "";
    if ("CODE" in node.properties) {
      const rawCode = node.properties.CODE;
      const unwrappedCode = this.unwrapValue(rawCode);
      if (unwrappedCode !== undefined) {
        codeVal = String(unwrappedCode);
      }
    }

    let lineNoVal: number | string = "";
    if ("LINE_NUMBER" in node.properties) {
      const rawLine = node.properties.LINE_NUMBER;
      const unwrappedLine = this.unwrapValue(rawLine);
      if (unwrappedLine !== undefined) {
        lineNoVal = unwrappedLine;
      }
    }

    return {
      code: codeVal,
      id: idVal,
      label: labelVal,
      line_no: lineNoVal,
      name: nameVal,
      properties: node.properties,
    };
  }

  /**
   * Type guard: checks if x is an object with a "@value" key.
   */
  private isValueWrapper(x: unknown): x is { "@value": unknown } {
    return typeof x === "object" && x !== null && "@value" in (x as Record<string, unknown>);
  }

  /**
   * Type guard: checks if x is an array of unknowns,
   * and at least one element is a ValueWrapper or primitive.
   */
  private isValueWrapperArray(x: unknown): x is unknown[] {
    return Array.isArray(x);
  }

  private unwrapValue(x: unknown): number | string | undefined {
    if (x == null) {
      return undefined;
    }

    if (typeof x === "string" || typeof x === "number") {
      return x;
    }

    if (this.isValueWrapper(x)) {
      const inner = x["@value"];

      if (typeof inner === "string" || typeof inner === "number") {
        return inner;
      }

      if (this.isValueWrapper(inner)) {
        return this.unwrapValue(inner["@value"]);
      }

      if (this.isValueWrapperArray(inner)) {
        return this.unwrapValue(inner);
      }

      return undefined;
    }

    if (this.isValueWrapperArray(x)) {
      for (const elem of x) {
        const unwrapped = this.unwrapValue(elem);
        if (unwrapped !== undefined) {
          return unwrapped;
        }
      }
      return undefined;
    }

    return undefined;
  }
}
