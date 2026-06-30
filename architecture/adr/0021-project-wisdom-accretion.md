# ADR-0021: Project wisdom accretion — two memory stores

Status: Accepted

## Context
The OS builds many products over time. Bugs hit and solutions found *while building* are hard-won
knowledge that should make the **next similar build** better — "similar" meaning the **same profile/stack**.
Today that knowledge evaporates: e.g. in T02 the GLM worker discovered that `better-sqlite3` needs a
default import under `verbatimModuleSyntax` and self-corrected, but the lesson was never saved.

ADR-0016 gave us a memory DB (episodic/semantic/bug, `db.sh`, SQLite+FTS5). Used naively it **conflates
two different things**: the factory's own *operational* memory (dispatch/gate/CI failures, OS bugs) and
*product-domain* wisdom (stack/profile lessons). The owner's requirement: keep these **separate**, make
project wisdom **persistent across a project reset**, and keep it **DB-backed**. ADR-0002 isolation and the
reset semantics agree: a reset wipes *projects* but must **keep** accreted wisdom + profiles.

## Decision
1. **Two stores, one tool.** `db.sh` already honors `AI_OS_DB`, so no engine change is needed:
   - **System memory** — `reports/metrics/memory.db`: factory operational events/errors/OS bugs.
     Gitignored, prunable; a reset MAY prune `component:*`-scoped rows (project-specific).
   - **Project wisdom** — `knowledge/wisdom.db`: durable, cross-project lessons + product bugs, scoped by
     profile/stack. The retrieval source of truth. A reset **never** touches it.
2. **Scope/tag convention = the retrieval key for "similar projects".** Lessons are profile-scoped and
   tagged: `--scope profile:<family>/<variant> --tags "profile:<…>,dep:<pkg>,topic:<area>"`. "Similar" ≡
   same profile.
3. **Capture, per the ADR-0019 split.** Workers record raw bugs they hit+fixed via `db.sh bug add`
   (component-scoped — already permitted). The **Lead promotes** the reusable ones into profile-scoped
   semantic lessons in the wisdom DB (`AI_OS_DB=knowledge/wisdom.db db.sh learn …`). Only the Lead writes
   semantic, so the durable layer stays curated, deduped, and non-contradictory — not a noise dump.
   **Promotion is BATCHED (per sprint/phase), never per-task** — the only per-task cost is the worker's
   free `bug add`. At volume, a cheap model (the scribe) drafts candidate lessons from the accumulated raw
   bugs and the Lead merely *approves* a batch (`wisdom.sh curate`, follow-up) — Lead-as-gate without
   per-task Opus authoring.
4. **Portability.** A committed markdown export (`knowledge/lessons.md`, generated like the bug registry)
   lets wisdom travel with the repo (forks inherit it) and be PR-reviewed; a fresh clone rebuilds
   `wisdom.db` from it. (Export/import is follow-up; the `.db` + `recall` is the core that starts now.)
5. **Injection — the payoff (later).** `dispatch.sh` and the verifier prepend lessons recalled by the
   component's profile + the deps/topic the task touches — retrieval-augmented dispatch — so future similar
   builds start pre-warned. Additive; wires once a handful of lessons exist.
6. **Reset semantics.** Reset keeps `knowledge/` + `wisdom.db` + profiles; prunes `component:*` rows from
   `memory.db`. Wisdom outlives projects by construction.

## Consequences
- **+** Wisdom accretes across projects, scoped for reuse; system vs project memory cleanly separated;
  survives reset; **almost no new code** — `db.sh` + `AI_OS_DB` + `--tags`/`--scope` already exist.
- **+** Lead curation keeps quality, matching the scarce-Lead-as-coherence-owner role (§6 weekly promote).
- **−** Two DBs to keep straight (mitigated by the `AI_OS_DB=knowledge/wisdom.db` convention + this ADR).
- **−** Committed export + clone-rebuild is deferred machinery (fine — single operator, no fork yet).
- **−** Until injection is wired, capture depends on discipline; a completion-report "Lessons" section + a
  `prompts/task-execution.md` line reduce reliance on memory.
