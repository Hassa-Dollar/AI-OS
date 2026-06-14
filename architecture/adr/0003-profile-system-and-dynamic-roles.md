# ADR-0003: Profile system & dynamic role binding

- **Status:** Accepted
- **Date:** 2026-06-13
- **Deciders:** Lead (Opus) + human operator

## Context
One forkable system must specialize per project type (web / embedded / data / …) **without** forking
a new system and **without** adding runtime complexity or tech-debt (the operator's explicit
constraint). Roles must not be fixed: a model must never be permanently "the frontend model" on an
embedded project that has no frontend. Coherence must hold when one project spans multiple stacks.

## Decision
- A **profile** is a reusable template directory `profiles/<family>/<variant>/` holding the files that
  vary by stack/domain: `conventions.md`, `invariants.md`, `ci-env.sh`, `ci.yml`, `product-skeleton/`,
  and `profile.json`.
- **`profile.json` carries the role→model bindings** and recommended risk thresholds:
  `{ name, description, roles: { implementer, verifier, researcher, … }, thresholds: { max_files, max_lines } }`.
  `roles` is a **flat dict**; a profile declares only the roles its domain needs.
- **Dynamic roles:** the global role→model table leaves `AGENTS.md §1`. That file keeps only the
  **model catalog** (what exists), the **role definitions**, and the **P8 rule**. The binding for a
  piece of work comes from the **active component's profile**. `dispatch.sh` resolves
  implementer/verifier from the component's profile (a spec may override) and **still enforces P8**
  (verifier family ≠ author family) regardless of where the pin came from.
- **Taxonomy:** two levels (`family/variant`); **each leaf is complete and self-contained.**
  **No `extends:` / merge / runtime composition.** Depth capped at 2. A `profiles/<family>/_shared/`
  of copy-at-authoring snippets may be added **only if** duplication later hurts.
- **Lifecycle:** a component's profile is recorded in its `.component.yml` and **locked for that
  component's life**. The Lead "shifts the system" by **routing the next task to a component**
  (selection ≠ mutation; no gate; smooth). Adding a component is **additive** (+ a light ADR).
  Changing an existing component's stack is a **migration → ADR + HUMAN-REQUIRED**. The system never
  changes a coherence boundary autonomously.
- **Application:** `scripts/profile.sh apply <family/variant> <component>` copies seam files to their
  canonical locations idempotently and records the choice in `.ai-os.yml`; `bootstrap.sh --profile
  <family/variant>` runs it after seeding the neutral core. **Scripts never branch on a profile or
  component name** — they read canonical files + `profile.json`.
- Ship **one** profile leaf now: `web-app/ts-node-service` = today's TS / `node:http` config, extracted.
  Other leaves are documented ("copy a sibling, swap ~5 files"), not built.

## Consequences
- Specialization = adding a directory; the runtime stays boring — the property that keeps this debt-free.
- Roles exist only where a domain needs them; no idle "frontend model" on an embedded build.
- `AGENTS.md` shrinks to the universal spine; bindings are per profile and diffable.
- The current TS/Node coding conventions (AGENTS.md §4) and stack invariants migrate into the
  `web-app/ts-node-service` profile during execution (T-E).

## Alternatives considered
- **Runtime composition / `extends:` inheritance:** powerful but reintroduces "which layer set this?"
  and logic-in-scripts. Rejected as overengineering for a solo operator.
- **Keep pins in a single global `AGENTS.md` table:** forces a fixed roster, contradicting dynamic
  roles. Rejected.
