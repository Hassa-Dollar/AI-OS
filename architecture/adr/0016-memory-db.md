# ADR-0016: Local memory DB (episodic + semantic + bug) for the AI-Dev-OS

- **Status:** Accepted
- **Date:** 2026-06-21
- **Deciders:** Lead (Opus) + human operator

## Context
Agents — and humans running scripts — wake from zero and re-derive context from raw code; failures often
happen with **no agent active**. We want persistent, **dated**, cross-session memory any actor can write
mid-flight and later query for patterns (bugs, causes, fixes, decisions). Research grounds this: the
production norm is the **working/episodic/semantic/procedural** memory taxonomy + **local-first SQLite +
FTS5** (Mem0/Letta/Zep). Right-sizing the git principle (not abandoning it): **git stays source-of-truth for
the procedural/source layer** (scripts, prompts, contracts, ADRs, specs); the **DB owns episodic + semantic
memory** (git can't retrieve/scale memory).

## Decision
- **SQLite, one local gitignored file** (`reports/metrics/memory.db`) + FTS5; schema in `scripts/db/schema.sql`.
- **Tables:** `episodic` (dated event log; `actor` = `agent:` | `system:` | `human:`; FTS5) · `semantic`
  (categorized knowledge; FTS5) · `bug` (registry lifecycle). Every row carries **`scope`** (`os` |
  `component:<name>`) — the relevance filter and the unit of memory that travels when a component is extracted.
- **`scripts/db.sh`** — the ONE reader/writer: `remember · learn · bug · recall · state · export · ledger`.
  Parameterized (SQLite-escaped), **secret-scanned on write** (ADR-0014), `actor`/`role` auto-filled.
- **Autonomous writers (no AI required):** `_lib.sh` `die()` + an `EXIT` trap log failures to episodic;
  `ledger-append.sh` dual-writes CSV + DB. Best-effort + **non-fatal** (logging never breaks a script);
  recursion- and subshell-guarded.
- **Retrieval = RAG, scoped + bounded + role-gated:** `recall` filters by scope/recency at a small top-k;
  broad/deep research is researcher-only (`db research`, v2), never inside an implement/verify gate; workers
  **escalate** instead of open-ended-researching mid-task (AGENTS §8).
- **Tested:** `scripts/test/db.bats` (round-trip · secret-scan · scope · autonomous capture) runs in os-ci.
- **Phasing:** **v1** = FTS5 + all the above (this ADR). **v2** = sqlite-vec semantic/vector RAG. **v3** =
  consolidation (episodic→semantic) + pruning. RAG auto-injection at dispatch/gate = v1.1.

## Consequences
- A queryable, dated black box of what ran and what broke — agent or not; the human-run breakages we kept
  hitting are now captured automatically. `ledger.csv` + the bug registry become DB-backed (markdown kept as
  a generated view via `db export registry`).
- New local dependency: the `sqlite3` CLI (FTS5-enabled). Git stays authoritative for code + decisions.
- Built by the Lead for now (core OS-internals); once the OS is proven, this class of task is dispatched to
  the workforce (the Lead just leads).

## Alternatives considered
- **All-markdown (status quo):** no retrieval/scale; agents keep re-deriving context. Rejected.
- **Hosted memory (Mem0/Zep/Letta):** external dependency + cost, against the local / ~$30-mo ethos. Rejected for now.
- **Vector DB from day one:** heavier infra (embeddings) for marginal v1 gain; FTS5 covers exact-term recall
  (error codes, slugs), most of the early value. Deferred to v2.
