#!/usr/bin/env bash
# land.sh — finish a PR that gate.sh armed for auto-merge: wait for required checks,
# confirm the merge, sync main, delete the branch (local + remote), refresh the
# handoff AUTO-STATE block. The post-merge half of the loop, in one command.
#
# Usage: land.sh <task-id|branch>     (works for task/, chore/ and fix/ branches)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"

arg="${1:?usage: land.sh <task-id|branch>}"
if git rev-parse --verify "$arg" >/dev/null 2>&1; then
  branch="$arg"; id="${arg##*/}"; id="${id%%-*}"
else
  id="$arg"
  branch="$(git for-each-ref --format='%(refname:short)' refs/heads/ | grep -E "^(task|chore|fix)/${id}([.-]|$)" | head -1 || true)"
fi
[[ -n "${branch:-}" ]] || die "no local branch matches '$arg'"
command -v gh >/dev/null 2>&1 || die "land.sh needs the GitHub CLI (gh)"

state="$(gh pr view "$branch" --json state --jq .state 2>/dev/null || echo NONE)"
[[ "$state" == "NONE" ]] && die "no PR for $branch — run scripts/gate.sh first"
draft="$(gh pr view "$branch" --json isDraft --jq .isDraft 2>/dev/null || echo false)"
[[ "$draft" == "true" && "$state" == "OPEN" ]] \
  && die "PR for $branch is a DRAFT — risk-flagged for the Opus gate. Review it (prompts/code-review.md addendum), mark ready, then rerun land.sh."

if [[ "$state" == "OPEN" ]]; then
  # GitHub needs a few seconds to REPORT check runs on a fresh PR. During that window
  # `gh pr checks` exits 1 with "no checks reported" — that is scheduling lag, not a failure.
  # (Exit codes: 0 = all green, 8 = reported-but-pending, 1 = failed OR not yet reported.)
  log "waiting for checks to be reported on $branch ..."
  reported=0
  for _ in $(seq 1 24); do
    out="$(gh pr checks "$branch" 2>&1)" && rc=0 || rc=$?
    if [[ $rc -eq 0 || $rc -eq 8 ]]; then reported=1; break; fi
    if ! grep -qi 'no checks reported' <<<"$out"; then reported=1; break; fi  # real result — let --watch render it
    sleep 5
  done
  (( reported )) || die "no checks appeared on $branch after ~2min — is ci.yml on this branch? Inspect: gh pr view $branch --web"
  log "checks reported — watching ..."
  if ! gh pr checks "$branch" --watch --fail-fast; then
    sleep 10  # grace: a green run can still race the merge bookkeeping
    state="$(gh pr view "$branch" --json state --jq .state 2>/dev/null || echo OPEN)"
    [[ "$state" == "MERGED" ]] || die "required checks FAILED on $branch — fix, commit, re-run scripts/gate.sh (the PR stays open)."
  fi
  log "checks green — waiting for auto-merge to complete ..."
  for _ in $(seq 1 24); do
    state="$(gh pr view "$branch" --json state --jq .state 2>/dev/null || echo OPEN)"
    [[ "$state" == "MERGED" ]] && break
    sleep 5
  done
fi
[[ "$state" == "MERGED" ]] \
  || die "PR still $state — auto-merge didn't complete (branch protection? conflict?). Inspect: gh pr view $branch --web"

log "merged — syncing main"
git checkout main >/dev/null 2>&1 || die "could not checkout main (commit or stash local changes first)"
git pull --ff-only
git branch -D "$branch" >/dev/null 2>&1 || true
git push origin --delete "$branch" >/dev/null 2>&1 || true
git fetch --prune >/dev/null 2>&1 || true
"$DIR/ledger-append.sh" land "$id" "branch=$branch main=$(git rev-parse --short=8 main)"
if [[ -x "$DIR/handoff.sh" ]]; then "$DIR/handoff.sh" || warn "handoff refresh failed (non-fatal)"; fi
log "DONE — main @ $(git log -1 --format='%h %s')"
