#!/usr/bin/env bash
# pr.sh — push the CURRENT branch, open an auto-merge PR, and land it. The Lead's
# one-command path for chore/* and fix/* branches (task branches go through ship.sh,
# which adds the QA gate). Usage: commit your work on a branch, then: scripts/pr.sh
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"

branch="$(git branch --show-current)"
[[ -n "$branch" && "$branch" != "main" ]] || die "switch to a work branch first (you are on '${branch:-detached}')"
[[ -z "$(git status --porcelain)" ]] || die "uncommitted changes — commit them first"
command -v gh >/dev/null 2>&1 || die "pr.sh needs the GitHub CLI (gh)"

git push -u origin "$branch" || die "could not push $branch (see git output above — pre-push hook? auth? behind remote?)"
prnum="$(gh pr view "$branch" --json number --jq .number 2>/dev/null || true)"
if [[ -z "$prnum" ]]; then
  gh pr create --fill --base main --head "$branch" || die "gh pr create failed"
fi
gh pr merge "$branch" --auto --merge >/dev/null 2>&1 || warn "auto-merge not armed (already merged, or check repo settings)"
exec "$DIR/land.sh" "$branch"
