#!/usr/bin/env bash
#
# vLLM, the API and the web UI in one terminal.
#
#   scripts/up.sh                  start everything
#   scripts/up.sh --reconfigure    ask the setup questions again
#
# The first run asks which model, which GPUs, and where to keep the weights, and
# writes the answers to .env. Compose reads .env by itself, so later runs are
# silent and the file stays editable.
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

#   id | label | approx GiB on disk
MODELS=(
  "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ|Qwen2.5-Coder 32B, 4-bit|19"
  "Qwen/Qwen2.5-Coder-14B-Instruct|Qwen2.5-Coder 14B, FP16|28"
  "Qwen/Qwen2.5-Coder-7B-Instruct|Qwen2.5-Coder 7B, FP16|15"
  "Qwen/Qwen2.5-Coder-32B-Instruct|Qwen2.5-Coder 32B, FP16 (needs 2 GPUs)|64"
  "Qwen/Qwen2.5-0.5B-Instruct|Qwen2.5 0.5B -- plumbing test only, finds nothing|1"
)

info() { printf '\033[36m%s\033[0m\n' "$*"; }

ask() {
  local prompt="$1" default="$2" answer
  read -rp "$(printf '%s \033[90m[%s]\033[0m: ' "$prompt" "$default")" answer </dev/tty
  echo "${answer:-$default}"
}

configure() {
  info "First run -- these answers go to .env and are not asked again."
  echo

  local i=0 id label size
  for entry in "${MODELS[@]}"; do
    IFS='|' read -r id label size <<<"$entry"
    i=$((i + 1))
    printf '  %d) %-46s ~%s GiB\n' "$i" "$label" "$size"
  done
  printf '  %d) something else\n\n' "$((i + 1))"

  local pick model
  pick=$(ask "Model" "1")
  if [[ "$pick" == "$((i + 1))" ]]; then
    model=$(ask "Hugging Face id" "")
  else
    IFS='|' read -r model _ _ <<<"${MODELS[$((pick - 1))]}"
  fi
  [[ -n "$model" ]] || { echo "no model given" >&2; exit 1; }

  local gpus=0 tp=1 count
  count=$(nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | wc -l)
  if [[ "$count" -gt 1 ]]; then
    echo
    printf '  1) GPU 0 only\n  2) GPU 1 only\n  3) both, tensor parallel (needed for a 32B at FP16)\n\n'
    case "$(ask "GPUs" "1")" in
      2) gpus=1 ;;
      3) gpus="0,1"; tp=2 ;;
      *) gpus=0 ;;
    esac
  fi

  echo
  local cache
  cache=$(ask "Where to keep downloaded weights" "${HF_HOME:-$HOME/.cache/huggingface}")
  mkdir -p "$cache"

  cat > .env <<EOF
# Written by scripts/up.sh. Compose reads this file automatically.
# Edit freely, or re-run: scripts/up.sh --reconfigure
VLLM_MODEL=$model
VLLM_GPUS=$gpus
VLLM_TP=$tp
HF_HOME=$cache
EOF
  echo
  info "wrote .env"
}

[[ "${1:-}" == "--reconfigure" ]] && rm -f .env
[[ -f .env ]] || configure

# shellcheck disable=SC1091
set -a; . ./.env; set +a
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
  printf '\n\033[36mstopping api and web (vllm stays up: scripts/run.sh down)\033[0m\n'
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

info "starting ${VLLM_MODEL} (weights in ${HF_HOME}) -- first pull can take a while"
echo "  follow it with: scripts/run.sh vllm-logs"
docker compose --profile vllm up -d --wait vllm

# AGENT_MODEL must be the id the server reports, so ask instead of guessing.
AGENT_MODEL=$(curl -s "http://localhost:${VLLM_PORT}/v1/models" |
  python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(d[0]['id'])")
export AGENT_MODEL
export AGENT_BASE_URL="http://localhost:${VLLM_PORT}/v1"
export NEXT_PUBLIC_API_PORT="$API_PORT"

start api 35 ".venv/bin/uvicorn api.main:app --host 0.0.0.0 --port $API_PORT --reload"
start web 34 "cd web && npm run dev -- --port $WEB_PORT"

printf '\n  \033[1mready\033[0m  web http://localhost:%s/inspect   api :%s   model %s\n\n' \
  "$WEB_PORT" "$API_PORT" "$AGENT_MODEL"

wait
