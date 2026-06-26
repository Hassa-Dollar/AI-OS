# ADR-0019: Least-privilege memory-DB writes for workforce runs

- **Status:** Accepted
- **Date:** 2026-06-26
- **Deciders:** Lead (Opus) + human operator

## Context
The memory DB (ADR-0016) is written through one tool, `db.sh`, with defined, secret-scanned ops (ADR-0014)
and no raw-SQL or delete path. But every op lets the caller choose `--scope`, `--actor`, and (`learn`)
arbitrary semantic knowledge. That was fine while only the operator + the Lead wrote to it. We are about to
dispatch **workers** (T01), which write to the DB during a run — at minimum via the autonomous `die()`/exit
capture in `_lib.sh`. A worker bound to one component must not pollute OS-level or another component's
memory, curate semantic knowledge, or attribute its writes to the operator.

Threat model — deliberately bounded: the workers are open-weight models the operator runs via `opencode` in
their own WSL. The risk is **buggy / misaligned automation, not an adversary**. The DB is local + gitignored
(low blast radius).

## Decision
Enforce a **least-privilege write policy + trusted provenance** in `db.sh`, with identity injected by the
dispatcher — NOT a sandbox.

- **Identity is injected by `dispatch.sh` / `gate.sh`**, scoped to the worker run only (an `env` prefix on
  the `opencode` invocation, never a global export): `AI_OS_ACTOR=agent:<model>`, `AI_OS_ROLE`
  (`implementer` / `verifier`), `AI_OS_COMPONENT=<component>`, `AI_OS_TASK=<id>`. Only for **component
  tasks**; an OS/chore task (no component) runs unconfined (Lead-approved + rare).
- **`db.sh` confines a run** when `AI_OS_ROLE` is set and `!= lead`:
  - `remember` / `bug` writes are **pinned to `component:<AI_OS_COMPONENT>`** (a conflicting
    `--scope`/`--component` is overridden) and to the **injected actor** (`--actor`/`--found-by` ignored) —
    no cross-scope writes, no impersonation. A confined write with no component **refuses** (loud, and
    non-fatal to autonomous capture, which is best-effort).
  - `learn` (semantic / OS knowledge) is **denied** — semantic memory stays Lead-curated.
  - secret-scan on write (ADR-0014) unchanged.
  - the **operator / Lead** (no `AI_OS_ROLE`, or `lead`) is unrestricted.
- **Tested** in `scripts/test/db.bats`: scope coercion · actor not impersonated · `learn` denied · operator
  unrestricted · confined-without-component refused.

## Consequences
- A worker can record its own component's episodic/bug memory and nothing else; the operator's hand-run
  access is unchanged. Autonomous capture for a worker lands in its component scope automatically.
- **Honest limit:** this is env-trust, not isolation. A worker with shell access could `unset AI_OS_ROLE`,
  forge the env, or call `sqlite3` on the DB file directly. True per-worker isolation (sandbox/container,
  blocking direct DB access) is a separate, larger effort — tracked with the self-healing/sandbox backlog.
  Given the threat model (buggy automation) and blast radius (local, gitignored), this is proportionate.
- New env contract: `AI_OS_ROLE` / `AI_OS_COMPONENT` now carry meaning for `db.sh`; the dispatcher owns them.

## Alternatives considered
- **Per-worker sandbox / container with the DB reachable only through a broker.** Real isolation, but heavy
  infra for a local, low-blast-radius DB and a non-adversarial threat model. Deferred (backlog).
- **No control, rely on provenance + audit only.** Every write already carries an actor, but a buggy worker
  could still overwrite OS/semantic memory. Rejected — confinement is cheap and prevents the likely failure.
- **Block direct `sqlite3` access.** Not possible without a sandbox; out of scope here (documented limit).
