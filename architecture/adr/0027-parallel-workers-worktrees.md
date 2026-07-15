# ADR-0027: Parallel workers — git-worktree isolation, serialized integration

- **Status:** Accepted (implementation = task OS-P6, after OS-P1/OS-P4)
- **Date:** 2026-07-14
- **Deciders:** human operator + Lead

## Context
Parallelism was designed in from day one — dispatch enforces disjoint `files_allowed` across active
specs AND in-flight task branches (P2/P3), so two workers can never touch the same file — but never
exercised: `dispatch.sh` checks the task branch out in the single shared worktree, so two concurrent
workers would trample each other physically even though they can't collide logically. Shrink has
genuinely parallel pairs waiting (api tasks vs web tasks; T05 vs T09). Single-worker wall-clock is
the current throughput bottleneck.

## Decision
1. **Isolation: one `git worktree` per task** at `.worktrees/<id>/` (gitignored), the task branch
   checked out there; the worker's cwd is its worktree; per-task identity env (ADR-0019) and a
   persistent `logs/<id>.log` (OS-V1). No containers: the threat model is sloppy-not-adversarial
   workers (ADR-0014), and a Docker prerequisite would hurt the forkable scaffold.
2. **Scheduler:** `scripts/os run --parallel N` (Python, ADR-0023) computes the ready-set from
   `tasks/active/` (optional `depends_on_tasks:` frontmatter; the existing disjointness check gates
   admission) and runs up to N workers concurrently (default 2 — OpenCode rate-limit friendly).
   Worker state (start/exit/escalate) is recorded as DB events and surfaced by `os status`.
3. **Integration is SERIALIZED:** gate and land acquire a single lock (flock) — QA model runs may
   overlap, but rebase-onto-main and merges never do; trunk stays linear. `db.sh` gains
   `PRAGMA busy_timeout` so concurrent workers' memory writes don't collide.
4. **Lifecycle:** worktree removed after land; a crashed worker leaves its worktree + log for
   diagnosis; retry = re-dispatch onto the same branch.

## Consequences
- Wall-clock for independent tasks ≈ max, not sum; the file-set discipline that always existed
  finally pays out.
- Merge conflicts stay impossible by construction (disjoint files) and drift is still caught by the
  gate's rebase, which is now the serialization point.
- New failure modes (orphan worktrees, lock starvation) are bounded by the lifecycle rules and
  visible in `os status`.

## Alternatives considered
- **Containers per worker:** stronger isolation the threat model doesn't need; adds a fork
  prerequisite + per-container node_modules. Rejected for now; revisit if workers gain network trust
  issues.
- **Parallel gates/lands too:** racing rebases and merges buys minutes and risks trunk integrity.
  Rejected — integration serial is the industry norm for a reason.
