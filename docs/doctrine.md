# Doctrine

The principles AI-OS runs on. They carry over unchanged from v1 (tag `v1-final`), plus one new rule, P12. When a
principle conflicts with an ADR, the ADR wins.

**P1 — Route by leverage, not price.**
`LEVERAGE = BlastRadius × Irreversibility × SpecGap`.
- High leverage goes to the Lead (decide, design, review).
- Low leverage, specified and test-verifiable work goes to the workforce.
- High SpecGap means the Lead closes the gap by writing a spec; a worker then executes it.

In v2 the router makes P1 executable (ADR-0031). A spec gap stops dispatch; high blast radius or irreversibility
raises the review gate. The Lead's product is specs and contracts, not bulk code.

**P2 — Intelligence over agent count.** One implementer and one verifier per task. Add a parallel worker only when its
file set is disjoint.

**P3 — Coordinate through artifacts.** Git, specs and records, not live chat. Committed state is per-task files only
(ADR-0030).

**P4 — Context quality over quantity.** A curated ~8K tokens beats a raw 800K. Specs carry compressed context, and
workers read the repo itself rather than dumps of it.

**P5 — One owner of coherence.** The Lead, persisted as ADRs and contracts.

**P6 — The spec is the unit of work.** It is self-contained: a worker needs nothing else (`spec.schema.md`).

**P7 — Verification is cheaper than generation.** Over-invest in cheap checks: tests, hidden acceptance checks, and a
second model.

**P8 — The writer never grades.** The verifier's family differs from the author's, and neither approves the merge.

**P9 — Useful output is merged and stays merged** (≈2 weeks), not lines of code. A record that gets reverted counts
against the task.

**P10 — Determinism where you can, intelligence where you must.** Plain code does dispatch, gating and landing. Models
do the judgement.

**P11 — Graceful degradation and reversibility.** One-command rollback, reproducible from the spec. When a dependency is
down (the router, a provider), fall back and record that you did.

**P12 — Cost-route within the workforce (new in v2).** Among models that can do a task, use the one with the lowest
expected cost *to a merged result*, not the lowest price per token. A cheap model that fails twice costs more than a
mid-tier model that passes once. Measure dollars per merged task from records, and let those numbers, not intuition,
move models between tiers.

## Separation of powers
The workforce implements against a spec. The verifier grades the diff against the spec. The gate (code, not a model)
decides the tier. Only the Lead or the operator approves anything flagged, and nothing in HUMAN-REQUIRED is ever
auto-merged.

## HUMAN-REQUIRED (hard stops; never decided by a model)
- **Product and scope:** direction; irreversible spend; external-facing releases.
- **Security and data:** auth/authz, payments, secrets, PII, production data migrations.
- **Interfaces:** breaking a public API or contract.
- **Hardware:** flashing devices; bootloader, fuses or secure-boot keys; OTA releases; anything that moves physical
  actuators or sets their safety limits.
