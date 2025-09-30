# Robust Path Resolution Utility

## Overview

The `pathResolver.ts` utility provides a robust solution for path resolution across the entire codebase, eliminating the common issues with relative paths that break when commands are run from different directories.

## Problem Solved

### Before (Problematic)

```typescript
// This breaks when run from different directories
const extractorPath = path.resolve(process.cwd(), "packages/core/ast/ASTExtractor.py");
const dfgPath = path.join(__dirname, "../../agent/dataset/v2/DFGExtractor.py");
```

### After (Robust)

```typescript
// This works regardless of current working directory
const extractorPath = await getValidatedPath("AST_EXTRACTOR");
const dfgPath = getPath("DFG_EXTRACTOR");
```

## Key Features

### 1. **Repository Root Detection**

- Automatically detects the repository root regardless of execution location
- Works from any subdirectory or package

### 2. **Consistent Path Resolution**

- All paths are resolved relative to the repository root
- No dependency on `process.cwd()` or `__dirname`

### 3. **ES Module Compatibility**

- Fully compatible with ES modules
- No `require()` usage that breaks in ES module scope

### 4. **Path Validation**

- Optional path validation to ensure files exist
- Clear error messages when paths are invalid

## Usage

### Basic Path Resolution

```typescript
import { getRepoRoot, getPackagesDir, getCoreDir } from "../utils/pathResolver";

// Get absolute paths
const repoRoot = getRepoRoot();
const packagesDir = getPackagesDir();
const coreDir = getCoreDir();
```

### Predefined Paths

```typescript
import { PATHS, getPath, getValidatedPath } from "../utils/pathResolver";

// Get path without validation (synchronous)
const astExtractorPath = getPath("AST_EXTRACTOR");

// Get path with validation (asynchronous)
const validatedPath = await getValidatedPath("AST_EXTRACTOR");
```

### Custom Path Resolution

```typescript
import { resolveFromRepoRoot, resolveFromCore } from "../utils/pathResolver";

// Resolve relative to repo root
const customPath = resolveFromRepoRoot("data/temp/custom");

// Resolve relative to core package
const corePath = resolveFromCore("ast/custom.py");
```

## Available Predefined Paths

| Key             | Description                  | Path                                        |
| --------------- | ---------------------------- | ------------------------------------------- |
| `AST_EXTRACTOR` | AST extraction Python script | `packages/core/ast/ASTExtractor.py`         |
| `DFG_EXTRACTOR` | DFG extraction Python script | `packages/agent/dataset/v2/DFGExtractor.py` |
| `DATA_DIR`      | Data directory               | `data`                                      |
| `TEMP_DIR`      | Temporary data directory     | `data/temp`                                 |
| `TEMPLATE_DIR`  | Template directory           | `data/temp/template`                        |
| `CPG_DIR`       | CPG directory                | `data/temp/cpg`                             |
| `AST_DIR`       | AST directory                | `data/temp/ast`                             |
| `DFG_DIR`       | DFG directory                | `data/temp/dfg`                             |

## API Reference

### Core Functions

#### `getRepoRoot(): string`

Returns the absolute path to the repository root.

#### `getPackagesDir(): string`

Returns the absolute path to the packages directory.

#### `getCoreDir(): string`

Returns the absolute path to the core package directory.

#### `getAgentDir(): string`

Returns the absolute path to the agent package directory.

#### `getCliDir(): string`

Returns the absolute path to the CLI package directory.

### Path Resolution Functions

#### `resolveFromRepoRoot(relativePath: string): string`

Resolves a path relative to the repository root.

#### `resolveFromPackages(relativePath: string): string`

Resolves a path relative to the packages directory.

#### `resolveFromCore(relativePath: string): string`

Resolves a path relative to the core package.

#### `resolveFromAgent(relativePath: string): string`

Resolves a path relative to the agent package.

#### `resolveFromCli(relativePath: string): string`

Resolves a path relative to the CLI package.

### Path Access Functions

#### `getPath(key: keyof typeof PATHS): string`

Gets a predefined path without validation (synchronous).

#### `getValidatedPath(key: keyof typeof PATHS): Promise<string>`

Gets a predefined path with validation (asynchronous).

#### `validatePath(filePath: string, description?: string): Promise<string>`

Validates that a file exists at the given path.

### Debug Functions

#### `debugPaths(): Promise<void>`

Prints all resolved paths for debugging purposes.

## Migration Guide

### Step 1: Replace Hardcoded Paths

**Before:**

```typescript
const extractorPath = path.resolve(process.cwd(), "packages/core/ast/ASTExtractor.py");
```

**After:**

```typescript
import { getPath } from "../utils/pathResolver";
const extractorPath = getPath("AST_EXTRACTOR");
```

### Step 2: Replace `__dirname` Usage

**Before:**

```typescript
const dfgPath = path.join(__dirname, "../../agent/dataset/v2/DFGExtractor.py");
```

**After:**

```typescript
import { getPath } from "../utils/pathResolver";
const dfgPath = getPath("DFG_EXTRACTOR");
```

### Step 3: Replace `process.cwd()` Usage

**Before:**

```typescript
const outputPath = path.resolve(process.cwd(), "data/temp/output");
```

**After:**

```typescript
import { resolveFromRepoRoot } from "../utils/pathResolver";
const outputPath = resolveFromRepoRoot("data/temp/output");
```

## Benefits

### 1. **Reliability**

- Paths work regardless of execution directory
- No more "file not found" errors due to relative paths

### 2. **Maintainability**

- Centralized path management
- Easy to update paths in one place

### 3. **Consistency**

- All paths use the same resolution strategy
- Predictable behavior across the codebase

### 4. **ES Module Compatibility**

- Works with modern ES module syntax
- No CommonJS dependencies

## Error Handling

The utility provides clear error messages when paths are invalid:

```typescript
try {
  const path = await getValidatedPath("AST_EXTRACTOR");
} catch (error) {
  // Error: ast extractor not found at: /path/to/ASTExtractor.py
  console.error(error.message);
}
```

## Debugging

Use the debug function to inspect all resolved paths:

```typescript
import { debugPaths } from "../utils/pathResolver";

await debugPaths();
// Output:
// === Path Resolution Debug ===
// Repo Root: /home/user/static-software-analysis-tool
// Packages Dir: /home/user/static-software-analysis-tool/packages
// Core Dir: /home/user/static-software-analysis-tool/packages/core
// ...
// === Predefined Paths ===
// AST_EXTRACTOR: /path/to/ASTExtractor.py ✓
// DFG_EXTRACTOR: /path/to/DFGExtractor.py ✓
// ...
```

## Best Practices

1. **Use predefined paths** when available
2. **Use validation** for critical paths
3. **Use synchronous functions** for constants
4. **Use asynchronous functions** for runtime path resolution
5. **Import only what you need** to keep bundle size small

## Examples

### In Endpoint Functions

```typescript
import { getValidatedPath, getPath } from "../utils/pathResolver";

export async function generateAst(template: TemplateNodes[]): Promise<IASTResult[]> {
  const extractorPath = await getValidatedPath("AST_EXTRACTOR");
  // ... rest of function
}

export const DFG_EXTRACTOR_PATH = getPath("DFG_EXTRACTOR");
```

### In CLI Commands

```typescript
import { resolveFromRepoRoot } from "../utils/pathResolver";

const outputPath = resolveFromRepoRoot("data/temp/output");
```

### In Test Files

```typescript
import { getPath, debugPaths } from "../utils/pathResolver";

// Debug paths in tests
await debugPaths();

// Use predefined paths
const testDataPath = getPath("TEMP_DIR");
```
