# ADR-0007: Bump GLM-5.1 → GLM-5.2

- **Status:** Accepted
- **Date:** 2026-06-16
- **Deciders:** Lead (Opus) + human operator

## Context
Zhipu shipped **GLM-5.2**, superseding GLM-5.1 (the default implementer). Per Failure Mode #3 (§14) and the
fixed-catalog policy (ADR-0005), a model version bump is a CHANGE — recorded here, applied across the
catalog, with a regression window — never a silent swap.

## Decision
- **GLM-5.1 → GLM-5.2**: slug `opencode-go/glm-5.1` → `opencode-go/glm-5.2`; display "GLM-5.2". This
  updates the GLM row of the fixed catalog (ADR-0005 / `AGENTS.md §1`); the set stays **seven** — no model
  added or removed.
- It keeps its role (default implementer). `family_of()` still maps `*glm*` → `zhipu`, so **P8 is
  unaffected**. Treat the first sprint on GLM-5.2 as a regression window (watch first-pass-QA + escaped
  defects in the ledger).
- Applied **everywhere** by operator choice, including historical task records — consistent with the Kimi
  K2.7-code rename (ADR-0005).

## Consequences
- The default implementer is GLM-5.2 across every profile that binds it.
- No structural change; family / P8 / dispatch logic untouched.

## Alternatives considered
- **Pin GLM-5.1 indefinitely:** forgoes upstream gains; rejected. Version bumps are normal and done
  deliberately (ADR + regression), not avoided.
