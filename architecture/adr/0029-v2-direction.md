# ADR-0029: AI-OS v2 — one gateway key, local router, target repos, stdlib-Python core

- **Status:** Accepted
- **Date:** 2026-10-21
- **Deciders:** Lead + human operator

## Context
v1 (tag `v1-final`) proved the doctrine: spec-first work, cross-family verification and risk-routed review. Its
mechanics did not hold up:
- **Fixed catalog.** The workforce was a fixed 7-model OpenCode-Go catalog (ADR-0005/0009). Every new model needed an
  ADR and hand edits, and the subscription has since been cancelled.
- **Bash plumbing.** About 2.1K lines of bash carried 28 of the 30 recorded bugs, and ~75 of 88 PRs were OS plumbing
  rather than product (ADR-0024).
- **Lost history.** The ledger and the memory DB were machine-local; they are gone.
- **Product in a public repo.** The product (Shrink) lived inside this public repo.

The operator wants three things:
1. one API key that reaches every current model and picks up new releases automatically;
2. a local model that sends each task to the cheapest model able to do it;
3. any kind of software (web through embedded) built in its own repo.

## Decision
We will rebuild AI-OS around five choices:
1. **Gateway.** OpenRouter, with one key stored at `~/.config/aios/credentials` (mode 0600, with a per-key credit
   limit), behind a thin OpenAI-compatible adapter. The frontier ("Lead") tier uses the same key. Automatic frontier
   use is off by default and capped.
2. **Routing.** A local decision model (Clef, via Ollama's System One API) classifies each task. A deterministic
   decision table then picks a model from a curated roster (ADR-0031).
3. **Products live in target repos.** AI-OS becomes a tool pointed at any repo. Per-project state lives in that repo's
   `.aios/` (ADR-0030).
4. **Core.** Python ≥3.11, standard library only at runtime. This amends ADR-0023's floor from 3.10 to 3.11, for
   `tomllib`. The worker harness is an external, pinned, sandboxed tool, chosen by measurement (ADR-0032).
5. **Budget in dollars.** Cost per merged task replaces v1's Lead-message budget, and the per-key credit limit is the
   hard backstop. The code budget stays explicit: `aios/` ≤ 1,600 lines for the walking skeleton and ≤ 3,200 for v2.0,
   enforced in CI. Raising either needs an ADR.

### Effect on earlier ADRs
| ADR | v2 status |
|---|---|
| 0005 fixed catalog · 0007 GLM bump | **Superseded** by this ADR: the roster replaces the catalog |
| 0011 · 0012 (Shrink) | **Moved** to the private Shrink repo |
| 0003 profiles | **Amended:** profiles declare checks and requirements, not role→model bindings |
| 0009 catalog enforcement | **Amended:** the fail-closed allowlist is now the roster (ADR-0031); verdict parsing stays fail-closed |
| 0013 · 0014 | **Amended:** checks and security guards are declared by the profile, not npm-only |
| 0016 · 0019 · 0021 memory | **Amended:** durable memory is the committed per-task records and lessons (ADR-0030); local DBs are caches |
| 0018 coherence | **Amended:** no generated files are committed; summaries are computed when read |
| 0022 roles v2 | **Amended:** the router's recorded decision replaces profile bindings; the one-resolver rule stays |
| 0023 Python port | **Amended:** Python ≥3.11, and a rewrite rather than a 1:1 port |
| 0027 worktrees | **Amended:** implemented by the v2 core |
| 0001 0002 0004 0006 0008 0010 0015 0017 0020 0024 0025 0026 0028 | Unchanged in principle |

## Consequences
- **Easier.** A new model can be used the day it ships: admitting it is one roster line plus a probe. There's no
  subscription lock-in, products can be private, and the core is a single language.
- **Harder.** Per-token pricing replaces a flat fee, so spend must be measured per task. We now depend on OpenRouter
  being available; the adapter keeps it swappable.
- **New invariants.** No secret ever enters a repo or a worker's environment. Every model call goes through the gateway
  adapter with the project's privacy policy applied.

## Alternatives considered
- **Patch v1** (swap slugs, keep bash). This keeps the defect-dense layer and the product-in-the-tool-repo model.
- **A flat-rate subscription** for one model family. Cheaper per task, but it fails "every model, one key".
