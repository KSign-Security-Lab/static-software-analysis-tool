# Template Module - Technical Documentation

## Table of Contents

1. [Overview](#overview)
2. [Execution Flow](#execution-flow)
3. [Component Responsibilities](#component-responsibilities)
4. [Data Transformations](#data-transformations)
5. [Design Rationale](#design-rationale)
6. [Configuration](#configuration)
7. [Integration with Endpoint](#integration-with-endpoint)
8. [Error Handling and Edge Cases](#error-handling-and-edge-cases)

---

## Overview

The Template module is a critical transformation layer in the static software analysis pipeline. When source code is analyzed, it first gets converted into a Code Property Graph (CPG) - a detailed representation containing all semantic information about the code. However, this CPG format is complex and not optimized for pattern matching or template-based analysis.

The Template module's role is to transform this complex CPG representation into a cleaner, normalized template format that is easier to work with for subsequent analysis steps. Think of it as translating a technical manual into a simplified, standardized format that other parts of the system can easily understand and process.

### The Problem Being Solved

Code Property Graphs are powerful representations that capture detailed semantic information about source code, including type information, control flow, data flow, and call relationships. However, this richness comes with complexity:

- **Verbose Representations**: CPG uses technical names like `<operator>.addition` instead of simple symbols like `+`
- **Graph Structure**: CPG stores relationships as edges in a graph, but many analysis algorithms need hierarchical tree structures
- **Inconsistent Formats**: Different code constructs may be represented in different ways in CPG
- **Missing Information**: Some information needed for analysis may be implicit or require inference

The Template module addresses these challenges by providing a standardized, normalized representation that:

- Uses familiar operator symbols and standard programming terminology
- Provides hierarchical tree structures that match code syntax
- Ensures consistent representation of similar constructs
- Infers missing information using multiple strategies

### What the Module Does

When an endpoint is called to analyze code, the Template module performs a series of transformations:

1. **Extracts** the abstract syntax tree structure from the CPG data
2. **Converts** CPG nodes into standardized template node types
3. **Normalizes** operators, types, and control structures to consistent formats
4. **Enhances** the template with additional information like source code snippets
5. **Flattens** the hierarchical tree structure into a graph format for analysis

This transformation enables the system to perform pattern matching, security analysis, and code generation tasks more effectively.

---

## Execution Flow

When an endpoint is called to generate templates from CPG data, the following sequence of operations occurs. This section provides a detailed walkthrough of each step in the transformation pipeline.

### Entry Point: buildTemplateArtifacts()

The template transformation process begins when the `buildTemplateArtifacts()` function is called from the endpoint. This function orchestrates all the template module components:

```typescript
function buildTemplateArtifacts(root: CPGRoot): {
  flatten: TemplateFlattenedGraph[];
  template: TreeNode[];
  templateResult: TemplateNodes[];
  textLines: string[];
} {
  const extractor = new TemplateExtractor();
  const converter = new TemplateConverter();
  const postProcessor = new PostProcessor();
  const planationTool = new PlanationTool([...]);

  const template: TreeNode[] = extractor.getTemplateTree(root.export);
  const converted = converter.convertTree(template);
  let templateResult = postProcessor.removeInvalidNodes(converted);
  templateResult = postProcessor.addCodeProperties(templateResult, root);

  const flatten = planationTool.flatten(templateResult);

  return { template, templateResult, textLines, flatten };
}
```

This function creates instances of each component and chains their operations together, with each step building upon the results of the previous step.

### Step 1: Tree Extraction (TemplateExtractor)

**What Happens**: The system receives CPG data in a graph format where relationships are stored as edges between nodes. The TemplateExtractor component reconstructs the hierarchical tree structure that represents the code's syntax.

**Why This Is Needed**: CPG stores information as a graph (nodes connected by edges), but for template analysis, we need a tree structure that reflects the code's syntax hierarchy - like a family tree showing which code elements contain which other elements.

**Detailed Process**:

The extraction process begins by validating and parsing the CPG data structure:

```typescript
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
```

The CPG format uses JSON-LD style wrappers where values are wrapped in objects with `@value` keys. The extractor first validates this structure and extracts the edges and vertices (nodes) from the CPG.

**Filtering AST Edges**:

Not all edges in the CPG represent syntax tree relationships. The extractor filters for only AST edges:

```typescript
const astEdges = edges.filter((e) => e.label === "AST");
```

AST edges represent parent-child relationships in the abstract syntax tree. Other edge types (like data flow edges, control flow edges, etc.) are ignored at this stage.

**Building Node Dictionary**:

The extractor creates a dictionary mapping node IDs to node information for efficient lookup:

```typescript
const nodeDict: Record<string, NodeInfo> = {};
for (const n of nodes) {
  if (this.isValueWrapper(n.id) && (typeof n.id["@value"] === "string" || typeof n.id["@value"] === "number")) {
    const key = String(n.id["@value"]);
    nodeDict[key] = n as unknown as NodeInfo;
  }
}
```

This dictionary allows quick lookup of node information when processing edges.

**Processing AST Edges**:

For each AST edge, the extractor identifies the parent (outV) and child (inV) nodes:

```typescript
const astData: EdgeInfo[] = astEdges.map((edge) => {
  let outNode: NodeInfo | null = null;
  let inNode: NodeInfo | null = null;

  if (this.isValueWrapper(edge.outV)) {
    const outIdRaw = edge.outV["@value"];
    const outIdUnwrapped = this.unwrapValue(outIdRaw);
    const outIdStr = outIdUnwrapped !== undefined ? String(outIdUnwrapped) : "";
    outNode = nodeDict[outIdStr] ?? null;
  }
  // Similar processing for inV...
  return { edge, inV_node: inNode, outV_node: outNode };
});
```

**Building Parent-Child Maps**:

The extractor builds two key data structures:

- `nodeInfoMap`: Maps node IDs to their extracted information
- `childrenMap`: Maps parent node IDs to arrays of their child node IDs

```typescript
const nodeInfoMap: Record<string, NodeInfo> = {};
const childrenMap: Record<string, string[]> = {};

for (const item of astData) {
  const edge = item.edge;
  if (this.isValueWrapper(edge.outV) && this.isValueWrapper(edge.inV)) {
    const outId = String(this.unwrapValue(edge.outV["@value"]));
    const inId = String(this.unwrapValue(edge.inV["@value"]));

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
```

**Identifying Root Nodes**:

Root nodes are nodes that have no incoming AST edges (no parent in the syntax tree):

```typescript
const allIds = new Set<string>(Object.keys(nodeInfoMap));
const childIds = new Set<string>();
for (const childArr of Object.values(childrenMap)) {
  for (const cid of childArr) {
    childIds.add(cid);
  }
}
const rootIds = Array.from(allIds).filter((id) => !childIds.has(id));
```

**Building Trees Recursively**:

Starting from root nodes, the extractor recursively builds tree structures:

```typescript
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
```

**Result**: A collection of tree structures where each tree represents a top-level code element (like a function or file). Each tree maintains the hierarchical structure of the original code's syntax.

### Step 2: Node Conversion (TemplateConverter)

**What Happens**: Each node in the extracted tree is examined and converted from its CPG representation into a standardized template node type. This is where operators get normalized, types get inferred, and special cases get handled.

**Why This Is Needed**: CPG uses verbose, technical names for operators (like `<operator>.addition`). The converter translates these into standard symbols (like `+`) that are more readable and easier to match in patterns. It also handles complex cases like distinguishing between arrays, pointers, and regular variables.

**Main Conversion Entry Point**:

The converter processes trees using a dispatch pattern:

```typescript
public convertTree(nodes: TreeNode[]): TemplateNodes[] {
  const convertedNodes: TemplateNodes[] = [];
  for (const node of nodes) {
    const single = this.dispatchConvert(node);
    if (single !== undefined) {
      convertedNodes.push(single);
    }
  }
  return convertedNodes;
}
```

**Dispatch Pattern**:

The `dispatchConvert` method examines each node's label and routes it to the appropriate handler:

```typescript
private dispatchConvert(node: TreeNode): TemplateNodes | undefined {
  try {
    switch (node.label) {
      case "BINDING":
      case "DEPENDENCY":
      case "META_DATA":
      // ... other skipped node types
        return this.handleSkippedNodes(node);

      case "BLOCK":
        return this.handleBlock(node);
      case "CALL":
        return this.handleCall(node);
      case "CONTROL_STRUCTURE":
        return this.handleControlStructure(node);
      case "IDENTIFIER":
        return this.handleIdentifier(node);
      case "LOCAL":
        return this.handleLocal(node);
      case "METHOD":
        return this.handleMethod(node);
      // ... more cases

      default:
        return this.assertNever(node.label);
    }
  } catch (error) {
    // Error handling with detailed context
    throw new Error(
      `Conversion failed for node id=${node.id} label=${node.label} name=${node.name}: ${error.message}`
    );
  }
}
```

**Operator Conversion Example**:

When a CALL node represents an operator, it gets converted to a BinaryExpression or UnaryExpression:

```typescript
private handleCall(node: TreeNode): CallReturnTypes {
  if (node.name.startsWith("<operator>.")) {
    return this.handleCallOperators(node);
  }
  // ... handle function calls
}

private handleCallOperators(node: TreeNode): CallOperatorsReturnTypes {
  if (Object.keys(BinaryExpressionOperatorMap).includes(node.name)) {
    return {
      nodeType: TemplateNodeTypes.BinaryExpression,
      id: Number(node.id) || -999,
      operator: BinaryExpressionOperatorMap[node.name],  // Maps "<operator>.addition" to "+"
      type: BinaryUnaryTypeWrapper(node),  // Infers the result type
      children: this.convertedChildren(node.children),
    };
  }

  if (Object.keys(UnaryExpressionOperatorMap).includes(node.name)) {
    return {
      nodeType: TemplateNodeTypes.UnaryExpression,
      id: Number(node.id) || -999,
      operator: UnaryExpressionOperatorMap[node.name],  // Maps "<operator>.postIncrement" to "++"
      type: BinaryUnaryTypeWrapper(node),
      children: this.convertedChildren(node.children),
    };
  }
  // ... handle special operators
}
```

**Control Structure Conversion**:

Control structures are identified by their `CONTROL_STRUCTURE_TYPE` property:

```typescript
private handleControlStructure(node: TreeNode): IIfStatement | IWhileStatement | ... {
  const properties = node.properties as unknown as ControlStructureVertexProperties;
  const controlStructureType = properties.CONTROL_STRUCTURE_TYPE["@value"]["@value"][0];

  switch (controlStructureType) {
    case "IF": {
      if (node.children.length < 2) {
        throw new Error(`Control structure node ${node.id} has ${node.children.length} children, expected at least 2.`);
      }

      const conditionChild = this.dispatchConvert(node.children[0]);
      const ifTrueChild = this.dispatchConvert(node.children[1]);
      const elseBranch = node.children[2] ? this.dispatchConvert(node.children[2]) : undefined;
      const elseChild = elseBranch && Array.isArray(elseBranch.children) ? elseBranch.children[0] : undefined;

      const restructuredChildren = [];
      if (conditionChild) restructuredChildren.push(conditionChild);
      if (ifTrueChild) restructuredChildren.push(ifTrueChild);
      if (elseChild) restructuredChildren.push(elseChild);

      return {
        nodeType: TemplateNodeTypes.IfStatement,
        id: Number(node.id) || -999,
        children: restructuredChildren,
      };
    }
    case "WHILE": {
      return {
        nodeType: TemplateNodeTypes.WhileStatement,
        id: Number(node.id) || -999,
        children: this.convertedChildren(node.children),
      };
    }
    // ... other control structures
  }
}
```

**Variable Declaration Conversion**:

The converter analyzes variable types to determine if they're arrays, pointers, or regular variables:

```typescript
private handleLocal(node: TreeNode): IArrayDeclaration | IPointerDeclaration | IVariableDeclaration {
  const properties = node.properties as unknown as LocalVertexProperties;
  const typeFullName = properties.TYPE_FULL_NAME["@value"]["@value"].join("/") || "";

  // Check for array declaration
  if (typeFullName.includes("[") && typeFullName.includes("]")) {
    const elementType = typeFullName.split("[")[0];
    const fullRawType = typeFullName.split("[")[1].split("]")[0];
    const length = Number(fullRawType) || fullRawType;

    return {
      nodeType: TemplateNodeTypes.ArrayDeclaration,
      id: Number(node.id) || -999,
      name: node.name,
      elementType,
      length,
      storage,
      children: this.convertedChildren(node.children),
    };
  }

  // Check for pointer declaration
  if (typeFullName.includes("*")) {
    const level = typeFullName.split("*").length - 1;
    const pointsTo = typeFullName.replace("*", "");

    return {
      nodeType: TemplateNodeTypes.PointerDeclaration,
      id: Number(node.id) || -999,
      name: node.name,
      pointingType: pointsTo,
      level,
      storage,
      children: this.convertedChildren(node.children),
    };
  }

  // Regular variable declaration
  return {
    nodeType: TemplateNodeTypes.VariableDeclaration,
    id: Number(node.id) || -999,
    name: node.name,
    type: predefinedType ?? typeFullName,
    storage,
    children: this.convertedChildren(node.children),
  };
}
```

**Function Declaration vs. Definition**:

The converter distinguishes between function declarations (signature only) and function definitions (with body):

```typescript
private handleMethod(node: TreeNode): IFunctionDeclaration | IFunctionDefinition | undefined {
  const properties = node.properties as unknown as MethodVertexProperties;
  const firstBlock = node.children.find((child) => child.label === "BLOCK");

  // Check if this is a function at file scope
  if (
    properties.FILENAME["@value"]["@value"][0] + ":<global>" === properties.AST_PARENT_FULL_NAME["@value"]["@value"][0] &&
    !properties.IS_EXTERNAL["@value"]["@value"][0] &&
    properties.SIGNATURE["@value"]["@value"].join("/").length > 0
  ) {
    // Build parameter list
    const paramList: IParameterList = {
      nodeType: TemplateNodeTypes.ParameterList,
      id: randomIntWithLength(node.id.length + 3) || -999,
      children: node.children
        .filter((child) => child.label === "METHOD_PARAMETER_IN")
        .map((child) => this.dispatchConvert(child))
        .filter((child): child is IParameterDeclaration => child !== undefined),
    };

    // Determine if this is a declaration or definition
    return {
      nodeType: firstBlock && firstBlock.code === "<empty>"
        ? TemplateNodeTypes.FunctionDeclaration
        : TemplateNodeTypes.FunctionDefinition,
      id: Number(node.id) || -999,
      name: node.name,
      returnType: properties.SIGNATURE["@value"]["@value"].join("/").split("(")[0],
      children: [paramList, ...nonFuncParamChildren],
    };
  }
}
```

**Recursive Child Conversion**:

All handlers recursively convert their children:

```typescript
private convertedChildren(children: TreeNode[]): TemplateNodes[] {
  return children
    .map((child) => this.dispatchConvert(child))
    .filter((child): child is TemplateNodes => child !== undefined);
}
```

**Result**: A tree of template nodes with standardized representations that are easier to analyze and match against patterns. All operators are in familiar symbol form, types are normalized, and special cases are properly identified.

### Step 3: Post-Processing (PostProcessor)

**What Happens**: The converted template tree is cleaned up and enhanced with additional information. Invalid nodes are removed, related nodes are merged, and source code snippets are attached to nodes.

**Why This Is Needed**: The conversion process may create nodes that don't map perfectly, or CPG may represent certain constructs in ways that need cleanup. Additionally, adding source code to nodes helps with debugging and code generation.

**Removing Invalid Nodes**:

Some CPG nodes don't have a corresponding template type. These are removed, and their children are promoted:

```typescript
public removeInvalidNodes(nodes: TemplateNodes[]): TemplateNodes[] {
  return nodes.flatMap((node) => this.validateNode(node));
}

private validateNode(node: TemplateNodes): TemplateNodes[] {
  const nodeKeys = Object.keys(node);
  if (!nodeKeys.includes("nodeType")) {
    // Inline grandchildren - remove invalid node, keep its children
    return (node.children ?? []).flatMap((child) => this.validateNode(child));
  }
  // Otherwise, keep this node but recurse into its children
  const processedChildren = (node.children ?? []).flatMap((child) => this.validateNode(child));
  return [{
    ...node,
    children: processedChildren,
  }];
}
```

**Adding Code Properties**:

Each node is enriched with the actual source code snippet it represents:

```typescript
public addCodeProperties(nodes: TemplateNodes[], cpg: CPGRoot): TemplateNodes[] {
  return nodes.map((node) => {
    const vertex = cpg.export["@value"].vertices.find((v) => v.id["@value"] === node.id);
    const code: string | undefined =
      vertex &&
      "CODE" in vertex.properties &&
      typeof vertex.properties.CODE === "object" &&
      typeof vertex.properties.CODE["@value"] === "object" &&
      Array.isArray(vertex.properties.CODE["@value"]["@value"])
        ? vertex.properties.CODE["@value"]["@value"].join("")
        : undefined;

    return {
      ...node,
      code,
      children: node.children ? this.addCodeProperties(node.children, cpg) : [],
    };
  });
}
```

This recursively adds code properties to all nodes in the tree, enabling better debugging and understanding of what each node represents.

**Merging Array Allocations**:

Sometimes CPG represents array size allocation as a separate node from the array declaration. When these appear together and have matching sizes, they're merged:

```typescript
public mergeArraySizeAllocation(nodes: TemplateNodes[]): TemplateNodes[] {
  return nodes.map((node) => {
    if (!node.children) return node;

    const mergedChildren: TemplateNodes[] = [];

    for (let i = 0; i < node.children.length; i++) {
      const current = node.children[i];
      const next = node.children[i + 1];

      if (current.nodeType === TemplateNodeTypes.ArrayDeclaration &&
          next?.nodeType === TemplateNodeTypes.ArraySizeAllocation) {
        const arrayDecl = current;
        const arraySize = next;

        mergedChildren.push({
          ...arrayDecl,
          length: arrayDecl.length === arraySize.length
            ? arrayDecl.length
            : arraySize.length,
          children: [...(arrayDecl.children ?? []), ...(arraySize.children ?? [])],
        });

        i++; // skip next (ArraySizeAllocation)
      } else {
        mergedChildren.push({
          ...current,
          children: current.children
            ? this.mergeArraySizeAllocation(current.children)
            : current.children,
        });
      }
    }

    return {
      ...node,
      children: mergedChildren,
    };
  });
}
```

**Isolating Translation Units**:

The system identifies and extracts file-level nodes (translation units):

```typescript
public isolateTranslationUnit(nodes: TemplateNodes[]): TemplateNodes[] {
  const tu = nodes.filter((node) => node.nodeType === TemplateNodeTypes.TranslationUnit);
  if (tu.length === 0) {
    throw new Error("No TranslationUnit node found in the provided AST");
  }
  return tu;
}
```

**Result**: A cleaned, enhanced template tree ready for flattening or further analysis. All nodes have code properties, invalid nodes are removed, and related nodes are merged for better representation.

### Step 4: Flattening (PlanationTool)

**What Happens**: The hierarchical tree structure is converted into a flat graph representation. Instead of nested children, the structure becomes a list of nodes and a list of edges connecting them.

**Why This Is Needed**: Many analysis algorithms work better with flat graph structures than with nested trees. A flat representation also makes it easier to traverse the code structure and perform pattern matching.

**Flattening Process**:

The flattening tool processes each root node separately:

```typescript
public flatten(astRoots: TemplateNodes[], removeBlackList = false): TemplateFlattenedGraph[] {
  const graphs: TemplateFlattenedGraph[] = [];

  for (const root of astRoots) {
    this.reset();
    this.traverse(root);

    // Sort nodes by ascending id
    this.nodes.sort((a, b) => a.id - b.id);
    // Sort edges by ascending sum of from+to
    this.edges.sort((e1, e2) => e1.from + e1.to - (e2.from + e2.to));

    // Validate that every edge references existing node ids
    this.validateEdges();

    graphs.push({
      edges: this.edges.slice(),
      nodes: this.nodes.slice(),
    });
  }

  if (removeBlackList) {
    // Filter out blacklisted nodes
    for (const graph of graphs) {
      graph.nodes = graph.nodes.filter((node) => !this.blacklist.has(node.nodeType));
      graph.edges = graph.edges.filter((edge) =>
        graph.nodes.some((n) => n.id === edge.from) &&
        graph.nodes.some((n) => n.id === edge.to)
      );
    }
  }

  return graphs;
}
```

**Recursive Traversal**:

The tool recursively traverses the tree, creating nodes and edges:

```typescript
private traverse(node: TemplateNodes & { children?: TemplateNodes[] }): number {
  // Clone node minus its children, attach id
  const { children, ...rest } = node;
  const clone: TemplateNodes & { id: number } = { ...(rest as TemplateNodes), id: node.id };
  this.nodes.push(clone);

  if (Array.isArray(children)) {
    for (const child of children) {
      const childId = this.traverse(child);
      this.edges.push({ from: clone.id, to: childId });
    }
  }

  return clone.id;
}
```

**Edge Validation**:

Before returning, the tool validates that all edges reference existing nodes:

```typescript
private validateEdges(): void {
  const existingIds = new Set(this.nodes.map((n) => n.id));
  for (const { from, to } of this.edges) {
    if (!existingIds.has(from)) {
      throw new Error(`Edge refers to unknown source node id ${from}`);
    }
    if (!existingIds.has(to)) {
      throw new Error(`Edge refers to unknown target node id ${to}`);
    }
  }
}
```

**Result**: A flat graph structure with nodes and edges that can be efficiently processed by analysis algorithms. The hierarchical structure is preserved through explicit edges, but the representation is flat for easier traversal.

### Complete Flow Summary

When `generateTemplate()` is called from an endpoint:

```text
1. CPG Data arrives
   ↓
2. TemplateExtractor extracts tree structures
   → Filters AST edges from CPG graph
   → Builds parent-child maps
   → Identifies root nodes
   → Recursively constructs hierarchical trees
   ↓
3. TemplateConverter converts each node
   → Dispatches based on node label
   → Normalizes operators (e.g., "<operator>.addition" → "+")
   → Infers types using multiple strategies
   → Handles special cases (arrays, pointers, control structures)
   → Recursively converts children
   → Creates standardized template nodes
   ↓
4. PostProcessor cleans and enhances
   → Removes invalid nodes (promotes their children)
   → Adds source code snippets from CPG
   → Merges related nodes (e.g., array declarations with allocations)
   → Isolates translation units
   ↓
5. PlanationTool flattens to graph
   → Recursively traverses tree
   → Assigns unique numeric IDs
   → Creates explicit edges for parent-child relationships
   → Validates edge references
   → Sorts nodes and edges for deterministic output
   → Optionally filters blacklisted node types
   ↓
6. Returns template nodes and flattened graphs
```

---

## Component Responsibilities

This section provides detailed explanations of each component's role, implementation approach, and key methods.

### TemplateExtractor

**Primary Role**: Reconstructs tree structures from CPG graph data.

**Key Responsibility**: The CPG format stores code relationships as edges in a graph, but template analysis needs hierarchical tree structures. The extractor identifies which edges represent parent-child relationships in the syntax tree and rebuilds the tree structure from these relationships.

**How It Works**:

The extractor uses a multi-phase approach:

1. **Validation and Parsing**: Validates the CPG structure and extracts edges and vertices
2. **Edge Filtering**: Filters for AST edges only (ignoring data flow, control flow, etc.)
3. **Dictionary Building**: Creates efficient lookup structures for nodes
4. **Relationship Mapping**: Builds parent-child maps from AST edges
5. **Root Identification**: Finds nodes with no incoming AST edges
6. **Tree Construction**: Recursively builds trees from root nodes

**Key Methods**:

- `getTemplateTree(cpg: unknown): TreeNode[]` - Main entry point that orchestrates the extraction process
- `extractNodeInfo(node: NodeInfo | null): NodeInfo` - Extracts and unwraps node information from CPG format
- `unwrapValue(x: unknown): number | string | undefined` - Recursively unwraps JSON-LD `@value` wrappers
- `isValueWrapper(x: unknown): boolean` - Type guard for JSON-LD value wrappers

**Value Unwrapping**:

CPG uses JSON-LD format where values are wrapped in objects. The extractor must handle nested wrappers:

```typescript
private unwrapValue(x: unknown): number | string | undefined {
  if (x == null) return undefined;

  if (typeof x === "string" || typeof x === "number") {
    return x;
  }

  if (this.isValueWrapper(x)) {
    const inner = x["@value"];

    if (typeof inner === "string" || typeof inner === "number") {
      return inner;
    }

    if (this.isValueWrapper(inner)) {
      return this.unwrapValue(inner["@value"]);  // Recursive unwrapping
    }

    if (Array.isArray(inner)) {
      return this.unwrapValue(inner);  // Handle arrays
    }
  }

  if (Array.isArray(x)) {
    for (const elem of x) {
      const unwrapped = this.unwrapValue(elem);
      if (unwrapped !== undefined) {
        return unwrapped;
      }
    }
  }

  return undefined;
}
```

**Rationale**: The CPG format stores relationships as edges rather than hierarchical structures. This component reconstructs the tree structure by filtering AST edges (which represent parent-child relationships), building bidirectional maps for efficient lookup, identifying roots (nodes without incoming AST edges), and recursively building trees from roots downward.

### TemplateConverter

**Primary Role**: Translates CPG node types into standardized template node types.

**Key Responsibility**: CPG uses technical, verbose representations that need to be normalized. The converter handles this translation, ensuring operators are in standard form, types are properly inferred, and special cases are correctly identified.

**How It Works**:

The converter uses a dispatch pattern with specialized handlers:

1. **Dispatch**: Examines each node's label and routes to appropriate handler
2. **Conversion**: Handler applies conversion rules, operator mappings, and type inference
3. **Recursion**: Recursively converts children nodes
4. **Error Handling**: Provides detailed error context when conversion fails

**Key Methods**:

- `convertTree(nodes: TreeNode[]): TemplateNodes[]` - Main entry point for tree conversion
- `dispatchConvert(node: TreeNode): TemplateNodes | undefined` - Routes nodes to appropriate handlers
- `handleCall(node: TreeNode): CallReturnTypes` - Handles function calls and operators
- `handleControlStructure(node: TreeNode): ...` - Handles if, while, for, switch, etc.
- `handleLocal(node: TreeNode): ...` - Handles variable declarations (arrays, pointers, regular)
- `handleMethod(node: TreeNode): ...` - Handles function declarations and definitions
- `handleIdentifier(node: TreeNode): ...` - Handles identifiers, literals, and pointer dereferences

**Configuration Dependencies**: The converter relies on configuration files that map CPG operators to standard symbols and identify standard library functions. These mappings are maintained separately to make the system easy to extend.

**Type Inference Integration**:

The converter uses `BinaryUnaryTypeWrapper` for type inference:

```typescript
if (Object.keys(BinaryExpressionOperatorMap).includes(node.name)) {
  return {
    nodeType: TemplateNodeTypes.BinaryExpression,
    id: Number(node.id) || -999,
    operator: BinaryExpressionOperatorMap[node.name],
    type: BinaryUnaryTypeWrapper(node), // Type inference here
    children: this.convertedChildren(node.children),
  };
}
```

**Special Operator Handling**:

Some operators require special handling beyond simple mapping:

```typescript
case "<operator>.assignment": {
  if (node.children.length !== 2) {
    throw new Error(`Call node ${node.id} has ${node.children.length} children, expected 2.`);
  }
  const allocChild = node.children.filter((child) => child.name === "<operator>.alloc");

  if (allocChild.length === 1) {
    // This is an array size allocation
    const typeFullName = properties.TYPE_FULL_NAME["@value"]["@value"].join("/");
    const rawSizeMatch = /\[(\d+)\]/.exec(typeFullName);
    const fullRawType = rawSizeMatch ? rawSizeMatch[1] : undefined;
    const length: number | string = fullRawType !== undefined
      ? Number(fullRawType) || fullRawType
      : typeFullName;

    return {
      nodeType: TemplateNodeTypes.ArraySizeAllocation,
      id: Number(node.id) || -999,
      length,
      children: this.convertedChildren(node.children),
    };
  }

  // Regular assignment
  return {
    nodeType: TemplateNodeTypes.AssignmentExpression,
    id: Number(node.id) || -999,
    operator: "=",
    children: this.convertedChildren(node.children),
  };
}
```

**Rationale**: The converter normalizes operators (converting verbose CPG names to standard symbols), infers types using multiple strategies, and classifies calls (distinguishing standard library calls from user-defined calls). This normalization is critical for accurate template matching and analysis.

### PostProcessor

**Primary Role**: Cleans up and enriches the template tree after conversion.

**Key Responsibility**: The conversion process may produce imperfect results or miss certain enhancements. The post-processor fixes these issues and adds valuable information like source code snippets.

**How It Works**:

The post-processor performs multiple passes over the tree:

1. **Invalid Node Removal**: Removes nodes without proper nodeType, promoting their children
2. **Code Property Addition**: Enriches nodes with source code snippets from CPG
3. **Node Merging**: Merges related nodes (e.g., array declarations with allocations)
4. **Translation Unit Isolation**: Extracts file-level nodes

**Key Methods**:

- `removeInvalidNodes(nodes: TemplateNodes[]): TemplateNodes[]` - Removes invalid nodes and promotes children
- `addCodeProperties(nodes: TemplateNodes[], cpg: CPGRoot): TemplateNodes[]` - Adds source code to nodes
- `mergeArraySizeAllocation(nodes: TemplateNodes[]): TemplateNodes[]` - Merges array declarations with allocations
- `isolateTranslationUnit(nodes: TemplateNodes[]): TemplateNodes[]` - Extracts file-level nodes
- `validateNode(node: TemplateNodes): TemplateNodes[]` - Validates and processes individual nodes

**Rationale**: The post-processor adds code properties (enabling better debugging and code generation), merges array allocations (creating more intuitive representations), removes invalid nodes (preventing downstream errors), and isolates translation units (providing clean entry points for analysis).

### PlanationTool

**Primary Role**: Converts hierarchical trees into flat graph structures.

**Key Responsibility**: While trees are intuitive for representing code structure, many analysis algorithms work better with flat graphs. The flattening tool bridges this gap.

**How It Works**:

The tool recursively traverses the tree:

1. **Traversal**: Recursively visits all nodes in the tree
2. **Node Creation**: Creates flat node entries with unique IDs
3. **Edge Creation**: Creates explicit edges for parent-child relationships
4. **Validation**: Ensures all edges reference existing nodes
5. **Sorting**: Sorts nodes and edges for deterministic output
6. **Filtering**: Optionally filters blacklisted node types

**Key Methods**:

- `flatten(astRoots: TemplateNodes[], removeBlackList = false): TemplateFlattenedGraph[]` - Main entry point
- `traverse(node: TemplateNodes): number` - Recursively traverses tree and creates nodes/edges
- `validateEdges(): void` - Validates that all edges reference existing nodes
- `reset(): void` - Resets internal state for processing new root

**Blacklist Support**:

The tool can filter out specific node types:

```typescript
const planationTool = new PlanationTool([
  TemplateNodeTypes.VariableDeclaration,
  TemplateNodeTypes.ArrayDeclaration,
  TemplateNodeTypes.PointerDeclaration,
  // ... more node types to filter
]);
```

When `removeBlackList` is true, these node types are filtered from the output.

**Rationale**: The flattening step enables graph analysis (many algorithms work better on flat structures), ID-based references (using numeric IDs enables efficient graph traversal), deterministic ordering (sorting ensures consistent output), and blacklist support (allows filtering of specific node types).

### BinaryUnaryTypeWrapper

**Primary Role**: Infers type information for expressions when explicit types aren't available.

**Key Responsibility**: Type information is crucial for accurate analysis, but CPG doesn't always provide explicit types. This utility infers types using multiple strategies.

**How It Works**:

The wrapper uses a multi-strategy approach with fallbacks:

```typescript
export function BinaryUnaryTypeWrapper(node: TreeNode): string {
  // 1) boolean-map override
  const boolType = BinaryExpressionBooleanMap[node.name];
  if (boolType) {
    return boolType;
  }

  // 2) trust TYPE_FULL_NAME shape
  const props = node.properties as unknown as CallVertexProperties;
  const rawList = props.TYPE_FULL_NAME["@value"]["@value"];
  if (rawList.length > 0) {
    return rawList.join("/");
  }

  // 3) infer from children
  const childrenTypes = node.children.map(inferTypeBottomUp);
  const unique = new Set(childrenTypes);
  if (unique.size === 1) {
    return [...unique][0];
  }

  // 4) give up
  return "<unknown>";
}
```

**Bottom-Up Type Inference**:

When explicit types aren't available, the wrapper infers types from children:

```typescript
export function inferTypeBottomUp(node: TreeNode): string {
  if (node.children.length === 0) {
    return "unknown";
  }
  const childTypes = node.children.map(inferTypeBottomUp);
  const unique = Array.from(new Set(childTypes));
  if (unique.length === 1) {
    return unique[0]; // All children have same type
  }
  return `(${unique.join(" ")})`; // Mixed types
}
```

**Rationale**: The multi-strategy approach maximizes accuracy (uses best available information), handles edge cases (boolean operators are handled explicitly), and provides graceful degradation (falls back to "unknown" rather than failing).

---

## Data Transformations

This section provides detailed examples of how data is transformed at each stage of the pipeline.

### CPG Format → Tree Structure

The CPG format represents code as a graph with nodes and edges. The extractor transforms this into a hierarchical tree structure.

**CPG Input Example**:

```json
{
  "@value": {
    "vertices": [
      {
        "id": { "@value": 1 },
        "label": "METHOD",
        "properties": {
          "NAME": { "@value": { "@value": ["main"] } },
          "CODE": { "@value": { "@value": ["int main() { ... }"] } }
        }
      },
      {
        "id": { "@value": 2 },
        "label": "BLOCK",
        "properties": { ... }
      }
    ],
    "edges": [
      {
        "label": "AST",
        "outV": { "@value": 1 },
        "inV": { "@value": 2 }
      }
    ]
  }
}
```

**Tree Output Example**:

```typescript
{
  id: "1",
  label: "METHOD",
  name: "main",
  code: "int main() { ... }",
  properties: { ... },
  children: [
    {
      id: "2",
      label: "BLOCK",
      name: "",
      code: "",
      properties: { ... },
      children: []
    }
  ]
}
```

**Transformation Process**:

- The extractor identifies AST edges (which represent syntax parent-child relationships)
- It builds parent-child maps from these edges
- It starts from root nodes and recursively builds trees
- Example: If CPG has edges showing that a function node contains a variable declaration node, the extractor builds a tree where the function is the parent and the variable is its child

### Tree Nodes → Template Nodes

CPG nodes have technical labels and properties. The converter transforms these into standardized template nodes.

**Before (CPG TreeNode)**:

```typescript
{
  id: "100",
  label: "CALL",
  name: "<operator>.addition",
  code: "a + b",
  properties: {
    TYPE_FULL_NAME: { "@value": { "@value": ["int"] } }
  },
  children: [...]
}
```

**After (Template Node)**:

```typescript
{
  nodeType: "BinaryExpression",
  id: 100,
  operator: "+",
  type: "int",
  children: [...]
}
```

**Key Transformations**:

- **Operators**: `<operator>.addition` → `+`
- **Types**: Extracted from `TYPE_FULL_NAME` property
- **Node Types**: `CALL` with operator name → `BinaryExpression`
- **Structure**: Maintains hierarchical children relationships

### Template Tree → Flat Graph

The hierarchical tree structure gets flattened into a graph with explicit nodes and edges.

**Before (Hierarchical Tree)**:

```typescript
{
  nodeType: "FunctionDefinition",
  id: 1,
  children: [
    {
      nodeType: "CompoundStatement",
      id: 2,
      children: [
        {
          nodeType: "BinaryExpression",
          id: 3,
          children: [...]
        }
      ]
    }
  ]
}
```

**After (Flat Graph)**:

```typescript
{
  nodes: [
    { nodeType: "FunctionDefinition", id: 1, ... },
    { nodeType: "CompoundStatement", id: 2, ... },
    { nodeType: "BinaryExpression", id: 3, ... }
  ],
  edges: [
    { from: 1, to: 2 },
    { from: 2, to: 3 }
  ]
}
```

**Transformation Process**:

- The flattening tool recursively traverses the tree
- Each node is added to a flat nodes array
- Parent-child relationships become explicit edges
- The hierarchical structure is preserved through edges, but the representation is flat

---

## Design Rationale

This section explains the reasoning behind key design decisions in the template module.

### Why Separate Components?

The template transformation is broken into distinct components, each with a single responsibility. This design provides several benefits:

- **Maintainability**: Each component can be modified independently without affecting others
- **Testability**: Each stage can be tested in isolation
- **Clarity**: The purpose of each component is clear and focused
- **Debugging**: When issues arise, it's easier to identify which stage is causing problems

**Example**: If operator conversion logic needs to change, only the TemplateConverter needs modification. The extractor and post-processor remain unaffected.

### Why Configuration Files?

Operator mappings and standard library function lists are stored in separate configuration files rather than hard-coded in the converter. This approach:

- **Enables Extension**: New operators or functions can be added by updating configuration files
- **Centralizes Maintenance**: All mappings are in one place, making updates easier
- **Improves Readability**: The converter code focuses on logic rather than long lists of mappings

**Example**: Adding support for a new operator only requires updating `BinaryExpression.ts`:

```typescript
export const BinaryExpressionOperatorMap: Record<string, string> = {
  "<operator>.addition": "+",
  "<operator>.subtraction": "-",
  // ... existing operators
  "<operator>.newOperator": "newSymbol", // Just add this line
};
```

### Why Recursive Processing?

All components use recursive algorithms to process tree structures. This approach:

- **Handles Arbitrary Depth**: Code can be nested to any depth, and recursion naturally handles this
- **Maintains Relationships**: Parent-child relationships are preserved naturally through recursive calls
- **Efficiency**: Single-pass processing is possible with recursion

**Example**: A deeply nested expression like `a + (b * (c - d))` is processed naturally through recursive traversal, maintaining the nesting structure.

### Why Type Inference?

Type information is critical for accurate analysis, but CPG doesn't always provide explicit types. The multi-strategy type inference approach:

- **Maximizes Accuracy**: Uses the best available information (hard-coded rules, explicit types, or inference)
- **Handles Edge Cases**: Special cases like boolean operators are handled explicitly
- **Graceful Degradation**: Falls back to "unknown" rather than failing when type information isn't available

**Example**: Comparison operators always return boolean, regardless of operand types. The boolean map handles this explicitly:

```typescript
export const BinaryExpressionBooleanMap: Record<string, string> = {
  "<operator>.equals": "boolean",
  "<operator>.notEquals": "boolean",
  "<operator>.lessThan": "boolean",
  // ...
};
```

### Why Flattening?

The flattening step converts trees to graphs, which may seem counterintuitive. However:

- **Analysis Algorithms**: Many graph analysis algorithms work better on flat structures
- **Pattern Matching**: Flat structures with explicit edges are easier to match against patterns
- **Efficiency**: Graph traversal can be more efficient than tree traversal for certain operations
- **Flexibility**: Graph structures can represent relationships that don't fit tree hierarchies

**Example**: Pattern matching for security vulnerabilities often needs to traverse relationships that don't follow the syntax tree structure. A flat graph with explicit edges enables this.

---

## Configuration

The template module relies on several configuration files that define mappings and registries. These files are critical for the conversion process and are designed to be easily extensible.

### Binary Expression Operators (`config/BinaryExpression.ts`)

Maps CPG binary operator names to standard mathematical symbols:

```typescript
export const BinaryExpressionOperatorMap: Record<string, string> = {
  "<operator>.addition": "+",
  "<operator>.subtraction": "-",
  "<operator>.multiplication": "*",
  "<operator>.division": "/",
  "<operator>.modulo": "%",
  "<operator>.shiftLeft": "<<",
  "<operator>.arithmeticShiftRight": ">>",
  "<operator>.and": "&",
  "<operator>.or": "|",
  "<operator>.xor": "^",
  "<operator>.logicalAnd": "&&",
  "<operator>.logicalOr": "||",
  "<operator>.equals": "==",
  "<operator>.notEquals": "!=",
  "<operator>.lessThan": "<",
  "<operator>.lessEqualsThan": "<=",
  "<operator>.greaterThan": ">",
  "<operator>.greaterEqualsThan": ">=",
  "<operator>.assignmentPlus": "+=",
  "<operator>.assignmentMinus": "-=",
  "<operator>.assignmentMultiplication": "*=",
  "<operator>.assignmentDivision": "/=",
  "<operator>.pointerCall": "()",
  "<operator>.conditional": "?:",
  "<operator>.op_ellipses": "...",
};
```

Also includes mappings for operators that always return boolean types:

```typescript
export const BinaryExpressionBooleanMap: Record<string, string> = {
  "<operator>.equals": "boolean",
  "<operator>.notEquals": "boolean",
  "<operator>.lessThan": "boolean",
  "<operator>.lessEqualsThan": "boolean",
  "<operator>.greaterThan": "boolean",
  "<operator>.greaterEqualsThan": "boolean",
  "<operator>.logicalAnd": "boolean",
  "<operator>.logicalOr": "boolean",
};
```

### Unary Expression Operators (`config/UnaryExpression.ts`)

Maps CPG unary operator names to standard symbols:

```typescript
export const UnaryExpressionOperatorMap: Record<string, string> = {
  "<operator>.postIncrement": "++",
  "<operator>.preIncrement": "++",
  "<operator>.postDecrement": "--",
  "<operator>.preDecrement": "--",
  "<operator>.plus": "+",
  "<operator>.minus": "-",
  "<operator>.logicalNot": "!",
  "<operator>.not": "~",
  "<operator>.indirection": "*",
  "<operator>.new": "new",
  "<operator>.delete": "delete",
  "<operator>.alloc": "alloc",
  "<operator>.arrayInitializer": "{}",
};
```

### Predefined Types (`config/Predefined.ts`)

Maps standard C/C++ identifiers to their known types:

```typescript
export const PredefinedIdentifierTypes = {
  stdin: "FILE*",
  stdout: "FILE*",
  stderr: "FILE*",
  errno: "int",
  EOF: "int",
  NULL: "void*",
  FILENAME_MAX: "int",
};
```

Also lists identifiers that should be treated as literals rather than variables:

```typescript
export const IdentifierToLiteralMap: string[] = ["NULL"];
```

### Standard Library Calls (`config/StandardLibCall.ts`)

Comprehensive registry of standard library functions from:

- C standard library (e.g., `malloc`, `strcpy`, `printf`)
- POSIX functions (e.g., `socket`, `bind`, `recv`)
- C++ STL methods (e.g., `push_back`, `insert`)
- Security-relevant functions (extensive list for vulnerability analysis)

This registry is used to distinguish standard library calls from user-defined function calls, enabling different handling strategies for each type. The registry contains hundreds of functions organized by category.

---

## Integration with Endpoint

When the analysis endpoint is called, the template module is invoked through the `generateTemplate()` function. This section explains how the module integrates with the broader analysis pipeline.

### Function Signature

```typescript
export function generateTemplate(cpg: CPGRoot): TemplateNodes[] {
  validateCPGRoot([cpg.export]);
  const artifacts = buildTemplateArtifacts(cpg);
  return artifacts.templateResult;
}
```

### Integration Flow

1. **CPG Generation**: Source code is first converted to CPG format (handled by CPGGenerator)
2. **Template Generation**: CPG is passed to `generateTemplate()`, which orchestrates the template transformation
3. **Validation**: CPG data is validated before processing
4. **Artifact Building**: `buildTemplateArtifacts()` creates all template-related artifacts
5. **Return**: Template nodes are returned for use in subsequent analysis steps

### Usage in Analysis Pipeline

The template nodes are then used by subsequent analysis steps:

- **AST Generation**: Templates are passed to Python-based AST extractors for further processing
- **DFG Generation**: Templates are combined with CPG data to build data flow graphs
- **Pattern Matching**: Templates are matched against security patterns and vulnerability signatures

### Artifacts Produced

The `buildTemplateArtifacts()` function produces multiple artifacts:

- **template**: Raw TreeNode structures extracted from CPG
- **templateResult**: Converted and processed TemplateNodes
- **textLines**: Text representation of templates (for debugging/display)
- **flatten**: Flattened graph representations

### Error Handling

The endpoint uses a `withContext()` wrapper to provide detailed error messages:

```typescript
function withContext<T>(fnName: string, fn: () => T): T {
  try {
    return fn();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`${fnName} failed: ${msg}`);
  }
}
```

This ensures that when errors occur, it's clear which stage of the transformation failed.

### Validation

Before flattening, the system validates that there are no duplicate node IDs:

```typescript
const flattenIds = collectIdsFromFlatten(flatten[0]);
const flattenUniqueIds = new Set(flattenIds);
if (flattenIds.length !== flattenUniqueIds.size) {
  const duplicates = flattenIds.filter((id, idx) => flattenIds.indexOf(id) !== idx);
  throw new Error(`Duplicate node ids found in flattened template: ${[...new Set(duplicates)].join(", ")}`);
}
```

The template format serves as a common intermediate representation that enables these various analysis tasks to work with a consistent, normalized code structure.

---

## Error Handling and Edge Cases

The template module includes comprehensive error handling and edge case management to ensure robust operation.

### Error Context

When conversion fails, detailed context is provided:

```typescript
catch (error) {
  const lines: string[] = [
    `Error converting node:`,
    `  • id:      ${node.id}`,
    `  • label:   ${node.label}`,
    `  • name:    ${node.name}`,
    ``,
    `Original error message:`,
    `  ${error instanceof Error ? error.message : String(error)}`,
    ``,
    `Stack trace:`,
    error instanceof Error && error.stack ? error.stack : "n/a",
  ];
  console.error(lines.join("\n"));
  throw new Error(
    `Conversion failed for node id=${node.id} label=${node.label} name=${node.name}: ${error.message}`
  );
}
```

### Validation Checks

The module includes multiple validation checks:

1. **Edge Validation**: Ensures all edges reference existing nodes
2. **ID Uniqueness**: Validates no duplicate IDs in flattened graphs
3. **Node Structure**: Validates node structure before processing
4. **Required Properties**: Checks for required properties before access

### Edge Cases Handled

**Missing Type Information**:

When type information is missing, the system gracefully degrades:

```typescript
// Falls back to "unknown" if type inference fails
return "<unknown>";
```

**Invalid Node Types**:

Invalid nodes are removed and their children are promoted:

```typescript
if (!nodeKeys.includes("nodeType")) {
  // Inline grandchildren
  return (node.children ?? []).flatMap((child) => this.validateNode(child));
}
```

**Empty Children Arrays**:

Empty children arrays are handled consistently:

```typescript
children: node.children ? this.addCodeProperties(node.children, cpg) : [],
```

**Missing Translation Units**:

If no translation unit is found, an error is thrown with a clear message:

```typescript
if (tu.length === 0) {
  throw new Error("No TranslationUnit node found in the provided AST");
}
```

**Nested Value Wrappers**:

The unwrapper handles deeply nested JSON-LD wrappers:

```typescript
if (this.isValueWrapper(inner)) {
  return this.unwrapValue(inner["@value"]); // Recursive unwrapping
}
```

### Graceful Degradation

The module is designed to handle incomplete or malformed CPG data:

- Missing properties default to empty strings or undefined
- Invalid nodes are removed rather than causing failures
- Type inference provides fallbacks when explicit types aren't available
- Edge validation prevents invalid graph structures

This robust error handling ensures the template module can process a wide variety of CPG inputs while providing clear feedback when issues occur.

---

## Conclusion

The Template module serves as a critical transformation layer in the static software analysis pipeline, converting complex CPG representations into normalized, standardized template formats. Through its four-stage pipeline (extraction, conversion, post-processing, and flattening), it enables effective pattern matching, security analysis, and code generation.

The module's design emphasizes separation of concerns, configuration-driven mappings, and robust error handling, making it maintainable, extensible, and reliable. By providing a consistent intermediate representation, it enables various analysis tasks to work with a unified, normalized code structure.
