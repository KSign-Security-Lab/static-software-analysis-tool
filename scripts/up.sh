#!/usr/bin/env bash
#
# vLLM, the API and the web UI in one terminal.
#
#   scripts/up.sh                  start everything (confirms the config first)
#   scripts/up.sh -y               start with the saved config, no questions
#   scripts/up.sh --reconfigure    ask the setup questions again
#
# The first run asks which model, which GPUs, and where to keep the weights, and
# writes the answers to .env. Later runs show that config and let you change it
# -- silently reusing it meant `down` then `up` relaunched the old model with no
# obvious way to pick another. Compose reads .env itself, so the file also stays
# editable by hand.
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

# id | label | approx GiB | tool-call parser | gpus needed
#
# The parser matters: vLLM refuses tool calling without one for the family, and
# the wrong one breaks it silently. `vllm serve --help=all` lists all 33.
# Every id here was checked against the Hugging Face API. The list is a starting
# point, not a whitelist -- "something else" takes any id.
MODELS=(
  "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ|Qwen2.5-Coder 32B, 4-bit -- code specialist|19|hermes|1"
  "Qwen/Qwen2.5-Coder-14B-Instruct|Qwen2.5-Coder 14B, FP16|28|hermes|1"
  "mistralai/Devstral-Small-2507|Devstral Small 24B -- built for code agents|48|mistral|2"
  "openai/gpt-oss-20b|gpt-oss 20B, MXFP4|13|openai|1"
  "openai/gpt-oss-120b|gpt-oss 120B, MXFP4|61|openai|2"
  "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct|DeepSeek-Coder V2 Lite 16B MoE|32|deepseek_v3|1"
  "meta-llama/Llama-3.1-8B-Instruct|Llama 3.1 8B (gated: needs HF_TOKEN)|16|llama3_json|1"
  "zai-org/GLM-4.5-Air|GLM-4.5 Air 106B MoE|60|glm45|2"
  "ibm-granite/granite-3.3-8b-instruct|Granite 3.3 8B|16|granite|1"
  "Qwen/Qwen2.5-0.5B-Instruct|Qwen2.5 0.5B -- plumbing test only, finds nothing|1|hermes|1"
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

  local i=0 id label size par need
  for entry in "${MODELS[@]}"; do
    IFS='|' read -r id label size par need <<<"$entry"
    i=$((i + 1))
    printf '  %2d) %-48s ~%3s GiB  %s\n' "$i" "$label" "$size" \
      "$([[ $need -gt 1 ]] && echo '(2 GPUs)' || echo '')"
  done
  printf '  %2d) something else (any Hugging Face id)\n\n' "$((i + 1))"

  local pick model parser needs=1
  pick=$(ask "Model" "1")
  if [[ "$pick" == "$((i + 1))" ]]; then
    model=$(ask "Hugging Face id" "")
    echo
    echo "  Tool calling needs a parser matching the model family. Without a"
    echo "  correct one, verification falls back to context-only."
    echo "  Options: hermes qwen3_coder mistral llama3_json llama4_json openai"
    echo "           deepseek_v3 glm45 glm47 granite jamba phi4_mini_json pythonic"
    echo "           kimi_k2 minimax internlm seed_oss xlam  (see: vllm serve --help=all)"
    echo
    parser=$(ask "Tool-call parser" "hermes")
  else
    IFS='|' read -r model _ _ parser needs <<<"${MODELS[$((pick - 1))]}"
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

  if [[ "$needs" -gt 1 && "$tp" -lt 2 ]]; then
    printf '\033[33mwarning:\033[0m %s\n' \
      "that model wants 2 GPUs; with one it will fail to allocate. Re-run with --reconfigure and pick 'both'."
  fi

  cat > .env <<EOF
# Written by scripts/up.sh. Compose reads this file automatically.
# Edit freely, or re-run: scripts/up.sh --reconfigure
VLLM_MODEL=$model
VLLM_TOOL_PARSER=$parser
VLLM_GPUS=$gpus
VLLM_TP=$tp
HF_HOME=$cache
EOF
  echo
  info "wrote .env"
}

# Show what is configured and let it be changed. Reusing .env silently meant
# `down` then `up` relaunched the old model with no way to pick another short
# of knowing --reconfigure existed.
confirm_config() {
  # shellcheck disable=SC1091
  (set -a; . ./.env; set +a
   printf '\n\033[36m현재 설정\033[0m\n'
   printf '  모델    %s  (parser %s)\n' "$VLLM_MODEL" "${VLLM_TOOL_PARSER:-hermes}"
   printf '  GPU     %s  (tp=%s)\n' "${VLLM_GPUS:-0}" "${VLLM_TP:-1}"
   printf '  가중치   %s\n\n' "${HF_HOME:-~/.cache/huggingface}")

  local answer
  answer=$(ask "Enter=시작 · c=변경 · q=취소" "")
  case "$answer" in
    c|C) rm -f .env; configure ;;
    q|Q) echo "취소했습니다."; exit 0 ;;
    *) ;;
  esac
}

ASSUME_YES=0
case "${1:-}" in
  -h|--help)
    # Without this an unrecognised flag fell through and started the stack,
    # which is a surprising thing for `--help` to do.
    awk 'NR==1 && /^#!/ {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"
    exit 0
    ;;
  --reconfigure) rm -f .env ;;
  -y|--yes) ASSUME_YES=1 ;;
  "") ;;
  *)
    printf '\033[31merror:\033[0m 알 수 없는 옵션: %s\n' "$1" >&2
    exit 1
    ;;
esac

if [[ ! -f .env ]]; then
  configure
elif [[ "$ASSUME_YES" -eq 0 && -t 0 ]]; then
  confirm_config
fi

# shellcheck disable=SC1091
set -a; . ./.env; set +a
VLLM_PORT="${VLLM_PORT:-8001}"

# A container left running from a previous model would be reused silently, so
# `up` would report a model the server is not actually serving.
running_model() {
  docker inspect "${VLLM_CONTAINER:-ssat-vllm}" --format '{{json .Config.Cmd}}' 2>/dev/null |
    python3 -c "
import json,sys
try: cmd = json.load(sys.stdin)
except Exception: sys.exit()
if '--model' in cmd: print(cmd[cmd.index('--model') + 1])
" 2>/dev/null || true
}

current=$(running_model)
if [[ -n "$current" && "$current" != "$VLLM_MODEL" ]]; then
  printf '\033[33mwarning:\033[0m 실행 중인 컨테이너는 %s 이고 설정은 %s 입니다.\n' "$current" "$VLLM_MODEL"
  if [[ "$ASSUME_YES" -eq 1 || ! -t 0 ]]; then
    printf '  설정에 맞춰 다시 시작합니다.\n'
    docker compose --profile vllm rm -sf vllm >/dev/null 2>&1 || true
  else
    case "$(ask "다시 시작할까요? Enter=예 · n=아니오(실행 중인 것 사용)" "")" in
      n|N) VLLM_MODEL="$current" ;;
      *) docker compose --profile vllm rm -sf vllm >/dev/null 2>&1 || true ;;
    esac
  fi
fi

pids=()

# uvicorn --reload forks a reloader and a server; npm forks sh then node.
# Killing only the pid we launched leaves the real server holding the port.
kill_tree() {
  local child
  for child in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$child"; done
  kill -TERM "$1" 2>/dev/null || true
}

cleanup() {
  local code=$?
  trap - INT TERM EXIT
  # Nothing started means nothing to stop, and saying otherwise hides whatever
  # actually went wrong -- which is how a failing preflight looked like a
  # successful shutdown.
  if [[ ${#pids[@]} -gt 0 ]]; then
    printf '\n\033[36mstopping api and web (vllm stays up: scripts/run.sh down)\033[0m\n'
    for pid in "${pids[@]}"; do
      kill_tree "$pid"
    done
    wait 2>/dev/null || true
  fi
  exit "$code"
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

# A stale server from a previous run holds the port, and uvicorn's and next's
# own errors for that are easy to misread. Name the process and how to kill it.
check_port() {
  local port="$1" name="$2" pid
  # `|| true`: a free port means grep finds nothing and exits 1, which under
  # `set -o pipefail` would abort the script instead of reporting "port free".
  pid=$(ss -ltnp 2>/dev/null | grep ":${port} " | grep -oP 'pid=\K[0-9]+' | head -1 || true)
  if [[ -z "$pid" ]]; then
    return 0
  fi
  printf '\033[31merror:\033[0m port %s (%s) is held by pid %s: %s\n' \
    "$port" "$name" "$pid" "$(ps -o args= -p "$pid" 2>/dev/null | head -1)" >&2
  printf '  kill it with:  kill %s\n  or use another port:  %s=NNNN scripts/run.sh up\n' \
    "$pid" "$([[ $name == api ]] && echo API_PORT || echo WEB_PORT)" >&2
  exit 1
}
check_port "$API_PORT" api
check_port "$WEB_PORT" web

info "starting ${VLLM_MODEL} (parser ${VLLM_TOOL_PARSER}, weights in ${HF_HOME})"
echo "  follow it with: scripts/run.sh vllm-logs"
docker compose --profile vllm up -d --wait vllm

# AGENT_MODEL must be the id the server reports, so ask instead of guessing.
AGENT_MODEL=$(curl -s "http://localhost:${VLLM_PORT}/v1/models" |
  python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(d[0]['id'])")
export AGENT_MODEL
export AGENT_BASE_URL="http://localhost:${VLLM_PORT}/v1"
export NEXT_PUBLIC_API_PORT="$API_PORT"

# Postgres, which this script never started even though the API does not run
# without it -- it relied on somebody having run `docker compose up` by hand.
# `--wait` blocks on the healthcheck, and `-d` makes it a no-op when it is
# already up.
docker compose up -d --wait postgres

# The corpus of known weaknesses (agent/rag/), in before the API serves its
# first request. Sample ids are derived from content, so an unchanged corpus
# costs one query and never loads the embedding model. Not fatal: a failure
# here means `search_corpus` has nothing to answer with, not that the tool
# cannot run.
.venv/bin/agent corpus ingest || echo "  corpus ingest failed; search_corpus will find nothing"

# --timeout-graceful-shutdown, or `--reload` is a trap. A reload waits for open
# requests to finish, and the progress stream does not finish: it ends when its
# run ends, and a tab left open on a finished run never delivers that. So every
# edit to a watched file hung the server with the port still listening and every
# request timing out, and the only way out was killing the worker by hand.
start api 35 ".venv/bin/uvicorn api.main:app --host 0.0.0.0 --port $API_PORT --reload --timeout-graceful-shutdown 2"
start web 34 "cd web && npm run dev -- --port $WEB_PORT"

printf '\n  \033[1mready\033[0m  web http://localhost:%s/inspect   api :%s   model %s\n\n' \
  "$WEB_PORT" "$API_PORT" "$AGENT_MODEL"

wait
