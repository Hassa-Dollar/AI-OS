---
id: OS-G1
slug: eslint-component-boundary
owner_role: implementer
branch: task/OS-G1-eslint-component-boundary
blast_radius: low
files_allowed:
  - components/api/eslint.config.js
  - profiles/web-app/ts-hono-api/product-skeleton/eslint.config.js
  - profiles/web-app/react-vite/product-skeleton/eslint.config.js
  - profiles/web-app/ts-node-service/product-skeleton/eslint.config.js
depends_on_contracts:
  - architecture/contracts/os-component-boundary.md
deps_preapproved: []       # use eslint core rules already present — a plugin needs Lead pre-approval
---

# Goal
Component isolation (ADR-0002: no import may climb out of `components/<name>/`) is enforced by ESLint
inside product CI — mechanically, per component — instead of only by the gate's advisory grep.

# Context (compressed)
architecture/invariants.md labels the gate's `../`-grep **[advisory]**; this task adds the
**[mechanical]** layer. Use eslint core `no-restricted-imports` patterns (e.g. forbid `../../*` paths
that resolve outside the component root and any `components/*` cross-import) in the component's flat
config and mirror it into each profile's product-skeleton so future components inherit it. The gate's
grep stays as the repo-level tripwire.

# Acceptance criteria  (executable)
- [ ] `npm run lint` in components/api FAILS on a fixture import of `../../scripts/x` or
      `../web/src/y` (prove in the completion report, then remove the fixture).
- [ ] Legitimate intra-component relative imports still pass; current source lints clean.
- [ ] All three product-skeleton eslint configs carry the same rule block.

# Out of scope  (binding)
- No new eslint plugins/dependencies; no changes to gate.sh; no component src changes.

# Stop conditions
- Core rules can't express the boundary and a plugin (e.g. eslint-plugin-boundaries) is needed →
  STOP, escalate (dependency adoption is Lead-owned, ADR-0014).

# Working notes  (worker appends)
