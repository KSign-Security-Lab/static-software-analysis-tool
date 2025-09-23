# @ssat/prisma - Database Service Package

A comprehensive database service for the Static Software Analysis Tool that handles graph data storage and retrieval using Prisma and PostgreSQL. This package provides type-safe database operations for AST, DFG, and other graph representations.

## 📁 Package Structure

```text
packages/prisma/
├── 📄 schema.prisma              # Prisma database schema definition
├── 📄 package.json               # Package configuration and dependencies
├── 📄 tsconfig.json              # TypeScript configuration
├── 📄 eslint.config.js           # ESLint configuration
├── 📄 docker-compose.yml         # PostgreSQL database setup
├── 📄 SETUP_GUIDE.md             # Detailed setup instructions
├── 📄 TYPE_CONSOLIDATION.md      # Documentation on shared types
├── 📄 setup.sh                   # Database setup script
├── 📁 src/                       # Source code
│   ├── 📄 index.ts               # Main package exports
│   ├── 📄 types.ts               # TypeScript type definitions
│   ├── 📄 schema.ts              # Re-exported Prisma types
│   ├── 📄 config.ts              # Database configuration helpers
│   ├── 📄 upload-utils.ts        # Graph upload utilities
│   ├── 📄 README.md              # Detailed API documentation
│   └── 📁 services/
│       └── 📄 database-service.ts # Core DatabaseService implementation
└── 📁 examples/                  # Example scripts and usage
    ├── 📄 seed.ts                # Database seeding script
    ├── 📄 example-usage.ts       # Comprehensive usage examples
    ├── 📄 simple-example.ts      # Basic usage demonstration
    └── 📄 shared-types-example.ts # Shared types demonstration
```

## 🔧 Core Files Explained

### **Database Schema & Configuration**

- **`schema.prisma`** - Defines the PostgreSQL database schema with Graph, ASTNode, ASTEdge, DFGNode, and DFGEdge models
- **`docker-compose.yml`** - PostgreSQL database container configuration for development
- **`config.ts`** - Database connection configuration and validation utilities

### **Main Source Files**

- **`index.ts`** - Main package entry point that exports all public APIs and re-exports core types
- **`types.ts`** - TypeScript type definitions for database operations, using shared types from `@ssat/core`
- **`schema.ts`** - Re-exports Prisma-generated types and core types for convenience
- **`upload-utils.ts`** - Utilities for uploading graphs from files and directories with validation
- **`services/database-service.ts`** - Core DatabaseService class with methods for all database operations

### **Example Scripts**

- **`seed.ts`** - Database seeding script that reads graph data from a folder structure
- **`example-usage.ts`** - Comprehensive examples showing all package features
- **`simple-example.ts`** - Basic usage demonstration for getting started
- **`shared-types-example.ts`** - Demonstrates how core types are shared across packages

## 🚀 Key Features

- **🔄 Shared Types** - Uses core types directly from `@ssat/core` package (no duplication)
- **📊 Multi-Graph Support** - Handles AST, DFG, CPG, and Template graphs
- **🛡️ Type Safety** - Full TypeScript support with Prisma ORM
- **🔍 Deduplication** - Automatic content hashing to prevent duplicate uploads
- **📦 Batch Operations** - Upload multiple graphs at once
- **🔎 Query Capabilities** - Search and filter graphs by various criteria
- **✅ Data Validation** - Validate graph data before upload
- **📁 Folder Upload** - Upload all graphs from a directory structure

## 🏗️ Architecture

### **Type Sharing**

The package uses shared types from `@ssat/core` to ensure consistency:

```typescript
// All core types are imported directly
import type {
  IASTResult,
  CPGGraphData,
  IDFGGraph,
  TemplateFlattenedGraph,
} from '@ssat/core';
```

### **Database Models**

- **Graph** - Main container for all graph types
- **ASTNode/ASTEdge** - Abstract Syntax Tree nodes and edges
- **DFGNode/DFGEdge** - Data Flow Graph nodes and edges

## 🚀 Quick Start

### 1. Install Dependencies

```bash
yarn install
```

### 2. Set up Environment

Create a `.env` file in the project root:

```env
DATABASE_URL="postgresql://username:password@localhost:6090/graphdb?schema=public"
```

### 3. Database Setup

```bash
# Start database
yarn db:up

# Generate Prisma client
yarn generate

# Push schema to database
yarn push
```

### 4. Seed Database (Optional)

```bash
# Seed from folder structure
yarn tsx examples/seed.ts
```

## 📖 Usage Examples

### Basic Graph Upload

```typescript
import { DatabaseService } from '@ssat/prisma';
import type { IASTResult } from '@ssat/core';

const db = new DatabaseService();
await db.connect();

// Upload AST graph
const astData: IASTResult[] = {
  /* ... */
};
const result = await db.uploadASTGraph(astData, 'example.c', 'v1.0.0');

await db.disconnect();
```

### Batch Upload from Directory

```typescript
import { uploadGraphsFromDirectory } from '@ssat/prisma';

// Upload all JSON files from a directory
const results = await uploadGraphsFromDirectory('path/to/graphs/', 'AST', {
  versionTag: 'v1.0.0',
});
```

### Folder Structure for Seeding

```text
data/
├── ast/     # AST graph JSON files
├── dfg/     # DFG graph JSON files
├── cpg/     # CPG graph JSON files
└── template/ # Template graph JSON files
```

## 🛠️ Available Scripts

### Database Management

```bash
yarn db:up          # Start PostgreSQL via docker-compose
yarn db:down        # Stop and remove database volume
yarn db:logs        # Follow database logs
yarn db:wait        # Wait until database is healthy
```

### Prisma Operations

```bash
yarn generate       # Generate Prisma client
yarn push           # Push schema to database (development)
yarn migrate        # Create/apply migrations (production)
yarn studio         # Open Prisma Studio
```

### Development

```bash
yarn type-check     # Run TypeScript type checking
yarn lint           # Run ESLint
yarn lint:fix       # Fix ESLint issues
yarn format         # Format code with Prettier
```

### Examples

```bash
yarn seed           # Run database seeding
yarn example        # Run example usage script
```

## 🔗 Integration

This package integrates seamlessly with the core package:

- **Shared Types** - Uses `@ssat/core` types directly
- **Type Safety** - Full TypeScript support across packages
- **Consistent API** - Same types used throughout the application

## 📚 Documentation

- **`src/README.md`** - Detailed API documentation
- **`SETUP_GUIDE.md`** - Comprehensive setup instructions
- **`TYPE_CONSOLIDATION.md`** - Explanation of shared type architecture

## 🧪 Testing

The package includes comprehensive examples and tests:

- Database seeding with real data
- Type consistency verification
- Upload functionality testing
- Error handling validation

## 🚨 Important Notes

- **CPG and Template graphs** are currently not supported in the database schema
- **AST and DFG graphs** are fully supported and tested
- **Type sharing** ensures consistency across all packages
- **Folder-based seeding** is the recommended approach for bulk data uploads
