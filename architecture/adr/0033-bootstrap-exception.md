# ADR-0033: Bounded bootstrap exception — the Lead builds the walking skeleton

- **Status:** Accepted
- **Date:** 2026-10-21
- **Deciders:** Lead + human operator

## Context
The doctrine keeps the Lead away from bulk implementation (P1). The v2 pipeline that would dispatch work to the
workforce doesn't exist yet. Waiting for it would be circular.

## Decision
The Lead implements the walking skeleton directly:

| Task | Scope |
|---|---|
| W1 | cli · config · spec · git · doctor · init |
| W2 | gateway · catalog · roster |
| W3 | router |
| W4 | harness adapter · dispatch |

The skeleton is capped at ≤ 1,600 lines of `aios/`, enforced in CI. Where a harness bake-off produces a passing
implementation of a skeleton module, the Lead reviews and merges that implementation instead of writing its own.
AI-1 (`aios/spec.py`) is the first case.

From D1 (gate and records) onward, every task is dispatched through `aios` itself. The Lead returns to writing specs,
contracts and review.

## Consequences
- **Gain:** the system becomes self-hosting after four bounded tasks.
- **Cost:** a known, one-time expense in Lead effort.
- **Expiry:** the exception lapses once W4 lands. Any further direct Lead implementation needs a new ADR.

## Alternatives considered
- **Hand-run each skeleton spec through a harness.** Slower and needs more review rounds. It is used opportunistically
  (AI-1) rather than as the rule.
