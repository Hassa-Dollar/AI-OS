#!/usr/bin/env bash
# verify-coherence.sh — fail if a GENERATED doc block drifted from the repo it describes (a CI "fitness
# function"; ADR-0018, analysis Step 4). Regenerates the deterministic AUTO-INVENTORY block in memory
# (gen_inventory, _lib.sh) and compares it to what is literally in each doc. A mismatch means the block was
# hand-edited, or components/profiles changed without running handoff.sh.
#
# Why compare the BLOCK, not `git diff` the whole file: architecture/README.md is MIXED (hand-written prose
# + one generated block) and ci-local.sh runs against a DIRTY tree (edit -> verify -> commit), so a
# whole-file diff would flag legitimate prose edits as "stale" (it would have on analysis Fix 6). Block
# compare is git-independent, mutates nothing, and has no such false positive.
#
# Only DETERMINISTIC blocks are checked. AUTO-STATE / AUTO-SHIPPED embed a timestamp + live git/PR state and
# cannot be reproduced in CI — out of scope by design.
# Invoke: bash scripts/verify-coherence.sh   (runs in ci-local.sh and os-ci)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"
shopt -s nullglob

gen_files=(architecture/README.md docs/handoff/SESSION-HANDOFF.md)
fresh="$(gen_inventory)"
checked=0

for f in "${gen_files[@]}"; do
  [[ -f "$f" ]] || continue
  grep -q 'AUTO-INVENTORY:BEGIN' "$f" || continue
  checked=$((checked + 1))
  have="$(block_inclusive "$f" AUTO-INVENTORY)"
  if [[ "$have" != "$fresh" ]]; then
    printf '\033[31m  drift in %s — block in file (<) vs expected from repo (>):\033[0m\n' "$f" >&2
    diff <(printf '%s\n' "$have") <(printf '%s\n' "$fresh") >&2 || true
    die "generated inventory in $f is stale" \
      "the AUTO-INVENTORY block was hand-edited, or components/profiles changed without regenerating it" \
      "run: bash scripts/handoff.sh   then commit the refreshed docs"
  fi
done

log "coherence: AUTO-INVENTORY matches the repo in ${checked} doc(s) ✓"
