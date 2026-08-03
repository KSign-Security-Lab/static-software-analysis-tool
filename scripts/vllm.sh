#!/usr/bin/env bash
#
# Start, stop and inspect a vLLM server for the agent package.
#
# Runs vLLM in Docker rather than on the host. The host install here is broken
# (vllm 0.17 against torch 2.4, which predates torch.library.infer_schema) and
# this workspace is on Python 3.14, which vLLM does not publish wheels for. The
# agent only needs an HTTP endpoint, so the two never have to share a runtime.
#
#   scripts/vllm.sh              interactive: pick a model and a GPU layout
#   scripts/vllm.sh start ...    non-interactive, see --help
#   scripts/vllm.sh status
#   scripts/vllm.sh logs [-f]
#   scripts/vllm.sh stop
#
set -euo pipefail

CONTAINER="${VLLM_CONTAINER:-ssat-vllm}"
IMAGE="${VLLM_IMAGE:-vllm/vllm-openai:latest}"
HF_CACHE="${HF_HOME:-$HOME/.cache/huggingface}"
DEFAULT_PORT=8001   # the SSAT API already owns 8000
DEFAULT_MAXLEN=16384

# Catalogue offered interactively. Sizes are weights only and approximate --
# KV cache needs headroom on top, which is what the fit check below allows for.
# Anything not listed can be typed in; the id is checked against the Hugging
# Face API before a download is started.
#
#   id | label | approx weight GiB | min GPUs
CATALOGUE=(
  "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ|Qwen2.5-Coder 32B, 4-bit AWQ|19|1"
  "Qwen/Qwen2.5-Coder-14B-Instruct|Qwen2.5-Coder 14B, FP16|28|1"
  "Qwen/Qwen2.5-Coder-7B-Instruct|Qwen2.5-Coder 7B, FP16|15|1"
  "Qwen/Qwen2.5-Coder-32B-Instruct|Qwen2.5-Coder 32B, FP16|64|2"
  "Qwen/Qwen3-32B|Qwen3 32B, FP16|64|2"
)

die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[36m%s\033[0m\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }

is_tty() { [[ -t 0 && -t 1 ]]; }

require_docker() {
  command -v docker >/dev/null || die "docker is not installed"
  docker info >/dev/null 2>&1 || die "cannot talk to the docker daemon"
}

# ---------------------------------------------------------------- GPU probing

gpu_count() { nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | wc -l; }

gpu_table() {
  nvidia-smi --query-gpu=index,name,memory.total,memory.used,compute_cap \
    --format=csv,noheader,nounits 2>/dev/null
}

# Free VRAM in GiB on a specific index.
gpu_free_gib() {
  local idx="$1" total used
  IFS=, read -r total used < <(
    nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits -i "$idx" 2>/dev/null
  )
  echo $(( (total - used) / 1024 ))
}

show_gpus() {
  info "GPUs"
  gpu_table | while IFS=, read -r idx name total used cap; do
    printf '  %s: %-32s %5s MiB total, %5s used, sm_%s\n' \
      "$idx" "$(echo "$name" | xargs)" "$(echo "$total" | xargs)" "$(echo "$used" | xargs)" \
      "$(echo "$cap" | xargs | tr -d '.')"
  done
}

# Tensor parallelism across mixed generations works, but it is worth knowing
# what it costs before choosing it.
warn_if_heterogeneous() {
  local caps
  caps=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | sort -u | wc -l)
  [[ "$caps" -le 1 ]] && return 0
  warn "the GPUs are different generations; tensor parallelism will run at the slower card's pace and FP8 is unavailable"
  if command -v nvidia-smi >/dev/null && ! nvidia-smi topo -m 2>/dev/null | grep -q NV[0-9]; then
    warn "no NVLink detected: all-reduce goes over PCIe, so TP buys capacity rather than speed"
  fi
}

# ------------------------------------------------------------------ model ids

# Check a model id before committing to a download that can run for an hour.
#
# The Hugging Face API answers 401 for a repository that does not exist, not
# 404: unauthenticated callers are not told the difference between "missing"
# and "private", so that probing cannot enumerate private repos. Gated-but-real
# models like meta-llama/* still answer 200 for metadata. In practice 401
# therefore means a typo, and treating it as "gated, carry on" -- which this
# did at first -- lets a typo start a multi-gigabyte download that cannot
# succeed.
model_exists() {
  local id="$1" code auth=()
  command -v curl >/dev/null || return 0   # cannot check; let the download decide
  [[ -n "${HF_TOKEN:-}" ]] && auth=(-H "Authorization: Bearer $HF_TOKEN")

  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${auth[@]}" \
    "https://huggingface.co/api/models/${id}" 2>/dev/null || echo 000)

  case "$code" in
    200) return 0 ;;
    404) return 1 ;;
    401|403)
      if [[ -n "${HF_TOKEN:-}" ]]; then
        warn "'$id' is not visible to your HF_TOKEN: it does not exist, or the licence is unaccepted"
      else
        warn "'$id' returned HTTP $code. Unauthenticated, that means either a typo or a private repo."
        warn "If it is real and gated, accept the licence and set HF_TOKEN; otherwise check the spelling."
      fi
      return 1
      ;;
    *)
      warn "could not reach the Hugging Face API (HTTP $code); skipping the existence check"
      return 0
      ;;
  esac
}

cached_locally() {
  local dir="${HF_CACHE}/hub/models--${1//\//--}"
  [[ -d "$dir" ]]
}

# ------------------------------------------------------------------- the menu

choose_model() {
  local total_free entry id label size mingpu fit n=0
  total_free=$(gpu_free_gib 0)

  echo >&2
  info "Models" >&2
  for entry in "${CATALOGUE[@]}"; do
    IFS='|' read -r id label size mingpu <<<"$entry"
    n=$((n + 1))
    if [[ "$mingpu" -gt 1 ]]; then
      fit="needs 2 GPUs (tensor parallel)"
    elif [[ "$size" -lt $((total_free * 8 / 10)) ]]; then
      fit="fits GPU 0"
    else
      fit="tight on one GPU"
    fi
    cached_locally "$id" && fit="$fit, already downloaded"
    printf '  %d) %-34s ~%3s GiB  %s\n' "$n" "$label" "$size" "$fit" >&2
  done
  printf '  %d) something else (type a Hugging Face id)\n' "$((n + 1))" >&2
  echo >&2

  local pick
  read -rp "Model [1]: " pick </dev/tty
  pick="${pick:-1}"

  if [[ "$pick" == "$((n + 1))" ]]; then
    read -rp "Hugging Face model id: " id </dev/tty
    [[ -n "$id" ]] || die "no model id given"
  elif [[ "$pick" =~ ^[0-9]+$ ]] && (( pick >= 1 && pick <= n )); then
    IFS='|' read -r id _ _ _ <<<"${CATALOGUE[$((pick - 1))]}"
  else
    die "not a choice: $pick"
  fi
  echo "$id"
}

choose_gpus() {
  local count pick
  count=$(gpu_count)
  if [[ "$count" -lt 2 ]]; then echo "0"; return; fi

  echo >&2
  info "GPU layout" >&2
  echo "  1) GPU 0 only          fastest card, no interconnect cost" >&2
  echo "  2) GPU 1 only" >&2
  echo "  3) both, tensor parallel   needed for a 32B at FP16" >&2
  echo >&2
  read -rp "Layout [1]: " pick </dev/tty
  case "${pick:-1}" in
    1) echo "0" ;;
    2) echo "1" ;;
    3) echo "0,1" ;;
    *) die "not a choice: $pick" ;;
  esac
}

# ------------------------------------------------------------------- commands

cmd_status() {
  require_docker
  if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "not running"
    docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER" &&
      echo "(a stopped container named $CONTAINER exists; 'stop' removes it)"
    return 1
  fi
  local port
  port=$(docker port "$CONTAINER" 8000/tcp 2>/dev/null | head -1 | sed 's/.*://')
  echo "running as $CONTAINER on port ${port:-?}"
  if command -v curl >/dev/null && [[ -n "$port" ]]; then
    local body
    body=$(curl -s --max-time 5 "http://localhost:${port}/v1/models" 2>/dev/null || true)
    if [[ -n "$body" ]]; then
      echo "served model ids:"
      python3 -c "import sys,json;[print('  '+m['id']) for m in json.load(sys.stdin)['data']]" <<<"$body" 2>/dev/null ||
        echo "  (unparseable response)"
      echo
      echo "  export AGENT_BASE_URL=http://localhost:${port}/v1"
    else
      echo "still loading -- weights download and load can take a long while"
      echo "  scripts/vllm.sh logs -f"
    fi
  fi
}

cmd_logs() { require_docker; docker logs "${1:-}" "$CONTAINER"; }

cmd_stop() {
  require_docker
  docker rm -f "$CONTAINER" >/dev/null 2>&1 && info "stopped $CONTAINER" || echo "nothing to stop"
}

cmd_start() {
  local model="" devices="" port="$DEFAULT_PORT" maxlen="$DEFAULT_MAXLEN" served="" quant="" parser="" verify=1 extra=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --no-verify) verify=0; shift ;;
      --model) model="$2"; shift 2 ;;
      --gpus) devices="$2"; shift 2 ;;
      --port) port="$2"; shift 2 ;;
      --max-model-len) maxlen="$2"; shift 2 ;;
      --served-model-name) served="$2"; shift 2 ;;
      --quantization) quant="$2"; shift 2 ;;
      --tool-call-parser) parser="$2"; shift 2 ;;
      --) shift; extra=("$@"); break ;;
      *) die "unknown option: $1" ;;
    esac
  done

  require_docker
  [[ "$(gpu_count)" -ge 1 ]] || die "no GPUs visible to nvidia-smi"

  docker image inspect "$IMAGE" >/dev/null 2>&1 ||
    die "image $IMAGE is not present. Pull it first: docker pull $IMAGE"

  if [[ -z "$model" ]]; then
    is_tty || die "no --model given and not attached to a terminal"
    show_gpus
    warn_if_heterogeneous
    model=$(choose_model)
    devices=$(choose_gpus)
  fi
  devices="${devices:-0}"
  served="${served:-agent}"

  if [[ "$verify" -eq 1 ]]; then
    model_exists "$model" ||
      die "cannot confirm '$model' exists. Fix the id, set HF_TOKEN, or pass --no-verify."
  fi

  if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    die "$CONTAINER is already running. 'scripts/vllm.sh stop' first."
  fi
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true

  if command -v ss >/dev/null && ss -ltn 2>/dev/null | grep -q ":${port} "; then
    die "port ${port} is already in use. Pass --port."
  fi

  local tp
  tp=$(awk -F, '{print NF}' <<<"$devices")

  local args=(--model "$model" --served-model-name "$served"
              --max-model-len "$maxlen" --tensor-parallel-size "$tp")
  [[ -n "$quant" ]] && args+=(--quantization "$quant")
  # Only needed for the agent's function_calling fallback: vLLM rejects tool
  # calling outright without a parser for the model family. The primary path
  # (json_schema guided decoding) works without it.
  [[ -n "$parser" ]] && args+=(--enable-auto-tool-choice --tool-call-parser "$parser")
  [[ ${#extra[@]} -gt 0 ]] && args+=("${extra[@]}")

  # Mixed-generation TP has no peer access here, so vLLM's custom all-reduce
  # cannot be used. It normally detects this; saying so explicitly avoids a
  # startup hang on the versions that do not.
  if [[ "$tp" -gt 1 ]] && ! peer_access_available; then
    args+=(--disable-custom-all-reduce)
    warn "peer access unavailable between these GPUs; passing --disable-custom-all-reduce"
  fi

  cached_locally "$model" ||
    warn "$model is not in $HF_CACHE yet; the first start downloads it, which can take a long time"

  info "starting $model on GPU(s) $devices, port $port (tp=$tp)"
  mkdir -p "$HF_CACHE"
  docker run -d --name "$CONTAINER" \
    --gpus "\"device=${devices}\"" \
    --ipc=host \
    -p "${port}:8000" \
    -v "${HF_CACHE}:/root/.cache/huggingface" \
    ${HF_TOKEN:+-e HF_TOKEN="$HF_TOKEN"} \
    "$IMAGE" "${args[@]}" >/dev/null

  info "container started; waiting for the server to answer"
  echo "  weights load (and download, first time) happens now -- this is the slow part"
  echo "  follow along with: scripts/vllm.sh logs -f"
  wait_for_ready "$port"
}

peer_access_available() {
  python3 - <<'PY' 2>/dev/null
import subprocess, sys
out = subprocess.run(["nvidia-smi", "topo", "-m"], capture_output=True, text=True).stdout
sys.exit(0 if any(tok.startswith("NV") and tok[2:].isdigit() for tok in out.split()) else 1)
PY
}

wait_for_ready() {
  local port="$1" waited=0
  while true; do
    if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
      echo
      warn "the container exited. Last lines:"
      docker logs --tail 30 "$CONTAINER" 2>&1 | sed 's/^/    /'
      return 1
    fi
    if curl -s --max-time 3 "http://localhost:${port}/v1/models" >/dev/null 2>&1; then
      echo
      info "ready"
      cmd_status
      echo
      echo "Now run the agent against it:"
      echo "  scripts/agent.sh"
      return 0
    fi
    printf '\r  waiting... %ds' "$waited"
    sleep 5
    waited=$((waited + 5))
  done
}

usage() {
  # The header comment is the usage text. Read until the first line that is not
  # a comment, rather than a line range that goes stale the moment the header
  # is edited -- which it already did.
  awk 'NR==1 && /^#!/ {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"
  cat <<'EOF'

start options:
  --model ID              Hugging Face id (prompted for if omitted)
  --gpus 0 | 1 | 0,1      which cards; a comma list sets tensor-parallel-size
  --port N                host port (default 8001; 8000 is the SSAT API)
  --max-model-len N       must exceed AGENT_CONTEXT_CHARS in tokens (default 16384)
  --served-model-name S   the id clients use; this is AGENT_MODEL (default "agent")
  --quantization Q        e.g. awq, gptq
  --no-verify             skip the Hugging Face existence check
  --tool-call-parser P    e.g. hermes, llama3_json. Only needed for the agent's
                          function_calling fallback; json_schema needs nothing.
  -- ...                  everything after -- is passed to `vllm serve`

environment:
  VLLM_CONTAINER, VLLM_IMAGE, HF_HOME, HF_TOKEN
EOF
}

main() {
  case "${1:-}" in
    ""|start)      [[ $# -gt 0 ]] && shift; cmd_start "$@" ;;
    status)        cmd_status ;;
    logs)          shift; cmd_logs "${1:-}" ;;
    stop)          cmd_stop ;;
    -h|--help)     usage ;;
    *)             usage; exit 1 ;;
  esac
}

main "$@"
