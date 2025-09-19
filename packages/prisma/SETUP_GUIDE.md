# Prisma Setup Guide for Beginners

## 🎯 Quick Start

### 1. Create Environment File

Create a `.env` file in the project root:

```bash
# In the project root directory
touch .env
```

Add your database configuration:

```env
# .env file
DATABASE_URL="postgresql://username:password@localhost:5432/ssat_db?schema=public"
```

### 2. Install Dependencies

```bash
# Install all workspace dependencies
yarn install

# Or install just the prisma package dependencies
yarn workspace @ssat/prisma install
```

### 3. Generate Prisma Client

```bash
# Generate the Prisma client (creates types and database access functions)
yarn db:generate
```

### 4. Set Up Database

Choose one of these options:

**Option A: Push Schema (Development)**
```bash
# Push the schema to your database (creates tables if they don't exist)
yarn db:push
```

**Option B: Migrate (Production)**
```bash
# Create and run migrations (recommended for production)
yarn db:migrate
```

### 5. Verify Setup

```bash
# Open Prisma Studio to see your database
yarn db:studio
```

## 🔍 Understanding Your Schema

Your database has three main tables:

### Graph Table
- Stores metadata about each graph (AST, CPG, DFG, Template)
- Contains source file info, version tags, and content hashes

### Node Table  
- Stores individual nodes from graphs
- Has different fields depending on graph type

### Edge Table
- Stores relationships between nodes
- Contains edge types and properties

## 🚀 Using Prisma in Your Code

### Basic Usage

```typescript
import { DatabaseService } from '@ssat/prisma';

// Create a database service instance
const db = new DatabaseService();

// Connect to database
await db.connect();

// Upload an AST graph
const result = await db.uploadASTGraph(astData, 'example.c', 'v1.0.0');

// Disconnect when done
await db.disconnect();
```

### Upload Different Graph Types

```typescript
// Upload AST graph
await db.uploadASTGraph(astGraphData, 'file.c', 'v1.0.0');

// Upload CPG graph  
await db.uploadCPGGraph(cpgGraphData, 'file.c', 'v1.0.0');

// Upload DFG graph
await db.uploadDFGGraph(dfgGraphData, 'file.c', 'v1.0.0');

// Upload Template graph
await db.uploadTemplateGraph(templateGraphData, 'file.c', 'v1.0.0');
```

### Query Data

```typescript
// Get all graphs
const allGraphs = await db.prisma.graph.findMany();

// Get graphs by type
const astGraphs = await db.prisma.graph.findMany({
  where: { type: 'AST' }
});

// Get graphs with their nodes and edges
const graphWithData = await db.prisma.graph.findUnique({
  where: { id: 'graph-id' },
  include: {
    nodes: true,
    edges: true
  }
});
```

## 🛠️ Common Commands

```bash
# Generate Prisma client (run after schema changes)
yarn db:generate

# Push schema changes to database (development)
yarn db:push

# Create and run migration (production)
yarn db:migrate

# Open database browser
yarn db:studio

# Seed database with sample data
yarn db:seed

# Run example usage
yarn db:example
```

## 🔧 Troubleshooting

### Database Connection Issues
- Check your `DATABASE_URL` in `.env`
- Ensure PostgreSQL is running
- Verify database credentials

### Schema Changes
- After modifying `schema.prisma`, run `yarn db:generate`
- Then run `yarn db:push` or `yarn db:migrate`

### Type Errors
- Run `yarn db:generate` to update types
- Restart your TypeScript server

## 📖 Next Steps

1. Try the example usage: `yarn db:example`
2. Explore your data in Prisma Studio: `yarn db:studio`
3. Check the detailed API docs in `src/README.md`
4. Look at the seed script in `src/seed.ts` for more examples
