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
  matches=()
  for m in "tasks/active/${arg}-"*.md "tasks/active/${arg}.md"; do [[ -f "$m" ]] && matches+=("$m"); done
  [[ ${#matches[@]} -ge 1 ]] || die "no active spec for id '$arg' in tasks/active/" \
    "the id is wrong, or the spec was never created / is already archived" \
    "create it: scripts/new-task.sh $arg <slug> [model] [verifier]"
  spec="${matches[0]}"
fi
log "spec: $spec"

id="$(fm_scalar "$spec" id)";              [[ -n "$id" ]]     || die "spec missing 'id'"
slug="$(fm_scalar "$spec" slug)"
branch="$(fm_scalar "$spec" branch)";      [[ -n "$branch" ]] || branch="task/${id}-${slug}"
model="$(fm_scalar "$spec" model)"
vmodel="$(fm_scalar "$spec" verifier_model)"
# dynamic roles (ADR-0003): inherit any unset pin from the target component's profile.json.
if [[ -z "$model" || -z "$vmodel" ]]; then
  _c="$(component_dir 2>/dev/null || true)"; _p=""
  [[ -n "$_c" && -f "$_c/.component.yml" ]] && _p="$(fm_scalar "$_c/.component.yml" profile)"
  if [[ -n "$_p" && -f "profiles/$_p/profile.json" ]]; then
    [[ -z "$model" ]]  && model="$(json_get "profiles/$_p/profile.json" implementer)"
    [[ -z "$vmodel" ]] && vmodel="$(json_get "profiles/$_p/profile.json" verifier)"
    log "roles inherited from profile $_p (model=${model:-?} verifier=${vmodel:-?})"
  fi
fi
[[ -n "$model" ]]  || die "no model for this task" \
  "the spec has no 'model:' and the component's profile didn't supply roles.implementer" \
  "add 'model:' to the spec, or set roles.implementer in the profile's profile.json"
[[ -n "$vmodel" ]] || die "no verifier_model for this task" \
  "the spec has no 'verifier_model:' and the profile didn't supply roles.verifier" \
  "add 'verifier_model:' (a different family, P8), or set roles.verifier in profile.json"
files="$(fm_list "$spec" files_allowed)";  [[ -n "$files" ]]  || die "spec has empty files_allowed" \
  "the spec lists no editable files" \
  "add files_allowed: paths under one component (schema: manual §6.6, contract os-component-boundary)"

# --- guardrail (ADR-0002): files_allowed must stay within ONE component ------
nroots="$(printf '%s\n' "$files" | sed -nE 's#^(components/[^/]+)/.*#\1#p' | sort -u | grep -c . || true)"
[[ "${nroots:-0}" -le 1 ]] || die "files_allowed spans multiple components" \
  "a task must stay within a single component (ADR-0002, contract os-component-boundary)" \
  "split this into one task per component, each on its own branch"
nonc="$(printf '%s\n' "$files" | grep -vE '^components/[^/]+/' | grep -vE '^reports/tasks/' || true)"
[[ -z "$nonc" ]] || warn "files_allowed mixes non-component paths: $(printf '%s' "$nonc" | tr '\n' ' ')" \
  "product tasks normally touch only their component + reports/tasks/<id>-completion.md" \
  "fine for an OS/chore task; confirm it isn't accidental scope creep into the OS"

# --- P8: verifier must be a different family than the author ----------------
af="$(family_of "$model")"; vf="$(family_of "$vmodel")"
[[ "$af" != "$vf" ]] || die "P8 violation: verifier family == author family ($af)" \
  "a model may never grade its own family (AGENTS.md §2); model and verifier_model are both $af" \
  "set verifier_model to another family in the spec (GLM↔DeepSeek/Kimi, Kimi↔DeepSeek)"
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
# ...and against specs queued on other LIVE task branches: since specs now ride their own
# branch (no queue-PR), the worktree alone cannot see every in-flight spec (P2/P3, manual §8.2).
tmpspec="$(mktemp)"
for br in $(git for-each-ref --format='%(refname:short)' refs/heads/task/ 2>/dev/null); do
  [[ "$br" == "${branch:-}" ]] && continue
  while IFS= read -r p; do
    [[ -n "$p" ]] || continue
    git show "${br}:${p}" > "$tmpspec" 2>/dev/null || continue
    oid="$(fm_scalar "$tmpspec" id)"; [[ "$oid" == "$id" ]] && continue
    clash="$(intersect "$files" "$(fm_list "$tmpspec" files_allowed)" || true)"
    [[ -z "$clash" ]] || die "file-set clash with in-flight task ${oid:-?} (branch $br) on: $(echo "$clash" | tr '\n' ' ')"
  done < <(git ls-tree -r --name-only "$br" -- tasks/active/ 2>/dev/null)
done
rm -f "$tmpspec"
log "file-set disjoint ok (worktree + live task branches)"

# --dry-run is validation-only: stop BEFORE any git mutation (no branch/checkout/commit/ledger).
if [[ "${DRY_RUN:-0}" == "1" ]]; then
  log "DRY_RUN: validation passed (spec parsed · P8 ok · file-set disjoint · component boundary)."
  log "DRY_RUN: would create branch '${branch}' off main, queue the spec, and dispatch to ${model} (verifier ${vmodel}). No changes made."
  exit 0
fi

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
  command -v opencode >/dev/null 2>&1 || die "opencode CLI not found" \
    "the OpenCode CLI isn't installed or isn't on PATH" \
    "install OpenCode + run 'opencode auth login' — or re-run 'dispatch.sh $id --dry-run' to validate without a model"
  # NOTE: adjust flags to your OpenCode version (`opencode run --help`). Single-shot, non-interactive:
  opencode run --model "$1" \
    "$(printf '%s\n\n--- TASK SPEC (%s) ---\n%s' "$(cat "$2")" "$3" "$(cat "$3")")"
}

# work happens on the task branch
git checkout "$branch" >/dev/null 2>&1 || die "could not checkout $branch"

# Queue the spec on the task branch itself — no separate "queue task" PR round-trip.
# gate.sh archives it on this same branch, so spec + implementation land on main together.
if [[ -n "$(git status --porcelain -- "$spec")" ]]; then
  git add "$spec"; git commit -q -m "chore(${id}): queue task spec"
  log "spec queued on $branch (committed)"
fi

log "dispatching task $id to $model ..."
run_worker "$model" "prompts/task-execution.md" "$spec"
log "worker finished task $id. Next: scripts/ship.sh $id   (gate + land in one command)"
