# @ssat/web — Web Interface

A Next.js application that provides an interactive UI for the Static Software Analysis Tool (SSAT). It exposes API routes that orchestrate the analysis pipeline (CPG → Template → AST → DFG) and integrates with the database layer for optional persistence.

## What It Does

- Upload C source and run the pipeline from the browser
- Visualize and download generated artifacts (CPG/Template/AST/DFG)
- Provide REST API endpoints that call `@ssat/core` conversion utilities
- No database dependency; results are returned in responses or downloadable as files

## Environment Setup

- Node.js >= 18.17 < 23
- Yarn
- No database required
- AST/DFG steps use Python subprocesses via `@ssat/core` (no HTTP server)
- Joern (for full C→CPG pipeline)

No database environment variables are needed.

## Development

Run only the web app:

```bash
yarn web:dev
```

Run the local stack for development (Joern via Docker + Web):

```bash
yarn docker:up   # Start/refresh Joern container
yarn web:dev     # Start Next.js dev server
```

Build and run production locally:

```bash
yarn web:build
yarn web:start
```

## Architecture

- Next.js App Router (`web/app/*`) for pages and API routes
- API handlers under `web/app/api/*` call `@ssat/core` pipeline steps
- API routes operate without persistence (in-memory/file-based workflows)
- Pipeline configuration in `web/src/pipeline/*`

Key internal API routes:

- `POST /api/cpg` → generate CPG
- `POST /api/template` → generate Template (optionally from CPG)
- `POST /api/ast` → generate AST (calls local FastAPI at `:8000`)
- `POST /api/dfg` → generate DFG (builds on AST/Template)

## Usage

- Open http://localhost:3000
- Upload files or paste code to trigger the pipeline
- Inspect results in the UI or download JSON artifacts

<!-- Database functionality was removed from the active stack -->

## Scripts

```bash
yarn workspace @ssat/web scripts:help

yarn web:dev     # Dev server
yarn web:build   # Build
yarn web:start   # Start (production)
```
