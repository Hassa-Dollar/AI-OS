#!/usr/bin/env bash
# dispatch.sh — validate a task spec, enforce the invariants, create its branch, hand it to a worker.
# Usage: dispatch.sh <task-id|spec-file> [--dry-run]
#
# Enforces, BEFORE any model runs:
#   * P8  : verifier family != author family
#   * P2/3: files_allowed is disjoint from every other active task (no two workers share a file)
#   * git : a clean branch off main
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"

arg="${1:?usage: dispatch.sh <task-id|spec-file> [--dry-run]}"
[[ "${2:-}" == "--dry-run" ]] && export DRY_RUN=1

# --- resolve the spec file -------------------------------------------------
if [[ -f "$arg" ]]; then
  spec="$arg"
else
  shopt -s nullglob
  matches=( "tasks/active/${arg}-"*.md "tasks/active/${arg}.md" )
  [[ ${#matches[@]} -ge 1 ]] || die "no active spec for id '$arg' in tasks/active/"
  spec="${matches[0]}"
fi
log "spec: $spec"

id="$(fm_scalar "$spec" id)";              [[ -n "$id" ]]     || die "spec missing 'id'"
slug="$(fm_scalar "$spec" slug)"
branch="$(fm_scalar "$spec" branch)";      [[ -n "$branch" ]] || branch="task/${id}-${slug}"
model="$(fm_scalar "$spec" model)";        [[ -n "$model" ]]  || die "spec missing 'model'"
vmodel="$(fm_scalar "$spec" verifier_model)"; [[ -n "$vmodel" ]] || die "spec missing 'verifier_model'"
files="$(fm_list "$spec" files_allowed)";  [[ -n "$files" ]]  || die "spec has empty files_allowed"

# --- P8: verifier must be a different family than the author ----------------
af="$(family_of "$model")"; vf="$(family_of "$vmodel")"
[[ "$af" != "$vf" ]] || die "P8 violation: verifier family == author family ($af). Pick a different verifier_model."
log "P8 ok: author=$af verifier=$vf"

# --- P2/P3: file-set disjointness across all other active specs -------------
shopt -s nullglob
for other in tasks/active/*.md; do
  oid="$(fm_scalar "$other" id)"
  [[ "$oid" == "$id" ]] && continue
  ofiles="$(fm_list "$other" files_allowed)"
  [[ -z "$ofiles" ]] && continue
  clash="$(intersect "$files" "$ofiles" || true)"
  [[ -z "$clash" ]] || die "file-set clash with task $oid on: $(echo "$clash" | tr '\n' ' ')"
done
log "file-set disjoint ok"

# --- git: branch off main --------------------------------------------------
git rev-parse --verify main >/dev/null 2>&1 || die "no 'main' branch found"
if git rev-parse --verify "$branch" >/dev/null 2>&1; then
  warn "branch $branch already exists — reusing"
else
  git branch "$branch" main
  log "created branch $branch"
fi

"$DIR/ledger-append.sh" dispatch "$id" "model=$model verifier=$vmodel branch=$branch"

# --- hand the spec to the worker -------------------------------------------
run_worker() {  # $1=model  $2=prompt-file  $3=spec-file
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    log "DRY_RUN: would run -> opencode run --model $1  (prompt=$2, spec=$3)"; return 0
  fi
  command -v opencode >/dev/null 2>&1 || die "opencode CLI not found (install OpenCode, or run with --dry-run)"
  # NOTE: adjust flags to your OpenCode version (`opencode run --help`). Single-shot, non-interactive:
  opencode run --model "$1" \
    "$(printf '%s\n\n--- TASK SPEC (%s) ---\n%s' "$(cat "$2")" "$3" "$(cat "$3")")"
}

# work happens on the task branch
git checkout "$branch" >/dev/null 2>&1 || die "could not checkout $branch"
log "dispatching task $id to $model ..."
run_worker "$model" "prompts/task-execution.md" "$spec"
log "worker finished task $id. Next: scripts/gate.sh $id"
