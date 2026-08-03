#!/usr/bin/env bash
#
# Run the LLM agent against a source tree, interactively.
#
# Finds a model endpoint, asks it what it serves, and sets AGENT_BASE_URL /
# AGENT_MODEL from the answer rather than making you guess -- getting
# AGENT_MODEL wrong (the Hugging Face path instead of the served id) is the
# usual first failure.
#
#   scripts/agent.sh                     interactive
#   scripts/agent.sh index PATH          index only, no model needed
#   scripts/agent.sh inspect PATH        non-interactive, uses AGENT_* from env
#
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
REPO="$PWD"
VENV="$REPO/.venv"
DEFAULT_TARGET="packages/ssat/tests/fixtures/f2a"

# Endpoints probed in order: the vLLM server this repo's script starts, the
# SSAT API's neighbour port, then Ollama, which is often already up.
CANDIDATE_ENDPOINTS=(
  "http://localhost:8001/v1"
  "http://localhost:8000/v1"
  "http://localhost:11434/v1"
)

die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[36m%s\033[0m\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
is_tty() { [[ -t 0 && -t 1 ]]; }

agent_bin() {
  [[ -x "$VENV/bin/agent" ]] || die "agent is not installed. Run: uv sync"
  echo "$VENV/bin/agent"
}

# Model ids an OpenAI-compatible endpoint reports, one per line.
models_at() {
  curl -s --max-time 5 "$1/models" 2>/dev/null |
    python3 -c "import sys,json;[print(m['id']) for m in json.load(sys.stdin).get('data',[])]" 2>/dev/null
}

live_endpoints() {
  local url
  for url in "${CANDIDATE_ENDPOINTS[@]}"; do
    [[ -n "$(models_at "$url")" ]] && echo "$url"
  done
}

choose_endpoint() {
  local found=() url
  mapfile -t found < <(live_endpoints)

  if [[ ${#found[@]} -eq 0 ]]; then
    warn "no OpenAI-compatible endpoint is answering on 8001, 8000 or 11434"
    echo "Start one with:  scripts/vllm.sh" >&2
    echo >&2
    read -rp "Endpoint URL (blank to abort): " url </dev/tty
    [[ -n "$url" ]] || die "no endpoint"
    echo "$url"
    return
  fi

  if [[ ${#found[@]} -eq 1 ]]; then
    echo "${found[0]}"
    return
  fi

  echo >&2
  info "Endpoints" >&2
  local i=0
  for url in "${found[@]}"; do
    i=$((i + 1))
    printf '  %d) %-38s %s\n' "$i" "$url" "$(models_at "$url" | paste -sd, - | cut -c1-48)" >&2
  done
  echo >&2
  local pick
  read -rp "Endpoint [1]: " pick </dev/tty
  pick="${pick:-1}"
  [[ "$pick" =~ ^[0-9]+$ ]] && (( pick >= 1 && pick <= ${#found[@]} )) || die "not a choice: $pick"
  echo "${found[$((pick - 1))]}"
}

choose_model() {
  local url="$1" models=() m i=0 pick
  mapfile -t models < <(models_at "$url")
  [[ ${#models[@]} -gt 0 ]] || die "$url reports no models"

  if [[ ${#models[@]} -eq 1 ]]; then
    echo "${models[0]}"
    return
  fi

  echo >&2
  info "Models served by $url" >&2
  for m in "${models[@]}"; do
    i=$((i + 1))
    printf '  %d) %s\n' "$i" "$m" >&2
  done
  echo >&2
  read -rp "Model [1]: " pick </dev/tty
  pick="${pick:-1}"
  [[ "$pick" =~ ^[0-9]+$ ]] && (( pick >= 1 && pick <= ${#models[@]} )) || die "not a choice: $pick"
  echo "${models[$((pick - 1))]}"
}

choose_target() {
  local target
  echo >&2
  read -rp "Path to inspect [$DEFAULT_TARGET]: " target </dev/tty
  target="${target:-$DEFAULT_TARGET}"
  [[ -d "$target" ]] || die "not a directory: $target"
  echo "$target"
}

count_chunks() {
  # Cheap and model-free: says how much work an inspection would be before any
  # of it is paid for.
  "$(agent_bin)" index "$1" 2>/dev/null | sed -n 's/.*"chunks": \([0-9]*\).*/\1/p' | head -1
}

cmd_index() {
  local target="${1:-}"
  [[ -n "$target" ]] || { is_tty && target=$(choose_target) || die "usage: agent.sh index PATH"; }
  exec "$(agent_bin)" index "$target"
}

cmd_inspect() {
  local target="${1:-}"
  [[ -n "$target" ]] || die "usage: agent.sh inspect PATH"
  # Checked before the model, so a mistyped path fails on the path rather than
  # on a confusing complaint about configuration.
  [[ -d "$target" ]] || die "not a directory: $target"
  [[ -n "${AGENT_MODEL:-}" ]] || die "AGENT_MODEL is not set. Run scripts/agent.sh with no arguments to pick one."
  exec "$(agent_bin)" inspect -v "$target"
}

interactive() {
  info "SSAT agent"
  echo

  local endpoint model target chunks mode
  endpoint=$(choose_endpoint)
  model=$(choose_model "$endpoint")
  target=$(choose_target)

  export AGENT_BASE_URL="$endpoint"
  export AGENT_MODEL="$model"

  echo
  info "Indexing (deterministic, no model calls)"
  "$(agent_bin)" index "$target" || die "indexing failed"
  chunks=$(count_chunks "$target")

  echo
  info "Ready"
  echo "  endpoint  $AGENT_BASE_URL"
  echo "  model     $AGENT_MODEL"
  echo "  target    $target"
  [[ -n "$chunks" ]] && echo "  chunks    $chunks  (one model call each, plus one per candidate finding)"
  echo
  echo "  1) inspect now"
  echo "  2) stop here, just print the environment"
  echo
  read -rp "Choice [1]: " mode </dev/tty
  case "${mode:-1}" in
    1)
      echo
      [[ -n "$chunks" && "$chunks" -gt 40 ]] &&
        warn "$chunks chunks is a long run; consider a smaller path first"
      info "Inspecting -- minutes, not seconds. Ctrl-C is safe: progress is kept."
      echo
      exec "$(agent_bin)" inspect -v "$target"
      ;;
    2)
      echo
      echo "export AGENT_BASE_URL=$AGENT_BASE_URL"
      echo "export AGENT_MODEL=$AGENT_MODEL"
      echo "$VENV/bin/agent inspect -v $target"
      ;;
    *) die "not a choice: $mode" ;;
  esac
}

usage() {
  # The header comment is the usage text; read until the first non-comment line
  # so editing the header cannot desynchronise it.
  awk 'NR==1 && /^#!/ {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"
  cat <<'EOF'

Re-running an inspection is cheap: chunk ids are content-derived, so unchanged
code is skipped and only edited functions are analysed again.
EOF
}

case "${1:-}" in
  "")         is_tty || { usage; exit 1; }; interactive ;;
  index)      shift; cmd_index "${1:-}" ;;
  inspect)    shift; cmd_inspect "${1:-}" ;;
  -h|--help)  usage ;;
  *)          usage; exit 1 ;;
esac
