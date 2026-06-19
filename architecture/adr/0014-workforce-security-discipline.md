# ADR-0014: Security discipline for the workforce (enforced before the build)

- **Status:** Accepted
- **Date:** 2026-06-18
- **Deciders:** Lead (Opus) + human operator

## Context
Before the seven models build a real SaaS (auth, payments, a public surface), we want security to be
*enforced*, not merely requested — so we can see whether the workforce respects it and catch a serious
mistake early. The repo is public (CLAUDE.md §8): a hostile reader can clone/fork. `gitleaks` already proved
its worth in os-ci (it caught a false-positive on a doc, exactly the mechanism working). This ADR adds
machine-enforced guardrails on the workforce's *output*.

## Decision
Enforce, at the point shown:

1. **Dependency allowlist (`gate.sh`).** A task may ADD a runtime dependency only if it is in the spec's
   `deps_preapproved`. The gate diffs `package.json` runtime `dependencies` (branch vs `main`) and fails on
   any newly-added package not pre-approved. (devDependencies/tooling are conventionally trusted and still
   covered by SCA below.)
2. **No dynamic execution (`gate.sh`).** `eval`, `new Function`, and `child_process` are banned in component
   source; the gate greps `components/<name>/src` and fails on a hit. A genuine need is an `ESCALATE` + ADR.
3. **Secret-in-spec guard (`dispatch.sh`).** Before a spec is sent to a worker (and committed to a public
   repo), dispatch scans it for credential patterns (Stripe/AWS/GitHub tokens, private-key headers,
   `keyword=<high-entropy>`); a hit is a hard stop. Specs reference env-var *names*, never values.
4. **Dependency audit / SCA (`product-ci`).** Each component build runs `npm audit --audit-level=high`;
   a high/critical advisory fails the build.
5. **Verifier security is blocking (`code-review.md`).** Any security finding (injection, broken authz/
   ownership, secret exposure, unvalidated trust-boundary input, dangerous API, unapproved dep) forces
   `RISK: high` / `VERDICT: fail`.
6. **Profile conventions** state these rules so workers see them in-context.

Auth, payments, secrets, and PII remain HUMAN-REQUIRED hard stops (reviews/checklist.md) on top of the above.

## Consequences
- A worker cannot silently add a runtime dependency, use `eval`/`child_process`, or have a secret routed
  through it; the gate/dispatch reject these with actionable what/cause/try messages.
- The hard-run doubles as a test of whether the models respect *enforced* security discipline.
- `npm audit` may occasionally block on a transitive advisory — that is the intended signal; the Lead
  decides (bump, replace, or accept via an ADR). Tunable to `--audit-level=critical` if too noisy.

## Deferred (recommended next)
- **Pin GitHub Actions by commit SHA** (supply-chain): `actions/checkout`, `actions/setup-node`,
  `gitleaks/gitleaks-action` are still `@vN` tags. Pinning needs the exact SHAs; do it as a focused follow-up.

## Alternatives considered
- **Document-only (rely on AGENTS.md §3/§4):** rejected — unenforced rules are exactly what we want to test
  *and* not depend on; the gate makes them real.
- **Gate ALL deps incl. devDependencies:** rejected — flags standard tooling (vitest/eslint/tsc) and creates
  noise; runtime deps are the real supply-chain surface, and SCA covers the rest.
