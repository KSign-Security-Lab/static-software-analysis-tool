# Static Software Analysis Tool (SSAT)

A comprehensive monorepo tool for static analysis of C code, featuring a modern web interface, CLI tools, and multiple analysis pipelines. The tool extracts Code Property Graphs (CPGs) from C code, converts them to various formats (Template, AST, DFG), and provides both command-line and web-based interfaces for analysis. Note: database persistence has been dropped; artifacts are handled via files and in-memory.

## Features

### Core Analysis Pipeline

- **Code Property Graph Generation**: Extracts CPGs from C source code using Joern
- **Template Conversion**: Converts CPGs to Template format (KAST-style AST) with post-processing
- **Abstract Syntax Tree Generation**: Creates ASTs from Template outputs
- **Data Flow Graph Generation**: Builds DFGs from Template outputs for flow analysis
- **Parallel Processing**: Multi-worker support for efficient batch processing

### Modern Interfaces

- **Web Interface**: Next.js-based web application with interactive graph visualization
- **CLI Tools**: Comprehensive command-line interface with progress tracking
- **REST API**: FastAPI-based services for programmatic access

### Developer Experience

- **Monorepo Architecture**: Organized workspaces for different components
- **TypeScript**: Full type safety across all packages
- **Modern Tooling**: ESLint, Prettier, Jest for code quality
- **Hot Reload**: Development servers with live reloading
- **Comprehensive Testing**: Unit tests with coverage reporting

## Prerequisites

- Node.js 18.17+ (< 23)
- Joern 4.0.361+ (installed and configured)
- Python 3.x
- (No database required — persistence is not used)
- Yarn (workspace management)
- uv (Python package + environment manager)

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/keonoh00/static-software-analysis-tool.git
cd static-software-analysis-tool

# JS dependencies
yarn install

# Python environment (uv)
uv venv .venv
. .venv/bin/activate
uv pip install -r requirements.txt   # AST service + shared deps

# Python workspaces (optional, for package-specific tooling)
(cd packages/agent && uv sync)
(cd packages/graph && uv sync)
(cd packages/utils && uv sync)
```

### 2. Development Setup

```bash
# Start local dev (Joern via Docker + Web)
yarn docker:up      # Start/refresh Joern container
yarn web:dev        # Start Next.js web interface
```

### 3. Common Flows

Headless CLI (no web UI):

```bash
# Run the full pipeline on a project of .c files or precomputed CPG JSON (C/CPG → Template → AST → DFG)
yarn generate:full --data path/to/input --output result/full_out

# Or stage-by-stage if you want intermediate artifacts
# Pass .c files to cpg, then use the produced CPG JSON for later steps
yarn generate:cpg --data path/to/c/sources --output result/cpg_out
yarn generate:template --data result/cpg_out --output result/template_out
yarn generate:ast --data result/template_out --output result/ast_out
yarn generate:dfg --data result/template_out --output result/dfg_out
```

Local development with web UI:

```bash
# Start Joern (Docker) and the Next.js web app
yarn docker:up
yarn web:dev

# Open http://localhost:3000, upload code, run the pipeline, download JSON
```

Train and evaluate the ML agent:

```bash
# One-time env (Python) per the top of this README
(cd packages/agent && uv sync)

# Train using pyproject console script (writes results/*)
cd packages/agent
uv run train --save_name results/exp1 --device cuda:0 --epochs 50 --mode both

# Evaluate from saved config + checkpoints
uv run evaluate --results_dir results/exp1 --max_samples 200
```

Generate per-function AST/DFG from Template with Python graph tool:

```bash
cd packages/graph && uv sync
uv run dfg --data path/to/template_jsons --save results --emit-md
```

### 3. Persistence

The project currently does not use a database. Results are written to `result/` by default or to your `--output` path.

## CLI Usage

The tool provides comprehensive CLI commands through the `@ssat/cli` workspace:

### Available Commands

#### Generate Code Property Graph (CPG)

```bash
yarn generate:cpg --data <input> [options]
```

**Required Options:**

- `-d, --data <path>`: Input C source file or directory

**Options:**

- `-o, --output <path>`: Output directory (default: `result/cpg_<timestamp>`)
- `--ext <extensions>`: File extensions to process (comma-separated, default: "c,h,cpp,cc,cxx,hpp,hxx,java")
- `--workers <number>`: Number of parallel workers for batch processing (default: 4)
- `--repr <representation>`: Joern representation to export (default: "all")
- `-f, --format <format>`: Joern export format (default: "graphson")
- `--replace-macro`: Replace macros in source files (default: true)
- `--no-replace-macro`: Skip macro replacement
- `--copy-source`: Copy original source files alongside generated CPG JSON
- `--keep-intermediate`: Keep intermediate files
- `-v, --verbose`: Verbose output
- `--debug`: Enable debug mode
- `-h, --help`: Display help

For directory inputs, CPG generation preserves the input directory structure. Each source file is written to the corresponding output path with `.json` appended to the full filename, so `src/foo.c` becomes `out/foo.c.json` and `src/foo.h` becomes `out/foo.h.json`. With `--copy-source`, the original source file is copied next to its generated CPG.

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

#### Generate Template (Per Functions)

```bash
yarn generate:template:functions --data <input> [options]
```

Same options as `generate:template`, but saves results per function for detailed analysis.

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

#### Generate Full Pipeline

```bash
yarn generate:full --data <input> [options]
```

Runs the complete pipeline: C → CPG → Template → AST → DFG in a single command.

### Usage Examples

**Basic usage:**

```bash
# Generate CPG from a single C file
yarn generate:cpg --data input.c

# Generate CPG from a directory
yarn generate:cpg --data src/

# Generate CPG from a directory and keep source files next to CPG JSON
yarn generate:cpg --data src/ --output result/cpg_out --copy-source

# Generate Template from CPG
yarn generate:template --data cpg_output/

# Run complete pipeline in one command
yarn generate:full --data src/
```

**Advanced usage with options:**

```bash
# Generate CPG with custom output and verbose mode
yarn generate:cpg --data input.c --output custom-output --verbose

# Generate CPG with debug mode and custom file extensions
yarn generate:cpg --data src/ --debug --ext c,h --no-replace-macro

# Generate Template with intermediate files kept
yarn generate:template --data cpg_output/ --keep-intermediate --verbose

# Use multiple workers for parallel processing
yarn generate:cpg --data src/ --workers 4

# Preserve source files and nested directories in the CPG output tree
yarn generate:cpg --data java_sample --output result/java_sample_cpg --workers 4 --copy-source
```

**Get help:**

```bash
# Show help for a specific command
yarn generate:cpg --help

# List all available scripts
yarn scripts:help
```

## Web Interface

The project includes a modern Next.js web interface for interactive analysis:

### Starting the Web Interface

```bash
# Start Joern (Docker) and the web interface
yarn docker:up
yarn web:dev
```

### Web Interface Features

- **Interactive Graph Visualization**: View and explore CPGs, ASTs, and DFGs
- **File Upload**: Upload C source files for analysis
- **Pipeline Management**: Run analysis pipelines through the web interface
- No database dependency
- **Real-time Processing**: Live updates during analysis

### Database Features

Deprecated. Database-related scripts and services are not part of the active stack.

## Output

Outputs are written under `result/` by default (timestamped) unless `--output` is provided.

**CPG Output:**

- `<source-file-name>.<source-extension>.json`: Code Property Graph in JSON format, preserving the input directory structure
- `<source-file>`: Original source file, when `--copy-source` is used

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

### Monorepo Structure

The project is organized as a Yarn workspace monorepo with the following structure:

```bash
.
├── packages/                  # Workspace packages
│   ├── cli/                  # CLI package (@ssat/cli)
│   │   ├── src/
│   │   │   ├── index.ts      # Main CLI entry point
│   │   │   ├── parser.ts     # Command line argument parsing
│   │   │   ├── logger.ts     # Logging utilities
│   │   │   └── upload.ts     # Upload functionality
│   │   └── package.json
│   ├── core/                 # Core processing package (@ssat/core)
│   │   ├── ast/              # AST processing modules
│   │   │   ├── ASTExtractor.py
│   │   │   ├── server.py     # FastAPI AST service
│   │   │   └── utils.ts
│   │   ├── cpg/              # CPG processing modules
│   │   │   ├── CPGGenerator.ts
│   │   │   ├── CPGFilter.ts
│   │   │   └── validate/
│   │   ├── dfg/              # DFG processing modules
│   │   │   ├── DFGBuilder.ts
│   │   │   ├── DFGEdgeBuilder.ts
│   │   │   ├── DFGNodeBuilder.ts
│   │   │   └── python/
│   │   ├── template/         # Template processing modules
│   │   │   ├── TemplateConverter.ts
│   │   │   ├── TemplateExtractor.ts
│   │   │   ├── PlanationTool.ts
│   │   │   ├── PostProcessor.ts
│   │   │   └── config/
│   │   ├── types/            # Type definitions
│   │   │   ├── ast/
│   │   │   ├── cpg/
│   │   │   ├── dfg/
│   │   │   ├── template/
│   │   │   └── node.ts
│   │   ├── utils/            # Utility functions
│   │   │   ├── json.ts
│   │   │   ├── treeToText.ts
│   │   │   └── pathResolver.ts
│   │   ├── endpoint/         # API endpoints
│   │   └── package.json
│   └── agent/                # ML/AI agent package
│       ├── model/            # Machine learning models
│       ├── dataset/          # Dataset processing
│       ├── scripts/          # Analysis scripts
│       └── requirements.txt
├── web/                      # Next.js web application
│   ├── app/                  # Next.js app directory
│   │   ├── api/              # API routes
│   │   │   ├── ast/
│   │   │   ├── cpg/
│   │   │   ├── dfg/
│   │   │   ├── template/
│   │   │   
│   │   └── debug/            # Debug interface
│   ├── src/
│   │   ├── handlers/         # Request handlers
│   │   ├── pipeline/         # Pipeline configuration
│   │   └── server/           # Server-side utilities
│   └── package.json
├── data/                     # Sample datasets and test files
│   ├── C/                    # Juliet C test suite
│   ├── cpg-macro-replace/    # Preprocessed test data
│   └── full/                 # Complete test datasets
├── result/                   # Default output directory
├── requirements.txt          # Python dependencies
├── package.json              # Root package.json with workspaces
└── README.md
```

### Package Overview

**@ssat/cli** - Command Line Interface

- Main CLI entry point with Commander.js
- Command parsing and argument validation
- Progress tracking and logging utilities

**@ssat/core** - Core Processing Engine

- AST processing with Python FastAPI service
- CPG generation and filtering
- Template conversion and post-processing
- DFG building and analysis
- Type definitions for all graph structures
- Utility functions for I/O and text rendering

<!-- Database layer dropped from active stack -->

**@ssat/web** - Web Interface

- Next.js application with React 19
- Interactive graph visualization
- File upload and pipeline management
- API routes for all analysis types
- Debug interface and reporting

**@ssat/agent** - Machine Learning

- Graph Neural Network models
- Dataset processing and analysis
- Training and evaluation scripts
- Creative GNN implementations

### Key Directories

- `data/`: Sample datasets including Juliet C test suite
- `result/`: Default output directory for generated artifacts
- `packages/*/src/`: Source code for each workspace package
- `web/app/api/`: Next.js API routes for web interface
- `packages/core/ast/`: Python FastAPI service for AST processing

## Development Commands

### Workspace Management

```bash
# Install dependencies for all workspaces
yarn install

# Run commands across all workspaces
yarn type-check    # Type-check all workspaces
yarn lint          # Lint all workspaces
yarn lint:fix      # Fix linting issues
yarn format        # Format code with Prettier
yarn test          # Run tests in @ssat/core
```

### Scripts Quick Reference

```bash
# From repo root

# Pipeline (CLI workspace via root proxies)
yarn generate:cpg
yarn generate:template
yarn generate:template:functions
yarn generate:ast
yarn generate:dfg
yarn generate:full

# Services
yarn start:joern   # Start Joern server
yarn start:ast     # Start AST FastAPI server
# Start Joern + Web separately
yarn docker:up
yarn web:dev

# Web app
yarn web:dev
yarn web:build
yarn web:start

# Quality
yarn type-check
yarn lint
yarn lint:fix
yarn format
yarn format:check

# Script discovery
yarn scripts:help
```

### Individual Workspace Commands

```bash
# CLI workspace
yarn workspace @ssat/cli scripts:help

# Core workspace
yarn workspace @ssat/core scripts:help

# Web workspace
yarn workspace @ssat/web scripts:help

<!-- Prisma workspace removed from active stack -->
```

### Testing and Quality

```bash
# Run tests with coverage
yarn test:coverage

# Run tests with logging
yarn test:log

# Check formatting
yarn format:check

# Type checking
yarn type-check
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes and ensure tests pass: `yarn test`
4. Format your code: `yarn format`
5. Commit your changes: `git commit -m "Add your feature"`
6. Push to the branch: `git push origin feature/your-feature-name`
7. Submit a pull request

## License

This project is licensed under the ISC License - see the [LICENSE](LICENSE) file for details.

## Support

- **Issues**: Report bugs and request features on [GitHub Issues](https://github.com/keonoh00/static-software-analysis-tool/issues)
- **Documentation**: Check individual package READMEs for detailed documentation
- **Discussions**: Use GitHub Discussions for questions and community support
