#!/usr/bin/env bash
# ci-env.sh — CI commands gate.sh runs INSIDE the active component (it cd's into components/<name>).
# Same commands for every JS/TS component; the matrix product-ci (ADR-0013) runs `npm run -s ci` per
# component. NOT secret (no tokens) → committed on purpose. Respects already-set env vars.
export LINT_CMD="${LINT_CMD:-npm run -s lint}"
export TYPECHECK_CMD="${TYPECHECK_CMD:-npm run -s typecheck}"
export TEST_CMD="${TEST_CMD:-npm run -s test}"
export COVERAGE_CMD="${COVERAGE_CMD:-npm run -s coverage}"
export AUDIT_CMD="${AUDIT_CMD:-npm audit --omit=dev --audit-level=high}"   # AC8: no high/critical runtime advisories
export SECRET_SCAN_CMD="${SECRET_SCAN_CMD:-}"   # blank → gate.sh auto-uses gitleaks if installed
# Risk-router thresholds (gate.sh defaults; tune weekly from the ledger):
export MAX_FILES="${MAX_FILES:-12}"
export MAX_LINES="${MAX_LINES:-350}"
