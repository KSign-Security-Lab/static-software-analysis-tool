#!/usr/bin/env bash
# Dev launcher for the F2-A test API with auto-reload.
#
# Watches the ssat.f2a source and the api package via uvicorn --reload
# (watchfiles, bundled in uvicorn[standard]); any .py edit under those dirs
# restarts the worker automatically — no manual restart.
#
# Note: CPG generation runs an embedded Joern JVM in-process, so the FIRST
# request after each reload re-attaches the JVM and is a few seconds slower.
#
# Usage:  scripts/dev-api.sh            # defaults below
#         PORT=8001 scripts/dev-api.sh  # override port
set -euo pipefail

cd "$(dirname "$0")/.."

: "${JOERN_HOME:=/usr/bin/joern/joern-cli}"
: "${HOST:=0.0.0.0}"
: "${PORT:=8000}"
export JOERN_HOME

exec uv run uvicorn api.main:app \
  --host "$HOST" --port "$PORT" --app-dir . \
  --reload \
  --reload-dir packages/ssat/src/ssat \
  --reload-dir api
