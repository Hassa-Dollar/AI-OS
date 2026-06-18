# ADR-0008: Compress OPERATING_MANUAL.md (keep in repo, preserve anchors)

- **Status:** Accepted
- **Date:** 2026-06-16
- **Deciders:** Lead (Opus) + human operator

## Context
`OPERATING_MANUAL.md` was a ~1,290-line essay. It is referenced widely **by section number** ("manual §X")
from `CLAUDE.md`, `AGENTS.md`, several `scripts/`, the `prompts/`, the contracts, and the handoff — so removing
it (the original idea) would dangle all those pointers. Meanwhile the authoritative, live truth has moved into
the **ADRs + contracts + `AGENTS.md`/`CLAUDE.md` + the handoff**; the manual is now the "why"/doctrine layer.

## Decision
- **Keep `OPERATING_MANUAL.md`, compressed** (~1,290 → ~210 lines) — same job (the full-system doctrine
  reference), far less prose.
- **Preserve every referenced anchor** (§2.1, §5.6, §5.8, §6.6, §7.1, §8.2/8.3/8.5, §9.4/9.5, §10.1, §12.4,
  §13, §14, …) so all "manual §X" pointers keep resolving.
- Reflect the **current architecture** (components, profiles, the fixed 7-model catalog incl. GLM-5.2 + Kimi
  K2.7-Code, and the os-ci/product-ci split) and state that **the ADRs + contracts are the live authoritative
  layer — where the manual and an ADR differ, the ADR wins.**
- The manual remains the basis for the project's **future documentation page**.

## Consequences
- A cold reader gets the doctrine fast; every cross-reference stays valid; nothing dangles.
- The manual is cheaper to keep coherent (less prose to drift); the ADRs carry the load-bearing decisions.

## Alternatives considered
- **Remove it → external artifact (the original plan):** would dangle every "manual §X" reference across the
  repo. Rejected once the reference breadth was clear (keep + compress instead).
