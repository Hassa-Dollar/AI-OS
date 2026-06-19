# ADR-0012: Adopt Hono + Better Auth for the API profile

- **Status:** Accepted
- **Date:** 2026-06-18
- **Deciders:** Lead (Opus) + human operator

## Context
Shrink needs authentication. The operator's directive: prefer a bulletproof, self-hosted library that
needs **no online account** and **few dependencies** over hand-rolling auth. Two facts shaped the call:
- **Lucia is deprecated** (since ~2025) — it is now a "learn to roll your own sessions" resource, i.e. it
  pushes you *toward* hand-rolling, which we explicitly want to avoid.
- **Better Auth** is the current standard: framework-agnostic TypeScript, auth lives in *your* DB with no
  third-party service, MIT, widely adopted (recommended by Next.js/Nuxt/Astro). It handles password
  hashing, sessions, CSRF, etc. internally.

Better Auth wants a web-standard `Request`/`Response` handler. The existing `web-app/ts-node-service`
profile mandates raw `node:http` with **no framework**, which makes mounting Better Auth (and the Stripe
webhook raw-body handling, routing, middleware) awkward and glue-heavy.

## Decision
- Create a **new profile** `web-app/ts-hono-api` for `components/api`, built on **Hono** (+
  `@hono/node-server`) as the web layer and **Better Auth** for auth, with `better-sqlite3` (DB), `stripe`
  (payments), and `zod` (input validation).
- **Do not touch** `web-app/ts-node-service` — the minimal no-framework profile stays valid for back-ends
  that want it. This deviation is isolated to the new profile (profiles are self-contained, ADR-0003).
- Auth remains a **HUMAN-gated** concern even though a library implements it — the integration diff is
  reviewed at the gate (reviews/checklist.md).

## Consequences
- Backend direct deps: `hono`, `@hono/node-server`, `better-auth`, `better-sqlite3`, `stripe`, `zod` — a
  small, vetted set; far less risk/code than hand-rolled auth.
- Clean routing, middleware, and webhook raw-body access; Better Auth manages its own tables (schema in
  `shrink-db-schema.md`).
- A second back-end stack now exists in the catalog of profiles; the catalog of **models** is unchanged
  (ADR-0005/0009 still hold — profiles bind roles, never add models).

## Alternatives considered
- **Raw `node:http` + a Better Auth node adapter:** avoids Hono but is more custom glue (ironically more
  "scratch") and worse for webhooks/routing.
- **Hand-rolled `node:crypto` (scrypt + signed-cookie sessions):** rejected per the operator's preference
  for a vetted library + the security surface.
- **Express / Fastify:** heavier and more dated than Hono for a small web-standard API; Hono integrates
  with Better Auth's web-standard handler directly.
