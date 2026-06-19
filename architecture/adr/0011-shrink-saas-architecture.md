# ADR-0011: "Shrink" SaaS architecture (the full hard run)

- **Status:** Accepted
- **Date:** 2026-06-18
- **Deciders:** Lead (Opus) + human operator

## Context
To exercise the whole workforce (all seven catalog models) end-to-end, we build a complete SaaS locally:
full UI, authentication, database, and real payments. The build must respect every existing invariant
(components/isolation ADR-0002, profiles/dynamic-roles ADR-0003, fixed catalog ADR-0005/0009, CI split
ADR-0006) so the run is a true test of the system, not a bypass of it. Full plan: `shrink-build-plan.md`.

## Decision
- **Product:** "Shrink", a URL shortener. Free tier = 10 links + redirects; Pro tier (Stripe subscription)
  = unlimited links + click analytics.
- **Two components (ADR-0002), contract-first:**
  - `components/api` — HTTP API (profile `web-app/ts-hono-api`, see ADR-0012).
  - `components/web` — React SPA (profile `web-app/react-vite`).
  - They **never import each other's source** (one-way isolation guard). They agree on
    `architecture/contracts/shrink-api.md` and talk over HTTP; data shapes live in
    `architecture/contracts/shrink-db-schema.md`.
- **Database:** SQLite (`better-sqlite3`) — zero-infra, file-based, fully local.
- **Payments:** real Stripe in **test mode** (test keys; `stripe listen` for local webhooks).
- **Testing:** hybrid — unit + integration (vitest) per component, plus one Playwright golden-path e2e
  (`e2e/`, which is OS-level test infra, not a component).
- **Cleanups:** name the components `api` / `web`; **retire the vestigial `components/service`** demo so
  the run is a clean two-component repo.

## Consequences
- The repo is now genuinely multi-component → forces the CI generalization in **ADR-0013**.
- The API contract is **Lead-owned**; any change to it is a risk-routed (FLAG/HUMAN) diff, never a worker's.
- Auth and payments work routes to the **HUMAN gate** (reviews/checklist.md) — never auto-merges.
- Secrets (Stripe/Better-Auth) stay in a gitignored `.env`; `gitleaks` (os-ci) enforces. `.env.example`
  is committed.

## Alternatives considered
- **Single fullstack component** (one dir, server + client): rejected — breaks component extractability +
  isolation, and doesn't exercise the multi-component loop (the whole point of the hard run).
- **Next.js monolith:** rejected — couples front/back, hides the API contract, and tests far less of the
  determinism layer (one build, one profile) than two independent components do.
