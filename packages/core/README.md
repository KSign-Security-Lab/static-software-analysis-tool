# @ssat/core

Core processing modules for the Static Software Analysis Tool (SSAT). This package provides the fundamental conversion functions for transforming C source code into various representations including Code Property Graphs (CPG), Templates, Abstract Syntax Trees (AST), and Data Flow Graphs (DFG).

## Features

- **CPG Generation**: Convert C source code to Code Property Graphs using Joern
- **Template Conversion**: Transform CPG data into KAST-style template representations
- **AST Generation**: Generate Abstract Syntax Trees from template data
- **DFG Generation**: Create Data Flow Graphs from template data
- **Standalone Functions**: Self-contained conversion functions without external dependencies
- **Type Safety**: Full TypeScript support with comprehensive type definitions
- **Validation**: Built-in validation for CPG data using Zod schemas

## Installation

```bash
# Install as dependency
npm install @ssat/core

# Or using yarn
yarn add @ssat/core
```

## API Reference

### Core Conversion Functions

#### `convertToCPG(cSource: string, options?: CPGOptions): Promise<CPGResult>`

Converts C source code to a Code Property Graph using Joern.

**Parameters:**

- `cSource`: C source code as string
- `options`: Optional configuration object

**Options:**

```typescript
interface CPGOptions {
  filename?: string; // Input filename (default: "main.c")
  projectName?: string; // Project name for Joern
  validateInput?: boolean; // Validate CPG data (default: true)
  cleanupTempFiles?: boolean; // Clean up temporary files (default: true)
}
```

**Returns:**

```typescript
interface CPGResult {
  cpgData: CPGRoot; // Generated CPG data
  projectName: string; // Used project name
  methodCount: number; // Number of methods found
}
```

**Example:**

```typescript
import { convertToCPG } from "@ssat/core";

const cSource = `
#include <stdio.h>
int main() {
    printf("Hello, World!");
    return 0;
}
`;

const result = await convertToCPG(cSource, {
  filename: "hello.c",
  projectName: "hello-project",
});

console.log(`Generated CPG with ${result.methodCount} methods`);
```

#### `convertToTemplate(cpgData: CPGRoot, options?: TemplateOptions): TemplateResult`

Converts CPG data to template representation.

**Parameters:**

- `cpgData`: CPG data from `convertToCPG`
- `options`: Optional configuration object

**Options:**

```typescript
interface TemplateOptions {
  validateInput?: boolean; // Validate input CPG (default: true)
  filename?: string; // Input filename
}
```

**Returns:**

```typescript
interface TemplateResult {
  templateTree: unknown[]; // Raw template tree
  templateResult: TemplateNodes[]; // Processed template nodes
}
```

#### `convertToAST(cpgData: CPGRoot, options?: ASTOptions): Promise<ASTResult>`

Generates Abstract Syntax Tree from CPG data.

**Parameters:**

- `cpgData`: CPG data from `convertToCPG`
- `options`: Optional configuration object

**Options:**

```typescript
interface ASTOptions {
  liftPureCondCalls?: boolean; // Lift pure conditional calls (default: false)
  validateInput?: boolean; // Validate input CPG (default: true)
  filename?: string; // Input filename
}
```

#### `convertToDFG(cpgData: CPGRoot, options?: DFGOptions): Promise<DFGResult>`

Generates Data Flow Graph from CPG data.

**Parameters:**

- `cpgData`: CPG data from `convertToCPG`
- `options`: Optional configuration object

**Options:**

```typescript
interface DFGOptions {
  astData?: IASTResult[]; // Pre-computed AST data
  validateInput?: boolean; // Validate input CPG (default: true)
  filename?: string; // Input filename
}
```

### Standalone Conversion Functions

For environments where external dependencies are not available:

#### `convertToCPGStandalone(cSource: string, options?: { filename?: string }): Promise<StandaloneCPGResult>`

Standalone CPG conversion without external dependencies.

#### `convertToTemplateStandalone(): StandaloneTemplateResult`

Standalone template conversion (returns mock data).

#### `convertToDFGStandalone(): StandaloneDFGResult`

Standalone DFG conversion (returns mock data).

### Type Definitions

The package exports comprehensive TypeScript types:

```typescript
// Core types
export type { CPGRoot, ICPGRootExport } from "./types/cpg";
export type { TemplateNodes } from "./types/node";
export type { IASTResult } from "./types/ast";
export type { IDFGGraph } from "./types/dfg";

// Conversion options and results
export type { CPGOptions, CPGResult } from "./conversions/types";
export type { TemplateOptions, TemplateResult } from "./conversions/types";
export type { ASTOptions, ASTResult } from "./conversions/types";
export type { DFGOptions, DFGResult } from "./conversions/types";
```

## Dependencies

### Required External Tools

- **Joern 4.0.361**: For CPG generation
- **Python 3.x**: For AST server communication

### Node.js Dependencies

- `zod`: Runtime type validation
- `python-shell`: Python process communication

## Usage Examples

### Complete Pipeline

```typescript
import { convertToCPG, convertToTemplate, convertToAST, convertToDFG } from "@ssat/core";

async function processCFile(cSource: string) {
  // Step 1: Generate CPG
  const cpgResult = await convertToCPG(cSource, {
    filename: "input.c",
    projectName: "my-project",
  });

  // Step 2: Convert to Template
  const templateResult = convertToTemplate(cpgResult.cpgData, {
    validateInput: true,
  });

  // Step 3: Generate AST
  const astResult = await convertToAST(cpgResult.cpgData, {
    liftPureCondCalls: true,
  });

  // Step 4: Generate DFG
  const dfgResult = await convertToDFG(cpgResult.cpgData, {
    astData: astResult.astData,
  });

  return {
    cpg: cpgResult,
    template: templateResult,
    ast: astResult,
    dfg: dfgResult,
  };
}
```

### Error Handling

```typescript
import { convertToCPG } from "@ssat/core";

try {
  const result = await convertToCPG(cSource);
  console.log("CPG generated successfully");
} catch (error) {
  if (error.message.includes("joern-parse failed")) {
    console.error("Joern parsing failed:", error.message);
  } else if (error.message.includes("joern-export failed")) {
    console.error("Joern export failed:", error.message);
  } else {
    console.error("Unknown error:", error.message);
  }
}
```

### Validation

```typescript
import { validateCPGRoot } from "@ssat/core";

const isValid = validateCPGRoot(cpgData);
if (!isValid) {
  console.error("Invalid CPG data structure");
}
```

## Development

### Project Structure

```
src/
├── conversions/          # Main conversion functions
│   ├── cpg.ts           # CPG generation
│   ├── template.ts      # Template conversion
│   ├── ast.ts           # AST generation
│   ├── dfg.ts           # DFG generation
│   └── types.ts         # Type definitions
├── standalone-conversions.ts  # Standalone functions
├── core/                # Core utilities
│   ├── config.ts        # Configuration management
│   ├── file-manager.ts  # File system operations
│   └── path-resolver.ts # Path resolution
├── types/               # Type definitions
│   ├── cpg/            # CPG types
│   ├── ast/            # AST types
│   ├── dfg/            # DFG types
│   ├── template/       # Template types
│   └── node.ts         # Base node types
└── utils/              # Utility functions
    └── logger.ts       # Logging utilities
```

### Building

```bash
# Type checking
npm run type-check

# Linting
npm run lint

# Format code
npm run format
```

## License

ISC
