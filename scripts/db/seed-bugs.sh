#!/usr/bin/env bash
# seed-bugs.sh — backfill the determinism-layer registry (BUG-01..11) into the memory DB. Idempotent
# (`bug add` is INSERT-OR-IGNORE + field updates). The narrative source stays
# knowledge/postmortems/determinism-layer-hardening.md; this makes the registry queryable (recall/state/export).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
db() { bash "$DIR/../db.sh" bug add "$@"; }

db BUG-01 --severity med  --status fixed --fixed-pr 25 \
  --symptom "edits over the WSL mount strip the +x bit; git tracked it" \
  --root-cause "9p mount rewrites files at 644; core.fileMode=true recorded the flip" \
  --fix "core.fileMode=false in bootstrap + restore; os-ci exec-bit guard"
db BUG-02 --severity med  --status fixed --fixed-pr 32 \
  --symptom "deps-allowlist false-positive on a YAML-quoted scoped package" \
  --root-cause "fm_list did not strip surrounding YAML quotes" \
  --fix "fm_list strips quotes at the root; lib.bats test"
db BUG-03 --severity high --status fixed --fixed-pr 33 \
  --symptom "opencode: Argument list too long on a large diff" \
  --root-cause "whole prompt (incl. diff) passed as one argv > MAX_ARG_STRLEN" \
  --fix "pass diff+spec via -f file attachments; exclude lockfiles from review diff"
db BUG-04 --severity med  --status fixed --fixed-pr 33 \
  --symptom "land.sh leaves the handoff dirty on main → next task rebase fails" \
  --root-cause "post-merge handoff cannot be committed to protected main; rides next PR" \
  --fix "gate.sh restores the pending handoff at the start"
db BUG-05 --severity low  --status fixed --fixed-pr 33 \
  --symptom "gate preflight blamed a dirty handoff on 'worker forgot to commit'" \
  --root-cause "preflight did not exclude the auto-generated handoff" \
  --fix "handoff restored before the dirty check"
db BUG-06 --severity high --status fixed --fixed-pr 32 \
  --symptom "npm audit --audit-level=high blocked on dev-tooling CVEs" \
  --root-cause "audited all deps incl. dev tooling, not just runtime" \
  --fix "npm audit --omit=dev (runtime deps only)"
db BUG-07 --severity med  --status fixed --fixed-pr 33 \
  --symptom "a non-component (docs/research) task dies on gate component-resolution" \
  --root-cause "gate assumed every task targets exactly one component" \
  --fix "lighter gate when files_allowed has no component; lib.bats component_of_spec"
db BUG-08 --severity med  --status fixed --fixed-pr 32 \
  --symptom "no task-id uniqueness guard → Shrink ids collided with old demos" \
  --root-cause "new-task never checked active+completed for the id" \
  --fix "new-task rejects a duplicate id; dispatch.bats test"
db BUG-09 --severity low  --status fixed --fixed-pr 33 \
  --symptom "gate reused any non-empty verdict, even a partial one from a crash" \
  --root-cause "reuse keyed on file non-empty, not parseability" \
  --fix "verdict_field + reuse only if RISK+VERDICT parse; lib.bats test"
db BUG-10 --severity low  --status fixed --fixed-pr 33 \
  --symptom "dispatch also passed the worker prompt as one argv (same root as BUG-03)" \
  --root-cause "argv prompt-passing" \
  --fix "attach the spec via -f"
db BUG-11 --severity med  --status open \
  --symptom "ship.sh from main can't find the task's spec (no active spec for id)" \
  --root-cause "gate resolves the spec from the current worktree before checking out the task branch" \
  --fix "(planned) resolve the spec from the task branch it is about to gate"

echo "[seed] registry bugs BUG-01..11 written to the memory DB"
