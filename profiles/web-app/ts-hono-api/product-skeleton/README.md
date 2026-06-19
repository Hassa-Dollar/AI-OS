# components/api — Shrink HTTP API

Back-end for Shrink (URL shortener SaaS). **Profile:** `web-app/ts-hono-api`.

**Stack:** Hono (`@hono/node-server`) · Better Auth · better-sqlite3 · Stripe · zod · Vitest.

**Implements:** `architecture/contracts/shrink-api.md` against `architecture/contracts/shrink-db-schema.md`.

This skeleton is intentionally minimal. **Task T01** scaffolds the real component: `package.json` (with the
`ci` script = lint + typecheck + test + coverage), `tsconfig` (strict), ESLint, Vitest, and the Hono server
with `GET /healthz`. Subsequent tasks add the DB layer (T02), auth (T03), links/redirect/analytics
(T04–T06), and Stripe billing + webhook (T07–T08).

Run locally (after T01): `npm ci && npm run -s ci` then `npm run dev`.
