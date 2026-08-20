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

# Ask the endpoint which model it serves, rather than leaving the API unable to
# scan. `up.sh` has always done this -- AGENT_MODEL must be the id the server
# reports, so asking beats guessing, and there is deliberately no default because
# a wrong model silently produces plausible nonsense.
#
# This launcher did not, so an API started here answered `configured: false` and
# refused every 검사 시작 with a 503. Honouring an AGENT_MODEL that is already set
# means an explicit choice still wins.
if [[ -z "${AGENT_MODEL:-}" ]]; then
  : "${AGENT_BASE_URL:=http://localhost:8001/v1}"
  # `python3 -c`, the same way up.sh does it, and for a reason worth recording:
  # a sed over `"id"` matches the *last* one on the line, and vLLM nests a
  # `permission` array whose entries have ids too -- so it confidently exported
  # `modelperm-9bd057f2461ad393` as the model name.
  served=$(curl -fsS --max-time 3 "${AGENT_BASE_URL}/models" 2>/dev/null |
    python3 -c "import sys,json;print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null) || true
  if [[ -n "$served" ]]; then
    export AGENT_MODEL="$served"
    export AGENT_BASE_URL
    echo "dev-api: AGENT_MODEL=$served (from $AGENT_BASE_URL)" >&2
  else
    echo "dev-api: no model endpoint at $AGENT_BASE_URL -- scans will be refused until AGENT_MODEL is set" >&2
  fi
fi

# Every package the API imports, not only the two it started with. `packages/agent`
# was missing, so an edit to the inspection graph left the server running the
# previous one -- which looks exactly like a fix that did not work, and cost an
# afternoon proving a change against code that was never loaded.
exec uv run uvicorn api.main:app \
  --host "$HOST" --port "$PORT" --app-dir . \
  --reload \
  --reload-dir packages/ssat/src/ssat \
  --reload-dir packages/agent/src/agent \
  --reload-dir packages/graphify/src/graphify \
  --reload-dir api
