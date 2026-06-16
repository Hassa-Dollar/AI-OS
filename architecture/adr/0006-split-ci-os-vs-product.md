# ADR-0006: Split CI into an OS workflow + a product workflow

- **Status:** Accepted
- **Date:** 2026-06-15
- **Deciders:** Lead (Opus) + human operator

## Context
CI lived in one profile-owned `.github/workflows/ci.yml` (copied by `profile.sh apply`) that mixed two
concerns: **universal OS checks** (shellcheck the determinism scripts, secret-scan, the one-way
component-isolation guard) and **product build/test** (the component's lint/typecheck/test/coverage). As
profiles multiply, the OS checks should be identical in every fork and not be re-derived or accidentally
weakened by each profile; and each project type needs freedom to shape its own product CI (a web service,
embedded firmware, and a data pipeline differ).

## Decision
Two workflows:

- **`.github/workflows/os-ci.yml` — OS-owned, universal.** Job `os`: shellcheck (`scripts/*.sh`,
  `bootstrap.sh`, `.githooks/pre-push`), secret-scan (gitleaks), and component-isolation across **every**
  `components/*/` (one-way rule, ADR-0002). Identical in every repo/fork; **`profile.sh` never touches
  it**; `bootstrap.sh` seeds it.
- **`.github/workflows/product-ci.yml` — profile-owned.** Job `product`: the component's build/test
  (currently `npm ci`/lint/typecheck/test/coverage in `components/service`). `profile.sh apply` copies it
  from `profiles/<family>/<variant>/product-ci.yml`; a profile fully defines its own product-CI shape.
- **Required status checks become `os` + `product`** (replacing the single `gate`). `gate.sh` (local) and
  `.githooks/pre-push` still mirror the checks for fast local feedback; pre-push gains a shellcheck step.
- shellcheck runs at `--severity=warning` (catches real footguns like `ls|grep`; ignores info-level noise
  such as SC1091 "can't follow sourced file").

## Consequences
- OS guarantees (script lint, secret scan, isolation) are uniform and tamper-resistant across profiles;
  profiles own their product CI and can diverge per stack without touching OS checks.
- **One-time migration (operator):** removing `ci.yml` changes the required check name, so branch
  protection must be re-pointed from `gate` to `os` + `product`. The introducing PR cannot auto-merge
  until that's done (its checks report as `os`/`product`, not `gate`) — merge it manually after updating
  protection.
- `family_of` / P8 and the rest of the pipeline are unaffected.

## Alternatives considered
- **One OS-owned `ci.yml` with `os` / `product` / `gate (needs both)` jobs:** keeps branch protection
  unchanged (still one `gate` check), but the product job's *shape* is fixed by the OS file (only commands
  vary via `ci-env.sh`) — too rigid once profiles diverge (matrix builds, services, hardware sims).
  Rejected in favour of full per-profile product-CI ownership.
