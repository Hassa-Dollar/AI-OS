#!/usr/bin/env bash
# ci-env.sh — CI commands gate.sh reads from the environment (seam owned by this profile, ADR-0003).
# profile.sh apply copies this to scripts/ci-env.sh. NOT secret (no tokens) → committed on purpose.
# gate.sh runs each command INSIDE the active component (cd "$comp"), so these stay component-relative.
export LINT_CMD="${LINT_CMD:-npm run lint}"
export TYPECHECK_CMD="${TYPECHECK_CMD:-npm run typecheck}"
export TEST_CMD="${TEST_CMD:-npm test}"
export COVERAGE_CMD="${COVERAGE_CMD:-npm run coverage}"
export SECRET_SCAN_CMD="${SECRET_SCAN_CMD:-}"  # blank → gate.sh auto-uses gitleaks if installed
# Risk-router thresholds (also in profile.json; tune weekly from the ledger):
export MAX_FILES="${MAX_FILES:-10}"
export MAX_LINES="${MAX_LINES:-300}"
