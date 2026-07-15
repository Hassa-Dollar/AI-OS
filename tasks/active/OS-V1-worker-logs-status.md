---
id: OS-V1
slug: worker-logs-status
owner_role: implementer
model: opencode-go/glm-5.2                 # OS task (no component profile) → explicit pins, P8 pairing
verifier_model: opencode-go/deepseek-v4-pro
branch: task/OS-V1-worker-logs-status
blast_radius: med
files_allowed:
  - scripts/os/
  - scripts/os
  - scripts/dispatch.sh
  - scripts/gate.sh
  - scripts/test/
  - .gitignore
  - docs/handoff/SESSION-HANDOFF.md
depends_on_contracts: []
deps_preapproved: []       # Python 3 STDLIB ONLY (ADR-0023) — pip is a STOP condition
---

# Goal
The operator can watch any worker live (`tail -f logs/<id>.log`) and see the whole system at a glance
(`scripts/os status`): every in-flight task's role, branch, worker state, last log line, and gate/PR
state. This seeds the `scripts/os/` Python package (ADR-0023) with its first read-only command.

# Context (compressed)
Today `dispatch.sh` tees worker output to a `mktemp` file deleted on success (`run_worker`, the
`$wlog` variable) and `gate.sh` captures verifier stderr the same way — the operator is blind
(finding #1 of the 2026-07-14 review; sanctioned by ADR-0026 §4). Two changes:
1. **Persistent logs:** worker + verifier output goes to `logs/<id>.log` (append; one
   `=== <utc-timestamp> <script> model=<slug> ===` header per run). `logs/` is gitignored. Keep the
   live `tee` behavior (operator sees stdout too). Error paths keep quoting the real output (BUG-20).
2. **`scripts/os status`:** executable `scripts/os` (python3 stdlib) with a `status` subcommand.
   ONE ROW PER TASK found in `tasks/active/` OR with a live `task/*` branch — several rows at once IS
   the parallel view (OS-P6). Columns (operator requirements, 2026-07-15):
   - `id` · `agent` (the RESOLVED model slug + role, e.g. `glm-5.2/implementer`) · `branch`
   - `state` — the full lifecycle, derived deterministically:
     `queued` (spec active, no dispatch ledger event) → `running` (dispatch event, log mtime < 120s,
     no run footer) → `waiting-gate` (run footer says worker done, no qa event yet) → `gated-held`
     (opus-gate ledger event, PR still draft) → `done` (land event) / `failed` (footer or error event).
   - `report` — `reports/tasks/<id>-completion.md` when it exists (the operator reads THIS instead of
     asking the Lead), else `—`; plus `log` path + last log line (truncated).
   `dispatch.sh` writes a machine-readable run footer (`=== exit <code> <utc> ===`) to the log so
   state derivation never guesses. `gh` lookups optional and offline-tolerant (skip silently).
   Exit 0 always; `--json` emits the same rows for machine use (OS-P6's scheduler reads it).

# Acceptance criteria  (executable)
- [ ] A dispatched task's full worker output exists in `logs/<id>.log` after the run (success AND
      failure), with the timestamped header; re-runs append.
- [ ] `scripts/os status` prints the table for a fixture repo with one queued + one finished task;
      `--json` emits the same as JSON. No git/gh mutation (read-only — verify with a byte-identical
      worktree check).
- [ ] Python stdlib `unittest` covers state derivation (queued/running/done/failed) from fixture logs
      + ledger lines; `bats scripts/test` fully green (add a status.bats black-box test).
- [ ] `logs/` gitignored; SESSION-HANDOFF §2 daily-cycle notes gain the two commands.

# Out of scope  (binding)
- No notifications, no TUI/GUI (phase 2 — `tasks/backlog/os-v2-notify-tui.md`). No scheduler (OS-P6).
- No changes to what dispatch/gate DO — only where their output lands.

# Stop conditions
- Any capability seems to need a pip package → STOP, escalate.
- A bats test can only pass by weakening its assertion → STOP, escalate.

# Working notes  (worker appends)
