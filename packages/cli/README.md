# @ssat/cli

Command-line interface for the Static Software Analysis Tool (SSAT). This package provides a modern, user-friendly CLI built with Commander.js for converting C source code into various representations including Code Property Graphs (CPG), Templates, Abstract Syntax Trees (AST), and Data Flow Graphs (DFG).

## Features

- **Modern CLI Interface**: Built with Commander.js for intuitive command-line experience
- **Progress Tracking**: Visual progress bars during processing (suppressed in debug mode)
- **Multiple Conversion Modes**: CPG, Template, AST, and DFG generation
- **Flexible Input/Output**: Support for single files or directories with custom output paths
- **Debugging Support**: Verbose and debug modes for detailed processing information
- **File Extension Control**: Customizable file extensions for processing
- **Help System**: Comprehensive help documentation for all commands

## Installation

```bash
# Install globally
npm install -g @ssat/cli

# Or install locally in your project
npm install @ssat/cli
```

## Quick Start

```bash
# Generate CPG from a C file
ssat cpg input.c

# Generate CPG from a directory
ssat cpg src/

# Generate Template from CPG
ssat template cpg_output/

# Get help for any command
ssat cpg --help
```

## Commands

### `ssat cpg <input> [options]`

Generate Code Property Graph from C source code.

**Arguments:**

- `<input>`: Input C source file or directory

**Options:**

- `-o, --output <path>`: Output directory (default: `result/cpg_<timestamp>`)
- `--ext <extensions>`: File extensions to process (comma-separated, default: "c")
- `--replace-macro`: Replace macros in source files (default: true)
- `--no-replace-macro`: Skip macro replacement
- `--keep-intermediate`: Keep intermediate files
- `-v, --verbose`: Verbose output
- `--debug`: Enable debug mode
- `-h, --help`: Display help

**Examples:**

```bash
# Basic usage
ssat cpg input.c

# With custom output directory
ssat cpg src/ --output my-cpg-output

# Process multiple file types
ssat cpg src/ --ext c,h --verbose

# Debug mode with no macro replacement
ssat cpg input.c --debug --no-replace-macro
```

### `ssat template <input> [options]`

Generate Template artifacts from CPG data.

**Arguments:**

- `<input>`: Input CPG file or directory

**Options:**

- `-o, --output <path>`: Output directory (default: `result/template_<timestamp>`)
- `--ext <extensions>`: File extensions to process (comma-separated, default: "json")
- `--keep-intermediate`: Keep intermediate files
- `-v, --verbose`: Verbose output
- `--debug`: Enable debug mode
- `-h, --help`: Display help

**Examples:**

```bash
# Convert CPG to Template
ssat template cpg_output/

# With verbose output
ssat template cpg_file.json --verbose --output template-output
```

### `ssat ast <input> [options]`

Generate Abstract Syntax Tree from Template data.

**Arguments:**

- `<input>`: Input Template file or directory

**Options:**

- `-o, --output <path>`: Output directory (default: `result/ast_<timestamp>`)
- `--ext <extensions>`: File extensions to process (comma-separated, default: "json")
- `--keep-intermediate`: Keep intermediate files
- `-v, --verbose`: Verbose output
- `--debug`: Enable debug mode
- `-h, --help`: Display help

**Examples:**

```bash
# Generate AST from Template
ssat ast template_output/

# With debug information
ssat ast template_file.json --debug --output ast-output
```

### `ssat dfg <input> [options]`

Generate Data Flow Graph from Template data.

**Arguments:**

- `<input>`: Input Template file or directory

**Options:**

- `-o, --output <path>`: Output directory (default: `result/dfg_<timestamp>`)
- `--ext <extensions>`: File extensions to process (comma-separated, default: "json")
- `--keep-intermediate`: Keep intermediate files
- `-v, --verbose`: Verbose output
- `--debug`: Enable debug mode
- `-h, --help`: Display help

**Examples:**

```bash
# Generate DFG from Template
ssat dfg template_output/

# With custom output and verbose mode
ssat dfg template_file.json --output dfg-output --verbose
```

## Usage Examples

### Basic Workflow

```bash
# 1. Generate CPG from C source
ssat cpg src/ --output pipeline/cpg

# 2. Convert CPG to Template
ssat template pipeline/cpg/ --output pipeline/template

# 3. Generate AST from Template
ssat ast pipeline/template/ --output pipeline/ast

# 4. Generate DFG from Template
ssat dfg pipeline/template/ --output pipeline/dfg
```

### Advanced Usage

```bash
# Process specific file types with verbose output
ssat cpg src/ --ext c,h,cpp --verbose --output cpp-analysis

# Debug mode for troubleshooting
ssat cpg problematic.c --debug --no-replace-macro

# Keep intermediate files for inspection
ssat cpg src/ --keep-intermediate --output debug-output
```

### Batch Processing

```bash
# Process multiple directories
for dir in project1 project2 project3; do
  ssat cpg "$dir/src/" --output "results/$dir-cpg"
  ssat template "results/$dir-cpg/" --output "results/$dir-template"
done
```

## Output

### File Structure

Each command generates output in the specified directory (or `result/` by default):

```
output-directory/
├── cpg_result.json      # CPG output (from cpg command)
├── template_result.json # Template output (from template command)
├── ast_result.json      # AST output (from ast command)
└── dfg_result.json      # DFG output (from dfg command)
```

### Progress and Logging

- **Normal mode**: Shows progress bar during processing
- **Verbose mode** (`-v, --verbose`): Shows detailed file processing information
- **Debug mode** (`--debug`): Shows debugging information and suppresses progress bar

**Example output:**

```
[INFO] Static Software Analysis Tool (SSAT) v2.4.3
[INFO] Mode: cpg
[INFO] Input: src/
[INFO] Output: result/cpg_1758085425590
[VERBOSE] Verbose mode enabled
[VERBOSE] File extensions: c
Progress |████████████████████| 100% | 5/5 files | ETA: 0s
[INFO] ✓ Processing completed successfully
[INFO] Output written to: result/cpg_1758085425590/cpg_result.json
```

## Configuration

### Environment Variables

- `DEBUG=1`: Enable debug mode globally
- `AST_SERVER_URL`: Custom AST server URL (for AST generation)
- `NEXT_PUBLIC_AST_SERVER_URL`: Alternative AST server URL

### File Extensions

Default file extensions for each command:

- **CPG**: `.c` files
- **Template**: `.json` files
- **AST**: `.json` files
- **DFG**: `.json` files

Custom extensions can be specified with `--ext`:

```bash
ssat cpg src/ --ext c,h,cpp,cc
ssat template data/ --ext json,txt
```

## Error Handling

The CLI provides clear error messages for common issues:

```bash
# Missing required argument
$ ssat cpg
error: missing required argument 'input'

# File not found
$ ssat cpg nonexistent.c
[ERROR] ✗ Processing failed: ENOENT: no such file or directory, stat 'nonexistent.c'

# Invalid command
$ ssat invalid-command
Error: No valid command specified
```

## Development

### Project Structure

```
src/
├── index.ts            # Main CLI entry point
├── parser.ts           # Commander.js command definitions
└── types/              # TypeScript type definitions
```

### Building

```bash
# Type checking
npm run type-check

# Linting
npm run lint

# Format code
npm run format
```

### Dependencies

- **@ssat/core**: Core conversion functions
- **commander**: CLI framework
- **cli-progress**: Progress bar display
- **zod**: Runtime validation

## Troubleshooting

### Common Issues

1. **"joern-parse failed"**: Ensure Joern is installed and in PATH
2. **"AST server error"**: Check if AST server is running (for AST generation)
3. **"No files found"**: Verify input path and file extensions

### Debug Mode

Use `--debug` flag for detailed troubleshooting information:

```bash
ssat cpg input.c --debug
```

This will show:

- Detailed file processing information
- Debug messages from core functions
- Suppressed progress bar for better log visibility

### Verbose Mode

Use `-v, --verbose` for additional processing details:

```bash
ssat cpg src/ --verbose
```

This will show:

- File sizes and processing details
- Extension information
- Additional processing metadata

## License

ISC
