#!/usr/bin/env sh
set -eu

# Resolve relative paths against where the user ran npm from.
BASE="${INIT_CWD:-$PWD}"

# Required: --data passed as npm config (e.g., npm run generate:ast --data=./in.json)
DATA="${npm_config_data:?use --data=<path>}"
case "$DATA" in
  /*) : ;;
  *) DATA="$BASE/$DATA" ;;
esac

# Optional: --output
OUT="${npm_config_output:-}"
if [ -n "$OUT" ]; then
  case "$OUT" in
    /*) : ;;
    *) OUT="$BASE/$OUT" ;;
  esac
fi

# Allow overriding python executable: PYTHON=python3
PY="${PYTHON:-python}"

# Forward ALL original args (e.g., --mode ast, --verbose) untouched.
# Append normalized --data/--output at the end.
if [ -n "$OUT" ]; then
  exec "$PY" helpers/runner.py "$@" --data "$DATA" --output "$OUT"
else
  exec "$PY" helpers/runner.py "$@" --data "$DATA"
fi