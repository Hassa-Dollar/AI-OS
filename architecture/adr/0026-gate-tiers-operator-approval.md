# ADR-0026: Gate tiers — the Lead reviews judgment, the operator lands the rest

- **Status:** Accepted
- **Date:** 2026-07-14
- **Deciders:** human operator + Lead

## Context
The risk router had one escalation target: every flagged diff waited for the scarce Lead. T04 made
the waste concrete: adding `zod` — pre-approved in the spec's `deps_preapproved` (a Lead decision at
spec time) and mechanically verified by the ADR-0014 guard — would have cost a Lead review cycle to
learn nothing. Meanwhile size flags (`lines>MAX`) routinely fire on tasks whose specs the Lead wrote
big on purpose. The operator asked for the principle directly: the Lead is called at critical
moments; the human keeps the system moving otherwise.

## Decision
1. **Suppress `dependency-change` when it carries no information:** the ADR-0014 guard ran, the full
   dep-entry delta (dependencies + devDependencies, name@version) is additions-only, every added name
   ⊆ `deps_preapproved`, and the only manifest changes are the task component's `package.json` +
   lockfile. Removals, version changes, lockfile-only churn, or foreign manifests still flag.
2. **Two review tiers for flagged diffs:** OPERATOR = size-only flags (`files>`, `lines>`) — draft PR
   titled `OPERATOR GATE`, body tells the operator to skim the QA verdict and run `approve.sh`.
   LEAD = everything else (touches-contract, touches-architecture, blast-radius-high, security-path,
   model-override, verifier-risk-high, dependency-change). Ledger notes record `tier=`.
3. **HUMAN-REQUIRED (reviews/checklist.md) is unchanged** and sits above both tiers.
4. This ADR also sanctions **OS-V1** (worker visibility: logs + `os status`) and **OS-P6** (parallel
   dispatch, ADR-0027) as operator-requested additions to the ADR-0024 epic list.
5. Implemented as a small edit to pre-port `gate.sh` — a conscious, noted waiver of ADR-0023's
   no-new-bash-logic rule; OS-P3 ports it to Python with unit tests.

## Consequences
- Lead messages are spent only where judgment is needed; T04-class diffs land on operator time.
- A cross-family QA pass remains mandatory on every flagged diff regardless of tier — the tier only
  changes WHO reads the verdict, never whether verification happens.
- Risk: the operator rubber-stamps size flags. Mitigation: the QA verdict is in the PR body, and the
  weekly review reads `tier=` ledger notes to spot drift.

## Alternatives considered
- **Auto-approve size-only flags outright:** removes the human skim on big diffs; too far. Rejected.
- **Keep Lead on all flags:** the measured waste that prompted this ADR. Rejected.

## Amendment (2026-07-15): `touches-os-engine` is LEAD tier
OS-V1 (a worker diff modifying `gate.sh`/`dispatch.sh` themselves) routed as OPERATOR because its
only flag was size — too soft for guardrail code. The router now raises `touches-os-engine` (LEAD
tier) for any change to top-level `scripts/*.sh`, `scripts/os*`, or `scripts/db/`. `scripts/test/`
is deliberately not engine. Lead-direct chores (change.sh/pr.sh) never pass through gate.sh, so this
only affects dispatched worker tasks — exactly the intent.
