# Static Software Analysis Tool (SSAT)

A tool to generate C Abstract Syntax Trees (ASTs) using Joern.
This tool extracts CPGs from C code, converts them to KAST format, and provides optional DFG generation.

## Features

- Generates CPGs (Code Property Graphs) using Joern and keeps original directory layout
- Converts CPGs to KAST (KSIGN-style AST) with post-processing
- Generates DFGs from KAST/AST outputs when needed

## Prerequisites

- Node.js (version 14 or higher)
- Joern 4.0.361 (installed and configured)
- Python 3.x (for concurrent processing CPG generation)

## Usage

### 1. Install dependencies

```bash
npm install
pip install -r helpers/requirements.txt
```

### 2. Run the tool

Quickstart:

```bash
# End-to-end (CPG → KAST) on a folder of C files
npm run generate:full --data="<input_directory>"
```

Flags:

- `--data=<path>`: Input directory (raw C sources) or CPG directory for KAST
- `--save=<path>`: **[optional]** Output directory for CPG/KAST/DFG stages

Common tasks:

**[Full pipeline (CPG → KAST)]**

```bash
npm run generate:full --data="<input_directory/input_file.c>" --save="<out_dir>"
```

**[Generate only CPG]**

```bash
npm run generate:cpg --data="<input_directory/input_file.c>" --save="<out_dir>"
```

**[Generate only KAST] (from a CPG directory)**

```bash
npm run generate:kast --data="<cpg_dir/input_file.json>" --save="<out_dir>"
```

**🚧 [Under Development] 🚧 Generate DFG (from a KAST/AST directory)**

```bash
npm run generate:dfg --data="<kast_or_ast_dir/input_file.json>" --save="<out_dir>"
```

### Examples

```bash
# Initialize submodules (open-source samples)
npm run submodule

# End-to-end on Juliet C testcases
npm run generate:full --data="data/C/testcases"

# Mongoose sample
npm run mongoose

# Zephyr sample
npm run zephyr
```

## Output

Outputs are written under `result/` by default (timestamped) unless `--save`/`--output` is provided.
Each source will include:

- `*_astTree.json`: Basic AST Processed from CPG
- `*_templateTree.json`: KAST (KSIGN-style AST) Modified for our use case
- `*_flatten.json`: Flattened KAST (KSIGN-style AST)
- `*_text.txt`: Textual representation of KAST (KSIGN-style AST)

## Development

### Directory Structure Overview

```bash
.
├── data                      # Sample inputs (Juliet C tests, helper JSON, etc.)
├── public                    # Static client/demo assets
│   ├── index.html
│   └── client.js
├── result                    # Default output root for timestamped results
├── helpers
│   ├── ghidra.py
│   ├── requirements.txt
│   ├── runner.py             # Orchestrates CPG/KAST generation
│   └── shell
│       ├── compile.sh        # Build C sources (if needed)
│       ├── decompile.sh      # Decompile binaries (optional workflows)
│       └── install.sh        # Install system dependencies (optional)
├── src
│   ├── ast
│   │   ├── ASTExtractor.ts   # Build AST from CPG JSON
│   │   ├── BinaryUnaryTypeWrapper.ts
│   │   ├── KASTConverter.ts  # Convert AST to KAST (KSIGN-style)
│   │   ├── PlanationTool.ts  # Flatten/normalize KAST
│   │   ├── PostProcessor.ts  # Cleanup passes over KAST
│   │   ├── TreeConverter.ts  # Utilities for tree transforms
│   │   └── config/
│   │       ├── BinaryExpression.ts  # Expression-specific mappings
│   │       ├── Predefined.ts        # Predefined identifiers and types
│   │       ├── StandardLibCall.ts   # Stdlib call heuristics
│   │       └── UnaryExpression.ts   # Expression-specific mappings
│   ├── cpg
│   │   ├── CPGFilter.ts       # CPG pruning/filter helpers
│   │   └── validate/zod.ts    # Schema validation for CPG JSON
│   ├── dfg
│   │   └── DFGBuilder.ts      # Data Flow Graph builder from AST/KAST
│   ├── script
│   │   ├── generateAST.ts     # CLI: generate KAST from CPG
│   │   └── generateDFG.ts     # CLI: generate DFG from KAST/AST
│   ├── types
│   │   ├── ast/ ...
│   │   ├── cpg/ ...
│   │   ├── dfg/ ...
│   │   └── node.ts
│   └── utils
│       ├── index.ts           # Root utilities barrel
│       ├── json.ts            # Safe JSON IO helpers
│       └── treeToText.ts      # Pretty-printer for KAST
└── README.md
```

- `data/`: Input corpora and example datasets
- `public/`: Browser demo files (optional)
- `result/`: Default output location for generated artifacts
- `helpers/runner.py`: High-level pipeline driver (CPG → KAST)
- `helpers/shell/*`: Optional shell helpers to build/decompile/install
- `src/script/generateAST.ts`: CLI entry for KAST generation
- `src/script/generateDFG.ts`: CLI entry for DFG generation
- `src/ast/*`: KAST conversion, normalization, and post-processing
- `src/cpg/*`: CPG filtering and schema validation
- `src/dfg/*`: DFG builder components
- `src/types/*`: Strongly-typed definitions for AST/CPG/DFG
- `src/utils/*`: Common helpers (IO, text rendering)

### File-by-file explanations

Root files and configs:

- `package.json`: NPM scripts (`generate:cpg`, `generate:kast`, `generate:full`, `generate:dfg`), dependencies, metadata
- `package-lock.json`: Exact dependency lockfile
- `tsconfig.json`: TypeScript compiler options
- `eslint.config.js`: ESLint configuration
- `README.md`: Project documentation (this file)

Helpers:

- `helpers/runner.py`: Wraps Joern calls and orchestrates pipeline stages
- `helpers/ghidra.py`: Optional Ghidra integration helper
- `helpers/requirements.txt`: Python dependencies used by helper scripts
- `helpers/shell/compile.sh`: Build C sources for sample projects (if applicable)
- `helpers/shell/decompile.sh`: Decompile binaries (optional workflow)
- `helpers/shell/install.sh`: Install external tools or prerequisites (optional)

Public (demo assets):

- `public/index.html`: Minimal client page for visual/testing purposes
- `public/client.js`: Companion script for the demo page

Source: AST/KAST pipeline (`src/ast`):

- `src/ast/ASTExtractor.ts`: Builds internal AST from Joern CPG JSON
- `src/ast/KASTConverter.ts`: Converts internal AST into KAST representation
- `src/ast/PlanationTool.ts`: Normalizes and flattens KAST structures
- `src/ast/PostProcessor.ts`: Cleanup and refinement passes on KAST output
- `src/ast/TreeConverter.ts`: Utilities for transforming tree structures
- `src/ast/BinaryUnaryTypeWrapper.ts`: Type helpers for binary/unary expressions
- `src/ast/config/BinaryExpression.ts`: Mapping/handling for binary expressions
- `src/ast/config/UnaryExpression.ts`: Mapping/handling for unary expressions
- `src/ast/config/Predefined.ts`: Predefined identifiers/types and conversions
- `src/ast/config/StandardLibCall.ts`: Heuristics for standard library calls

Source: CPG utilities (`src/cpg`):

- `src/cpg/CPGFilter.ts`: Pruning/filtering helpers for CPG graphs
- `src/cpg/validate/zod.ts`: Zod schemas for CPG vertex/edge validation

Source: DFG (`src/dfg`):

- `src/dfg/DFGBuilder.ts`: Builds Data Flow Graph from AST/KAST artifacts

Source: Scripts/CLIs (`src/script`):

- `src/script/generateAST.ts`: CLI to generate KAST from CPG input
- `src/script/generateDFG.ts`: CLI to generate DFG from KAST/AST input

Source: Types (`src/types`):

- `src/types/node.ts`: Base node types shared across AST/CPG/DFG
- `src/types/ast/*`: AST node type definitions organized by category
  - `BaseNode/*`: Base AST node structures
  - `ProgramStructures/*`: Declarations (functions, variables, parameters, translation unit)
  - `ControlStructures/*`: Control flow nodes (if/switch/loop/return/etc.)
  - `Expressions/*`: Expression node kinds (binary/unary/call/literal/identifier/etc.)
  - `DataTypes/*`: Type declarations (struct/union/enum/typedef)
  - `PreprocessorDirectives/*`: Include and macro definitions
- `src/types/cpg/index.ts`: CPG type barrel
- `src/types/cpg/vertex.ts`: CPG vertex type definitions
- `src/types/cpg/edge.ts`: CPG edge type definitions
- `src/types/dfg/index.ts`: DFG type barrel

Source: Utilities (`src/utils`):

- `src/utils/index.ts`: Utility barrel exports
- `src/utils/json.ts`: Safe JSON read/write helpers
- `src/utils/treeToText.ts`: Textual rendering for tree structures
