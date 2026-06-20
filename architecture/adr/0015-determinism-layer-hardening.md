# ADR-0015: Determinism-layer hardening + bug procedure + a test harness

- **Status:** Accepted
- **Date:** 2026-06-20
- **Deciders:** Lead (Opus) + human operator

## Context
The first real build run (Shrink T01) surfaced several bugs in the OS scripts, because the determinism
layer had **no automated tests** — so every edge case detonated in a live run and got patched reactively,
which accretes instability. Full analysis + the **living registry**:
`knowledge/postmortems/determinism-layer-hardening.md`.

## Decision
1. **Bug procedure (doctrine).** Every harness bug is root-caused (not symptom-patched), fixed at the root
   with any prior patch reverted, given a **regression test**, and recorded in the registry. A temporary
   patch is allowed to keep momentum **only if it is logged in the registry**.
2. **Root-cause fixes** for the registry's bugs (BUG-01…10), landed in reviewed batches.
3. **A test harness** (`bats`) for the determinism layer, run in os-ci, with a regression test per bug —
   the keystone that stops silent regression.
4. **Concise docs.** The registry is the single source of truth and stays short; ADRs record decisions, not
   detail.

## Consequences
- The OS scripts become testable and tested; bugs can't silently recur.
- One correct mechanism per fix (no patch + root-fix coexisting).
- Slower than reactive patching now; far cheaper than compounding instability later.

## Alternatives considered
- **Keep patching reactively:** rejected — that is the tech-debt path this ADR exists to stop.
