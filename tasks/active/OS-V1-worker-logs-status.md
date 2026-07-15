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

## 2026-07-15 — ESCALATE (halted, no guessing)

**Blocking conflict between `files_allowed` shape and gate.sh's boundary audit + dispatch's disjointness check.**

The spec lists `files_allowed` as directory / prefix forms:
- `scripts/os/` (dir) · `scripts/os` (file) · `scripts/test/` (dir) · `scripts/dispatch.sh` · `scripts/gate.sh` · `.gitignore` · `docs/handoff/SESSION-HANDOFF.md`

But the boundary audit (gate.sh:89-101) and the P2/P3 disjointness check (dispatch.sh:105, via `intersect` → `grep -qxF`) both use **exact full-line fixed-string matching**, NOT prefix/directory matching. Verified empirically:
- `scripts/test/status.bats` → **NO-MATCH** against `scripts/test/` → recorded as an `escaped_files` guardrail → `die` aborts the gate BEFORE the risk router.
- `scripts/os/__main__.py` (package form) → **NO-MATCH** against `scripts/os/` → same abort.
- Exact entries (`scripts/dispatch.sh`, `scripts/gate.sh`, `.gitignore`, `docs/handoff/SESSION-HANDOFF.md`) DO match. `logs/*` is gitignored so it never enters the diff (not a concern).

The AC explicitly requires:
- AC#2: a `scripts/os` executable + a `status` subcommand.
- AC#3: "`bats scripts/test` fully green (add a status.bats black-box test)" + "Python stdlib `unittest` covers state derivation".

**AC#3 is unsatisfiable under the current audit:** any new file under `scripts/test/` (the `.bats` black-box test AND any Python `unittest` placed there) fails the exact-match audit and aborts `gate.sh`. AC#2's package form (`scripts/os/`) has the same problem; only the single-file form `scripts/os` (exact) passes.

**Out-of-scope (binding) forbids the obvious fix:** "No changes to what dispatch/gate DO — only where their output lands." Extending the boundary audit + `intersect` to honor trailing-slash directory-prefix entries is a change to what `gate`/`dispatch` DO (audit/guardrail semantics — a contract-grade invariant; the boundary contract `architecture/contracts/os-component-boundary.md` says changing it is HIGH leverage → Lead-owned, new ADR). So I cannot make that fix without violating §3 / the out-of-scope clause.

**Missing decision (Lead):** pick one so the task is implementable + gatable as specified:
1. **Approve extending the boundary audit (gate.sh) + disjointness check (dispatch.sh `intersect`) to honor trailing-slash directory-prefix `files_allowed` entries** (e.g. `scripts/os/` covers `scripts/os/*`). This is a guardrail-semantics change to `gate.sh`/`dispatch.sh` → needs a Lead blessing (and likely an ADR-0002 boundary note). I will implement it minimally + add tests. **Note:** this then changes AC#2's package shape from single-file `scripts/os` to the `scripts/os/` package (ADR-0023 §2), and lets AC#3's tests live under `scripts/test/`.
2. **Restate `files_allowed` with EXACT file paths** (e.g. `scripts/os` single executable file; `scripts/test/status.bats`; `scripts/test/test_status.py`), and confirm whether `scripts/os` should be a single executable Python **file** (exact match) or the `scripts/os/` **package** dir (which cannot exact-match without option 1). With exact paths, no audit change is needed, and I implement to the updated list.

I stopped here per AGENTS.md §3 / "Stop conditions" + the spec's own "Stop conditions" rather than guess a contract-grade change. No code changes made; worktree clean except this Working-Notes append + the pre-existing harmless auto-regenerated SESSION-HANDOFF state block.

### Lead decision (2026-07-15, answers the ESCALATE above)
Option 1 — LANDED on main as ADR-0028 (PR #79): `files_allowed` entries ending in `/` are directory
grants; the gate audit (`path_allowed`) and disjointness (`filesets_clash`) honor them. This branch
is rebased onto that main. Consequences for you: `scripts/os/` IS the package dir (ADR-0023 §2 shape,
plus the `scripts/os` executable entrypoint file — both are in files_allowed); your tests live under
`scripts/test/` (the dir grant covers new files). The spec is now implementable exactly as written —
proceed; no further guardrail changes are in scope for you.
