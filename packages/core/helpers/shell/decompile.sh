#!/usr/bin/env bash
set -euo pipefail

# decompile.sh - automate Ghidra headless decompilation (Bash decides output dir)
# Usage: ./decompile.sh <binary-directory>
# Example:
#   ./decompile.sh ./data/tmp/compiled

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <binary-dir>" >&2
  exit 1
fi

BINARY_DIR="$1"
PROJECT_NAME="$(basename "$BINARY_DIR")"
OUTPUT_DIR="$BINARY_DIR/decompiled"

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Resolve script path (relative to this file, else fallback to ./script)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -d "$SCRIPT_DIR/script" ]]; then
  SCRIPT_PATH="$SCRIPT_DIR/script"
else
  SCRIPT_PATH="script"
fi

echo "→ Decompiling binaries from '$BINARY_DIR' into '$OUTPUT_DIR'"

ghidraHeadless "$BINARY_DIR" "$PROJECT_NAME" \
  -import "$BINARY_DIR" \
  -recursive \
  -overwrite \
  -log "$BINARY_DIR/ghidra_headless.log" \
  -scriptPath "$SCRIPT_PATH" \
  -postScript ghidra.py "$OUTPUT_DIR"

echo "✔ Decompilation complete. Files are in '$OUTPUT_DIR'"