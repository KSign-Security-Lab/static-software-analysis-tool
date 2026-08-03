#!/usr/bin/env bash
#
# vLLM, the API and the web UI in one terminal.
#
# Compose runs vLLM. The API and web run on the host so their reloaders work,
# which is the only reason this file exists rather than being three more compose
# services. Ctrl-C stops them; the container is left up because reloading
# weights costs minutes.
#
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
VLLM_PORT="${VLLM_PORT:-8001}"

pids=()

# uvicorn --reload forks a reloader and a server; npm forks sh then node.
# Killing only the pid we launched leaves the real server holding the port.
kill_tree() {
  local child
  for child in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$child"; done
  kill -TERM "$1" 2>/dev/null || true
}

cleanup() {
  trap - INT TERM EXIT
  printf '\n\033[36mstopping api and web (vllm stays up: docker compose --profile vllm down)\033[0m\n'
  for pid in "${pids[@]:-}"; do [[ -n "$pid" ]] && kill_tree "$pid"; done
  wait 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM EXIT

# Through a process substitution, not a pipe: after a pipe `$!` is the last
# command, so we would record sed and kill the log prefixer instead.
start() {
  local prefix
  prefix=$(printf '\033[%sm%-4s\033[0m │ ' "$2" "$1")
  bash -c "$3" > >(sed -u "s/^/${prefix}/") 2>&1 &
  pids+=("$!")
}

docker compose --profile vllm up -d --wait vllm

# AGENT_MODEL must be the id the server reports, so ask instead of guessing.
export AGENT_MODEL=$(curl -s "http://localhost:${VLLM_PORT}/v1/models" |
  python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(d[0]['id'])")
export AGENT_BASE_URL="http://localhost:${VLLM_PORT}/v1"
export NEXT_PUBLIC_API_PORT="$API_PORT"

start api 35 ".venv/bin/uvicorn api.main:app --host 0.0.0.0 --port $API_PORT --reload"
start web 34 "cd web && npm run dev -- --port $WEB_PORT"

printf '\n  \033[1mready\033[0m  web http://localhost:%s/inspect   api :%s   model %s\n\n' \
  "$WEB_PORT" "$API_PORT" "$AGENT_MODEL"

wait
