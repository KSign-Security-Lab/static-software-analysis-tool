#!/usr/bin/env bash
#
# Bring the whole stack up in one terminal: vLLM, the API, and the web UI.
#
#   scripts/up.sh                  start everything
#   scripts/up.sh --model ID ...   options are passed to scripts/vllm.sh
#
# Ctrl-C stops the API and the web server. The vLLM container is left running,
# because loading weights costs minutes and the next `up` reuses it. Stop it
# with `scripts/vllm.sh stop`.
#
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
VENV="$PWD/.venv"

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
VLLM_PORT="${VLLM_PORT:-8001}"

die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[36m%s\033[0m\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }

pids=()

# Both services spawn: uvicorn --reload forks a reloader and a server, npm
# forks sh then node. Killing only the pid we launched leaves the real server
# running and the port held.
kill_tree() {
  local pid="$1" child
  for child in $(pgrep -P "$pid" 2>/dev/null); do
    kill_tree "$child"
  done
  kill -TERM "$pid" 2>/dev/null || true
}

cleanup() {
  trap - INT TERM EXIT
  [[ ${#pids[@]} -eq 0 ]] && exit 0
  echo
  info "stopping api and web (the vLLM container stays up; scripts/vllm.sh stop)"
  for pid in "${pids[@]}"; do
    kill_tree "$pid"
  done
  wait 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM EXIT

# Interleaved output is unreadable without knowing who wrote what.
#
# Output goes through a process substitution rather than a pipe: after a pipe
# `$!` is the *last* command, so we would record sed's pid and kill the prefixer
# instead of the service.
start() {
  local label="$1" colour="$2"
  shift 2
  local prefix
  prefix=$(printf '\033[%sm%-4s\033[0m │ ' "$colour" "$label")
  bash -c "$*" > >(sed -u "s/^/${prefix}/") 2>&1 &
  pids+=("$!")
}

port_busy() { command -v ss >/dev/null && ss -ltn 2>/dev/null | grep -q ":$1 "; }

wait_for() {
  local url="$1" name="$2" waited=0
  while ! curl -s --max-time 2 "$url" >/dev/null 2>&1; do
    sleep 1
    waited=$((waited + 1))
    if [[ $waited -gt 90 ]]; then
      warn "$name did not come up within 90s; leaving it running so you can read the log"
      return 1
    fi
  done
  return 0
}

# -- 1. model server --------------------------------------------------------

if scripts/vllm.sh status >/dev/null 2>&1; then
  info "vllm already running on :$VLLM_PORT"
else
  info "starting vllm"
  scripts/vllm.sh start "$@" || die "vllm failed to start"
fi

# AGENT_MODEL has to be the id the server reports, so ask rather than guess.
MODEL=$(
  curl -s --max-time 5 "http://localhost:${VLLM_PORT}/v1/models" 2>/dev/null |
    python3 -c "import sys,json;d=json.load(sys.stdin).get('data') or [];print(d[0]['id'] if d else '')" 2>/dev/null || true
)
[[ -n "$MODEL" ]] || die "vLLM is up but reports no models"

export AGENT_BASE_URL="http://localhost:${VLLM_PORT}/v1"
export AGENT_MODEL="$MODEL"
export NEXT_PUBLIC_API_PORT="$API_PORT"

# -- 2. api and web ---------------------------------------------------------

port_busy "$API_PORT" && die "port $API_PORT is in use; set API_PORT"
port_busy "$WEB_PORT" && die "port $WEB_PORT is in use; set WEB_PORT"

[[ -x "$VENV/bin/uvicorn" ]] || die "the venv is missing; run scripts/run.sh setup"
[[ -d web/node_modules ]] || die "web dependencies are missing; run scripts/run.sh setup"

info "starting api on :$API_PORT and web on :$WEB_PORT"
start api 35 "'$VENV/bin/uvicorn' api.main:app --host 0.0.0.0 --port $API_PORT --reload"
start web 34 "cd web && npm run dev -- --port $WEB_PORT"

wait_for "http://localhost:${API_PORT}/health" api || true
wait_for "http://localhost:${WEB_PORT}" web || true

TRACE=$("$VENV/bin/python" -c "
import sys; sys.path.insert(0, 'packages/agent/src')
from agent.tracing import status
s = status()
print(('on -> ' + s['project']) if s['enabled'] else 'off')
" 2>/dev/null || echo "unknown")

cat <<EOF

  $(printf '\033[1mready\033[0m')
    web        http://localhost:${WEB_PORT}/inspect
    api        http://localhost:${API_PORT}/docs
    model      ${MODEL}  (${AGENT_BASE_URL})
    langsmith  ${TRACE}

  Ctrl-C stops api and web. vLLM keeps running.

EOF

wait
