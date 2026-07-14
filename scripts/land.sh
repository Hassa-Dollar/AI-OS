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
[[ -n "${branch:-}" ]] || die "no local branch matches '$arg'" \
  "land.sh needs an existing local branch name (or a substring of one)" \
  "list them: git branch — then: scripts/land.sh <branch>"
command -v gh >/dev/null 2>&1 || die "land.sh needs the GitHub CLI (gh)" \
  "gh watches checks and completes the merge" \
  "install gh, then: gh auth login"

# report_failed_checks <branch> — on a failed check run, name WHICH check failed, print the exact command
# to read its failing step, and a likely-cause hint (ADR-0004 operator-facing errors). Caller then exits.
report_failed_checks() {
  local br="$1" rows name link job
  rows="$(gh pr checks "$br" --json name,bucket,link --jq '.[] | select(.bucket=="fail") | "\(.name)\t\(.link)"' 2>/dev/null || true)"
  printf '\033[31m[ai-os][err]\033[0m required checks FAILED on %s — the PR stays open.\n' "$br" >&2
  if [[ -z "$rows" ]]; then
    printf '             \033[31m↳ couldn'\''t read which check failed:\033[0m inspect in the browser: gh pr view %s --web\n' "$br" >&2
    return 0
  fi
  while IFS=$'\t' read -r name link; do
    [[ -n "$name" ]] || continue
    job="${link##*/job/}"; job="${job%%[^0-9]*}"
    printf '             \033[31m✗ %s\033[0m\n' "$name" >&2
    if [[ -n "$job" && "$job" != "$link" ]]; then
      printf '                ↳ failing step: \033[36mgh run view --job %s --log-failed\033[0m\n' "$job" >&2
    elif [[ -n "$link" ]]; then
      printf '                ↳ open: \033[36m%s\033[0m\n' "$link" >&2
    fi
    case "$name" in
      os|os-ci*)                  printf '                ↳ likely: shellcheck (scripts/*.sh), a gitleaks secret finding, or a component-isolation import\n' >&2 ;;
      product|build*|product-ci*) printf '                ↳ likely: a component build/test — reproduce: (cd components/<name> && npm ci && npm run -s ci)\n' >&2 ;;
    esac
  done <<< "$rows"
  printf '             ↳ fix on the branch, commit, then re-run \033[36mscripts/ship.sh <id>\033[0m (or scripts/pr.sh for a chore/fix branch)\n' >&2
}

state="$(gh pr view "$branch" --json state --jq .state 2>/dev/null || echo NONE)"
[[ "$state" == "NONE" ]] && die "no PR for $branch" \
  "land.sh finishes a PR that gate.sh opened; none exists for this branch yet" \
  "run scripts/gate.sh $id first (or scripts/ship.sh $id to gate + land in one go)"
draft="$(gh pr view "$branch" --json isDraft --jq .isDraft 2>/dev/null || echo false)"
if [[ "$draft" == "true" && "$state" == "OPEN" ]]; then
  # NOT an error — the risk router parked this for the Lead. Clean, capture-free stop: a die() here would
  # print [err], write a bogus error into the memory DB, and make ship.sh exit non-zero on a perfectly
  # normal flagged-task outcome.
  log "PR for $branch is a DRAFT — HELD for the Lead gate (expected; not an error)."
  log "  ↳ flagged (contract/security/large/high-blast), so it must not auto-land."
  log "  ↳ review with prompts/code-review.md (Lead-gate addendum), then: scripts/approve.sh $id"
  exit 0
fi

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
  (( reported )) || die "no checks appeared on $branch after ~2min" \
    "GitHub Actions never reported a run — usually a workflow under .github/workflows/ is missing on this branch or Actions is disabled" \
    "confirm .github/workflows/*.yml exist on $branch and Actions is enabled: gh pr view $branch --web"
  log "checks reported — watching ..."
  if ! gh pr checks "$branch" --watch --fail-fast; then
    sleep 10  # grace: a green run can still race the merge bookkeeping
    state="$(gh pr view "$branch" --json state --jq .state 2>/dev/null || echo OPEN)"
    [[ "$state" == "MERGED" ]] || { report_failed_checks "$branch"; exit 1; }
  fi
  log "checks green — requesting merge ..."
  # gate.sh arms auto-merge only on the auto-approve path; a Lead-gated PR (approved via approve.sh) and a
  # pr.sh chore PR where repo auto-merge is OFF have nothing armed. land.sh is the single chokepoint, so
  # REQUEST the merge here (checks are green) — this lands BOTH paths (BUG-24). Keep gh's real error.
  merge_err="$(gh pr merge "$branch" --merge 2>&1)" || true
  for _ in $(seq 1 24); do
    state="$(gh pr view "$branch" --json state --jq .state 2>/dev/null || echo OPEN)"
    [[ "$state" == "MERGED" ]] && break
    sleep 5
  done
fi
[[ "$state" == "MERGED" ]] \
  || die "PR still $state — merge did not complete" \
       "${merge_err:-branch protection may require a review/up-to-date branch, or there is a conflict}" \
       "if it says a review is required, make branch protection require status CHECKS not approvals (the Lead gate is the review); else inspect: gh pr view $branch --json mergeStateStatus,reviewDecision"

log "merged — syncing main"
git checkout main >/dev/null 2>&1 || die "could not checkout main (commit or stash local changes first)"
git pull --ff-only
git branch -D "$branch" >/dev/null 2>&1 || true
git push origin --delete "$branch" >/dev/null 2>&1 || true
git fetch --prune >/dev/null 2>&1 || true
bash "$DIR/ledger-append.sh" land "$id" "branch=$branch main=$(git rev-parse --short=8 main)"
if [[ -f "$DIR/handoff.sh" ]]; then bash "$DIR/handoff.sh" || warn "handoff refresh failed (non-fatal)"; fi
log "DONE — main @ $(git log -1 --format='%h %s')"
