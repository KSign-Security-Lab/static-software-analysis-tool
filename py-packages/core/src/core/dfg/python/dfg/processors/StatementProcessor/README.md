# StatementProcessor Module

## Overview

The `StatementProcessor` module is the central coordinator for processing different types of AST statements in the DFG extraction process. It delegates specific statement processing tasks to specialized sub-processors and manages the overall processing state.

## Architecture

This module follows a **coordinator pattern** where the main `StatementProcessor` class orchestrates the work of specialized processors:

- **StatementProcessor** - Main coordinator class
- **ProcessingState** - Centralized state management
- **Specialized Sub-processors** - Handle specific statement types

## Components

### StatementProcessor Class

**Purpose**: Main coordinator that processes all AST nodes and delegates to specialized processors.

**Key Responsibilities**:

- Process all AST nodes in sequence
- Delegate specific statement types to appropriate sub-processors
- Manage the overall processing flow
- Coordinate between different processors

**Main Methods**:

- `process_all_statements()` - Main processing loop
- `_process_single_statement()` - Process individual statements
- `_process_parameters()` - Handle function parameters
- `_check_assignment_rhs_call()` - Check for function calls in assignments

### ProcessingState Class

**Purpose**: Centralized state management for the entire DFG processing pipeline.

**Key Data Structures**:

- `last_def` - Tracks last definition of each variable
- `seen_edges` - Prevents duplicate edge creation
- `use_vars_by_sid` - Variables used in each statement
- `def_vars_by_sid` - Variables defined in each statement
- `iba_by_sid` - Buffer access tracking
- `is_sink_by_sid` - Sink detection tracking

### Sub-processors

The module delegates to these specialized processors:

1. **GuardProcessor** - Handles guard analysis and edge creation
2. **CallProcessor** - Processes function calls and sink analysis
3. **AssignmentProcessor** - Handles assignment expressions
4. **ControlFlowProcessor** - Processes control flow statements
5. **DeclarationProcessor** - Handles variable declarations
6. **EdgeManager** - Centralized edge creation and tracking

## Usage

```python
from dfg.processors.StatementProcessor import StatementProcessor, ProcessingState

# Create processing state
state = ProcessingState()

# Create statement processor
processor = StatementProcessor(dfg_extractor, state)

# Process all statements
processor.process_all_statements(nodes)
```

## Processing Flow

1. **Initialization**: Set up processors and edge manager
2. **Parameter Processing**: Handle function parameters as initial DEFs
3. **Statement Loop**: Process each AST node in sequence
4. **Statement Classification**: Determine statement type and delegate
5. **State Updates**: Update processing state with DEF/USE information
6. **Edge Creation**: Create DEF→USE edges through EdgeManager

## Statement Types Handled

- **AssignmentExpression** → AssignmentProcessor
- **CallExpression** → CallProcessor
- **IfStatement** → ControlFlowProcessor
- **ForStatement** → ControlFlowProcessor
- **WhileStatement** → ControlFlowProcessor
- **DeclStmt** → DeclarationProcessor
- **VarDecl** → DeclarationProcessor
- **ArrayDecl** → DeclarationProcessor

## Dependencies

- **GuardProcessor** - For guard analysis and edge creation
- **CallProcessor** - For function call processing
- **AssignmentProcessor** - For assignment analysis
- **ControlFlowProcessor** - For control flow handling
- **DeclarationProcessor** - For declaration processing
- **EdgeManager** - For centralized edge management

## Key Features

- **Centralized State Management**: All processing state in one place
- **Modular Design**: Easy to add new statement types
- **Edge Tracking**: Prevents duplicate edge creation
- **Guard Integration**: Seamless guard information handling
- **Error Handling**: Robust error handling for malformed AST

## Error Handling

The module includes comprehensive error handling:

- Malformed AST node handling
- Missing statement type handling
- Invalid variable name filtering
- Edge creation error recovery

## Performance Considerations

- **Efficient State Updates**: Minimal overhead for state management
- **Edge Deduplication**: Prevents expensive duplicate edge creation
- **Lazy Processing**: Only processes relevant statement types
- **Memory Efficient**: Reuses state objects across processing

## Extension Points

To add support for new statement types:

1. Create a new specialized processor
2. Add statement type detection in `_process_single_statement()`
3. Delegate to the new processor
4. Update the processor initialization

## Related Modules

- **InitializationProcessor** - Sets up the DFG before processing
- **OutputProcessor** - Generates final output after processing
- **GuardMapProcessor** - Builds guard information for edge creation
- **AssignmentAnalysisProcessor** - Provides assignment analysis utilities
