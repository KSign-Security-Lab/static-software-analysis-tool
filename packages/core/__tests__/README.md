# DFG Test Package

This package provides Jest-based testing for DFG (Data Flow Graph) generation and related functionality.

## Features

- **Jest Test Suite**: Test cases for DFG-related functionality
- **Type Validation**: Tests for data structure validation
- **Core Integration**: Tests TypeScript DFG generation
- **Mock Data**: Test cases with proper data structures

## Installation

```bash
# Install dependencies
npm install

# Build the package
npm run build
```

## Usage

### Running Tests with Jest

```bash
# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage
```

### Running Tests

```bash
# Run Jest tests
npm test

# Run tests with coverage
npm run test:coverage

# Run tests in watch mode
npm run test:watch
```

### Running via CLI

```bash
# Run tests via CLI (from project root)
yarn workspace @ssat/cli test

# Run with verbose output
yarn workspace @ssat/cli test --verbose

# Run with custom Python path
yarn workspace @ssat/cli test --python-path /usr/bin/python3
```

## Test Case Format

Test cases should follow this structure:

```typescript
interface TestCase {
  name: string; // Test case name
  cpg: CPGRoot; // CPG data for core DFG generation
  astNodeIds: number[][]; // AST node IDs for each function
  templates: TemplateNodes[]; // Template nodes
  astJson: any; // AST JSON for Python extractor
  astResult: any; // AST result data for Python extractor
  sinkMode?: string; // Sink mode (default: 'k1')
}
```

## Comparison Features

The test runner compares:

### Node Features

- `nodeType` / `node_type_id`
- `inDegreeDFG` / `in_degree_dfg`
- `outDegreeDFG` / `out_degree_dfg`
- `defCount` / `def_count`
- `useCount` / `use_count`
- Buffer access flags
- Sink assignment flags
- Call-related flags

### Edge Features

- Flow types (VALUE, INDEX, SIZE, BASE)
- Guard types (IF, LOOP, NONE, SWITCH)
- Guard flags (lower/upper bounds)
- Upper guard normalization values

## Requirements

- Node.js 16+
- Python 3.7+
- TypeScript 5.0+

## Python Environment

The test runner requires:

1. Python 3.7 or higher
2. The `DFGExtractor.py` file in the `dfg/` directory
3. All Python dependencies for the extractor

## Test Structure

```text
src/
├── __tests__/           # Jest test files
├── types/              # TypeScript type definitions
└── index.ts            # Package exports
```

## Contributing

1. Add new test cases in `src/__tests__/`
2. Update types in `src/types/DFGComparison.ts` as needed

## Troubleshooting

### Python Environment Issues

- Ensure Python 3.7+ is installed
- Check that `DFGExtractor.py` is accessible
- Verify all Python dependencies are installed

### Test Failures

- Check the generated report for detailed differences
- Verify test case data is correctly formatted
- Ensure both Python and Core implementations are working

### Build Issues

- Run `npm run clean` and `npm run build`
- Check TypeScript configuration
- Verify all dependencies are installed
