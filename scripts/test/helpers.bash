#!/usr/bin/env bash
# helpers.bash — shared fixtures for the determinism-layer integration tests (registry §3).
# A test `load helpers`, calls make_repo to get a throwaway git repo containing the REAL scripts under
# test + a clean commit (its 'main'), then writes synthetic specs and runs dispatch/new-task against it.

REPO_UT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"   # the AI-OS repo the tests run from

make_repo() {
  FIX="$(mktemp -d)"
  mkdir -p "$FIX"/scripts "$FIX"/tasks/active "$FIX"/tasks/completed "$FIX"/reports/tasks "$FIX"/components
  cp "$REPO_UT"/scripts/*.sh "$FIX"/scripts/
  [ -d "$REPO_UT/scripts/db" ] && cp -r "$REPO_UT/scripts/db" "$FIX"/scripts/db
  [ -f "$REPO_UT/AGENTS.md" ] && cp "$REPO_UT/AGENTS.md" "$FIX"/
  cd "$FIX" || return 1
  git -c init.defaultBranch=main init -q
  git config user.email test@example.com; git config user.name test; git config commit.gpgsign false
  git add -A; git commit -qm init
}

teardown() { [ -n "${FIX:-}" ] && [ -d "$FIX" ] && rm -rf "$FIX"; return 0; }

# write_spec <id> <model> <verifier> -- a minimal valid-shaped spec (one api-component file).
write_spec() {
  cat > "tasks/active/$1-x.md" <<EOF
---
id: "$1"
slug: x
model: $2
verifier_model: $3
branch: task/$1-x
files_allowed:
  - components/api/src/x.ts
deps_preapproved: []
---
# Goal
placeholder
EOF
}
