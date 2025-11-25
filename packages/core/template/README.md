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

- **Verbose Representations**: CPG uses technical names like `<operator>.addition` instead of simple symbols like `+`. This verbosity makes pattern matching difficult because analysts must write patterns using CPG's technical terminology rather than familiar programming symbols. The template module normalizes these to standard mathematical and logical operators that match how developers think about code.

- **Graph Structure**: CPG stores relationships as edges in a graph, but many analysis algorithms need hierarchical tree structures. While graphs are powerful for representing complex relationships, tree structures better match the syntactic structure of code and are more intuitive for pattern matching. The template module reconstructs the hierarchical syntax tree from the graph representation.

- **Inconsistent Formats**: Different code constructs may be represented in different ways in CPG. For example, array declarations might be represented differently depending on whether they're initialized or not, or whether they're function parameters versus local variables. The template module ensures consistent representation regardless of how CPG originally encoded the construct.

- **Missing Information**: Some information needed for analysis may be implicit or require inference. CPG might not always provide explicit type information for expressions, or might represent certain constructs in ways that require additional processing to extract meaningful information. The template module uses multiple inference strategies to fill these gaps.

The Template module addresses these challenges by providing a standardized, normalized representation that:

- Uses familiar operator symbols and standard programming terminology, making patterns more readable and maintainable
- Provides hierarchical tree structures that match code syntax, enabling intuitive traversal and pattern matching
- Ensures consistent representation of similar constructs, reducing the complexity of pattern definitions
- Infers missing information using multiple strategies, maximizing the accuracy of analysis even when CPG data is incomplete

### What the Module Does

When an endpoint is called to analyze code, the Template module performs a series of transformations:

1. **Extracts** the abstract syntax tree structure from the CPG data - The CPG format represents code as a graph with various edge types (AST, data flow, control flow, etc.). The extraction phase filters for AST edges only and reconstructs the hierarchical tree structure that represents the code's syntax.

2. **Converts** CPG nodes into standardized template node types - Each CPG node type (CALL, LOCAL, METHOD, etc.) is examined and converted into a corresponding template node type with normalized properties. This includes translating verbose operator names to standard symbols and inferring type information.

3. **Normalizes** operators, types, and control structures to consistent formats - Operators like `<operator>.addition` become `+`, types are extracted and standardized, and control structures are consistently represented regardless of how CPG encoded them.

4. **Enhances** the template with additional information like source code snippets - The original source code is attached to each node, enabling better debugging, code generation, and understanding of what each node represents.

5. **Flattens** the hierarchical tree structure into a graph format for analysis - While trees are intuitive, many analysis algorithms work better with flat graph structures. The flattening step converts the nested tree into a flat list of nodes with explicit edges, preserving the hierarchical relationships while enabling efficient graph-based analysis.

This transformation enables the system to perform pattern matching, security analysis, and code generation tasks more effectively. The normalized format reduces the complexity of writing analysis patterns, while the consistent structure ensures reliable matching across different code styles and CPG representations.

---

## Execution Flow

When an endpoint is called to generate templates from CPG data, the following sequence of operations occurs. This section provides a detailed walkthrough of each step in the transformation pipeline, explaining not just what happens, but why each step is necessary and how it contributes to the overall transformation goal.

### Entry Point: buildTemplateArtifacts()

The template transformation process begins when the `buildTemplateArtifacts()` function is called from the endpoint. This function serves as the orchestration layer that coordinates all template module components in a specific sequence. The orchestration is intentional - each step depends on the output of the previous step, and the order matters.

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

The function creates instances of four main components: TemplateExtractor, TemplateConverter, PostProcessor, and PlanationTool. Each component is responsible for a specific transformation phase, and they are chained together to form a complete pipeline. The function returns multiple artifacts: the raw extracted tree structure, the converted template nodes, flattened graph representations, and text representations for debugging.

This design allows downstream consumers to choose which representation they need. Some analysis tasks work better with hierarchical trees, while others require flat graphs. By producing both, the module supports diverse analysis needs without requiring multiple passes over the data.

### Step 1: Tree Extraction (TemplateExtractor)

**What Happens**: The system receives CPG data in a graph format where relationships are stored as edges between nodes. The TemplateExtractor component reconstructs the hierarchical tree structure that represents the code's syntax.

**Why This Is Needed**: CPG stores information as a graph (nodes connected by edges), but for template analysis, we need a tree structure that reflects the code's syntax hierarchy - like a family tree showing which code elements contain which other elements. The graph representation is powerful for representing complex relationships (data flow, control flow, call relationships), but the syntax tree structure is what we need for pattern matching and template-based analysis. Trees are more intuitive for representing code structure because they naturally reflect the nested nature of programming constructs - functions contain statements, statements contain expressions, expressions contain sub-expressions, and so on.

**Detailed Process**:

The extraction process is a multi-phase operation that transforms a graph into a tree. The main entry point is the `getTemplateTree()` method:

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
  // ... rest of extraction logic
}
```

The process begins with validation and parsing of the CPG data structure. The CPG format uses JSON-LD style wrappers where values are wrapped in objects with `@value` keys. This wrapping can be nested multiple levels deep, requiring careful unwrapping. The extractor first validates that the input has the expected structure - checking for the presence of the `@value` wrapper, ensuring edges and vertices arrays exist, and handling cases where the structure might be malformed or incomplete.

**Filtering AST Edges**: The CPG graph contains many different types of edges representing different relationships: AST edges (syntax tree parent-child relationships), data flow edges (how data moves through the program), control flow edges (execution order), call edges (function call relationships), and more. For tree extraction, we only care about AST edges because they represent the syntactic containment relationships - which code elements are nested inside which other elements. Filtering to AST edges only is crucial because including other edge types would create cycles and invalid tree structures. For example, a data flow edge might connect a variable declaration to a use of that variable later in the code, but that's not a parent-child relationship in the syntax tree.

**Building Node Dictionary**: To efficiently process edges, the extractor first builds a dictionary that maps node IDs to their full node information. This dictionary enables O(1) lookup when processing edges, rather than searching through the entire nodes array for each edge. The dictionary building process must handle the JSON-LD wrapping format, unwrapping node IDs from their `@value` wrappers to create string keys. This phase also serves as a validation step - nodes with invalid or missing IDs are filtered out at this stage.

**Processing AST Edges**: For each AST edge, the extractor identifies the parent node (outV - the node the edge originates from) and the child node (inV - the node the edge points to). This requires unwrapping the edge's endpoint IDs from their JSON-LD wrappers and looking them up in the node dictionary. The extractor creates a data structure that pairs each edge with its corresponding parent and child node information, making the subsequent tree-building phase more efficient.

**Building Parent-Child Maps**: The extractor builds two complementary data structures: `nodeInfoMap` (maps node IDs to their extracted information) and `childrenMap` (maps parent node IDs to arrays of their child node IDs). The `nodeInfoMap` stores all the metadata about each node (label, name, code, line number, properties), while the `childrenMap` captures the tree structure by recording which nodes are children of which parents. These maps are built by iterating through all AST edges and recording the parent-child relationships. The extractor also extracts node information at this stage, unwrapping properties from their JSON-LD wrappers and normalizing the data structure.

**Identifying Root Nodes**: Root nodes are nodes that have no incoming AST edges - meaning they have no parent in the syntax tree. These represent top-level code elements like file-level declarations, global functions, or translation units. To identify roots, the extractor collects all node IDs that appear as children in the `childrenMap`, then finds all node IDs that are not in this set. These are the roots from which tree construction begins. There can be multiple root nodes if the CPG represents multiple files or multiple top-level declarations.

**Building Trees Recursively**: Starting from each root node, the extractor recursively builds tree structures. The recursive algorithm is straightforward: for each node, create a TreeNode object with the node's information and an empty children array. Then, look up the node's children in the `childrenMap`, and for each child, recursively call the tree-building function. The recursion naturally handles arbitrary nesting depth - whether you have a simple expression or a deeply nested structure like `a + (b * (c - (d / e)))`, the recursive approach handles it uniformly. The recursion terminates when a node has no children, creating leaf nodes in the tree.

**Result**: The extraction phase produces a collection of tree structures where each tree represents a top-level code element (like a function, file, or translation unit). Each tree maintains the complete hierarchical structure of the original code's syntax, with parent-child relationships preserved through the tree's nested structure. This tree representation is what the subsequent conversion phase operates on.

### Step 2: Node Conversion (TemplateConverter)

**What Happens**: Each node in the extracted tree is examined and converted from its CPG representation into a standardized template node type. This is where operators get normalized, types get inferred, and special cases get handled.

**Why This Is Needed**: CPG uses verbose, technical names for operators (like `<operator>.addition`). The converter translates these into standard symbols (like `+`) that are more readable and easier to match in patterns. It also handles complex cases like distinguishing between arrays, pointers, and regular variables. The conversion is necessary because CPG's representation is optimized for semantic analysis and graph traversal, not for human-readable pattern matching. By converting to a normalized template format, we make it possible to write patterns that match code constructs in a way that's intuitive to developers and security analysts.

**Main Conversion Entry Point**:

The converter processes trees using a dispatch pattern - a design that routes each node to a specialized handler based on its type. The main entry point is `convertTree()`:

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

This pattern is used because different CPG node types require different conversion logic. A CALL node representing an operator needs different handling than a CALL node representing a function call. A LOCAL node might be an array, pointer, or regular variable depending on its type information. The dispatch pattern allows each handler to focus on the specific conversion rules for its node type, making the code more maintainable and easier to extend.

**Dispatch Pattern and Error Handling**:

The `dispatchConvert` method examines each node's label and routes it to the appropriate handler using a switch statement:

```typescript
private dispatchConvert(node: TreeNode): TemplateNodes | undefined {
  try {
    switch (node.label) {
      case "BINDING":
      case "DEPENDENCY":
      case "META_DATA":
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
    throw new Error(
      `Conversion failed for node id=${node.id} label=${node.label} name=${node.name}: ${error.message}`
    );
  }
}
```

This centralized dispatch point also provides comprehensive error handling. When conversion fails, the error handler captures the node's ID, label, and name, providing detailed context that helps diagnose issues. This is crucial because conversion failures can be subtle - a node might have unexpected children, missing properties, or malformed data. The detailed error context makes debugging much easier.

Some node types are intentionally skipped (BINDING, DEPENDENCY, META_DATA, etc.) because they represent CPG-internal metadata that doesn't correspond to actual code constructs. These nodes are filtered out during conversion, but their children are preserved and converted, ensuring no actual code is lost.

**Operator Conversion**:

When a CALL node represents an operator (identified by names starting with `<operator>.`), it gets converted to a BinaryExpression or UnaryExpression. The `handleCall()` method routes operator calls to `handleCallOperators()`:

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

The conversion process involves several steps:

1. **Operator Mapping**: The operator's CPG name (like `<operator>.addition`) is looked up in configuration maps that translate it to a standard symbol (like `+`). These maps are maintained separately to make the system easily extensible.

2. **Type Inference**: The converter uses the `BinaryUnaryTypeWrapper` utility to infer the result type of the expression. This is important because the type information might not be explicitly available in the CPG node, or it might need to be inferred from the operand types.

3. **Child Conversion**: The operator's operands (stored as children) are recursively converted. This ensures that complex nested expressions are fully normalized.

The distinction between binary and unary operators is important because they have different semantics and different numbers of operands. Binary operators like `+` and `*` have two operands, while unary operators like `++` and `!` have one operand. The converter handles both cases appropriately.

**Control Structure Conversion**:

The `handleControlStructure()` method processes control structures (if statements, while loops, for loops, switch statements, etc.):

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

Control structures are identified by their `CONTROL_STRUCTURE_TYPE` property. The conversion process must handle the specific semantics of each control structure type:

- **If Statements**: Must have at least two children (condition and then-branch), with an optional third child (else-branch). The converter validates this structure and restructures the children to match the template format's expectations.

- **While Loops**: Have a condition child and a body child. The converter ensures these are properly structured.

- **For Loops**: Have initialization, condition, increment, and body children. The converter handles the specific ordering and structure required by the template format.

- **Switch Statements**: Have a selector expression and multiple case/default branches. The converter structures these appropriately.

Each control structure type requires specific validation because malformed control structures indicate issues with the CPG data or the extraction process. The converter throws descriptive errors when it encounters invalid structures, helping identify data quality issues early.

**Variable Declaration Conversion**:

The `handleLocal()` method analyzes variable types to determine if they're arrays, pointers, or regular variables:

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

This classification is important because different variable types have different semantics and require different handling in pattern matching:

- **Array Declarations**: Identified by type names containing `[` and `]`. The converter extracts the element type and array length from the type string. The length might be a number (for fixed-size arrays) or a string (for variable-length arrays or incomplete type information).

- **Pointer Declarations**: Identified by type names containing `*`. The converter counts the number of asterisks to determine the pointer level (single pointer, double pointer, etc.) and extracts the pointed-to type.

- **Regular Variable Declarations**: Variables that are neither arrays nor pointers. The converter checks for predefined types (like `stdin`, `stdout`, `NULL`) and uses those when available, falling back to the type information from CPG.

The distinction between these types is crucial for security analysis. For example, buffer overflow vulnerabilities often involve arrays, while use-after-free vulnerabilities involve pointers. Accurate classification enables more precise pattern matching.

**Function Declaration vs. Definition**:

The `handleMethod()` method distinguishes between function declarations (signature only, like in header files) and function definitions (with implementation body):

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

This distinction is important because:

- Function declarations provide interface information but no implementation details
- Function definitions contain the actual code that needs to be analyzed
- Some analysis tasks only need declarations (like checking function signatures), while others need definitions (like analyzing function bodies for vulnerabilities)

The converter identifies functions at file scope by checking that the function's parent is the global scope. It then checks if the function has an empty body block to determine if it's a declaration or definition. The converter also extracts the function's parameter list by filtering for METHOD_PARAMETER_IN children and converting them to parameter declarations. The return type is extracted from the function's signature property.

**Recursive Child Conversion**:

All handlers recursively convert their children using the `convertedChildren` helper method:

```typescript
private convertedChildren(children: TreeNode[]): TemplateNodes[] {
  return children
    .map((child) => this.dispatchConvert(child))
    .filter((child): child is TemplateNodes => child !== undefined);
}
```

This recursive approach ensures that the entire tree is converted, regardless of nesting depth. The helper method also filters out undefined results, which can occur when certain node types are skipped or when conversion fails for specific children. This filtering ensures that the resulting tree structure is valid even when some nodes can't be converted.

**Result**: The conversion phase produces a tree of template nodes with standardized representations. All operators are in familiar symbol form (making patterns more readable), types are normalized (enabling consistent matching), and special cases are properly identified (ensuring accurate classification). The tree structure is preserved, but each node is now in a format optimized for pattern matching and analysis.

### Step 3: Post-Processing (PostProcessor)

**What Happens**: The converted template tree is cleaned up and enhanced with additional information. Invalid nodes are removed, related nodes are merged, and source code snippets are attached to nodes.

**Why This Is Needed**: The conversion process may create nodes that don't map perfectly, or CPG may represent certain constructs in ways that need cleanup. Additionally, adding source code to nodes helps with debugging and code generation. The post-processing phase serves as a quality assurance and enhancement step, ensuring that the template tree is in the best possible state for downstream analysis. It fixes issues that the conversion phase couldn't handle, adds valuable metadata, and optimizes the structure for specific use cases.

**Removing Invalid Nodes**:

The `removeInvalidNodes()` method removes nodes that don't have a corresponding template type:

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

Some CPG nodes don't have a corresponding template type - they might represent CPG-internal structures, metadata, or constructs that don't map cleanly to the template format. These invalid nodes are identified by the absence of a `nodeType` property. Rather than failing or leaving these nodes in the tree, the post-processor removes them and promotes their children. This "promotion" ensures that no actual code is lost - if an invalid node contained valid child nodes, those children are preserved and moved up in the tree hierarchy.

The removal process is recursive, ensuring that invalid nodes at any depth are handled. The process uses `flatMap` to both filter and flatten the tree structure in a single pass, making it efficient. This cleanup is important because invalid nodes can cause issues in downstream analysis - they might not match patterns correctly, or they might cause errors when the analysis tries to access properties that don't exist.

**Adding Code Properties**:

The `addCodeProperties()` method enriches each node with the actual source code snippet it represents:

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

This enhancement is valuable for several reasons:

1. **Debugging**: When a pattern match fails or produces unexpected results, having the source code attached to nodes makes it much easier to understand what the node represents and why the match failed.

2. **Code Generation**: Some analysis tasks need to generate code or produce reports that include the original source code. Having the code attached to nodes makes this straightforward.

3. **Human Readability**: When displaying analysis results to users, showing the actual source code is much more meaningful than showing abstract node types and properties.

The code property addition process recursively traverses the tree and looks up each node's corresponding vertex in the original CPG data. The CPG format stores code in a nested JSON-LD structure, so the post-processor must unwrap the code from its wrappers and join array elements (since CPG may split code across multiple array elements). If a node doesn't have code information in the CPG (which can happen for synthetic nodes or nodes representing implicit constructs), the code property is set to undefined, and the process continues gracefully.

**Merging Array Allocations**:

Sometimes CPG represents array size allocation as a separate node from the array declaration. This can happen when the array size is determined dynamically or when CPG's analysis creates separate nodes for the declaration and the size specification. When these appear as consecutive siblings in the tree, and they have matching sizes, the post-processor merges them into a single ArrayDeclaration node. This merging creates a more intuitive representation - instead of having two separate nodes that represent a single logical construct, we have one node that contains all the relevant information.

The merging process looks for pairs of consecutive children where the first is an ArrayDeclaration and the second is an ArraySizeAllocation. When such a pair is found, the post-processor creates a new ArrayDeclaration node that combines the information from both nodes. If the sizes match, it uses that size; if they don't match, it uses the size from the allocation node (which is typically more accurate). The children of both nodes are combined, ensuring that any initialization or other related constructs are preserved.

**Isolating Translation Units**:

Translation units represent file-level code structures. In C/C++, each source file is a translation unit, and the template system needs to identify these top-level structures. The post-processor filters for TranslationUnit nodes and validates that at least one exists. If no translation unit is found, it throws an error because this indicates a problem with the CPG data or the extraction/conversion process.

Isolating translation units is important because many analysis tasks operate at the file level. For example, vulnerability scanning might need to analyze each file separately, or code generation might need to produce output organized by file. Having translation units clearly identified makes these tasks easier.

**Result**: The post-processing phase produces a cleaned, enhanced template tree. All nodes have code properties (when available), invalid nodes are removed (with their children preserved), related nodes are merged (creating more intuitive representations), and translation units are isolated (providing clear entry points for file-level analysis). The tree is now in optimal condition for flattening or direct analysis.

### Step 4: Flattening (PlanationTool)

**What Happens**: The hierarchical tree structure is converted into a flat graph representation. Instead of nested children, the structure becomes a list of nodes and a list of edges connecting them.

**Why This Is Needed**: Many analysis algorithms work better with flat graph structures than with nested trees. While trees are intuitive for representing code structure, graphs are more flexible and efficient for certain types of analysis:

1. **Graph Algorithms**: Many classic graph algorithms (shortest path, cycle detection, topological sorting, etc.) are designed for flat graph structures with explicit edges. Converting trees to graphs enables the use of these algorithms.

2. **Pattern Matching**: Pattern matching algorithms often need to traverse relationships that don't follow the tree hierarchy. For example, a pattern might need to match a variable declaration and its uses, which might be connected through data flow edges rather than AST edges. A flat graph makes it easier to add and traverse these additional relationships.

3. **Efficiency**: Graph traversal can be more efficient than tree traversal for certain operations. With a flat graph, you can use efficient data structures like adjacency lists or hash maps for node lookup, rather than recursively traversing nested structures.

4. **Flexibility**: Graph structures can represent relationships that don't fit tree hierarchies. While the initial flattening only creates edges for parent-child relationships, the flat structure makes it easy to add additional edge types (data flow, control flow, etc.) later.

**Flattening Process**:

The `flatten()` method processes each root node separately, creating a separate graph for each root:

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

This separation is important because different roots might represent different files or different top-level declarations, and keeping them separate makes it easier to analyze them independently.

For each root, the tool:

1. Resets its internal state (clearing nodes and edges arrays)
2. Recursively traverses the tree starting from the root
3. Sorts nodes by ID and edges by the sum of their endpoint IDs (ensuring deterministic output)
4. Validates that all edges reference existing nodes
5. Optionally filters blacklisted node types

The sorting step is important for deterministic output - it ensures that the same input always produces the same output, which is crucial for testing and debugging. The validation step catches errors early - if an edge references a non-existent node, it indicates a bug in the flattening process.

**Recursive Traversal**:

The `traverse()` method recursively traverses the tree, creating flat node entries and explicit edges:

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

For each node, it:

1. Creates a clone of the node without its children (since children will be separate nodes in the flat structure)
2. Adds the cloned node to the nodes array
3. Recursively processes each child
4. Creates an edge from the current node to each child

The recursive approach naturally handles arbitrary nesting depth. The traversal preserves the hierarchical relationships through explicit edges - if node A contains node B in the tree, there will be an edge from A to B in the graph. This means the tree structure is preserved, just represented differently.

**Edge Validation**:

Before returning, the tool validates that all edges reference existing nodes. This validation is crucial because:

1. It catches bugs in the flattening process early
2. It ensures the graph is valid (no dangling references)
3. It provides clear error messages when issues are found

The validation creates a set of all node IDs, then checks that every edge's `from` and `to` IDs are in that set. If any edge references a non-existent node, it throws a descriptive error. This validation prevents downstream analysis from encountering invalid graph structures.

**Blacklist Support**:

The tool supports filtering out specific node types through a blacklist mechanism. This is useful when certain node types aren't needed for a particular analysis task. For example, if you're only interested in function calls and control structures, you might blacklist variable declarations and other node types to reduce the graph size and focus the analysis.

When blacklisting is enabled, the tool filters nodes and also filters edges to remove any edges that reference blacklisted nodes. This ensures that the resulting graph is still valid and doesn't contain dangling references.

**Result**: The flattening phase produces a flat graph structure with nodes and edges. The hierarchical structure is preserved through explicit edges (parent-child relationships are represented as edges), but the representation is flat, making it efficient for graph-based analysis algorithms. Each root node produces a separate graph, enabling independent analysis of different code units.

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

CPG uses JSON-LD format where values are wrapped in objects with `@value` keys. This wrapping can be nested multiple levels deep, and the extractor must handle all these cases. The unwrapping process is recursive because:

1. Values might be wrapped once: `{ "@value": "actualValue" }`
2. Values might be wrapped multiple times: `{ "@value": { "@value": "actualValue" } }`
3. Values might be in arrays: `{ "@value": ["value1", "value2"] }`
4. Arrays might contain wrapped values: `[{ "@value": "value1" }, { "@value": "value2" }]`

The unwrapper handles all these cases by recursively unwrapping until it finds a primitive value (string or number) or exhausts all wrapping layers. For arrays, it unwraps each element and returns the first non-undefined value found. This robust unwrapping ensures that the extractor can handle CPG data regardless of how deeply values are wrapped.

**Rationale**: The CPG format stores relationships as edges rather than hierarchical structures. This design choice makes sense for CPG's goals (representing complex semantic relationships), but it's not ideal for template-based analysis. The extractor bridges this gap by reconstructing the tree structure that matches the code's syntax. It does this by filtering AST edges (which represent parent-child relationships in the syntax tree), building efficient lookup structures (enabling O(1) node access), identifying roots (nodes without incoming AST edges, representing top-level code elements), and recursively building trees from roots downward (preserving the hierarchical structure naturally through recursion). This reconstruction is essential because subsequent analysis phases expect tree structures that match the code's syntax hierarchy.

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

The converter uses `BinaryUnaryTypeWrapper` for type inference when converting operators. Type information is crucial for accurate analysis - knowing that an expression returns `int` versus `bool` versus `char*` enables more precise pattern matching. However, CPG doesn't always provide explicit type information, so the converter uses a multi-strategy inference approach:

1. **Boolean Map Override**: Some operators always return boolean (comparison operators, logical operators). The converter checks a boolean map first and uses those types directly.

2. **Explicit Type Information**: If available, the converter uses the `TYPE_FULL_NAME` property from the CPG node.

3. **Bottom-Up Inference**: If explicit types aren't available, the converter infers types from the operand types. If all operands have the same type, the expression likely returns that type.

4. **Graceful Degradation**: If all inference strategies fail, the converter uses `"<unknown>"` rather than failing, ensuring the conversion process continues.

This multi-strategy approach maximizes accuracy while handling edge cases gracefully.

**Special Operator Handling**:

Some operators require special handling beyond simple mapping. The assignment operator (`<operator>.assignment`) is a prime example because it can represent different constructs depending on context:

- **Regular Assignment**: `x = y` - a simple assignment expression
- **Array Size Allocation**: `int arr[10]` - when the assignment involves an allocation operator, it represents array size specification

The converter distinguishes these cases by examining the assignment's children. If one child is an allocation operator (`<operator>.alloc`), the converter treats it as an array size allocation and extracts the size from the type information. Otherwise, it treats it as a regular assignment. This special handling is necessary because CPG represents array declarations and size allocations in ways that don't map directly to simple assignment expressions.

Other operators with special handling include pointer operations, array indexing, and function pointer calls. Each requires specific logic to correctly classify and convert the construct.

**Rationale**: The converter serves as a normalization layer that translates CPG's technical, verbose representations into standardized, human-readable formats. This normalization is critical for several reasons:

1. **Pattern Readability**: Patterns written using standard operators (`+`, `-`, `*`) are much more readable than patterns using CPG names (`<operator>.addition`, `<operator>.subtraction`). This readability makes patterns easier to write, maintain, and debug.

2. **Consistency**: By normalizing operators and types, the converter ensures that similar code constructs are represented consistently, regardless of how CPG originally encoded them. This consistency reduces the complexity of pattern definitions.

3. **Type Accuracy**: The multi-strategy type inference ensures that type information is as accurate as possible, even when CPG doesn't provide explicit types. This accuracy is crucial for type-sensitive analysis tasks.

4. **Call Classification**: By distinguishing standard library calls from user-defined calls, the converter enables different handling strategies. Standard library calls might have known security properties or behaviors that can be leveraged in analysis.

This normalization transforms CPG from a format optimized for semantic analysis into a format optimized for pattern matching and security analysis.

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

**Key Responsibility**: Type information is crucial for accurate analysis, but CPG doesn't always provide explicit types. This utility infers types using multiple strategies, maximizing accuracy while gracefully handling cases where type information is incomplete.

**How It Works**:

The `BinaryUnaryTypeWrapper()` function uses a multi-strategy approach with fallbacks:

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

The wrapper tries the most reliable strategies first and falls back to less reliable ones:

1. **Boolean Map Override**: The first strategy checks a boolean map that explicitly defines which operators always return boolean types. This is the most reliable strategy because it's based on language semantics - comparison operators (`==`, `!=`, `<`, `>`, etc.) and logical operators (`&&`, `||`) always return boolean regardless of their operand types. This strategy takes precedence because it's based on language rules rather than potentially incomplete CPG data.

2. **Explicit Type Information**: If the boolean map doesn't apply, the wrapper checks for explicit type information in the CPG node's `TYPE_FULL_NAME` property. This property contains the type information that CPG's analysis determined. If available, this is highly reliable because it comes from CPG's semantic analysis.

3. **Bottom-Up Inference**: If explicit types aren't available, the wrapper infers types from the operand types using a bottom-up approach. It recursively determines the types of all operands, and if they all have the same type, it assumes the expression returns that type. For example, if both operands of an addition are `int`, the result is likely `int`. This strategy is less reliable because it makes assumptions, but it's better than nothing.

4. **Graceful Degradation**: If all strategies fail, the wrapper returns `"<unknown>"` rather than failing. This ensures that the conversion process can continue even when type information is incomplete. Downstream analysis can handle unknown types appropriately (e.g., by treating them as wildcards in pattern matching).

**Bottom-Up Type Inference**:

The `inferTypeBottomUp()` function recursively determines types by examining child nodes:

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

The algorithm works as follows:

- For leaf nodes (nodes with no children), it returns `"unknown"` because there's no information to infer from.
- For internal nodes, it recursively determines the types of all children.
- If all children have the same type, it returns that type (assuming the expression preserves type).
- If children have mixed types, it returns a tuple representation like `"(int char)"` indicating the mixed types.

This bottom-up approach is based on the observation that many expressions preserve the types of their operands (e.g., `int + int = int`), or that the result type can be determined from operand types (e.g., `int < int = bool`). However, it's not perfect - some expressions change types (e.g., pointer arithmetic), and the inference can't always determine these cases correctly.

**Rationale**: The multi-strategy approach is designed to maximize accuracy while providing graceful degradation. By trying the most reliable strategies first (boolean map, explicit types) and falling back to less reliable ones (inference), the wrapper ensures that type information is as accurate as possible given the available data. The explicit handling of boolean operators is important because these operators have special semantics that can't be inferred from operand types alone. The graceful degradation to `"<unknown>"` ensures that incomplete type information doesn't break the conversion process, allowing analysis to proceed with partial information rather than failing completely.

---

## Data Transformations

This section provides detailed examples of how data is transformed at each stage of the pipeline, illustrating the concrete changes that occur as code moves through the transformation process.

### CPG Format → Tree Structure

The CPG format represents code as a graph with nodes (vertices) and edges. The extractor transforms this graph representation into a hierarchical tree structure that matches the code's syntax.

**CPG Input Characteristics**:

The CPG format uses JSON-LD style wrappers where values are nested in objects with `@value` keys. A typical CPG structure contains:

- **Vertices**: Nodes representing code elements (functions, variables, expressions, etc.), each with an ID, label (type), and properties
- **Edges**: Relationships between nodes, with different edge types (AST, data flow, control flow, etc.)
- **Wrapping**: Values are wrapped in `@value` objects, which can be nested multiple levels deep

For example, a function node might have an ID wrapped as `{ "@value": 1 }`, a name wrapped as `{ "@value": { "@value": ["main"] } }`, and code wrapped similarly. An AST edge connects a parent node (function) to a child node (block) using `outV` (parent) and `inV` (child) properties.

**Tree Output Characteristics**:

The extracted tree structure is much simpler and more intuitive:

- **Direct Values**: IDs, names, and other properties are unwrapped from their JSON-LD wrappers
- **Hierarchical Structure**: Parent-child relationships are represented through nested `children` arrays rather than separate edges
- **Simplified Properties**: Node properties are extracted and normalized, making them easier to access

A function node in the tree has a direct `id` (string), `name` (string), `code` (string), and a `children` array containing its child nodes. This structure naturally represents the syntax hierarchy - a function contains a block, which contains statements, which contain expressions, etc.

**Transformation Process**:

The transformation from graph to tree involves several key steps:

1. **Edge Filtering**: The extractor filters for AST edges only, ignoring other edge types (data flow, control flow, etc.) that don't represent syntax tree relationships.

2. **Parent-Child Mapping**: AST edges are processed to build maps showing which nodes are children of which parents. An edge from node A to node B means A is the parent and B is the child in the syntax tree.

3. **Root Identification**: Nodes with no incoming AST edges are identified as roots - these represent top-level code elements like file-level functions or global declarations.

4. **Recursive Tree Building**: Starting from each root, the extractor recursively builds tree structures. For each node, it creates a tree node object and recursively processes its children, building the complete hierarchy.

The result is a collection of trees where each tree represents a top-level code element, and the nested structure naturally represents the code's syntax hierarchy. This tree structure is what the conversion phase operates on.

### Tree Nodes → Template Nodes

CPG nodes have technical labels and verbose properties that need normalization. The converter transforms these into standardized template nodes optimized for pattern matching and analysis.

**Before (CPG TreeNode)**:

A CPG node representing an addition operation has:

- A technical label: `"CALL"` (indicating it's a function call, even though it's actually an operator)
- A verbose name: `"<operator>.addition"` (using CPG's technical naming convention)
- Wrapped properties: Type information nested in JSON-LD wrappers like `{ "@value": { "@value": ["int"] } }`
- Generic structure: The node type doesn't clearly indicate it's a binary expression

**After (Template Node)**:

The converted template node has:

- A semantic node type: `"BinaryExpression"` (clearly indicating what kind of construct this is)
- A standard operator: `"+"` (using familiar mathematical notation)
- Direct type information: `"int"` (unwrapped and normalized)
- Preserved structure: The hierarchical children relationships are maintained

**Key Transformations**:

The conversion process performs several important normalizations:

1. **Operator Normalization**: Technical CPG names like `<operator>.addition` are mapped to standard symbols like `+`. This mapping is crucial because it makes patterns readable and intuitive. A pattern matching `a + b` is much clearer than a pattern matching `<operator>.addition`.

2. **Type Extraction**: Types are extracted from nested JSON-LD wrappers and normalized. The `TYPE_FULL_NAME` property might contain `["int"]` wrapped in multiple layers, which gets unwrapped to the simple string `"int"`.

3. **Node Type Classification**: The converter examines the node's label and name to determine the appropriate template node type. A `CALL` node with an operator name becomes a `BinaryExpression` or `UnaryExpression`, while a `CALL` node with a function name becomes a `FunctionCall`.

4. **Structure Preservation**: The hierarchical children relationships are maintained through the conversion. A function still contains its body, which still contains its statements, etc. This preservation ensures that the tree structure remains intact for tree-based analysis.

### Template Tree → Flat Graph

The hierarchical tree structure gets flattened into a graph with explicit nodes and edges. This transformation changes the representation format while preserving all relationships.

**Before (Hierarchical Tree)**:

The tree structure uses nested `children` arrays to represent parent-child relationships. A function node contains a compound statement node, which contains expression nodes, etc. This nested structure is intuitive and matches how code is naturally organized, but it requires recursive traversal to access nodes.

**After (Flat Graph)**:

The flat graph structure uses separate arrays for nodes and edges. All nodes are in a single flat array, and parent-child relationships are represented as explicit edges with `from` and `to` IDs. This flat structure enables efficient graph-based algorithms and makes it easy to add additional relationship types beyond parent-child.

**Transformation Process**:

The flattening process involves:

1. **Recursive Traversal**: The flattening tool recursively traverses the entire tree, visiting every node.

2. **Node Extraction**: Each node is cloned (without its children) and added to a flat nodes array. The node's ID is preserved, enabling edge references.

3. **Edge Creation**: For each parent-child relationship in the tree, an explicit edge is created with `from` pointing to the parent's ID and `to` pointing to the child's ID.

4. **Structure Preservation**: The hierarchical structure is preserved through the edges - if node A was the parent of node B in the tree, there's an edge from A to B in the graph. The tree structure is still accessible, just represented differently.

5. **Sorting and Validation**: Nodes and edges are sorted for deterministic output, and edges are validated to ensure they reference existing nodes.

The result is a graph structure that preserves all the information from the tree but in a format optimized for graph-based analysis algorithms. The hierarchical relationships are still accessible through the edges, but the flat structure enables efficient traversal and the addition of additional relationship types.

---

## Design Rationale

This section explains the reasoning behind key design decisions in the template module, providing insight into why the system is structured the way it is and how the design choices support the module's goals.

### Why Separate Components?

The template transformation is broken into distinct components (TemplateExtractor, TemplateConverter, PostProcessor, PlanationTool), each with a single responsibility. This separation of concerns follows the Single Responsibility Principle and provides several important benefits:

- **Maintainability**: Each component can be modified independently without affecting others. If operator conversion logic needs to change, only the TemplateConverter needs modification. The extractor, post-processor, and flattening tool remain unaffected. This independence reduces the risk of introducing bugs when making changes and makes the codebase easier to maintain over time.

- **Testability**: Each stage can be tested in isolation. You can test tree extraction without running conversion, test conversion without post-processing, etc. This isolation makes it easier to write comprehensive tests and to identify which stage is failing when tests fail. Unit tests can focus on specific components, while integration tests can verify the pipeline as a whole.

- **Clarity**: The purpose of each component is clear and focused. When reading the code, it's immediately obvious what each component does. This clarity makes the codebase easier to understand for new developers and reduces the cognitive load when working with the code.

- **Debugging**: When issues arise, it's easier to identify which stage is causing problems. Error messages can indicate which component failed, and you can inspect the intermediate results between stages to pinpoint where issues occur. This makes debugging much more efficient.

- **Reusability**: Components can potentially be reused in different contexts. For example, the flattening tool might be useful for other tree-to-graph transformations, or the extractor might be adapted for other CPG processing tasks.

The component separation also enables parallel development - different developers can work on different components simultaneously without conflicts, as long as the interfaces between components remain stable.

### Why Configuration Files?

Operator mappings and standard library function lists are stored in separate configuration files rather than hard-coded in the converter. This configuration-driven approach provides several advantages:

- **Enables Extension**: New operators or functions can be added by updating configuration files without modifying the converter code. This makes the system easily extensible - adding support for a new operator is as simple as adding a line to a configuration file. This extensibility is important because CPG might support new operators in future versions, or the system might need to handle language-specific operators.

- **Centralizes Maintenance**: All mappings are in one place, making updates easier. If an operator mapping is incorrect, you know exactly where to fix it. This centralization reduces the chance of inconsistencies and makes maintenance more efficient.

- **Improves Readability**: The converter code focuses on logic rather than long lists of mappings. This separation makes the converter code easier to read and understand - the logic is clear without being obscured by hundreds of mapping entries.

- **Enables Testing**: Configuration files can be tested independently. You can verify that all expected operators are mapped, that mappings are correct, etc., without running the full conversion process.

- **Supports Multiple Languages**: Different configuration files could potentially support different languages or language variants, making the system more flexible.

The configuration files serve as a contract between the converter and the mappings - the converter expects certain mappings to exist, and the configuration files provide those mappings. This separation makes it easy to update mappings without touching the conversion logic.

### Why Recursive Processing?

All components use recursive algorithms to process tree structures. This recursive approach is natural for tree processing and provides several benefits:

- **Handles Arbitrary Depth**: Code can be nested to any depth (expressions within expressions, statements within blocks, etc.), and recursion naturally handles this. An iterative approach would require maintaining a stack manually, which is more error-prone and less intuitive. Recursion handles arbitrary nesting depth automatically.

- **Maintains Relationships**: Parent-child relationships are preserved naturally through recursive calls. When you recursively process a node's children, the call stack itself maintains the parent-child relationship context. This natural preservation reduces the chance of errors in relationship handling.

- **Efficiency**: Single-pass processing is possible with recursion. You can process the entire tree in one traversal, visiting each node exactly once. This efficiency is important for performance, especially when processing large codebases.

- **Clarity**: Recursive algorithms are often more intuitive for tree processing. The code structure mirrors the tree structure - processing a node involves processing its children recursively, which matches how we think about tree structures.

- **Simplicity**: Recursive code is often simpler than iterative code for tree processing. You don't need to manually manage stacks or queues - the call stack handles that for you.

The recursive approach does have some limitations (potential stack overflow for very deep trees), but in practice, code syntax trees are rarely deep enough to cause issues, and the benefits of recursion outweigh these concerns.

### Why Type Inference?

Type information is critical for accurate analysis, but CPG doesn't always provide explicit types. The multi-strategy type inference approach addresses this challenge:

- **Maximizes Accuracy**: The system uses the best available information, trying the most reliable strategies first (hard-coded rules for boolean operators, explicit types from CPG) and falling back to less reliable ones (inference from operands) when necessary. This multi-strategy approach ensures that type information is as accurate as possible given the available data.

- **Handles Edge Cases**: Special cases like boolean operators are handled explicitly because they have semantics that can't be inferred from operand types. Comparison operators always return boolean regardless of their operand types, and this needs to be handled explicitly rather than inferred.

- **Graceful Degradation**: When type information isn't available, the system falls back to "unknown" rather than failing. This graceful degradation ensures that the conversion process can continue even with incomplete type information, allowing analysis to proceed with partial information rather than failing completely.

- **Language Semantics**: The type inference respects language semantics. For example, in C/C++, comparison operators return `int` (0 or 1), but for analysis purposes, we treat them as boolean. The boolean map handles this explicitly, ensuring that analysis patterns can rely on comparison operators returning boolean.

The multi-strategy approach balances accuracy with robustness - it tries to be as accurate as possible while gracefully handling cases where accuracy isn't possible.

### Why Flattening?

The flattening step converts trees to graphs, which may seem counterintuitive since we just converted a graph to a tree. However, this transformation serves important purposes:

- **Analysis Algorithms**: Many graph analysis algorithms (shortest path, cycle detection, topological sorting, etc.) are designed for flat graph structures with explicit edges. While these algorithms can be adapted for trees, they're more efficient and easier to implement for flat graphs.

- **Pattern Matching**: Pattern matching algorithms often need to traverse relationships that don't follow the syntax tree structure. For example, a pattern might need to match a variable declaration and its uses, which might be connected through data flow edges rather than AST edges. A flat graph makes it easier to add and traverse these additional relationship types.

- **Efficiency**: Graph traversal can be more efficient than tree traversal for certain operations. With a flat graph, you can use efficient data structures like hash maps for node lookup, adjacency lists for edge traversal, etc. These data structures enable O(1) or O(log n) operations that would be slower with tree traversal.

- **Flexibility**: Graph structures can represent relationships that don't fit tree hierarchies. While the initial flattening only creates edges for parent-child relationships, the flat structure makes it easy to add additional edge types (data flow, control flow, call relationships, etc.) later. This flexibility enables more sophisticated analysis.

- **Consistency**: Having a consistent graph format makes it easier to build analysis tools. Different analysis algorithms can all work with the same graph format, reducing the need for format conversions.

The flattening doesn't lose information - the tree structure is preserved through explicit edges. It just changes the representation format to one that's more suitable for graph-based analysis algorithms.

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

When the analysis endpoint is called, the template module is invoked through the `generateTemplate()` function. This section explains how the module integrates with the broader analysis pipeline, how it's called, what it produces, and how its output is used by downstream analysis steps.

### Function Signature and Entry Point

The `generateTemplate()` function serves as the main entry point for template generation:

```typescript
export function generateTemplate(cpg: CPGRoot): TemplateNodes[] {
  validateCPGRoot([cpg.export]);
  const artifacts = buildTemplateArtifacts(cpg);
  return artifacts.templateResult;
}
```

It takes CPG data as input and returns template nodes as output. The function performs two main operations:

1. **Validation**: Before processing, it validates that the CPG data has the expected structure. This validation catches data quality issues early and provides clear error messages if the CPG data is malformed or incomplete.

2. **Artifact Building**: It calls `buildTemplateArtifacts()` to perform the full transformation pipeline, then returns the converted template nodes.

This simple interface hides the complexity of the transformation pipeline - callers don't need to know about extractors, converters, post-processors, or flattening tools. They just call `generateTemplate()` and get template nodes back.

### Integration Flow

The template module fits into a larger analysis pipeline:

1. **CPG Generation**: Source code is first converted to CPG format by the CPGGenerator. This CPG generation is a separate process that performs semantic analysis of the source code, extracting type information, control flow, data flow, and other semantic relationships.

2. **Template Generation**: The CPG data is passed to `generateTemplate()`, which orchestrates the template transformation. This transformation converts the CPG's graph-based, verbose representation into a normalized template format optimized for pattern matching.

3. **Validation**: Before processing, the CPG data is validated to ensure it has the expected structure. This validation prevents errors later in the pipeline and provides early feedback if the CPG data is problematic.

4. **Artifact Building**: The `buildTemplateArtifacts()` function creates all template-related artifacts through the four-stage pipeline (extraction, conversion, post-processing, flattening).

5. **Return**: Template nodes are returned for use in subsequent analysis steps. The template format serves as a common intermediate representation that enables various analysis tasks to work with a consistent, normalized code structure.

This flow ensures that each stage of the pipeline has clean, validated input, making the entire system more reliable and easier to debug.

### Usage in Analysis Pipeline

The template nodes produced by the module are used by various downstream analysis steps:

- **AST Generation**: Templates are passed to Python-based AST extractors for further processing. These extractors might perform additional transformations or extract specific information from the templates.

- **DFG Generation**: Templates are combined with CPG data to build data flow graphs. The template structure provides the syntax tree context, while CPG provides the data flow relationships. Combining these enables sophisticated data flow analysis.

- **Pattern Matching**: Templates are matched against security patterns and vulnerability signatures. The normalized template format makes it easier to write patterns that match code constructs reliably, regardless of how the original code was written or how CPG encoded it.

- **Code Generation**: Some analysis tasks need to generate code or produce reports. The template format, with its normalized structure and attached source code, makes code generation straightforward.

The template format serves as a bridge between CPG's semantic representation and the needs of specific analysis tasks. It provides a consistent, normalized view of code that's easier to work with than raw CPG data.

### Artifacts Produced

The `buildTemplateArtifacts()` function produces multiple artifacts, each serving different purposes:

- **template**: Raw TreeNode structures extracted from CPG. These represent the tree structure before conversion and are useful for debugging extraction issues or understanding how CPG structures were interpreted.

- **templateResult**: Converted and processed TemplateNodes. This is the main output used by downstream analysis - it's the normalized template format with operators, types, and structures standardized.

- **textLines**: Text representation of templates for debugging and display. This human-readable format makes it easier to understand what the template represents and to debug issues.

- **flatten**: Flattened graph representations. These are used by graph-based analysis algorithms that work better with flat graph structures than with nested trees.

By producing multiple artifacts, the module supports diverse analysis needs. Some tasks work better with trees, others with graphs, and having both available enables flexibility.

### Error Handling

The endpoint uses a `withContext()` wrapper to provide detailed error messages. This wrapper catches errors from the template generation process and adds context about which function failed. This context is crucial because:

- **Debugging**: When errors occur, it's immediately clear which stage of the transformation failed. This makes debugging much more efficient.

- **User Feedback**: Error messages are more meaningful to users when they include context about what operation was being performed.

- **Logging**: Error logs are more useful when they include context, making it easier to identify patterns in failures.

The error handling ensures that failures are caught and reported clearly, rather than causing silent failures or cryptic error messages.

### Validation

Before returning results, the system performs several validation checks:

- **ID Uniqueness**: The system validates that there are no duplicate node IDs in flattened graphs. Duplicate IDs would cause ambiguity and indicate bugs in the flattening process. This validation ensures graph integrity.

- **Edge Validity**: Edges are validated to ensure they reference existing nodes. Dangling references would indicate bugs and cause issues in downstream analysis.

- **Structure Validity**: The template structure is validated to ensure it's well-formed and complete.

These validations ensure that the template module produces high-quality output that downstream analysis can rely on. Rather than producing potentially invalid data and letting downstream analysis fail mysteriously, the module validates its output and provides clear error messages when validation fails.

The template format serves as a common intermediate representation that enables these various analysis tasks to work with a consistent, normalized code structure. By providing this normalized format, the template module reduces the complexity of downstream analysis and enables more reliable, maintainable analysis tools.

---

## Error Handling and Edge Cases

The template module includes comprehensive error handling and edge case management to ensure robust operation. The system is designed to handle incomplete, malformed, or unexpected CPG data gracefully, providing clear feedback when issues occur while continuing processing when possible.

### Error Context

When conversion fails, the system provides detailed context to help diagnose the issue. The error handling captures:

- **Node Identification**: The node's ID, label, and name are included in error messages, making it easy to locate the problematic node in the source code or CPG data
- **Original Error**: The underlying error message is preserved, providing technical details about what went wrong
- **Stack Trace**: When available, the full stack trace is included, showing exactly where in the code the error occurred

This detailed context is crucial because conversion failures can be subtle. A node might have unexpected children, missing properties, or malformed data that only becomes apparent during conversion. The detailed error context makes it much easier to identify and fix these issues.

### Validation Checks

The module includes multiple validation checks at different stages:

1. **Edge Validation**: Before returning flattened graphs, the system validates that all edges reference existing nodes. This prevents downstream analysis from encountering invalid graph structures with dangling references. If an edge references a non-existent node, it indicates a bug in the flattening process, and the validation catches it early with a clear error message.

2. **ID Uniqueness**: The system validates that there are no duplicate node IDs in flattened graphs. Duplicate IDs would cause ambiguity - if two nodes have the same ID, it's unclear which one an edge refers to. This validation ensures graph integrity.

3. **Node Structure**: Before processing nodes, the system validates their structure. Nodes must have the expected properties and structure for their type. Invalid structures are handled gracefully (nodes are removed, children are preserved) rather than causing failures.

4. **Required Properties**: Before accessing properties, the system checks that they exist. This prevents errors when CPG data is incomplete or when certain properties are optional. Missing properties are handled with defaults (empty strings, undefined, etc.) rather than causing crashes.

### Edge Cases Handled

**Missing Type Information**:

When type information is missing or cannot be inferred, the system gracefully degrades by using `"<unknown>"` as the type. This approach ensures that:

- The conversion process continues even when type information is incomplete
- Downstream analysis can handle unknown types appropriately (e.g., by treating them as wildcards)
- The system doesn't fail completely due to missing type information

This graceful degradation is important because CPG data might be incomplete for various reasons (incomplete analysis, missing type information in source code, etc.), and the template module should handle these cases rather than failing.

**Invalid Node Types**:

Some CPG nodes don't have corresponding template types - they might represent CPG-internal structures, metadata, or constructs that don't map to the template format. Rather than failing, the system removes these invalid nodes and promotes their children. This "promotion" ensures that:

- No actual code is lost (valid children are preserved)
- The tree structure remains valid (invalid nodes don't break the hierarchy)
- The conversion process continues (invalid nodes don't cause failures)

This handling is important because CPG might include nodes that aren't relevant for template-based analysis, and the system should filter these out gracefully.

**Empty Children Arrays**:

Empty children arrays are handled consistently throughout the system. When a node has no children, the `children` property is set to an empty array rather than undefined or null. This consistency:

- Simplifies traversal code (no need to check for undefined)
- Ensures predictable structure (children is always an array)
- Prevents errors in code that iterates over children

**Missing Translation Units**:

Translation units represent file-level code structures, and the system expects at least one to exist. If no translation unit is found, it indicates a problem with the CPG data or the extraction/conversion process. Rather than silently continuing with invalid data, the system throws a clear error. This fail-fast approach helps identify data quality issues early.

**Nested Value Wrappers**:

The CPG format uses JSON-LD wrappers that can be nested multiple levels deep. The unwrapper handles this by recursively unwrapping until it finds a primitive value. This recursive approach:

- Handles arbitrary nesting depth (CPG might wrap values multiple times)
- Works with arrays (unwraps array elements)
- Provides fallbacks (returns undefined if unwrapping fails)

This robust unwrapping ensures that the system can handle CPG data regardless of how deeply values are wrapped.

### Graceful Degradation

The module is designed with a philosophy of graceful degradation - when data is incomplete or malformed, the system handles it gracefully rather than failing completely. This approach includes:

- **Missing Properties**: Default to empty strings or undefined rather than causing errors
- **Invalid Nodes**: Remove them and preserve their children rather than failing
- **Type Inference**: Provide fallbacks when explicit types aren't available
- **Edge Validation**: Prevent invalid graph structures from being created

This robust error handling ensures that the template module can process a wide variety of CPG inputs, from perfectly formed data to incomplete or malformed data. The system provides clear feedback when issues occur (through detailed error messages) while continuing processing when possible (through graceful degradation). This balance between robustness and error reporting makes the system reliable for production use while still providing useful debugging information when problems occur.

---

## Conclusion

The Template module serves as a critical transformation layer in the static software analysis pipeline, converting complex CPG representations into normalized, standardized template formats. Through its four-stage pipeline (extraction, conversion, post-processing, and flattening), it enables effective pattern matching, security analysis, and code generation.

The module's design emphasizes separation of concerns, configuration-driven mappings, and robust error handling, making it maintainable, extensible, and reliable. By providing a consistent intermediate representation, it enables various analysis tasks to work with a unified, normalized code structure.
