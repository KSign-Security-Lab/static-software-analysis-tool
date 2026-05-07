# GuardMapProcessor Module

## Overview

The `GuardMapProcessor` module handles the complex logic for building guard maps that analyze AST guard edges and propagate guard information to all relevant statements. This is crucial for accurate DEF→USE edge creation with proper guard context.

## Purpose

This module is responsible for:

- Analyzing AST guard edges from control flow statements
- Extracting variable-specific guard information (lower/upper bounds)
- Propagating guard information to all statements within guarded blocks
- Building comprehensive guard maps for edge creation
- Supporting If, For, While, and Switch statements

## Architecture

The module follows a **propagation pattern** where guard information flows through the control flow graph:

- **GuardMapProcessor** - Main guard analysis class
- **Guard Extraction** - Extracts guards from condition ASTs
- **Guard Propagation** - Spreads guards through control flow
- **Guard Mapping** - Creates comprehensive guard maps

## Components

### GuardMapProcessor Class

**Purpose**: Handles all guard map building and guard information propagation.

**Key Responsibilities**:

- Analyze AST guard edges
- Extract guard information from conditions
- Propagate guards through control flow
- Build comprehensive guard maps

**Main Methods**:

- `build_guard_map()` - Main guard map building
- `_get_next_sids()` - Find next statements for propagation
- `_extract_guards_from_condition()` - Extract guards from AST
- `_propagate_guards()` - Spread guards through blocks

## Usage

```python
from dfg.processors.GuardMapProcessor import GuardMapProcessor

# Create guard map processor
guard_processor = GuardMapProcessor(dfg_extractor)

# Build guard map
guard_map = guard_processor.build_guard_map()
```

## Guard Map Structure

The guard map is a nested dictionary structure:

```python
{
    dst_sid: {
        var_name: {
            "kind": int,           # Guard type (0=none, 1=if, 2=loop)
            "lower": int,          # Has lower bound guard (0/1)
            "upper": int,          # Has upper bound guard (0/1)
            "upper_const": float,  # Upper bound constant value
        },
        "*": { ... },             # Aggregate guards for all variables
        "__agg__": { ... },       # Same as "*" for compatibility
    }
}
```

## Guard Types

### 1. If Statement Guards

- **Kind**: 1
- **Scope**: Only applies to 'then' branch (guard_branch == 0)
- **Logic**: Does not apply inverse logic to 'else' branches
- **Example**: `if (x > 5)` → applies to then branch only

### 2. Loop Guards

- **Kind**: 2
- **Scope**: Applies to entire loop body
- **Logic**: Includes both condition and initializer guards
- **Example**: `for (i = 0; i < n; i++)` → applies to loop body

### 3. Switch Guards

- **Kind**: 0
- **Scope**: No variable guards (only kind is propagated)
- **Logic**: Only propagates guard kind, not variable bounds

## Guard Information Types

### Lower Bounds

- **Source**: Loop initializers, condition comparisons
- **Example**: `for (i = 0; ...)` → `i >= 0`
- **Detection**: Analyzes loop initializer expressions

### Upper Bounds

- **Source**: Condition comparisons, loop bounds
- **Example**: `for (...; i < n; ...)` → `i < n`
- **Detection**: Analyzes condition expressions

### Upper Constants

- **Source**: Numeric constants in conditions
- **Example**: `if (x < 10)` → `upper_const = 10.0`
- **Detection**: Extracts numeric values from conditions

## Processing Flow

### 1. Guard Edge Analysis

- Parse AST guard edges from input
- Group guards by source statement ID
- Extract guard metadata (branch, type, condition)

### 2. Guard Extraction

- Analyze condition AST for variable guards
- Extract lower/upper bound information
- Handle different statement types (If, For, While)

### 3. Guard Propagation

- Start from guard destination statements
- Follow SB (statement order) and PC (parent-child) edges
- Propagate guards to all reachable statements

### 4. Guard Mapping

- Create comprehensive guard map
- Merge overlapping guard information
- Apply guard kind and bounds to variables

## Key Features

### Comprehensive Guard Analysis

- **Multiple Statement Types**: If, For, While, Switch
- **Variable-Specific Guards**: Per-variable guard tracking
- **Aggregate Guards**: Fallback guards for all variables
- **Guard Merging**: Combines overlapping guard information

### Robust Propagation

- **Control Flow Following**: Uses SB and PC edges
- **Cycle Detection**: Prevents infinite propagation loops
- **Scope Management**: Proper guard scoping per statement type

### Flexible Guard Extraction

- **Condition Analysis**: Extracts guards from complex conditions
- **Loop Handling**: Special handling for For loop initializers
- **Numeric Extraction**: Extracts constants from conditions

## Guard Extraction Methods

### From Condition AST

- Analyzes comparison expressions
- Extracts variable bounds
- Handles complex boolean expressions

### From For Loop Headers

- Processes loop initializers
- Analyzes loop conditions
- Combines initializer and condition guards

### From Loop Initializers

- Extracts lower bounds from initializers
- Handles various initialization patterns
- Supports complex initializer expressions

## Error Handling

The module includes comprehensive error handling:

- **Malformed Guard Edges**: Skips invalid guard edges
- **Missing Condition AST**: Handles missing condition data
- **Propagation Errors**: Graceful handling of edge traversal errors
- **Type Errors**: Safe handling of type mismatches

## Performance Considerations

### Efficient Propagation

- **Breadth-First Traversal**: Uses deque for efficient propagation
- **Visited Tracking**: Prevents redundant processing
- **Early Termination**: Stops when no new statements found

### Memory Management

- **Incremental Building**: Builds guard map incrementally
- **Efficient Data Structures**: Uses defaultdict for efficient access
- **Minimal Overhead**: Optimized for large control flow graphs

## Configuration Options

### Guard Types

- Configurable guard type handling
- Custom guard extraction methods
- Flexible guard merging strategies

### Propagation Scope

- Configurable propagation depth
- Custom edge traversal strategies
- Scope-specific guard application

## Dependencies

- **AST Data**: Guard edges and condition ASTs
- **Constants**: KEYWORDS for variable filtering
- **DFG Extractor**: Parent extractor with utility methods

## Extension Points

### Custom Guard Types

- Add new statement type support
- Implement custom guard extraction
- Add new guard information types

### Propagation Strategies

- Custom propagation algorithms
- Alternative edge traversal methods
- Scope-specific propagation rules

## Related Modules

- **StatementProcessor** - Uses guard map for edge creation
- **EdgeManager** - Applies guard information to edges
- **InitializationProcessor** - Provides AST data
- **OutputProcessor** - Uses guard information in output

## Troubleshooting

### Common Issues

1. **Empty guard map**: Check AST guard edge data
2. **Missing guards**: Verify condition AST completeness
3. **Propagation errors**: Check SB/PC edge data integrity

### Debug Tips

- Enable guard extraction debugging
- Verify AST guard edge structure
- Check condition AST completeness
- Validate propagation traversal
