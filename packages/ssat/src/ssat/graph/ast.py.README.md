# AST Extractor V1.12 - Technical Documentation

## Table of Contents

1. [Overview](#overview)
2. [Execution Flow](#execution-flow)
3. [Component Responsibilities](#component-responsibilities)
4. [Data Transformations](#data-transformations)
5. [Node Types and Features](#node-types-and-features)
6. [Edge Types](#edge-types)
7. [Control Flow Handling](#control-flow-handling)
8. [Call Semantics and Flags](#call-semantics-and-flags)
9. [Integration with Pipeline](#integration-with-pipeline)

---

## Overview

The `ASTExtractorV1_12` class is responsible for transforming hierarchical Template JSON (function-level AST) into a flattened, statement-level graph representation suitable for Graph Neural Network (GNN) training. It extracts Abstract Syntax Tree (AST) information while preserving control flow relationships, guard conditions, and semantic annotations.

### The Problem Being Solved

Template JSON provides a hierarchical AST representation of code functions, but GNN models require:

- **Flattened Structure**: GNNs work better with flat node lists rather than deeply nested trees
- **Statement-Level Granularity**: Analysis needs to operate at the statement level (assignments, declarations, control statements) rather than expression level
- **Control Flow Preservation**: The relationships between control statements (if, for, while, switch) and their guarded blocks must be explicitly represented
- **Feature Extraction**: Each node needs numeric features that capture semantic information (node type, loop context, guard constraints, call semantics)

The AST extractor addresses these requirements by:

- **Flattening**: Converting hierarchical AST into a flat list of statement-level nodes
- **Edge Creation**: Creating three types of edges (parent-child, sibling, guard) to preserve structure and control flow
- **Feature Computation**: Extracting features for each node including type IDs, loop context, guard information, buffer declarations, and call semantics
- **Control Flow Handling**: Properly handling if/else, loops (for, while, do-while), and switch statements with guard edges

### What the Module Does

The `ASTExtractorV1_12` class:

1. **Initialization**: Takes Template JSON (function-level AST) and builds an index of all nodes by ID
2. **Flattening**: Processes the function body (`CompoundStatement`) and creates statement-level nodes
3. **Edge Creation**: Generates parent-child (PC), sibling (SB), and guard edges
4. **Feature Extraction**: Computes numeric features for each node suitable for GNN input
5. **Post-Processing**: Applies call semantics to control nodes and finalizes the graph structure

The output is a graph representation with:

- **Nodes**: Statement-level nodes with features (`sid`, `node_type`, `code`, `feat`, `debug`)
- **Edges**: Three edge families (`edges_ast_pc`, `edges_ast_sb`, `edges_ast_guard`)

---

## Execution Flow

### Initialization

When `ASTExtractorV1_12` is instantiated:

```python
def __init__(self, ast_json: Dict[str, Any], *,
             lift_pure_cond_calls: bool = False):
    self.ast = ast_json
    # Build id -> node map for quick lookup
    self.idmap: Dict[int, Dict[str, Any]] = {}
    self.parent: Dict[int, int] = {}

    # Recursively index all nodes
    def _idx(n, parent_id: Optional[int] = None):
        if isinstance(n, dict):
            nid = n.get('id')
            if isinstance(nid, int):
                self.idmap[nid] = n
                if isinstance(parent_id, int):
                    self.parent[nid] = parent_id
            for c in (n.get("children") or []):
                _idx(c, nid)

    _idx(self.ast)

    # Initialize result containers
    self.nodes: List[Dict[str,Any]] = []
    self.id2sid: Dict[int, int] = {}  # AST orig_id -> created sid
    self.edges_pc: List[Tuple[int,int,int]] = []  # (src, dst, 0)
    self.edges_sb: List[Tuple[int,int,int]] = []  # (src, dst, 1)
    self.edges_ast_guard: List[Dict[str,Any]] = []  # guard edges

    # Create FunctionEntry node (sid=0)
    self.nodes.append({
        "sid": 0,
        "node_type": "FunctionEntry",
        "code": f"<entry:{func_name}>",
        "feat": {...}  # Initial features
    })
```

**Step 1: AST Indexing**

The `_idx()` function recursively traverses the AST and builds:

- `idmap`: Maps original AST node IDs to node dictionaries for O(1) lookup
- `parent`: Maps node IDs to their parent IDs for navigation

**Step 2: Container Initialization**

The extractor initializes:

- `nodes`: List of flattened statement-level nodes
- `id2sid`: Mapping from original AST IDs to new sequential IDs (sid)
- `edges_pc`: Parent-child edges (hierarchical structure)
- `edges_sb`: Sibling edges (statement order)
- `edges_ast_guard`: Guard edges (control flow)

**Step 3: Function Entry Node**

A `FunctionEntry` node with `sid=0` is created as the root of the flattened graph.

### Main Extraction Process

When `run()` is called:

```python
def run(self) -> Dict[str,Any]:
    # 1. Emit parameter declarations as prologue
    self._emit_param_statements_prologue()

    # 2. Find function body (CompoundStatement)
    func_body = None
    for c in (self.ast.get("children") or []):
        if isinstance(c, dict) and c.get("nodeType") == "CompoundStatement":
            func_body = c
            break

    # 3. Process function body
    if func_body is not None:
        _first, _last = self._process_block(func_body, 0, {}, 0)

    # 4. Post-process control nodes
    self._postprocess_control_calls()

    # 5. Return flattened graph
    return {
        "nodes": self.nodes,
        "edges_ast_pc": self.edges_pc,
        "edges_ast_sb": self.edges_sb,
        "edges_ast_guard": self.edges_ast_guard
    }
```

**Step 1: Parameter Prologue**

The `_emit_param_statements_prologue()` function creates statement-level nodes for each function parameter, connected via PC and SB edges from the `FunctionEntry` node.

**Step 2: Body Processing**

The `_process_block()` function recursively processes the function body (`CompoundStatement`), creating nodes for each statement and connecting them with appropriate edges.

**Step 3: Post-Processing**

The `_postprocess_control_calls()` function applies call semantics to control nodes (if, for, while, switch) that contain function calls in their conditions.

**Step 4: Graph Return**

The flattened graph is returned with nodes and three edge families.

---

## Component Responsibilities

### Block Processing

**Primary Role**: Recursively processes `CompoundStatement` blocks and creates statement-level nodes.

**Key Responsibility**: The `_process_block()` function is the core of the flattening process. It traverses statements in a block, creates nodes, and connects them with PC, SB, and guard edges.

**How It Works**:

```python
def _process_block(self, block_node: Dict[str,Any], parent_sid: int,
                   active_guards: Dict[str, Dict[str,Any]], in_loop: int) -> Tuple[Optional[int], Optional[int]]:
    sb_prev: Optional[int] = None
    first_sid: Optional[int] = None

    for ch in (block_node.get("children") or []):
        t = ch.get("nodeType")

        # Handle nested blocks
        if t == "CompoundStatement":
            child_first, child_last = self._process_block(ch, parent_sid, dict(active_guards), in_loop)
            # Connect via SB edge
            if sb_prev is not None:
                self.edges_sb.append((sb_prev, child_first, 1))
            sb_prev = child_last
            continue

        # Handle control statements (if, for, while, switch)
        if t == "IfStatement":
            # Process if statement...
        elif t == "ForStatement":
            # Process for loop...
        # ... etc

        # Handle regular statements
        sid = self._make_node(...)
        self.edges_pc.append((parent_sid, sid, 0))
        if sb_prev is not None:
            self.edges_sb.append((sb_prev, sid, 1))
        sb_prev = sid

    return first_sid, sb_prev
```

The function:

1. Iterates through children of the block
2. Handles nested blocks recursively
3. Processes control statements (if, for, while, switch) with special logic
4. Creates nodes for regular statements
5. Connects nodes via PC (parent-child) and SB (sibling) edges
6. Returns the first and last statement IDs in the block

**Rationale**: The recursive block processing ensures that nested control structures are properly flattened while preserving their hierarchical relationships through PC edges and sequential order through SB edges.

### Node Creation

**Primary Role**: Creates statement-level nodes with features.

**Key Responsibility**: The `_make_node()` function creates a flattened node with all necessary features for GNN training.

**How It Works**:

```python
def _make_node(self, node_type: str, code: str, in_loop: int, is_loop: int,
               guard_lower: int, guard_upper: int, upper_norm: float,
               name_hint: str = "", orig_id: Optional[int] = None,
               debug_extra: dict | None = None) -> int:
    # Assign sequential ID
    sid = self.sid_counter
    self.sid_counter += 1

    # Compute call semantics for call nodes
    if node_type in {"StandardLibCall","UserDefinedCall","CallExpression"}:
        call_sem_cat_id = call_sem_cat_id_from_name(name_hint)
        call_flags = self.compute_call_flags(fname=name_hint, call_ast=call_ast, code=code)
    else:
        call_sem_cat_id = 0
        call_flags = self._zero_call_flags()

    # Compute buffer declaration features
    is_buf_decl = 1 if node_type == "ArrayDeclaration" else 0
    if is_buf_decl:
        buf_state, buf_norm = parse_array_size_state_and_norm(code)
    else:
        buf_state, buf_norm = (0, 0.0)

    # Compute guard context strength
    ctx_strength = (1 if guard_lower else 0) + (2 if guard_upper else 0)

    # Training mask (exclude break/continue from training)
    train_mask = 0 if node_type in {"BreakStatement","ContinueStatement"} else 1

    # Build feature dictionary
    feat = {
        "node_type_id": _node_type_id(node_type),
        "train_mask": train_mask,
        "in_loop": in_loop,
        "is_loop": is_loop,
        "ctx_guard_strength": ctx_strength,
        "ctx_upper_bound_norm": (upper_norm if guard_upper else 0.0),
        "is_buffer_decl": is_buf_decl,
        "buffer_size_state": buf_state,
        "buffer_size_norm": buf_norm,
        "call_sem_cat_id": call_sem_cat_id,
        # ... call flags ...
    }

    # Create node
    row = {
        "sid": sid,
        "node_type": node_type,
        "code": code,
        "orig_id": orig_id,
        "feat": feat,
    }
    if debug_extra:
        row["debug"] = dict(debug_extra)

    self.nodes.append(row)
    if isinstance(orig_id, int):
        self.id2sid[orig_id] = sid

    return sid
```

The function:

1. Assigns a sequential ID (`sid`) to the node
2. Computes call semantics and flags for call nodes
3. Extracts buffer declaration features for array declarations
4. Computes guard context strength from active guards
5. Sets training mask (excludes break/continue from training)
6. Builds the feature dictionary with all numeric features
7. Creates the node dictionary and appends it to `self.nodes`
8. Maps original AST ID to new sequential ID

**Rationale**: Centralizing node creation ensures consistent feature extraction and allows easy modification of the feature set. The separation of training features (`feat`) and debug information (`debug`) keeps the graph representation clean for GNN input.

### Control Flow Handling

**Primary Role**: Processes control statements (if, for, while, switch) and creates guard edges.

**Key Responsibility**: Control statements require special handling to create guard edges that connect the control node to the first statement in each branch.

**If Statement Processing**:

```python
if t == "IfStatement":
    kids = ch.get("children", []) or []
    cond = kids[0]  # Condition
    then_block = kids[1]  # Then block
    else_block = kids[2]  # Else block (optional)

    # Lift calls from condition if needed
    if self.LIFT_PURE_COND_CALLS:
        sb_prev, _lifted_sid = self._maybe_lift_call_in_condition(...)

    # Create IfStatement node
    cond_code = cond.get("code","")
    sid_if = self._make_node("IfStatement", cond_code, in_loop, 0, 0, 0, 0.0)
    self.edges_pc.append((parent_sid, sid_if, 0))
    if sb_prev is not None:
        self.edges_sb.append((sb_prev, sid_if, 1))

    # Extract guard constraints from condition
    cond_guards = self._guards_from_condition_ast(cond)

    # Process then block
    if then_block is not None:
        then_first, _then_last = self._process_block(then_block, sid_if,
                                                     _push_guards(active_guards, cond_guards), in_loop)
        if then_first is not None:
            _emit_guard(sid_if, then_first, 1, 0)  # guard_kind=1 (if), branch=0 (then)

    # Process else block
    if else_block is not None:
        else_first, _else_last = self._process_block(else_block, sid_if,
                                                     dict(active_guards), in_loop)
        if else_first is not None:
            _emit_guard(sid_if, else_first, 1, 1)  # guard_kind=1 (if), branch=1 (else)
```

**For Loop Processing**:

```python
elif t == "ForStatement":
    kids = ch.get("children", []) or []
    init = kids[0]  # Initialization
    cond = kids[1]  # Condition
    inc = kids[2]  # Increment
    body = kids[3]  # Body

    # Extract guard constraints from for header
    for_guards = self._guards_from_for_header(ch)

    # Create ForStatement node
    cond_code = self._extract_for_condition_code(ch)
    sid_for = self._make_node("ForStatement", cond_code, in_loop, 1, ...)

    # Process body with loop context
    body_first, _body_last = self._process_block(body, sid_for,
                                                  _push_guards(active_guards, for_guards), 1)
    if body_first is not None:
        _emit_guard(sid_for, body_first, 2, 2)  # guard_kind=2 (loop), branch=2
```

**Switch Statement Processing**:

```python
elif t == "SwitchStatement":
    kids = ch.get("children", []) or []
    cond = kids[0]  # Switch expression
    body = kids[1]  # Switch body (contains CaseLabel/DefaultLabel)

    # Create SwitchStatement node
    cond_code = self._extract_switch_condition_code(ch)
    sid_sw = self._make_node("SwitchStatement", cond_code, in_loop, 0, ...)

    # Process switch body (contains case labels)
    switch_body = self._find_switch_body(ch)
    if switch_body is not None:
        # Process each case label
        for case_ch in (switch_body.get("children") or []):
            if case_ch.get("nodeType") == "CaseLabel":
                case_first, _case_last = self._process_case_block(
                    label_node=case_ch, switch_sid=sid_sw, ...)
                if case_first is not None:
                    case_label = self._normalize_case_label(case_ch)
                    _emit_guard(sid_sw, case_first, 4, case_label)  # guard_kind=4 (switch)
```

**Rationale**: Control statements require guard edges to explicitly represent which statements are guarded by which conditions. This enables GNNs to learn patterns about how control flow affects vulnerability detection. The guard edges encode both the type of control (if, loop, switch) and the specific branch (then/else, loop body, case label).

### Guard Edge Emission

**Primary Role**: Creates guard edges connecting control nodes to guarded statements.

**Key Responsibility**: The `_emit_guard()` function creates guard edges with appropriate `guard_kind` and `guard_branch` values.

**How It Works**:

```python
def _emit_guard(src_sid: int, dst_sid: int, guard_kind: int, branch_label: Any):
    """
    guard_kind: 1=if, 2=loop, 4=switch
    branch_label: if → 0(then)/1(else), loop → 2, switch → case label
    """
    mode = getattr(self, "SWITCH_BRANCH_MODE", "int")  # "int" | "label"
    gb = branch_label

    edge = {"src": src_sid, "dst": dst_sid, "edge_type": 2, "guard_kind": guard_kind}

    if guard_kind == 4 and mode == "int":
        # Switch: convert label to integer
        if branch_label == "default":
            gb = -1
        else:
            try:
                gb = self._parse_case_int(str(branch_label), src_sid)
            except Exception:
                # Fallback mapping
                m = self._switch_case_fallback.setdefault(src_sid, {})
                if branch_label not in m:
                    m[branch_label] = len(m)
                gb = m[branch_label]
        edge["guard_branch"] = gb
        edge.setdefault("debug", {})["guard_label"] = str(branch_label)
    else:
        # if/loop or label mode
        edge["guard_branch"] = gb

    self.edges_ast_guard.append(edge)
```

**Guard Kinds**:

- `1`: If statement (branch: 0=then, 1=else)
- `2`: Loop (for, while, do-while) (branch: 2)
- `4`: Switch statement (branch: case label as integer or string)

**Rationale**: Guard edges explicitly encode control flow relationships, allowing GNNs to understand which statements are conditionally executed. The `guard_kind` distinguishes between different types of control, while `guard_branch` identifies the specific branch.

---

## Data Transformations

### Template JSON → Flattened Graph

**Input Structure** (Template JSON):

```json
{
  "id": 123,
  "name": "vulnerable_function",
  "nodeType": "FunctionDefinition",
  "code": "void vulnerable_function(char *input) { ... }",
  "children": [
    {
      "id": 124,
      "nodeType": "ParameterList",
      "children": [...]
    },
    {
      "id": 125,
      "nodeType": "CompoundStatement",
      "children": [
        {
          "id": 126,
          "nodeType": "IfStatement",
          "code": "if (condition) { ... }",
          "children": [...]
        },
        ...
      ]
    }
  ]
}
```

**Transformation Process**:

1. **Indexing**: All nodes are indexed by ID for O(1) lookup
2. **Flattening**: Hierarchical structure is flattened into statement-level nodes
3. **Edge Creation**: Three edge types are created to preserve structure and control flow
4. **Feature Extraction**: Numeric features are computed for each node

**Output Structure** (Flattened Graph):

```json
{
  "nodes": [
    {
      "sid": 0,
      "node_type": "FunctionEntry",
      "code": "<entry:vulnerable_function>",
      "feat": {
        "node_type_id": 1,
        "train_mask": 1,
        "in_loop": 0,
        "is_loop": 0,
        ...
      }
    },
    {
      "sid": 1,
      "node_type": "IfStatement",
      "code": "condition",
      "feat": {...}
    },
    ...
  ],
  "edges_ast_pc": [[0, 1, 0], [1, 2, 0], ...],
  "edges_ast_sb": [[1, 3, 1], [3, 5, 1], ...],
  "edges_ast_guard": [
    {"src": 1, "dst": 2, "edge_type": 2, "guard_kind": 1, "guard_branch": 0},
    ...
  ]
}
```

### Node Feature Extraction

Each node's `feat` dictionary contains:

**Basic Features**:

- `node_type_id`: Integer ID for the node type (1=FunctionEntry, 3=VariableDeclaration, etc.)
- `train_mask`: 1 for training, 0 for debug-only nodes (break/continue)

**Context Features**:

- `in_loop`: 1 if node is inside a loop, 0 otherwise
- `is_loop`: 1 if node is a loop statement itself, 0 otherwise
- `ctx_guard_strength`: Strength of active guard constraints (0=none, 1=lower, 2=upper, 3=both)
- `ctx_upper_bound_norm`: Normalized upper bound from guard constraints (0.0 to 1.0)

**Buffer Declaration Features**:

- `is_buffer_decl`: 1 if node is an array declaration, 0 otherwise
- `buffer_size_state`: 0=NA, 1=CONST, 2=NONCONST
- `buffer_size_norm`: Normalized buffer size (0.0 to 1.0) for constant sizes

**Call Semantics Features**:

- `call_sem_cat_id`: Semantic category ID (0=none, 1=mem_alloc, 2=mem_copy, etc.)
- `call_flag_danger_unbounded`: 1 if call is unbounded (e.g., `strcpy` without size)
- `call_flag_len_linked_to_dst`: 1 if size argument uses `sizeof(dst)`
- `call_flag_sizeof_non_dst`: 1 if `sizeof` is used but not linked to destination
- `call_flag_has_varargs`: 1 if call has variable arguments
- `call_dst_is_field`: 1 if destination is a struct field
- `call_size_kind`: 0=none, 1=literal, 2=non-const, 3=sizeof only, 4=sizeof in expression
- `call_len_linked_to_dst_extended`: Extended version of len-linked check
- `call_size_is_sizeof_base_struct`: 1 if size is `sizeof(base_struct)`
- `call_size_mismatch_field`: 1 if size doesn't match field size
- `alloc_sizeof_state`: State for allocation size analysis

---

## Node Types and Features

### Supported Node Types

The extractor processes the following statement-level node types (defined in `KEEP_TYPES`):

**Declarations**:

- `VariableDeclaration`: Variable declaration (e.g., `int x;`)
- `ArrayDeclaration`: Array declaration (e.g., `char buf[100];`)
- `PointerDeclaration`: Pointer declaration (e.g., `char *p;`)
- `ParameterDeclaration`: Function parameter declaration

**Expressions**:

- `AssignmentExpression`: Assignment statement (e.g., `x = 5;`)

**Control Statements**:

- `IfStatement`: If statement
- `ForStatement`: For loop
- `WhileStatement`: While loop
- `DoWhileStatement`: Do-while loop
- `SwitchStatement`: Switch statement

**Control Flow** (debug-only, `train_mask=0`):

- `BreakStatement`: Break statement
- `ContinueStatement`: Continue statement

**Function Calls**:

- `StandardLibCall`: Standard library function call
- `UserDefinedCall`: User-defined function call
- `CallExpression`: Generic call expression

### Node Type IDs

Node types are mapped to integer IDs for GNN embedding:

```python
NODE_TYPE_ID = {
    "FunctionEntry": 1,
    "ParameterDeclaration": 2,
    "VariableDeclaration": 3,
    "ArrayDeclaration": 4,
    "PointerDeclaration": 5,
    "AssignmentExpression": 6,
    "IfStatement": 10,
    "ForStatement": 11,
    "WhileStatement": 12,
    "DoWhileStatement": 13,
    "SwitchStatement": 14,
    "BreakStatement": 20,
    "ContinueStatement": 21,
    "StandardLibCall": 30,
    "UserDefinedCall": 31,
    "CallExpression": 32,
}
```

**Rationale**: Integer IDs allow GNNs to use embedding layers for node types. The IDs are grouped by category (declarations, control, calls) to enable the model to learn type-based patterns.

---

## Edge Types

The extractor creates three types of edges:

### Parent-Child Edges (`edges_ast_pc`)

**Format**: `(parent_sid, child_sid, 0)`

**Purpose**: Preserves hierarchical structure from the original AST.

**Examples**:

- `FunctionEntry` → `ParameterDeclaration`
- `IfStatement` → statements in then/else blocks
- `ForStatement` → statements in loop body

**Rationale**: PC edges allow GNNs to understand the hierarchical structure of code, which is important for understanding scope and nesting.

### Sibling Edges (`edges_ast_sb`)

**Format**: `(prev_sid, next_sid, 1)`

**Purpose**: Represents sequential statement order within a block.

**Examples**:

- Statement 1 → Statement 2 → Statement 3 (sequential execution)
- Parameter 1 → Parameter 2 → Parameter 3 (parameter order)

**Rationale**: SB edges encode the execution order of statements, which is crucial for understanding data flow and control flow sequences.

### Guard Edges (`edges_ast_guard`)

**Format**: `{"src": control_sid, "dst": guarded_sid, "edge_type": 2, "guard_kind": kind, "guard_branch": branch}`

**Purpose**: Explicitly connects control statements to the statements they guard.

**Guard Kinds**:

- `1`: If statement
  - `guard_branch`: 0=then, 1=else
- `2`: Loop (for, while, do-while)
  - `guard_branch`: 2
- `4`: Switch statement
  - `guard_branch`: case label as integer (or string in label mode)

**Examples**:

- `IfStatement` → first statement in then block (guard_kind=1, guard_branch=0)
- `IfStatement` → first statement in else block (guard_kind=1, guard_branch=1)
- `ForStatement` → first statement in loop body (guard_kind=2, guard_branch=2)
- `SwitchStatement` → first statement in case block (guard_kind=4, guard_branch=case_value)

**Rationale**: Guard edges explicitly encode conditional execution relationships, enabling GNNs to learn patterns about how control flow affects vulnerability detection. For example, a buffer overflow might be safe if guarded by a size check.

---

## Control Flow Handling

### If Statements

If statements are processed with special handling for guard extraction and branch creation:

```python
if t == "IfStatement":
    kids = ch.get("children", []) or []
    cond = kids[0]  # Condition expression
    then_block = kids[1]  # Then block
    else_block = kids[2]  # Else block (optional)

    # Optionally lift calls from condition
    if self.LIFT_PURE_COND_CALLS:
        sb_prev, _lifted_sid = self._maybe_lift_call_in_condition(...)

    # Create IfStatement node (condition code only)
    cond_code = cond.get("code","")
    sid_if = self._make_node("IfStatement", cond_code, in_loop, 0, ...)

    # Extract guard constraints from condition
    cond_guards = self._guards_from_condition_ast(cond)

    # Process then block with updated guards
    then_first, _then_last = self._process_block(then_block, sid_if,
                                                  _push_guards(active_guards, cond_guards), in_loop)
    if then_first is not None:
        _emit_guard(sid_if, then_first, 1, 0)  # then branch

    # Process else block
    if else_block is not None:
        else_first, _else_last = self._process_block(else_block, sid_if,
                                                      dict(active_guards), in_loop)
        if else_first is not None:
            _emit_guard(sid_if, else_first, 1, 1)  # else branch
```

**Guard Extraction**: The `_guards_from_condition_ast()` function extracts constraint information from the condition (e.g., `x < 100` → upper bound constraint on `x`).

**Rationale**: If statements create two guarded paths (then and else), and guard edges explicitly connect the if node to the first statement in each branch. Guard constraints are propagated to the then block to enable constraint-aware analysis.

### Loops (For, While, Do-While)

Loops are processed with loop context tracking:

```python
elif t == "ForStatement":
    kids = ch.get("children", []) or []
    init = kids[0]  # Initialization
    cond = kids[1]  # Condition
    inc = kids[2]  # Increment
    body = kids[3]  # Body

    # Extract guard constraints from for header
    for_guards = self._guards_from_for_header(ch)

    # Create ForStatement node
    cond_code = self._extract_for_condition_code(ch)
    sid_for = self._make_node("ForStatement", cond_code, in_loop, 1, ...)

    # Process body with loop context (in_loop=1)
    body_first, _body_last = self._process_block(body, sid_for,
                                                  _push_guards(active_guards, for_guards), 1)
    if body_first is not None:
        _emit_guard(sid_for, body_first, 2, 2)  # loop guard
```

**Loop Context**: Nodes inside loops have `in_loop=1`, and loop statements themselves have `is_loop=1`. This allows GNNs to distinguish loop-related patterns.

**Rationale**: Loops create a single guarded path (the loop body), and guard edges connect the loop node to the first statement in the body. Guard constraints from the loop condition are propagated to enable loop-aware analysis.

### Switch Statements

Switch statements require special handling for case labels:

```python
elif t == "SwitchStatement":
    kids = ch.get("children", []) or []
    cond = kids[0]  # Switch expression
    body = kids[1]  # Switch body

    # Create SwitchStatement node
    cond_code = self._extract_switch_condition_code(ch)
    sid_sw = self._make_node("SwitchStatement", cond_code, in_loop, 0, ...)

    # Process switch body (contains CaseLabel/DefaultLabel nodes)
    switch_body = self._find_switch_body(ch)
    if switch_body is not None:
        for case_ch in (switch_body.get("children") or []):
            if case_ch.get("nodeType") == "CaseLabel":
                case_first, _case_last = self._process_case_block(
                    label_node=case_ch, switch_sid=sid_sw, ...)
                if case_first is not None:
                    case_label = self._normalize_case_label(case_ch)
                    _emit_guard(sid_sw, case_first, 4, case_label)  # switch guard
```

**Case Label Processing**: The `_process_case_block()` function processes each case label and its associated statements, creating guard edges from the switch node to the first statement in each case.

**Label Encoding**: Case labels can be encoded as integers (default) or strings (debug mode). Integer encoding allows GNNs to learn numeric patterns in switch cases.

**Rationale**: Switch statements create multiple guarded paths (one per case), and guard edges explicitly connect the switch node to the first statement in each case. This enables GNNs to learn patterns about switch-based control flow.

---

## Call Semantics and Flags

### Call Semantic Categories

Function calls are categorized into semantic categories for vulnerability analysis:

```python
CALL_SEM_ID = {
    "none": 0,
    "mem_alloc": 1,      # Memory allocation (malloc, calloc, etc.)
    "mem_copy": 2,       # Memory/string copy (memcpy, strcpy, etc.)
    "ext_input": 3,      # External input (gets, scanf, read, etc.)
    "format_print": 4,  # Format string output (sprintf, printf, etc.)
    "mem_set": 5,        # Memory set (memset, bzero, etc.)
    "net_connect": 6,    # Network connect
    "net_close": 7,      # Network close
    "socket_create": 8,  # Socket creation
    "parse_int_unchecked": 9,   # Unchecked integer parsing (atoi, etc.)
    "parse_int_checked": 10,    # Checked integer parsing (strtol, etc.)
}
```

**Category Mapping**: The `call_sem_cat_id_from_name()` function maps function names to category IDs using a priority-based lookup table.

**Rationale**: Semantic categories enable GNNs to learn patterns about different types of function calls. For example, `mem_copy` calls are often sources of buffer overflows, while `ext_input` calls are sources of tainted data.

### Call Flag Computation

The `compute_call_flags()` function computes detailed flags about function calls:

```python
def compute_call_flags(self, fname: str | None = None,
                   call_ast: dict | None = None,
                   code: str | None = None) -> Dict[str, int]:
    flags = {
        "call_flag_danger_unbounded": 0,      # Unbounded call (e.g., strcpy)
        "call_flag_len_linked_to_dst": 0,     # Size uses sizeof(dst)
        "call_flag_sizeof_non_dst": 0,        # sizeof used but not linked to dst
        "call_flag_has_varargs": 0,           # Variable arguments
        "call_dst_is_field": 0,               # Destination is struct field
        "call_size_kind": 0,                  # Size argument kind
        "call_len_linked_to_dst_extended": 0, # Extended len-linked check
        "call_size_is_sizeof_base_struct": 0,  # Size is sizeof(base_struct)
        "call_size_mismatch_field": 0,        # Size mismatch with field
        "alloc_sizeof_state": 0,              # Allocation size state
    }

    # Compute flags based on AST and code analysis
    # ...

    return flags
```

**Flag Computation**:

1. **Unbounded Detection**: Checks if call is in `UNBOUNDED_CALLS` set (e.g., `strcpy`, `gets`)
2. **Size Analysis**: Analyzes size arguments to determine if they use `sizeof(dst)` or other patterns
3. **Field Sensitivity**: Checks if destination is a struct field (`base.field` or `base->field`)
4. **Size Kind**: Classifies size argument as literal, non-const, sizeof-only, or sizeof-in-expression

**Rationale**: Call flags provide detailed information about function calls that is crucial for vulnerability detection. For example, unbounded calls are dangerous, while calls with `sizeof(dst)` size arguments are often safe.

### Call Lifting from Conditions

When `lift_pure_cond_calls=True`, calls in condition expressions are "lifted" to separate statement nodes:

```python
def _maybe_lift_call_in_condition(self, parent_sid: int, sb_prev: int | None,
                                   in_loop: int, cond_node: dict) -> Tuple[int | None, int | None]:
    # Find first call in condition
    call_node = self._find_first_call_node(cond_node)
    if call_node is None:
        return sb_prev, None

    # Check if call is "liftable" (pure function, no side effects)
    # ...

    # Create lifted call node
    lifted_sid = self._make_node("StandardLibCall", call_code, in_loop, 0, ...)
    self.edges_pc.append((parent_sid, lifted_sid, 0))
    if sb_prev is not None:
        self.edges_sb.append((sb_prev, lifted_sid, 1))

    return lifted_sid, lifted_sid
```

**Rationale**: Lifting calls from conditions makes them explicit statement nodes, enabling better analysis of their effects. This is particularly useful for calls like `strlen()` that are often used in conditions.

---

## Integration with Pipeline

### Input Format

The extractor expects Template JSON (function-level AST) as input:

```json
{
  "id": 123,
  "name": "function_name",
  "nodeType": "FunctionDefinition",
  "code": "void function_name(int x) { ... }",
  "children": [
    {"nodeType": "ParameterList", "children": [...]},
    {"nodeType": "CompoundStatement", "children": [...]}
  ]
}
```

### Output Format

The extractor returns a flattened graph:

```json
{
  "nodes": [
    {"sid": 0, "node_type": "FunctionEntry", "code": "...", "feat": {...}},
    {"sid": 1, "node_type": "IfStatement", "code": "...", "feat": {...}},
    ...
  ],
  "edges_ast_pc": [[0, 1, 0], [1, 2, 0], ...],
  "edges_ast_sb": [[1, 3, 1], [3, 5, 1], ...],
  "edges_ast_guard": [
    {"src": 1, "dst": 2, "edge_type": 2, "guard_kind": 1, "guard_branch": 0},
    ...
  ]
}
```

### Usage in Pipeline

The extractor is used in the graph package's CLI:

```python
# packages/graph/src/graph/__init__.py
from graph.ast import ASTExtractorV1_12

# Extract AST for a function
ast_ext = ASTExtractorV1_12(function)
ast_result = ast_ext.run()

# ast_result is then used for DFG extraction
dfg_ext = DFGExtractorV1_12(function, ast_result, sink_mode="k1")
dfg_result = dfg_ext.run()
```

**Rationale**: The AST extractor is the first step in the graph extraction pipeline. Its output (flattened AST) is used by the DFG extractor to build data flow graphs, and both are combined into the final graph representation for GNN training.

---

## Conclusion

The `ASTExtractorV1_12` class provides a comprehensive solution for transforming hierarchical Template JSON into flattened, statement-level graph representations suitable for GNN training. Its design emphasizes:

- **Flattening**: Converting nested AST structures into flat node lists
- **Edge Preservation**: Maintaining structure (PC), order (SB), and control flow (guard) through explicit edges
- **Feature Extraction**: Computing rich numeric features for each node
- **Control Flow Handling**: Properly processing if, loops, and switch statements with guard edges
- **Call Semantics**: Categorizing and analyzing function calls for vulnerability detection

The extractor's output enables GNNs to learn patterns about code structure, control flow, and semantic operations, making it a critical component of the vulnerability detection pipeline.
