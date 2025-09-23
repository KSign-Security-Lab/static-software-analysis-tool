# Type Consolidation - Using Core Types Directly

This document explains how the Prisma package now uses core types directly instead of duplicating type definitions.

## Before: Type Duplication

Previously, the Prisma package had its own type definitions that duplicated types from the core package:

```typescript
// ❌ OLD: Duplicated imports
import { IASTResult } from '@ssat/core/types/ast';
import { CPGGraphData } from '@ssat/core/types/cpg';
import { IDFGGraph } from '@ssat/core/types/dfg';
import { TemplateFlattenedGraph } from '@ssat/core/types/node';
```

## After: Shared Types

Now, the Prisma package imports core types directly from the main core package:

```typescript
// ✅ NEW: Consolidated imports
import type {
  IASTResult,
  CPGGraphData,
  IDFGGraph,
  TemplateFlattenedGraph,
} from '@ssat/core';
```

## Benefits

### 1. **Single Source of Truth**

- Types are defined once in `@ssat/core`
- All packages use the same type definitions
- No risk of type mismatches between packages

### 2. **Reduced Maintenance**

- No need to keep duplicate types in sync
- Changes to core types automatically propagate
- Less code to maintain

### 3. **Better Type Safety**

- TypeScript can better track type relationships
- Compile-time guarantees that types match
- Easier refactoring across packages

### 4. **Cleaner Imports**

- Single import statement for all core types
- Clear dependency on core package
- Easier to understand package relationships

## Files Updated

### Core Package (`@ssat/core`)

- `packages/core/index.ts` - Exports all types from submodules
- `packages/core/types/*` - Contains the actual type definitions

### Prisma Package (`@ssat/prisma`)

- `packages/prisma/src/types.ts` - Now imports from core
- `packages/prisma/src/services/database-service.ts` - Uses core types
- `packages/prisma/src/upload-utils.ts` - Uses core types
- `packages/prisma/src/index.ts` - Re-exports core types
- `packages/prisma/src/schema.ts` - Re-exports core types

## Usage Examples

### In Prisma Package

```typescript
import type { IASTResult, IDFGGraph } from '@ssat/core';

// Use core types directly
const astData: IASTResult[] = [
  {
    /* ... */
  },
  {
    /* ... */
  },
}];
const dfgData: IDFGGraph = {
  /* ... */
};
```

### In Other Packages

```typescript
import type { IASTResult, IDFGGraph } from '@ssat/core';

// Same types, consistent across all packages
const processGraph = (graph: IASTResult) => {
  // Type-safe processing
};
```

## Type Hierarchy

```text
@ssat/core (source of truth)
├── types/ast/index.ts → IASTResult
├── types/cpg/index.ts → CPGGraphData
├── types/dfg/index.ts → IDFGGraph
└── types/node.ts → TemplateFlattenedGraph

@ssat/prisma (consumer)
├── imports from @ssat/core
├── re-exports for convenience
└── uses core types in database operations

Other packages (consumers)
├── import from @ssat/core
└── get consistent types
```

## Migration Guide

If you were previously importing types from individual core modules:

```typescript
// ❌ OLD: Individual imports
import { IASTResult } from '@ssat/core/types/ast';
import { IDFGGraph } from '@ssat/core/types/dfg';

// ✅ NEW: Consolidated import
import type { IASTResult, IDFGGraph } from '@ssat/core';
```

## Testing

The consolidation has been tested with:

- ✅ TypeScript compilation
- ✅ ESLint validation
- ✅ Database operations
- ✅ Seed script functionality
- ✅ Type consistency across packages

## Conclusion

This consolidation eliminates type duplication, improves maintainability, and ensures type consistency across all packages. The core package remains the single source of truth for all graph-related types.
