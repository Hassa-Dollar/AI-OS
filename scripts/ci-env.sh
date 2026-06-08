#!/usr/bin/env bash
# ci-env.sh — the CI commands gate.sh reads from the environment.
# NOT secret (no tokens here) → committed on purpose. `source scripts/ci-env.sh` before gate.sh,
# or add `source scripts/ci-env.sh` to your shell profile / .envrc.
# This repo's stack: TypeScript + Node — these map to package.json scripts.
export LINT_CMD="${LINT_CMD:-npm run lint}"
export TYPECHECK_CMD="${TYPECHECK_CMD:-npm run typecheck}"
export TEST_CMD="${TEST_CMD:-npm test}"
export COVERAGE_CMD="${COVERAGE_CMD:-npm run coverage}"
export SECRET_SCAN_CMD="${SECRET_SCAN_CMD:-}"  # blank → gate.sh auto-uses gitleaks if installed
# Risk-router thresholds (gate.sh defaults shown; tune weekly from the ledger):
export MAX_FILES="${MAX_FILES:-10}"
export MAX_LINES="${MAX_LINES:-300}"
