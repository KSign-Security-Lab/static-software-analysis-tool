# Static Software Analysis Tool (SSAT)

A tool to generate C Abstract Syntax Trees (ASTs) using Joern.
This tool extracts CPGs from C code, converts them to KAST format, and provides optional DFG generation.

## Features

- **Modern CLI Interface**: Uses Commander.js for intuitive command-line interface with proper help system
- **Progress Tracking**: Visual progress bars during processing (suppressed in debug mode)
- **Flexible Input/Output**: Support for single files or directories with custom output paths
- **Multiple Conversion Stages**:
  - Generates CPGs (Code Property Graphs) using Joern
  - Converts CPGs to Template (AST based on KSIGN-style) with post-processing
  - Generates ASTs from Template outputs when needed
  - Generates DFGs from Template outputs when needed
- **Debugging Support**: Verbose and debug modes for detailed processing information
- **File Extension Control**: Customizable file extensions for processing

## Prerequisites

- Node.js (version 14 or higher)
- Joern 4.0.361 (installed and configured)
- Python 3.x (for concurrent processing CPG generation)

## Usage

### 1. Install dependencies

```bash
yarn install
pip install -r packages/core/helpers/requirements.txt
```

### 2. CLI Commands

The tool provides four main commands for different conversion stages:

#### Generate Code Property Graph (CPG)

```bash
yarn generate:cpg --data <input> [options]
```

**Required Options:**

- `-d, --data <path>`: Input C source file or directory

**Options:**

- `-o, --output <path>`: Output directory (default: `result/cpg_<timestamp>`)
- `--ext <extensions>`: File extensions to process (comma-separated, default: "c")
- `--replace-macro`: Replace macros in source files (default: true)
- `--no-replace-macro`: Skip macro replacement
- `--keep-intermediate`: Keep intermediate files
- `-v, --verbose`: Verbose output
- `--debug`: Enable debug mode
- `-h, --help`: Display help

#### Generate Template

```bash
yarn generate:template --data <input> [options]
```

**Required Options:**

- `-d, --data <path>`: Input CPG file or directory

**Options:**

- `-o, --output <path>`: Output directory (default: `result/template_<timestamp>`)
- `--ext <extensions>`: File extensions to process (comma-separated, default: "json")
- `--keep-intermediate`: Keep intermediate files
- `-v, --verbose`: Verbose output
- `--debug`: Enable debug mode
- `-h, --help`: Display help

#### Generate Abstract Syntax Tree (AST)

```bash
yarn generate:ast --data <input> [options]
```

**Required Options:**

- `-d, --data <path>`: Input Template file or directory

**Options:**

- `-o, --output <path>`: Output directory (default: `result/ast_<timestamp>`)
- `--ext <extensions>`: File extensions to process (comma-separated, default: "json")
- `--keep-intermediate`: Keep intermediate files
- `-v, --verbose`: Verbose output
- `--debug`: Enable debug mode
- `-h, --help`: Display help

#### Generate Data Flow Graph (DFG)

```bash
yarn generate:dfg --data <input> [options]
```

**Required Options:**

- `-d, --data <path>`: Input Template file or directory

**Options:**

- `-o, --output <path>`: Output directory (default: `result/dfg_<timestamp>`)
- `--ext <extensions>`: File extensions to process (comma-separated, default: "json")
- `--keep-intermediate`: Keep intermediate files
- `-v, --verbose`: Verbose output
- `--debug`: Enable debug mode
- `-h, --help`: Display help

### 3. Usage Examples

**Basic usage:**

```bash
# Generate CPG from a single C file
yarn generate:cpg --data input.c

# Generate CPG from a directory
yarn generate:cpg --data src/

# Generate Template from CPG
yarn generate:template --data cpg_output/
```

**Advanced usage with options:**

```bash
# Generate CPG with custom output and verbose mode
yarn generate:cpg --data input.c --output custom-output --verbose

# Generate CPG with debug mode and custom file extensions
yarn generate:cpg --data src/ --debug --ext c,h --no-replace-macro

# Generate Template with intermediate files kept
yarn generate:template --data cpg_output/ --keep-intermediate --verbose
```

**Get help:**

```bash
# Show help for a specific command
yarn generate:cpg --help

# Show help for all commands
yarn generate:cpg
```

### 4. Pipeline Examples

```bash
# Complete pipeline: C → CPG → Template → AST → DFG
yarn generate:cpg --data src/ --output pipeline/cpg
yarn generate:template --data pipeline/cpg/ --output pipeline/template
yarn generate:ast --data pipeline/template/ --output pipeline/ast
yarn generate:dfg --data pipeline/template/ --output pipeline/dfg
```

## Output

Outputs are written under `result/` by default (timestamped) unless `--output` is provided.

**CPG Output:**

- `cpg_result.json`: Code Property Graph in JSON format

**Template Output:**

- `template_result.json`: Template artifacts (KAST-style AST) in JSON format

**AST Output:**

- `ast_result.json`: Abstract Syntax Tree in JSON format

**DFG Output:**

- `dfg_result.json`: Data Flow Graph in JSON format

**Progress and Logging:**

- Progress bars are shown during processing (suppressed in debug mode)
- Verbose mode provides detailed file processing information
- Debug mode shows additional debugging information

## Development

### Directory Structure Overview (Old)

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

- `package.json`: Yarn scripts (`generate:cpg`, `generate:kast`, `generate:full`, `generate:dfg`), dependencies, metadata
- `yarn.lock`: Exact dependency lockfile
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
