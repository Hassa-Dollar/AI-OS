#!/usr/bin/env bash
# approve.sh <task-id|branch> — the Lead's APPROVE for a Lead-gated (draft) PR. Mirrors gate.sh's
# auto-approve, but triggered by the Lead after a code-review pass (prompts/code-review.md): archive the task
# spec on the branch so it lands atomically, mark the PR ready, then hand off to land.sh (which requests the
# merge). Run ONLY when the review PASSES — during change-iteration you re-run gate.sh/ship.sh, not this.
# (BUG-24: the draft path never archived the spec nor armed a merge.)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"
command -v gh >/dev/null 2>&1 || die "approve.sh needs the GitHub CLI (gh)" \
  "gh marks the PR ready and land.sh completes the merge" \
  "install gh, then: gh auth login"

arg="${1:?usage: approve.sh <task-id|branch>}"
if git rev-parse --verify "$arg" >/dev/null 2>&1; then
  branch="$arg"; id="${arg##*/}"; id="${id%%-*}"
else
  id="$arg"; branch="$(git for-each-ref --format='%(refname:short)' refs/heads/ | grep -E "^task/${id}-" | head -1 || true)"
fi
[[ -n "${branch:-}" ]] || die "no local task branch for '$arg'" \
  "approve.sh acts on a task/* branch that gate.sh opened as a draft PR" \
  "list them: git branch — then: scripts/approve.sh <branch>"

# A pending handoff AUTO-refresh (left by land.sh after the previous merge) must not block the checkout.
git restore docs/handoff/SESSION-HANDOFF.md 2>/dev/null || true
git checkout "$branch" >/dev/null 2>&1 || die "could not checkout $branch" \
  "the worktree has uncommitted changes that conflict with the branch" \
  "commit or stash them, then re-run scripts/approve.sh $id"

# Archive the spec on the branch (idempotent) so spec + implementation merge together — exactly the shape
# gate.sh's auto-approve path produces (spec ends in tasks/completed/ on main).
shopt -s nullglob
specs=( "tasks/active/${id}-"*.md "tasks/active/${id}.md" )
if [[ ${#specs[@]} -ge 1 && -f "${specs[0]}" ]]; then
  mkdir -p tasks/completed
  git mv "${specs[0]}" "tasks/completed/$(basename "${specs[0]}")"
  git commit -q -m "chore(${id}): archive completed task spec"
  git_push_resilient origin "$branch"
  log "archived $(basename "${specs[0]}") -> tasks/completed/ and pushed"
else
  log "spec already archived for $id (nothing to move)"
fi

gh pr ready "$branch" >/dev/null 2>&1 || warn "could not mark $branch ready" "it may already be ready" "check: gh pr view $branch"
bash "$DIR/ledger-append.sh" opus-gate "$id" "lead-approved branch=$branch"
log "approved $id (Lead gate) — landing ..."
exec bash "$DIR/land.sh" "$branch"
