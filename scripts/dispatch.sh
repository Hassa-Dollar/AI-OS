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

# --- security (ADR-0014): never hand a spec containing a secret to a worker (or commit it) -----
# NB: env-var REFERENCES (process.env.X, ${X}, <PLACEHOLDER>) are the CORRECT pattern per ADR-0014 — the
# filter below drops them so the scanner never flags the very thing it tells you to use (BUG-26).
_secret_lines="$(grep -niIE \
  -e 'sk_(live|test)_[0-9A-Za-z]{16,}' \
  -e 'gh[pousr]_[0-9A-Za-z]{30,}' \
  -e 'github_pat_[0-9A-Za-z_]{30,}' \
  -e 'AKIA[0-9A-Z]{16}' \
  -e 'whsec_[0-9A-Za-z]{16,}' \
  -e 'BEGIN [A-Z ]*PRIVATE KEY' \
  -e '(secret|token|api[_-]?key|password|passwd|bearer)[[:space:]]*[:=][[:space:]]*[A-Za-z0-9/+_=.-]{20,}' \
  "$spec" 2>/dev/null \
  | grep -vEi 'process\.env|import\.meta\.env|os\.environ|Deno\.env|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|<[A-Za-z_][A-Za-z0-9_]*>' \
  | cut -d: -f1 | tr '\n' ' ' || true)"
[[ -z "$_secret_lines" ]] || die "spec appears to contain a secret (line(s): $_secret_lines)" \
  "a task spec must never carry a credential — it is sent verbatim to a worker model and committed to a public repo" \
  "remove it from $spec; reference an env-var NAME instead (the app reads process.env; see .env.example / ADR-0014)"

id="$(fm_scalar "$spec" id)";              [[ -n "$id" ]]     || die "spec missing 'id'"
slug="$(fm_scalar "$spec" slug)"
branch="$(fm_scalar "$spec" branch)";      [[ -n "$branch" ]] || branch="task/${id}-${slug}"
# roles v2 (ADR-0022): the profile is the single source of role→model; the spec names owner_role.
# resolve_roles (in _lib.sh) is the SINGLE source of this, shared with gate.sh, so which-model-runs and the
# P8/verifier check can never drift apart (BUG-27 + BUG-30).
orole="$(fm_scalar "$spec" owner_role)"; orole="${orole:-implementer}"
IFS=$'\t' read -r model vmodel < <(resolve_roles "$spec")
log "roles: owner_role=$orole model=${model:-?} verifier=${vmodel:-?} (resolved via the component's profile, ADR-0022)"
pj="$(profile_of_spec "$spec")"
[[ -n "$model" ]]  || die "no model for this task" \
  "$(if [[ -n "$pj" ]]; then echo "the profile ($pj) doesn't bind role '$orole' and the spec has no override"; else echo "an OS/chore spec (no component profile) must carry an explicit 'model:'"; fi)" \
  "bind '$orole' in the profile's roles, pick a bound owner_role, or (component spec) add model_override: + override_reason:"
[[ -n "$vmodel" ]] || die "no verifier for this task" \
  "$(if [[ -n "$pj" ]]; then echo "the profile ($pj) supplies no usable verifier — roles.verifier missing, or the author shares its family and roles.verifier_secondary is unset"; else echo "an OS/chore spec (no component profile) must carry an explicit 'verifier_model:'"; fi)" \
  "set roles.verifier (+ verifier_secondary for same-family authors, P8) in profile.json, or verifier_model: on an OS spec"

# --- roles v2 guard (ADR-0022): a model pin on a profile-governed spec is an AUDITED exception ---------
ov="$(override_of_spec "$spec")"
if [[ -n "$pj" && -n "$ov" && -z "$(fm_scalar "$spec" override_reason)" ]]; then
  die "model pin without override_reason ($ov)" \
    "component specs inherit models from their profile — the single source (ADR-0022); a pin drifts silently when the profile is re-bumped (the BUG-27/30 failure mode)" \
    "remove '$ov' from $spec to inherit via owner_role, or add override_reason: <why> (the gate will risk-flag it for Lead review)"
fi

# --- fixed catalog (ADR-0009): reject off-catalog / superseded / typo slugs before anything runs ---
assert_in_catalog "$model"  "model"
assert_in_catalog "$vmodel" "verifier_model"

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
  clash="$(filesets_clash "$files" "$ofiles" || true)"   # dir-grant aware (ADR-0028)
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
    clash="$(filesets_clash "$files" "$(fm_list "$tmpspec" files_allowed)" || true)"   # ADR-0028
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

bash "$DIR/ledger-append.sh" dispatch "$id" "model=$model verifier=$vmodel branch=$branch"

# --- ADR-0019: the worker's trusted identity (component tasks are confined; OS tasks run unconfined) ---
comp_name="$(component_of_spec "$spec" 2>/dev/null || true)"; comp_name="${comp_name#components/}"

# --- hand the spec to the worker -------------------------------------------
run_worker() {  # $1=model  $2=prompt-file  $3=spec-file
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    log "DRY_RUN: would run -> opencode run --model $1  (prompt=$2, spec=$3)"; return 0
  fi
  command -v opencode >/dev/null 2>&1 || die "opencode CLI not found" \
    "the OpenCode CLI isn't installed or isn't on PATH" \
    "install OpenCode + run 'opencode auth login' — or re-run 'dispatch.sh $id --dry-run' to validate without a model"
  # ADR-0019: inject a trusted identity for THIS run only (env prefix via `env`, NOT a global export) so any
  # db.sh write during the worker run is attributed + confined to this task's component. Component tasks
  # only; an OS/chore task (no component) runs unconfined (Lead-approved, rare).
  local idenv=()
  [[ -n "${comp_name:-}" ]] && idenv=("AI_OS_ACTOR=agent:$1" "AI_OS_ROLE=implementer" "AI_OS_COMPONENT=$comp_name" "AI_OS_TASK=$id")
  # `-f` is a GREEDY [array] option, so the message MUST come BEFORE any -f or the prompt is swallowed into
  # the file list ("File not found: <prompt>"). Spec is attached via -f, not inlined (registry BUG-03/10).
  # --dangerously-skip-permissions: a dispatched worker runs unattended (no TTY to approve its file writes /
  # npm / git); the gate's boundary audit + component isolation are the safety net (true sandbox = backlog).
  # Stream live (tee) AND capture, so a failure logs the REAL opencode output, not a bare "non-zero exit".
  local wlog; wlog="$(mktemp)"
  if ! env "${idenv[@]}" opencode run --model "$1" --dangerously-skip-permissions \
    "$(cat "$2")

Your task spec is attached as a file (\`$3\`). Implement it per AGENTS.md and the component's conventions." \
    -f "$3" 2>&1 | tee "$wlog"; then
    die "opencode worker FAILED (task $id, model $1)" "$(tail -n 6 "$wlog")" \
      "check the worker output above; verify opencode auth (scripts/doctor.sh) + the model slug"
  fi
  rm -f "$wlog"
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
