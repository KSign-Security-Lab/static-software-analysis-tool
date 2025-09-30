# Static Software Analysis Tool (SSAT)

A comprehensive monorepo tool for static analysis of C code, featuring a modern web interface, CLI tools, and multiple analysis pipelines. The tool extracts Code Property Graphs (CPGs) from C code, converts them to various formats (Template, AST, DFG), and provides both command-line and web-based interfaces for analysis.

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
- **Database Integration**: PostgreSQL with Prisma ORM for data persistence

### Developer Experience

- **Monorepo Architecture**: Organized workspaces for different components
- **TypeScript**: Full type safety across all packages
- **Modern Tooling**: ESLint, Prettier, Jest for code quality
- **Hot Reload**: Development servers with live reloading
- **Comprehensive Testing**: Unit tests with coverage reporting

## Prerequisites

- **Node.js**: Version 18.17 or higher (but less than 23)
- **Joern**: 4.0.361+ (installed and configured)
- **Python**: 3.x (for CPG generation and FastAPI services)
- **PostgreSQL**: For web interface database features (optional)
- **Yarn**: Package manager for workspace management

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/keonoh00/static-software-analysis-tool.git
cd static-software-analysis-tool

# Install dependencies
yarn install

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Development Setup

```bash
# Start all services (Joern, AST service, and web interface)
yarn start:all

# Or start services individually:
yarn start:joern    # Start Joern server
yarn start:ast      # Start AST FastAPI service
yarn web:dev        # Start Next.js web interface
```

### 3. Database Setup (Optional)

```bash
# Initialize database with Prisma
yarn db:init

# Or start database and generate client
yarn db:start
yarn db:generate
yarn db:push
```

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
- `--ext <extensions>`: File extensions to process (comma-separated, default: "c")
- `--replace-macro`: Replace macros in source files (default: true)
- `--no-replace-macro`: Skip macro replacement
- `--keep-intermediate`: Keep intermediate files
- `--workers <number>`: Number of parallel workers (default: 1)
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
# Start all services (recommended for development)
yarn start:all

# Or start web interface only
yarn web:dev
```

### Web Interface Features

- **Interactive Graph Visualization**: View and explore CPGs, ASTs, and DFGs
- **File Upload**: Upload C source files for analysis
- **Pipeline Management**: Run analysis pipelines through the web interface
- **Database Integration**: Store and retrieve analysis results
- **Real-time Processing**: Live updates during analysis

### Database Features

```bash
# Database management commands
yarn db:start      # Start PostgreSQL database
yarn db:init       # Initialize database with Prisma
yarn db:generate   # Generate Prisma client
yarn db:push       # Push schema to database
yarn db:studio     # Open Prisma Studio
yarn db:seed       # Seed database with sample data
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
│   ├── prisma/               # Database package (@ssat/prisma)
│   │   ├── src/
│   │   │   ├── schema.ts
│   │   │   ├── services/
│   │   │   └── types.ts
│   │   ├── schema.prisma
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
│   │   │   └── upload/
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
- Upload functionality for web interface

**@ssat/core** - Core Processing Engine

- AST processing with Python FastAPI service
- CPG generation and filtering
- Template conversion and post-processing
- DFG building and analysis
- Type definitions for all graph structures
- Utility functions for I/O and text rendering

**@ssat/prisma** - Database Layer

- Prisma ORM schema and client
- Database services and utilities
- Type-safe database operations
- Migration and seeding support

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

### Individual Workspace Commands

```bash
# CLI workspace
yarn workspace @ssat/cli scripts:help

# Core workspace
yarn workspace @ssat/core scripts:help

# Web workspace
yarn workspace @ssat/web scripts:help

# Prisma workspace
yarn workspace @ssat/prisma scripts:help
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
