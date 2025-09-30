# DFG Processors Module

## Overview

The `processors` module contains the core processing components for the DFG (Data Flow Graph) extraction system. It implements a modular architecture where different aspects of DFG extraction are handled by specialized processors.

## Architecture

The processors follow a **pipeline pattern** where data flows through specialized processing stages:

```
Input AST → Initialization → Statement Processing → Guard Analysis → Output Generation
```

## Module Structure

### Core Processors

1. **InitializationProcessor** - Sets up the DFG and prepares data structures
2. **StatementProcessor** - Main coordinator for processing AST statements
3. **GuardMapProcessor** - Builds guard maps for control flow analysis
4. **AssignmentAnalysisProcessor** - Provides assignment analysis utilities
5. **OutputProcessor** - Generates the final DFG output

### StatementProcessor Sub-modules

The `StatementProcessor` contains specialized sub-processors:

- **GuardProcessor** - Handles guard analysis and edge creation
- **CallProcessor** - Processes function calls and sink analysis
- **AssignmentProcessor** - Handles assignment expressions
- **ControlFlowProcessor** - Processes control flow statements
- **DeclarationProcessor** - Handles variable declarations
- **EdgeManager** - Centralized edge creation and tracking

## Processing Pipeline

### 1. Initialization Phase

- **InitializationProcessor** processes input AST data
- Creates DFG node structure
- Builds essential mappings (sid2flat, id2orig)
- Sets up compatibility attributes

### 2. Statement Processing Phase

- **StatementProcessor** coordinates statement processing
- Delegates to specialized sub-processors
- Manages processing state
- Creates DEF→USE relationships

### 3. Guard Analysis Phase

- **GuardMapProcessor** builds guard maps
- Analyzes control flow statements
- Propagates guard information
- Prepares guard data for edge creation

### 4. Output Generation Phase

- **OutputProcessor** generates final output
- Creates node features
- Formats DEF→USE edges
- Calculates node degrees

## Key Features

### Modular Design

- **Separation of Concerns**: Each processor handles specific functionality
- **Easy Extension**: Simple to add new processors or modify existing ones
- **Clear Interfaces**: Well-defined interfaces between processors

### Robust Processing

- **Error Handling**: Comprehensive error handling throughout
- **State Management**: Centralized state management via ProcessingState
- **Edge Tracking**: Prevents duplicate edge creation

### Performance Optimized

- **Efficient Algorithms**: Optimized for large codebases
- **Memory Management**: Efficient memory usage patterns
- **Parallel Processing**: Designed for potential parallelization

## Usage

### Basic Usage

```python
from dfg.processors import (
    InitializationProcessor,
    StatementProcessor,
    GuardMapProcessor,
    OutputProcessor
)

# Initialize DFG
init_processor = InitializationProcessor(dfg_extractor)
init_processor.initialize_dfg(ast_json, ast_result, sink_mode)

# Build guard map
guard_processor = GuardMapProcessor(dfg_extractor)
guard_map = guard_processor.build_guard_map()

# Process statements
statement_processor = StatementProcessor(dfg_extractor, state)
statement_processor.process_all_statements(nodes)

# Generate output
output_processor = OutputProcessor(dfg_extractor)
final_output = output_processor.build_final_output(state, deg_in, deg_out)
```

### Advanced Usage

```python
# Custom processing with specific processors
from dfg.processors.StatementProcessor import (
    AssignmentProcessor,
    CallProcessor,
    ControlFlowProcessor
)

# Use individual processors
assignment_processor = AssignmentProcessor(dfg_extractor, state)
call_processor = CallProcessor(dfg_extractor, state)
control_processor = ControlFlowProcessor(dfg_extractor, state)
```

## Data Flow

### Input Data

- **AST JSON**: Abstract Syntax Tree in JSON format
- **AST Result**: Processed AST with additional metadata
- **Configuration**: Sink mode and other settings

### Intermediate Data

- **Processing State**: Centralized state management
- **Guard Map**: Guard information for all statements
- **Node Mappings**: Various ID and reference mappings

### Output Data

- **DFG Nodes**: Processed nodes with features
- **DFG Edges**: DEF→USE edges with guard information
- **Metadata**: Additional analysis information

## Error Handling

### Comprehensive Error Handling

- **Input Validation**: Validates input data integrity
- **Processing Errors**: Handles processing failures gracefully
- **State Recovery**: Maintains consistent state during errors
- **Debugging Support**: Provides detailed error information

### Error Types

- **Data Errors**: Malformed or missing input data
- **Processing Errors**: Errors during statement processing
- **State Errors**: Inconsistent processing state
- **Output Errors**: Errors during output generation

## Performance Considerations

### Optimization Strategies

- **Efficient Data Structures**: Optimized for DFG processing
- **Minimal Memory Overhead**: Efficient memory usage
- **Single-Pass Processing**: Where possible, processes data in single pass
- **Caching**: Caches frequently accessed data

### Scalability

- **Large Codebases**: Designed to handle large codebases
- **Memory Efficiency**: Optimized for memory usage
- **Processing Speed**: Optimized for processing speed

## Extension Points

### Adding New Processors

1. Create new processor class
2. Implement required interface methods
3. Add to processor initialization
4. Update processing pipeline

### Customizing Processing

1. Override processor methods
2. Add custom analysis logic
3. Implement custom state management
4. Add custom output formatting

## Dependencies

### Internal Dependencies

- **Constants**: Shared constants and keywords
- **Utils**: Utility functions and helpers
- **Debug**: Debugging and analysis tools

### External Dependencies

- **Python Standard Library**: Collections, typing, re
- **AST Data**: Input AST structures
- **Configuration**: Processing configuration

## Testing

### Unit Testing

- Each processor can be tested independently
- Mock data for testing individual components
- Comprehensive test coverage

### Integration Testing

- End-to-end processing pipeline testing
- Real AST data testing
- Performance testing

## Troubleshooting

### Common Issues

1. **Processing Errors**: Check input data format
2. **State Inconsistencies**: Verify state management
3. **Memory Issues**: Check data structure usage
4. **Performance Issues**: Profile processing pipeline

### Debug Tips

- Enable debug logging
- Use debugging tools
- Check intermediate results
- Validate data structures

## Related Documentation

- **StatementProcessor/README.md** - Statement processing details
- **InitializationProcessor/README.md** - Initialization details
- **OutputProcessor/README.md** - Output generation details
- **GuardMapProcessor/README.md** - Guard analysis details
- **AssignmentAnalysisProcessor/README.md** - Assignment analysis details

## Contributing

### Code Style

- Follow existing code patterns
- Add comprehensive documentation
- Include error handling
- Write unit tests

### Adding Features

- Design for modularity
- Consider performance impact
- Maintain backward compatibility
- Update documentation
