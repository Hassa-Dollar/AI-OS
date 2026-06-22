# ADR-0017: Bug provenance (`found_by`) on the memory DB

- **Status:** Accepted
- **Date:** 2026-06-22
- **Deciders:** Lead (Opus) + human operator
- **Extends:** ADR-0016 (memory DB). This is a v1.1 schema increment.

## Context
The `episodic` table already records who/what produced each event via `actor`
(`system:<script>` | `agent:<model>` | `human:<user>`), so auto-captured failures are already
separable from deliberate logs. The `bug` (curated registry) table had **no actor field** — once a
bug was in the registry there was no way to tell whether the *system* caught it, *which AI* found it,
or a human logged it. As more agents (and the system itself) write bugs, that provenance matters for
trust, triage, and auditing.

## Decision
- Add **`found_by TEXT`** to the `bug` table, reusing the **same actor taxonomy** as `episodic`:
  `system:<script>` (autonomous capture, no AI), `agent:<model>` (an AI — the **suffix names which one**,
  e.g. `agent:glm-5.2`, `agent:opus-lead`), `human:<user>`. The **prefix** is the auto-vs-AI-vs-human
  separation the operator asked for; the **suffix** is the "which AI" identifier. One field, one taxonomy.
- `db.sh bug add` fills `found_by` at **creation** from `--found-by` or, failing that, `$AI_OS_ACTOR`
  (default `human:$USER`). It is **set on add, not overwritten on later updates** unless `--found-by` is
  passed explicitly — so "who found it" survives a status change made by someone else.
- **Migration:** the schema gains the column for fresh DBs; existing DBs are migrated by an **idempotent
  guarded `ALTER TABLE ... ADD COLUMN`** in `db.sh` (run every invocation; a no-op once present). This is
  the DB's first migration and the pattern for future ones.
- `db.sh export registry` gains a **`by`** column so provenance is visible in the generated view.
- `dispatch.sh` should export `AI_OS_ACTOR=agent:<model>` for the worker it launches (follow-up), so an
  agent's writes are self-attributed without the agent doing anything.

## Consequences
- Every bug now says who found it; system-caught (`system:`) is queryable separately from AI-logged
  (`agent:`) and human-logged (`human:`), and the exact model is recorded.
- Historic rows (BUG-01..17) predate the column → backfilled once to `agent:opus-lead` (the Lead found
  them all; the human only typed them because the Lead's sandbox was down).
- New local dependency on a tiny migration step; `db.sh` stays the only writer.

## Alternatives considered
- **Two booleans (`auto_caught`, `ai_logged`):** redundant with the actor prefix and can't name the model. Rejected.
- **Reuse episodic only (no bug field):** the registry would still be unattributed; you'd have to join on
  timing/ids to guess provenance. Rejected — the registry should be self-describing.
