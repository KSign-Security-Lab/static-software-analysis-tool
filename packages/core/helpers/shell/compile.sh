#!/usr/bin/env bash
# compile.sh - wrapper to run make in a specified directory
# Usage: ./compile.sh <make-directory> [make-target]
# Example: ./compile.sh data/raw_src/SARD_Juliet/C/testcases/CWE690_NULL_Deref_From_Return/sel individuals

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <directory> [target]" >&2
  exit 1
fi

MAKE_DIR="$1"
# Default make target is 'individuals'
MAKE_TARGET="${2:-individuals}"

if [[ ! -d "$MAKE_DIR" ]]; then
  echo "Error: directory '$MAKE_DIR' does not exist" >&2
  exit 1
fi

echo "→ Running make in '$MAKE_DIR' with target '$MAKE_TARGET'"
make -C "$MAKE_DIR" "$MAKE_TARGET"

echo "✔ Make completed in '$MAKE_DIR'"