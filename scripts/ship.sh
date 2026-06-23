#!/usr/bin/env bash
# ship.sh — the whole back half of a task in one command: gate (CI + cross-family QA +
# risk router + PR/auto-merge) then land (watch checks, confirm merge, sync main, cleanup).
#
# Usage: ship.sh <task-id|branch>
# If the risk router flags the diff, gate.sh opens a DRAFT PR for the Opus gate and
# land.sh stops with instructions — nothing merges without the Lead.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
arg="${1:?usage: ship.sh <task-id|branch>}"
bash "$DIR/gate.sh" "$arg"
bash "$DIR/land.sh" "$arg"
