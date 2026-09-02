#!/usr/bin/env bash
#
# One entry point for this repo: the container stack and the dev tasks.
#
#   scripts/ssat.sh              the menu
#   scripts/ssat.sh up           vLLM, Postgres, the API and the web UI
#   scripts/ssat.sh up vllm      start named containers and nothing else
#   scripts/ssat.sh down vllm    stop containers; `delete` also removes them
#   scripts/ssat.sh status       what is running
#   scripts/ssat.sh logs vllm    follow a container's log
#   scripts/ssat.sh <task> ...   run a [tool.tasks] entry from pyproject.toml
#
# Flags for `up`: -y takes the saved config without asking, --reconfigure asks
# the setup questions again.
#
# Stack actions live in this file because they are Compose calls with a service
# picker in front. Dev tasks live in [tool.tasks] and this file only dispatches
# them, so the manifest stays the list and the two cannot disagree.
#
# Compose runs the containers. The API and the web UI run on the host so their
# reloaders work, which is the only reason `up` is a script rather than a fourth
# Compose service. Ctrl-C stops those two; the containers are left up because
# reloading model weights costs minutes.
#
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Overridable so the tests can point the dispatcher at a manifest of their own
# and prove that no task is hard-coded here.
MANIFEST="${SSAT_MANIFEST:-pyproject.toml}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

info() { printf '\033[36m%s\033[0m\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*"; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

interactive() { [[ -t 0 ]]; }

# The prompt goes to stderr (bash does that for read -p), so this stays usable
# inside a command substitution that is capturing the answer.
ask() {
  local prompt="$1" default="$2" answer
  read -rp "$(printf '%s \033[90m[%s]\033[0m: ' "$prompt" "$default")" answer </dev/tty
  echo "${answer:-$default}"
}

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

# name | compose profile | label | the compose services it stands for
#
# `secbench` is one target rather than two because its daemon is an
# implementation detail: the tooling without it is a container that cannot
# reach Docker.
TARGETS=(
  "vllm|vllm|the model server|vllm"
  "postgres||the run database|postgres"
  "joern||the CPG backend|joern"
  "secbench|secbench|SEC-bench tooling and its own Docker daemon|secbench secbench-docker"
)

target_field() {
  local wanted="$1" field="$2" name profile label services
  for entry in "${TARGETS[@]}"; do
    IFS='|' read -r name profile label services <<<"$entry"
    [[ "$name" == "$wanted" ]] || continue
    case "$field" in
      profile) echo "$profile" ;;
      label) echo "$label" ;;
      services) echo "$services" ;;
    esac
    return 0
  done
  return 1
}

target_names() {
  local name
  for entry in "${TARGETS[@]}"; do
    IFS='|' read -r name _ <<<"$entry"
    echo "$name"
  done
}

# Fills PROFILE_FLAGS and SERVICE_LIST. Compose needs --profile for a service
# that declares one and otherwise silently matches nothing, which reads as
# "already stopped" rather than as the mistake it is.
PROFILE_FLAGS=()
SERVICE_LIST=()
resolve_targets() {
  PROFILE_FLAGS=()
  SERVICE_LIST=()
  local target profile
  for target in "$@"; do
    profile=$(target_field "$target" profile) ||
      die "unknown target: $target (one of: $(target_names | tr '\n' ' '))"
    [[ -z "$profile" ]] || PROFILE_FLAGS+=(--profile "$profile")
    # Word splitting is the point: one target can name several services.
    # shellcheck disable=SC2206
    SERVICE_LIST+=($(target_field "$target" services))
  done
}

# Numbers, names, "all"; comma or space separated. Prints the chosen names one
# per line, with the menu itself on stderr so the caller can capture the choice.
pick_targets() {
  local heading="$1" default="${2:-}"
  local -a names=()
  mapfile -t names < <(target_names)

  printf '\n\033[1m%s\033[0m\n\n' "$heading" >&2
  local i=0 name
  for name in "${names[@]}"; do
    i=$((i + 1))
    printf '  %2d) %-9s %s\n' "$i" "$name" "$(target_field "$name" label)" >&2
  done
  printf '\n  \033[90mseveral at once: 1,2 · everything: all\033[0m\n\n' >&2

  local answer
  answer=$(ask "choice" "$default")
  [[ -n "$answer" ]] || die "nothing chosen"

  local -a chosen=()
  local token
  for token in ${answer//,/ }; do
    case "$token" in
      all) chosen=("${names[@]}"); break ;;
      [0-9]*)
        [[ "$token" -ge 1 && "$token" -le ${#names[@]} ]] || die "no such choice: $token"
        chosen+=("${names[$((token - 1))]}")
        ;;
      *)
        target_field "$token" profile >/dev/null || die "unknown target: $token"
        chosen+=("$token")
        ;;
    esac
  done
  printf '%s\n' "${chosen[@]}"
}

# ---------------------------------------------------------------------------
# vLLM configuration
# ---------------------------------------------------------------------------

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

configure() {
  info "these answers go to .env; change them later with: scripts/ssat.sh up --reconfigure"
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
  [[ -n "$model" ]] || die "no model given"

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
    warn "that model wants 2 GPUs; with one it will fail to allocate. Re-run with --reconfigure and pick 'both'."
  fi

  cat > .env <<EOF
# Written by scripts/ssat.sh. Compose reads this file automatically.
# Edit freely, or re-run: scripts/ssat.sh up --reconfigure
VLLM_MODEL=$model
VLLM_TOOL_PARSER=$parser
VLLM_GPUS=$gpus
VLLM_TP=$tp
HF_HOME=$cache
EOF
  echo
  info "wrote .env"
}

show_config() {
  [[ -f .env ]] || return 0
  # shellcheck disable=SC1091
  (set -a; . ./.env; set +a
   printf '\n  \033[1mvLLM\033[0m  %s  \033[90m(parser %s, GPU %s, tp %s)\033[0m\n' \
     "${VLLM_MODEL:-unset}" "${VLLM_TOOL_PARSER:-hermes}" "${VLLM_GPUS:-0}" "${VLLM_TP:-1}"
   printf '        \033[90mweights in %s\033[0m\n' "${HF_HOME:-$HOME/.cache/huggingface}")
}

# ---------------------------------------------------------------------------
# up
# ---------------------------------------------------------------------------

port_holder() {
  # `|| true`: a free port means grep finds nothing and exits 1, which under
  # pipefail would abort the script instead of reporting "port free".
  ss -ltnp 2>/dev/null | grep ":${1} " | grep -oP 'pid=\K[0-9]+' | head -1 || true
}

# A stale server from a previous run holds the port, and uvicorn's and next's
# own errors for that are easy to misread. Name the process and how to kill it.
check_port() {
  local port="$1" name="$2" pid
  pid=$(port_holder "$port")
  [[ -n "$pid" ]] || return 0
  printf '\033[31merror:\033[0m port %s (%s) is held by pid %s: %s\n' \
    "$port" "$name" "$pid" "$(ps -o args= -p "$pid" 2>/dev/null | head -1)" >&2
  printf '  kill it with:  kill %s\n  or use another port:  %s=NNNN scripts/ssat.sh up\n' \
    "$pid" "$([[ $name == api ]] && echo API_PORT || echo WEB_PORT)" >&2
  exit 1
}

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

PIDS=()

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
  if [[ ${#PIDS[@]} -gt 0 ]]; then
    printf '\n\033[36mstopping api and web (containers stay up: scripts/ssat.sh down)\033[0m\n'
    local pid
    for pid in "${PIDS[@]}"; do kill_tree "$pid"; done
    wait 2>/dev/null || true
  fi
  exit "$code"
}

# Through a process substitution, not a pipe: after a pipe `$!` is the last
# command, so we would record sed and kill the log prefixer instead.
start_host_process() {
  local prefix
  prefix=$(printf '\033[%sm%-4s\033[0m │ ' "$2" "$1")
  bash -c "$3" > >(sed -u "s/^/${prefix}/") 2>&1 &
  PIDS+=("$!")
}

start_containers() {
  resolve_targets "$@"
  docker compose "${PROFILE_FLAGS[@]+"${PROFILE_FLAGS[@]}"}" up -d --wait "${SERVICE_LIST[@]}"
  info "up: $*"
}

# vLLM, Postgres, the API and the web UI, in this terminal.
start_everything() {
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
  local vllm_port="${VLLM_PORT:-8001}"

  local current
  current=$(running_model)
  if [[ -n "$current" && "$current" != "$VLLM_MODEL" ]]; then
    warn "the running container serves $current but the config says $VLLM_MODEL."
    if [[ "$ASSUME_YES" -eq 1 ]] || ! interactive; then
      echo "  restarting it to match the config."
      docker compose --profile vllm rm -sf vllm >/dev/null 2>&1 || true
    else
      case "$(ask "restart it? Enter=yes · n=no (use the running one)" "")" in
        n|N) VLLM_MODEL="$current" ;;
        *) docker compose --profile vllm rm -sf vllm >/dev/null 2>&1 || true ;;
      esac
    fi
  fi

  check_port "$API_PORT" api
  check_port "$WEB_PORT" web

  trap cleanup INT TERM EXIT

  info "starting ${VLLM_MODEL} (parser ${VLLM_TOOL_PARSER}, weights in ${HF_HOME})"
  echo "  follow it with: scripts/ssat.sh logs vllm"
  docker compose --profile vllm up -d --wait vllm

  # AGENT_MODEL must be the id the server reports, so ask instead of guessing.
  AGENT_MODEL=$(curl -s "http://localhost:${vllm_port}/v1/models" |
    python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(d[0]['id'])")
  export AGENT_MODEL
  export AGENT_BASE_URL="http://localhost:${vllm_port}/v1"
  export NEXT_PUBLIC_API_PORT="$API_PORT"

  # The API does not run without Postgres. `--wait` blocks on the healthcheck
  # and `-d` makes this a no-op when it is already up.
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
  start_host_process api 35 ".venv/bin/uvicorn api.main:app --host 0.0.0.0 --port $API_PORT --reload --timeout-graceful-shutdown 2"
  start_host_process web 34 "cd web && npm run dev -- --port $WEB_PORT"

  printf '\n  \033[1mready\033[0m  web http://localhost:%s/inspect   api :%s   model %s\n\n' \
    "$WEB_PORT" "$API_PORT" "$AGENT_MODEL"

  wait
}

action_up() {
  [[ -f .env ]] || configure

  # Named targets skip both questions: `up vllm` is what a script writes.
  if [[ $# -gt 0 ]]; then
    start_containers "$@"
    return 0
  fi
  if [[ "$ASSUME_YES" -eq 1 ]] || ! interactive; then
    start_everything
    return 0
  fi

  # One screen, one prompt: the config that `everything` would use, and what
  # else can be started instead. Reusing .env silently meant `down` then `up`
  # relaunched the old model with no obvious way to pick another.
  while true; do
    show_config
    printf '\n  \033[36m 1)\033[0m everything  vLLM, Postgres, the API and the web UI\n' >&2
    local i=1 name
    while IFS= read -r name; do
      i=$((i + 1))
      printf '  \033[36m%2d)\033[0m %-11s %s\n' "$i" "$name" "$(target_field "$name" label)" >&2
    done < <(target_names)
    printf '\n  \033[90mseveral at once: 2,3 · c=change the vLLM config · q=cancel\033[0m\n\n' >&2

    local answer
    answer=$(ask "choice" "1")
    case "$answer" in
      c|C) rm -f .env; configure; continue ;;
      q|Q) echo "cancelled."; return 0 ;;
      1) start_everything; return 0 ;;
    esac

    local -a names=() chosen=()
    mapfile -t names < <(target_names)
    local token
    for token in ${answer//,/ }; do
      case "$token" in
        all) chosen=("${names[@]}"); break ;;
        [0-9]*)
          [[ "$token" -ge 2 && "$token" -le $((${#names[@]} + 1)) ]] || die "no such choice: $token"
          chosen+=("${names[$((token - 2))]}")
          ;;
        *) chosen+=("$token") ;;
      esac
    done
    start_containers "${chosen[@]}"
    return 0
  done
}

# ---------------------------------------------------------------------------
# Stack actions other than up
# ---------------------------------------------------------------------------

action_status() {
  info "containers"
  docker compose --profile vllm --profile secbench ps -a
  printf '\n'
  info "host processes"
  local entry port name pid
  for entry in "api:$API_PORT" "web:$WEB_PORT"; do
    name="${entry%%:*}"; port="${entry#*:}"
    pid=$(port_holder "$port")
    if [[ -n "$pid" ]]; then
      printf '  %-4s :%-5s pid %s\n' "$name" "$port" "$pid"
    else
      printf '  %-4s :%-5s \033[90mnot running\033[0m\n' "$name" "$port"
    fi
  done
}

action_down() {
  local -a targets=("$@")
  if [[ ${#targets[@]} -eq 0 ]]; then
    interactive || die "which containers? e.g. scripts/ssat.sh down vllm"
    mapfile -t targets < <(pick_targets "stop which containers?")
  fi
  resolve_targets "${targets[@]}"
  # `stop` on named services, not `compose down`: a bare down would also take
  # the Joern container that ssat's docker backend is using.
  docker compose "${PROFILE_FLAGS[@]+"${PROFILE_FLAGS[@]}"}" stop "${SERVICE_LIST[@]}"
  info "stopped: ${targets[*]}"
}

action_delete() {
  local -a targets=("$@")
  if [[ ${#targets[@]} -eq 0 ]]; then
    interactive || die "which containers? e.g. scripts/ssat.sh delete vllm"
    mapfile -t targets < <(pick_targets "remove which containers?")
  fi
  # Containers only. The Postgres volume is named so that removing a container
  # does not take the runs with it; the weights cache is a slow re-download and
  # SEC-bench's image root is ~200 GB. None of the three is this command's to
  # delete, and `docker volume rm` is explicit enough when you do mean it.
  if interactive; then
    printf '\n  removes the containers for: \033[1m%s\033[0m\n' "${targets[*]}" >&2
    printf '  \033[90mstored runs, downloaded weights and SEC-bench images are untouched.\033[0m\n\n' >&2
    case "$(ask "Enter=remove · q=cancel" "")" in
      q|Q) echo "cancelled."; return 0 ;;
    esac
  fi
  resolve_targets "${targets[@]}"
  docker compose "${PROFILE_FLAGS[@]+"${PROFILE_FLAGS[@]}"}" rm -sf "${SERVICE_LIST[@]}"
  info "removed: ${targets[*]}"
}

action_logs() {
  local target="${1:-}"
  if [[ -z "$target" ]]; then
    interactive || die "which container? e.g. scripts/ssat.sh logs vllm"
    target=$(pick_targets "follow which log?" "1" | head -1)
  fi
  resolve_targets "$target"
  docker compose "${PROFILE_FLAGS[@]+"${PROFILE_FLAGS[@]}"}" logs -f --tail 200 "${SERVICE_LIST[@]}"
}

# ---------------------------------------------------------------------------
# Dev tasks, from [tool.tasks]
# ---------------------------------------------------------------------------

# Emit "name<TAB>description<TAB>command" for each entry in [tool.tasks].
#
# A comment line directly above an entry is its description, which is why the
# listing cannot drift from the commands: both come from the same lines.
#
# Plain awk on purpose. A Makefile would mean installing make to run a CLI, uv
# has no task runner, and tomllib needs Python 3.11+ which the system
# interpreter here is not -- while `setup` has to work before any venv exists.
parse_tasks() {
  awk '
    /^\[tool\.tasks\]/ { inside = 1; next }
    /^\[/              { inside = 0 }
    !inside            { next }
    /^[[:space:]]*$/   { desc = ""; next }
    /^[[:space:]]*#/   { sub(/^[[:space:]]*#[[:space:]]?/, ""); desc = $0; next }
    /^[A-Za-z0-9_-]+[[:space:]]*=/ {
      name = $0
      sub(/[[:space:]]*=.*$/, "", name)
      command = $0
      sub(/^[^=]*=[[:space:]]*/, "", command)
      # Strip the surrounding double quotes TOML requires.
      sub(/^"/, "", command)
      sub(/"[[:space:]]*$/, "", command)
      printf "%s\t%s\t%s\n", name, desc, command
      desc = ""
    }
  ' "$MANIFEST"
}

run_task() {
  local wanted="$1"; shift
  local name desc command found=""
  while IFS=$'\t' read -r name desc command; do
    if [[ "$name" == "$wanted" ]]; then found="$command"; break; fi
  done < <(parse_tasks)
  [[ -n "$found" ]] || die "unknown task: $wanted (run scripts/ssat.sh for the list)"
  # Through bash -c so a task can use &&, ||, cd and pipes exactly as written in
  # the manifest. "$@" appends the caller's arguments to the command.
  bash -c "$found \"\$@\"" "ssat.sh:$wanted" "$@"
}

# ---------------------------------------------------------------------------
# The menu
# ---------------------------------------------------------------------------

STACK_ACTIONS=(
  "up|start vLLM, Postgres, the API and the web UI"
  "down|stop containers"
  "delete|stop and remove containers"
  "status|what is running right now"
  "logs|follow a container's log"
)

is_stack_action() {
  local name
  for entry in "${STACK_ACTIONS[@]}"; do
    IFS='|' read -r name _ <<<"$entry"
    [[ "$name" == "$1" ]] && return 0
  done
  return 1
}

# The listing, for a pipe or for --help. Every name here is runnable as an
# argument, which is what makes the menu numbers optional.
listing() {
  local name desc
  printf '\033[1mstack\033[0m\n'
  for entry in "${STACK_ACTIONS[@]}"; do
    IFS='|' read -r name desc <<<"$entry"
    printf '  \033[36m%-11s\033[0m %s\n' "$name" "$desc"
  done
  printf '\n\033[1mtasks\033[0m  (declared in %s)\n' "$MANIFEST"
  while IFS=$'\t' read -r name desc _; do
    printf '  \033[36m%-11s\033[0m %s\n' "$name" "$desc"
  done < <(parse_tasks)
  printf '\nWeb-only tasks live in web/package.json and run there directly.\n'
}

# One action per invocation, and then the script exits -- the same thing a
# named argument does, so the menu is a way to find the name rather than a
# second mode with its own behaviour.
menu() {
  local -a choices=()
  local name desc i=0

  printf '\n\033[1mstack\033[0m\n'
  for entry in "${STACK_ACTIONS[@]}"; do
    IFS='|' read -r name desc <<<"$entry"
    i=$((i + 1)); choices+=("$name")
    printf '  \033[36m%2d)\033[0m %-11s %s\n' "$i" "$name" "$desc"
  done

  printf '\n\033[1mtasks\033[0m  \033[90m(declared in %s)\033[0m\n' "$MANIFEST"
  while IFS=$'\t' read -r name desc _; do
    i=$((i + 1)); choices+=("$name")
    printf '  \033[36m%2d)\033[0m %-11s %s\n' "$i" "$name" "$desc"
  done < <(parse_tasks)

  printf '\n  \033[90ma number or a name · q=quit\033[0m\n\n'
  local answer
  answer=$(ask "choice" "1")
  case "$answer" in
    q|Q|"") return 0 ;;
    [0-9]*)
      [[ "$answer" -ge 1 && "$answer" -le ${#choices[@]} ]] || die "no such choice: $answer"
      dispatch "${choices[$((answer - 1))]}"
      ;;
    # Split so a name can be given with arguments, without glob expansion.
    *) local -a parts=(); read -ra parts <<<"$answer"; dispatch "${parts[@]}" ;;
  esac
}

dispatch() {
  local what="$1"; shift || true
  if is_stack_action "$what"; then
    "action_$what" "$@"
  else
    run_task "$what" "$@"
  fi
}

# ---------------------------------------------------------------------------

ASSUME_YES=0

main() {
  [[ -f "$MANIFEST" ]] || die "$MANIFEST not found"

  case "${1:-}" in
    -h|--help)
      awk 'NR==1 && /^#!/ {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"
      listing
      return 0
      ;;
    # For the tests: names and descriptions, machine-readable, same parser.
    --list-tasks)
      parse_tasks | cut -f1,2
      return 0
      ;;
    "")
      # No tty means a pipe or CI, where a prompt would hang. Print the list.
      # Written out rather than `interactive && menu || listing`, which fell
      # back to the listing whenever the chosen task exited non-zero -- so a
      # failing `lint` printed the menu again and reported success.
      if interactive; then menu; else listing; fi
      return $?
      ;;
  esac

  local what="$1"; shift

  # `up` is the only action with flags of its own, and an unrecognised one used
  # to fall through and start the stack -- surprising for `--help`.
  if [[ "$what" == "up" ]]; then
    local -a rest=()
    local arg
    for arg in "$@"; do
      case "$arg" in
        -y|--yes) ASSUME_YES=1 ;;
        --reconfigure) rm -f .env ;;
        -*) die "unknown option: $arg" ;;
        *) rest+=("$arg") ;;
      esac
    done
    action_up "${rest[@]+"${rest[@]}"}"
    return 0
  fi

  dispatch "$what" "$@"
}

main "$@"
