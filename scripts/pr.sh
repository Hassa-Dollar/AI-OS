#!/usr/bin/env bash
# pr.sh — push the CURRENT branch, open an auto-merge PR, and land it. The Lead's
# one-command path for chore/* and fix/* branches (task branches go through ship.sh,
# which adds the QA gate). Usage: commit your work on a branch, then: scripts/pr.sh
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"

branch="$(git branch --show-current)"
[[ -n "$branch" && "$branch" != "main" ]] || die "switch to a work branch first (you are on '${branch:-detached}')"
# A pending handoff AUTO-refresh (left by land.sh after the previous merge) is safe to ride along —
# fold it in automatically. ANY other uncommitted change is still a real "commit first" stop.
others="$(git status --porcelain | grep -vE 'docs/handoff/SESSION-HANDOFF\.md$' || true)"
[[ -z "$others" ]] || die "uncommitted changes — commit them first" \
  "the worktree has changes beyond the auto-generated handoff refresh" \
  "review them (git status -s), commit your work, then re-run scripts/pr.sh"
if [[ -n "$(git status --porcelain)" ]]; then
  git add docs/handoff/SESSION-HANDOFF.md && git commit -q -m "docs(handoff): refresh AUTO-STATE"
  log "folded the pending handoff refresh into $branch"
fi
command -v gh >/dev/null 2>&1 || die "pr.sh needs the GitHub CLI (gh)"

git push -u origin "$branch" || die "could not push $branch (see git output above — pre-push hook? auth? behind remote?)"
prnum="$(gh pr view "$branch" --json number --jq .number 2>/dev/null || true)"
if [[ -z "$prnum" ]]; then
  gh pr create --fill --base main --head "$branch" || die "gh pr create failed"
fi
gh pr merge "$branch" --auto --merge >/dev/null 2>&1 || warn "auto-merge not armed (already merged, or check repo settings)"
exec "$DIR/land.sh" "$branch"
