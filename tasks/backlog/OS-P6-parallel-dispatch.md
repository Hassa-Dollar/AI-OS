---
id: OS-P6
slug: parallel-dispatch
owner_role: autonomous
model: opencode-go/kimi-k2.7-code          # OS task (no component profile) → explicit pins, P8 pairing
verifier_model: opencode-go/deepseek-v4-pro
branch: task/OS-P6-parallel-dispatch
blast_radius: high         # the execution engine itself
files_allowed:
  - scripts/os/
  - scripts/os
  - scripts/dispatch.sh
  - scripts/gate.sh
  - scripts/land.sh
  - scripts/db.sh
  - scripts/test/
  - .gitignore
depends_on_contracts: []
deps_preapproved: []       # Python 3 STDLIB ONLY (ADR-0023) — pip is a STOP condition
---

# Goal
`scripts/os run --parallel N` executes multiple ready tasks concurrently, each worker in its own git
worktree with its own log, while gates/lands stay strictly serialized — per ADR-0027.

# Context (compressed)
Design is FIXED by ADR-0027 — implement it, don't redesign it. Prerequisites already landed: the
`scripts/os` package + `os status --json` (OS-V1), the Python speclib (OS-P1), the dispatch port
(OS-P4). Key mechanics:
- **Worktrees:** `git worktree add .worktrees/<id> <task-branch>` (gitignored); worker cwd = its
  worktree; per-task identity env (ADR-0019); output → `logs/<id>.log` (OS-V1 format). Remove after
  land (`os worktree clean <id>`); a crash leaves worktree + log.
- **Scheduler:** ready-set = active specs whose optional `depends_on_tasks:` are all in
  `tasks/completed/` and whose `files_allowed` are disjoint from every RUNNING task (reuse the ported
  dispatch disjointness check — do not re-implement). Launch up to N (default 2). Record
  `dispatch-start`/`dispatch-exit` DB events; `os status` shows them.
- **Serialization:** gate/land wrap their body in an exclusive flock on `.git/ai-os-integration.lock`
  — two simultaneous gate invocations must queue, never interleave. QA model calls may overlap.
- **DB concurrency:** add `PRAGMA busy_timeout=5000` to db.sh init (concurrent worker writes).

# Acceptance criteria  (executable)
- [ ] Fixture repo: two tasks with disjoint files + stub workers (a `WORKER_CMD` test hook or
      DRY_RUN-style injection) run CONCURRENTLY (overlapping timestamps in both logs) under
      `os run --parallel 2`; both branches end committed.
- [ ] A third task whose `files_allowed` overlaps a RUNNING task is NOT admitted until it finishes.
- [ ] A task with `depends_on_tasks: [X]` waits until X's spec is in `tasks/completed/`.
- [ ] Two simultaneous `gate.sh --dry-run` invocations serialize on the lock (observable ordering).
- [ ] Crash path: kill a stub worker → `os status` shows `failed`, worktree + log preserved;
      re-dispatch reuses the branch.
- [ ] `bats scripts/test` fully green; concurrent `db.sh remember` from two processes both land.

# Out of scope  (binding)
- No auto-shipping after workers finish (operator/Lead still runs ship). No containers. No
  notification hooks (phase 2). No change to the QA/risk-router semantics.

# Stop conditions
- ADR-0027 seems wrong or incomplete for a criterion → STOP, escalate (architecture is Lead-owned).
- Any capability seems to need a pip package → STOP, escalate.

# Working notes  (worker appends)
