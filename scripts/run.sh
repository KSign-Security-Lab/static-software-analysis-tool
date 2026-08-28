#!/usr/bin/env bash
#
# Runs the tasks declared in [tool.tasks] in pyproject.toml.
#
# That table is the list -- open pyproject.toml to read it, the same way you
# would open package.json. This file only dispatches; it holds no task
# definitions of its own, so the two cannot disagree.
#
#   scripts/run.sh              list the tasks
#   scripts/run.sh <task> ...   run one; extra arguments are appended
#
# Plain bash and awk on purpose. A Makefile would mean installing make to run a
# CLI, uv has no task runner, and tomllib needs Python 3.11+ which the system
# interpreter here is not -- while `setup` has to work before any venv exists.
#
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
MANIFEST="pyproject.toml"

die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# Emit "name<TAB>description<TAB>command" for each entry in [tool.tasks].
#
# A comment line directly above an entry is its description, which is why the
# listing cannot drift from the commands: both come from the same lines.
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

usage() {
  awk 'NR==1 && /^#!/ {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"
  printf '\033[1mtasks\033[0m  (declared in %s)\n\n' "$MANIFEST"
  parse_tasks | while IFS=$'\t' read -r name desc _; do
    printf '  \033[36m%-11s\033[0m %s\n' "$name" "$desc"
  done
  printf '\nWeb-only tasks live in web/package.json and run there directly.\n'
}

main() {
  [[ -f "$MANIFEST" ]] || die "$MANIFEST not found"

  local wanted="${1:-}"
  if [[ -z "$wanted" || "$wanted" == "-h" || "$wanted" == "--help" ]]; then
    usage
    return 0
  fi
  shift

  local name desc command found=""
  while IFS=$'\t' read -r name desc command; do
    if [[ "$name" == "$wanted" ]]; then
      found="$command"
      break
    fi
  done < <(parse_tasks)

  [[ -n "$found" ]] || die "unknown task: $wanted (run scripts/run.sh for the list)"

  # Through bash -c so a task can use &&, ||, cd and pipes exactly as written in
  # the manifest. "$@" appends the caller's arguments to the command.
  bash -c "$found \"\$@\"" "run.sh:$wanted" "$@"
}

main "$@"
