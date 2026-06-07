# ADR-0001: Adopt the Solo AI-Dev-OS operating model

- **Status:** Accepted
- **Date:** 2026-06-07
- **Deciders:** Lead (Opus) + human operator

## Context
A single operator is building software with AI. Premium model capacity (Claude Opus, via
Claude Pro) is scarce and rate-limited; open-weight coding models (via OpenCode Go) are
effectively unbounded at flat rate. We need an operating model that spends the scarce
resource only at leverage points and routes volume to the workforce.

## Decision
We adopt the AI-Dev-OS as described in `OPERATING_MANUAL.md`:
- **Routing:** `Leverage = BlastRadius × Irreversibility × SpecGap`. High-leverage work
  (contracts, schemas, security, ADRs, the review gate, hard bugs) stays with the Lead;
  everything specified + test-verifiable goes to the workforce (`AGENTS.md`).
- **Separation of powers (P8):** the model that writes a diff never grades it; the verifier
  is always a different model family. Enforced by `scripts/dispatch.sh` and `scripts/gate.sh`.
- **Spec-first:** the unit of work is a self-contained task spec (manual §6.6); a worker
  handed one spec needs nothing else.
- **Determinism layer:** dispatch, gate, ledger and rollback are scripts (`scripts/`), not
  model judgement. One task = one `--no-ff` merge = one-command rollback.
- **Model pins:** the exact model→role map lives in `AGENTS.md §1`. A version bump is a
  CHANGE → regression run + a new ADR.

## Consequences
- Coherence is owned in one place (`architecture/`) and on disk, not in any model's memory.
- Cost is bounded by Opus *attention*, tracked in `reports/metrics/ledger.csv`.
- The team progresses through the automation phases (manual §13) deliberately; we do not
  skip Phase 1 calibration.

## Alternatives considered
- One premium model does everything: blows the rate limit, no volume.
- Many cheap agents, no Lead: architectural drift and reward-hacking with no owner of coherence.
