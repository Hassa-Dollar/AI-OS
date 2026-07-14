#!/usr/bin/env bash
# ledger-append.sh — append one row to reports/metrics/ledger.csv (creates header if missing).
# Usage: ledger-append.sh <event> <task_id> <note...>
#   event: dispatch | qa | auto-approve | opus-gate | merge | rollback | opus-msg | guardrail
#   (opus-gate/opus-msg are the HISTORICAL kind names for the Lead gate / Lead messages — kept for
#    ledger continuity, ADR-0025; do not rename past events.)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"

event="${1:?event required}"; task_id="${2:-}"; shift $(( $# >= 2 ? 2 : $# )) || true
note="${*:-}"
csv="$(ledger_path)"; mkdir -p "$(dirname "$csv")"
[[ -f "$csv" ]] || echo "ts,event,task_id,branch,actor,note" > "$csv"

branch="$(git -C "$(repo_root)" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '-')"
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
# CSV-escape the note (wrap in quotes, double any internal quotes).
esc_note="\"${note//\"/\"\"}\""
echo "$ts,$event,$task_id,$branch,${USER:-unknown},$esc_note" >> "$csv"
# mirror into the memory DB (ADR-0016) — dual-write during v1 so nothing breaks; best-effort + non-fatal.
[[ -f "$DIR/db.sh" ]] && bash "$DIR/db.sh" ledger "$event" "$task_id" "$note" >/dev/null 2>&1 || true
log "ledger += $event $task_id"
