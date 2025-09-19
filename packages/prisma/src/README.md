# Database Service for Static Software Analysis Tool

This module provides database functionality for uploading and managing graph-typed data (AST, CPG, DFG, and Template graphs) using Prisma and PostgreSQL.

**Location**: `/prisma` - Centralized database management for the entire project.

## Features

- **Multi-graph support**: Upload AST, CPG, DFG, and Template graphs
- **Type safety**: Full TypeScript support with Prisma
- **Deduplication**: Automatic content hashing to prevent duplicate uploads
- **Batch operations**: Upload multiple graphs at once
- **Query capabilities**: Search and filter graphs by various criteria
- **Data validation**: Validate graph data before upload

## Setup

### 1. Install Dependencies

```bash
yarn add @prisma/client
yarn add -D prisma
```

### 2. Environment Configuration

Create a `.env` file in the project root with your database configuration:

```env
DATABASE_URL="postgresql://username:password@localhost:5432/ssat_db?schema=public"
```

### 3. Database Setup

```bash
# Generate Prisma client
yarn db:generate

# Push schema to database (for development)
yarn db:push

# Or run migrations (for production)
yarn db:migrate
```

### 4. Seed Database (Optional)

```bash
yarn db:seed
```

## Usage

### Basic Usage

```typescript
import { DatabaseService, uploadGraph } from '@ssat/prisma';

// Upload a single graph
const result = await uploadGraph(
  {
    type: 'AST',
    data: astGraphData,
  },
  {
    sourceFile: 'example.c',
    sourceLabel: '1',
    versionTag: 'v1.0.0',
  }
);

console.log(`Uploaded graph: ${result.graph.id}`);
```

### Using DatabaseService Directly

```typescript
import { DatabaseService } from '@ssat/prisma';

const db = new DatabaseService();
await db.connect();

// Upload AST graph
const astGraph = await db.uploadASTGraph(astData, 'example.c', 'v1.0.0');

// Upload DFG graph
const dfgGraph = await db.uploadDFGGraph(dfgData, 'example.c', 'v1.0.0');

// Note: CPG and Template uploads are not currently supported in the schema

// Query graphs
const graphs = await db.getGraphsByTypeAndFile('AST', 'example.c');

await db.disconnect();
```

### Batch Upload

```typescript
import { uploadGraphs } from '@ssat/prisma';

const results = await uploadGraphs([
  {
    data: { type: 'AST', data: astData },
    options: { sourceFile: 'file1.c', versionTag: 'v1.0.0' },
  },
  {
    data: { type: 'DFG', data: dfgData },
    options: { sourceFile: 'file2.c', versionTag: 'v1.0.0' },
  },
]);

console.log(`Uploaded ${results.successful} graphs successfully`);
```

### Upload from Files

```typescript
import { uploadGraphFromFile, uploadGraphsFromDirectory } from '@ssat/prisma';

// Upload single file
const result = await uploadGraphFromFile('path/to/graph.json', 'AST', {
  versionTag: 'v1.0.0',
});

// Upload all JSON files from directory
const results = await uploadGraphsFromDirectory('path/to/graphs/', 'AST', {
  versionTag: 'v1.0.0',
});
```

## Database Schema

### Graph Model

- `id`: Unique identifier
- `type`: Graph type (AST, CPG, DFG, TEMPLATE)
- `sourceFile`: Source file path
- `sourceLabel`: Optional label (for AST graphs)
- `versionTag`: Optional version tag
- `contentHash`: Unique hash for deduplication
- `meta`: Additional metadata as JSON

### Node Model

- `id`: Unique identifier
- `graphId`: Reference to parent graph
- `externalId`: External ID from source data
- `label`: Node label/type
- `code`: Source code (if applicable)
- `features`: Node features as JSON
- `properties`: Additional properties (for CPG)
- `nodeType`: Template node type
- `lineNumber`: Line number (for AST/CPG)
- `columnNumber`: Column number (for AST/CPG)

### Edge Model

- `id`: Unique identifier
- `graphId`: Reference to parent graph
- `srcExternalId`: Source node external ID
- `dstExternalId`: Destination node external ID
- `kind`: Edge type/kind
- `features`: Edge features as JSON
- `properties`: Additional properties (for CPG)
- `edgeType`: Edge type number (for AST)
- `guardKind`: Guard kind (for AST guard edges)
- `guardBranch`: Guard branch (for AST guard edges)

## API Reference

### DatabaseService

#### Methods

- `connect()`: Connect to database
- `disconnect()`: Disconnect from database
- `uploadASTGraph(data, sourceFile, versionTag?)`: Upload AST graph
- `uploadDFGGraph(data, sourceFile, versionTag?)`: Upload DFG graph
- `uploadCPGGraph(data, sourceFile, versionTag?)`: Upload CPG graph (throws error - not supported)
- `uploadTemplateGraph(data, sourceFile, versionTag?)`: Upload Template graph (throws error - not supported)
- `getGraphById(id)`: Get graph by ID with nodes and edges
- `getGraphsByTypeAndFile(type, sourceFile)`: Get graphs by type and file
- `deleteGraph(id)`: Delete graph and all related data

### Upload Utilities

#### Functions

- `uploadGraph(graphData, options)`: Upload any graph type
- `uploadGraphs(graphDataList)`: Upload multiple graphs
- `uploadGraphFromFile(filePath, graphType, options)`: Upload from file
- `uploadGraphsFromDirectory(directoryPath, graphType, options)`: Upload from directory
- `validateGraphData(graphData)`: Validate graph data

## Development

### Scripts

- `yarn db:generate`: Generate Prisma client
- `yarn db:push`: Push schema to database
- `yarn db:migrate`: Run database migrations
- `yarn db:studio`: Open Prisma Studio
- `yarn db:seed`: Seed database with sample data

### Example Usage

Run the example usage script:

```bash
yarn tsx examples/example-usage.ts
```

## Error Handling

The service includes comprehensive error handling:

- Database connection errors
- Data validation errors
- Duplicate upload prevention
- Transaction rollback on failures

## Performance Considerations

- Uses connection pooling for better performance
- Indexes on frequently queried fields
- Batch operations for multiple uploads
- Content hashing for deduplication
