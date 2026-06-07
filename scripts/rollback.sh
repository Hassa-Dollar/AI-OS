#!/usr/bin/env bash
# rollback.sh — revert one merged task in one command (manual §9.5, P11).
# Usage: rollback.sh <merge-tag-or-commit> [reason...]
#   Reverts the merge commit (gate.sh merges with --no-ff, so -m 1 is valid),
#   tags the rollback, and records the reason in the ledger (feeds the weekly review).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"

ref="${1:?usage: rollback.sh <merge-tag-or-commit> [reason...]}"; shift || true
reason="${*:-unspecified}"
commit="$(git rev-list -n1 "$ref" 2>/dev/null)" || die "cannot resolve ref '$ref'"

git checkout main >/dev/null 2>&1 || die "cannot checkout main"
if git rev-parse "${commit}^2" >/dev/null 2>&1; then
  git revert --no-edit -m 1 "$commit"          # merge commit → revert the merge
else
  git revert --no-edit "$commit"               # plain commit → straight revert
fi
tag="rollback/$(date +%s)"; git tag "$tag"
"$DIR/ledger-append.sh" rollback "-" "reverted=$commit ref=$ref reason=$reason"

log "rolled back $commit (reason: $reason) — tag $tag"
log "CI re-runs on main; you should be back to a known-good state. A rollback is DATA:"
log "the weekly review reads it to find the fragile task class or model (manual §8.5)."
