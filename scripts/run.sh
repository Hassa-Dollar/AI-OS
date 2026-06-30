#!/usr/bin/env bash
# run.sh — take ONE task spec end-to-end: validate → dispatch to the worker → gate + land (or Opus draft).
# The Lead's one-command path for a TASK (engine/chore edits use change.sh). Every subscript's output streams
# through unfiltered, so all [ai-os] messages, CI lines, the QA verdict, and any diagnostics stay visible.
#   run.sh <task-id|spec-file>
#   e.g.  scripts/run.sh T03
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"
id="${1:?usage: run.sh <task-id>   (e.g. scripts/run.sh T03)}"

log "run $id — 1/3 validate (dispatch --dry-run): P8 · file-set disjoint · catalog · boundary · secret-scan"
bash "$DIR/dispatch.sh" "$id" --dry-run     # dies with its own diagnostics if the spec is invalid — cheap, before any worker spend
log "run $id — 2/3 dispatch to the worker ..."
bash "$DIR/dispatch.sh" "$id"
log "run $id — 3/3 ship: CI · cross-family QA · risk router → land or Opus draft ..."
exec bash "$DIR/ship.sh" "$id"
