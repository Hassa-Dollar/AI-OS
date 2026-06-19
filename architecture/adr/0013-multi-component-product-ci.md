# ADR-0013: Multi-component product-ci (matrix over components/*)

- **Status:** Accepted
- **Date:** 2026-06-18
- **Deciders:** Lead (Opus) + human operator

## Context
The CI split (ADR-0006) gave us OS-owned `os-ci` (shellcheck, secret-scan, component-isolation) and a
profile-owned `product-ci` that builds/tests the product. But the current `product-ci.yml` **hardcodes
`working-directory: components/service`** — it assumes exactly one component. Shrink has two (`api`, `web`),
and the system is meant to host any number. This is the one true *loop* gap for multi-component work
(identified in `sprint-plan.md` §8).

## Decision
- Rewrite `.github/workflows/product-ci.yml` to run a **matrix discovered from `components/*/`**. For each
  component directory that contains a `package.json`, CI runs `npm ci` then `npm run -s ci` **inside that
  component**, where each component's `package.json` defines a single `ci` script (lint + typecheck + test +
  coverage). A component without a `package.json` is skipped.
- The job is named `product`; matrix legs surface as `product (<component>)`. **Branch protection** requires
  the `product` matrix (all legs) plus `os` (unchanged).
- `product-ci.yml` becomes **OS-owned** again (it is generic over components); profiles no longer each ship
  a colliding `product-ci.yml`. A profile still owns its component's **`ci` script** (in the
  product-skeleton `package.json`) and its `ci-env.sh` — that is where stack-specific commands live.

## Consequences
- Any number of components is covered with no workflow edits; adding a component = adding a dir with a
  `package.json` that has a `ci` script.
- Reinforces extractability (ADR-0002): each component must build/test **independently** (its own
  `npm ci && npm run -s ci`), with no repo-root build.
- One-time branch-protection update when the matrix leg names settle (api, web).

## Alternatives considered
- **One `product-ci.yml` per profile** (e.g. `product-ci-api.yml`): filename/þjob collisions, and branch
  protection must be hand-edited per component. Rejected.
- **Keep hardcoding a component list** in the workflow: brittle; drifts from `components/`. Rejected in
  favor of discovery.
