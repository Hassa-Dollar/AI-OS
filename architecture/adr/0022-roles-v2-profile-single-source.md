# ADR-0022: Roles v2 — the profile is the single source of role→model

- **Status:** Accepted
- **Date:** 2026-07-13
- **Deciders:** Lead + human operator

## Context
Model selection had two live sources of truth: task specs could pin `model:`/`verifier_model:` AND
profiles bound role→model, reconciled by `resolve_roles` inheritance. This produced BUG-27 (dispatch
inferred the wrong profile), BUG-30 (gate didn't inherit → P8 false-positives), coherence check 7 (a
police check for a problem the design created), and three mutually contradictory `_note` fields across
the profile.json files. Root cause: `resolve_roles` hard-coded `roles.implementer` and ignored the
spec's `owner_role` — so any task for the `autonomous` role HAD to pin a model, and pins kept creeping
back. Separately, the catalog (slugs + families) lived as a bash array + substring globs in `_lib.sh`.

## Decision
1. **The component's profile is the ONLY source of role→model.** A task spec names a role:
   `owner_role:` (default `implementer`); `resolve_roles` maps it via `profile.json` `roles[owner_role]`.
2. **The verifier is profile-bound and P8 is structural:** `roles.verifier`, falling to
   `roles.verifier_secondary` when the author's family would collide. Coherence check 8 lints every
   profile: all bindings on-catalog, and P8 solvable for every author role. Dispatch keeps the hard
   check as defense-in-depth.
3. **Overrides are audited exceptions:** `model_override:`/`verifier_override:` (legacy alias
   `model:`/`verifier_model:`) beat the profile only with `override_reason:`. Dispatch dies without the
   reason; coherence check 7 flags active specs; the gate adds a `model-override` risk flag so every
   override reaches the Lead.
4. **OS/chore specs are exempt:** no component → no profile → explicit `model:`+`verifier_model:`
   (P8 checked as before).
5. **The catalog becomes data:** `architecture/catalog.json` holds the fixed seven slugs + families —
   parsed by `_lib.sh` (exact match; superseded slugs are `unknown` and fail closed), mirrored by the
   AGENTS.md §1 table (coherence check 9). A version bump = edit catalog.json in the same commit as its ADR.

## Consequences
- A catalog/model bump is a one-line profile or catalog edit; zero spec edits; nothing drifts.
- The Lead plans in ROLE vocabulary (who-kind), not model bookkeeping — fewer scarce messages spent.
- Check 7 inverts from "flag redundant pins" to "flag unreasoned pins" — the simpler, stronger rule.
- The `family_of` substring globs are gone; off-catalog input fails closed everywhere.
- Supersedes the "a spec may override per task" clause of ADR-0003; everything else in ADR-0003 stands.

## Alternatives considered
- **Specs always pin; kill inheritance:** simplest scripts, but reverts the reason ADR-0003 exists —
  every catalog bump edits N specs and the Lead does model bookkeeping. Rejected.
- **Keep the hybrid + more checks:** the status quo that produced BUG-27/30 and check 7. Rejected.
