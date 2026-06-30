#!/usr/bin/env bash
# change.sh — package the working-tree edits into a fresh chore/fix branch, verify, commit, and land.
# The Lead's one-command path for ENGINE / chore changes (product work goes through dispatch → ship).
# Wraps the repeated dance: pull main · branch · add · ci-local · commit · pr.sh.
#   change.sh <branch> -m "<commit message>"
#   e.g.  scripts/change.sh fix/foo -m "fix(foo): do the thing"
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"

branch="${1:-}"; [[ "$branch" == -* ]] && branch=""    # tolerate `change.sh -m ...` (missing branch)
[[ -n "$branch" ]] && shift || true
msg=""
while [[ $# -gt 0 ]]; do case "$1" in
  -m|--message) msg="${2:?-m needs a message}"; shift 2 ;;
  *) die "unknown argument: $1" "change.sh takes <branch> -m \"<message>\"" "e.g. scripts/change.sh fix/foo -m \"fix(x): ...\"" ;;
esac; done

[[ -n "$branch" ]] || die "no branch name" "usage: change.sh <branch> -m \"<message>\"" "e.g. scripts/change.sh fix/foo -m \"fix(x): summary\""
[[ -n "$msg" ]]    || die "no commit message" "usage: change.sh <branch> -m \"<message>\"" "pass -m \"<type>(<scope>): <summary>\""
[[ "$branch" != main ]] || die "refusing to target main" "main is protected; changes land via a branch + PR" "pick a branch, e.g. fix/<slug>"

cur="$(git branch --show-current)"
[[ "$cur" == main ]] || die "you are on '$cur', not main" \
  "change.sh starts a fresh branch from main and carries your working-tree edits onto it" \
  "git switch main first (your uncommitted edits follow), then re-run"
[[ -n "$(git status --porcelain)" ]] || die "no changes to ship" "the working tree is clean" "make your edits first, then re-run change.sh"
git rev-parse --verify "$branch" >/dev/null 2>&1 && die "branch '$branch' already exists" \
  "pick a new name, or delete it: git branch -D $branch" "then re-run change.sh"

git pull --ff-only || die "git pull --ff-only failed" "main diverged or has local commits" "reconcile main (git status), then re-run"
git switch -c "$branch"           # uncommitted edits carry onto the new branch
git add -A
git add --chmod=+x scripts/*.sh 2>/dev/null || true   # any NEW script carries +x in the index (check 6 / ADR-0010)
log "running ci-local before commit ..."
cl="$(mktemp)"
if ! bash "$DIR/ci-local.sh" 2>&1 | tee "$cl"; then
  fails="$(grep -nE '✗|\[ai-os\]\[err\]|not ok' "$cl" | head -n 15 || true)"; rm -f "$cl"
  die "ci-local failed — NOT committing or pushing (changes are staged on '$branch')" \
    "failing checks:
$fails" \
    "fix them, re-run bash scripts/ci-local.sh, then: git commit -m \"$msg\" && scripts/pr.sh"
fi
rm -f "$cl"
git commit -m "$msg"
log "committed on $branch — handing off to pr.sh (push · PR · land)"
exec bash "$DIR/pr.sh"
