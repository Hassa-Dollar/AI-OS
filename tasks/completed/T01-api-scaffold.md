---
id: "T01"
slug: api-scaffold
owner_role: implementer
model: opencode-go/glm-5.2
verifier_model: opencode-go/deepseek-v4-pro   # P8: zhipu author != deepseek verifier
branch: task/T01-api-scaffold
blast_radius: low
files_allowed:
  - components/api/package.json
  - components/api/package-lock.json
  - components/api/tsconfig.json
  - components/api/eslint.config.js
  - components/api/vitest.config.ts
  - components/api/.gitignore
  - components/api/src/app.ts
  - components/api/src/server.ts
  - components/api/src/app.test.ts
depends_on_contracts:
  - architecture/contracts/shrink-api.md
deps_preapproved:
  - hono
  - "@hono/node-server"
---

# Goal
Scaffold the `components/api` Hono service for Shrink: TypeScript on Node 22 (ESM, `strict`), Vitest, ESLint,
an `npm run -s ci` script (lint -> typecheck -> test -> coverage), and exactly ONE route —
`GET /healthz` -> `200 {"status":"ok"}` — with a passing test. This is the foundation every later API task
(T02-T08) builds on. Nothing more.

# Context (compressed)
- Profile `web-app/ts-hono-api` governs this component; its rules live in `components/api/conventions.md`
  (TS `strict`, Hono + `@hono/node-server`, ESM, secrets only from env later). Read it first.
- The component is **independently buildable**: `npm ci && npm run -s ci` from INSIDE `components/api` — no
  repo-root build (extractability, ADR-0002). Product CI runs exactly that per component on Node 22.
- HTTP contract: `architecture/contracts/shrink-api.md`. For THIS task ONLY `GET /healthz` ->
  `200 { status: "ok" }` applies. Do not implement any other endpoint.
- Gate commands (profile `ci-env.sh`): `lint`/`typecheck`/`test`/`coverage` are each `npm run -s <name>`;
  provide all four, a `ci` script that runs them in order, and a `dev` script.
- **Split app from server** so tests need no open port: `src/app.ts` exports the Hono `app`; `src/server.ts`
  is the runtime entrypoint that `serve()`s it via `@hono/node-server`. Tests import `app`, never `server`.

# Acceptance criteria (executable)
- [ ] `package.json`: `"type": "module"`; scripts `lint`, `typecheck` (`tsc --noEmit`), `test`
      (`vitest run`), `coverage` (`vitest run --coverage`), `ci` (= lint -> typecheck -> test -> coverage),
      `dev` (run `src/server.ts`, e.g. via `tsx`). Runtime `dependencies` EXACTLY `hono` +
      `@hono/node-server`; everything else is `devDependencies` (typescript, vitest, @vitest/coverage-v8,
      eslint, typescript-eslint, @types/node, tsx).
- [ ] A committed `package-lock.json` exists (so `npm ci` works in CI).
- [ ] `tsconfig.json`: `strict: true`, ESM (`module`/`moduleResolution` = `NodeNext`), `target` ES2022,
      no `any`, no unused.
- [ ] `npm ci && npm run -s ci` succeeds from inside `components/api`: ESLint clean, `tsc --noEmit` clean,
      tests pass, coverage threshold met.
- [ ] `GET /healthz` returns HTTP `200` with body exactly `{"status":"ok"}`, asserted in `src/app.test.ts`
      via Hono's `app.request('/healthz')` (no network, no port bind).
- [ ] `vitest.config.ts`: coverage provider `v8`, threshold **90** (lines/functions/branches/statements),
      `include: ['src/**']`, **`exclude: ['src/server.ts']`** (runtime bootstrap has no testable logic).
- [ ] `src/server.ts` imports the app and starts `@hono/node-server` reading `PORT` (default `8787`);
      it typechecks and is imported by no test.
- [ ] `npm audit --omit=dev --audit-level=high` is clean (no high/critical runtime advisories).

# Out of scope (binding — no gold-plating)
- No DB / better-sqlite3 (T02), no Better Auth (T03), no links/redirect/analytics (T04-T06), no Stripe
  (T07-T08), no other routes, no CORS or middleware beyond what `/healthz` needs.
- No runtime dependency other than `hono` + `@hono/node-server`. No env reading beyond `PORT`.
- Do NOT touch any file outside `files_allowed`. The OS-owned inventory regenerates itself — not your job.

# Stop conditions (emit `ESCALATE: <reason>` and halt — do not guess)
- `shrink-api.md` looks wrong or needs a change -> ESCALATE (contracts are Lead-owned).
- A tool/config genuinely needs a file not in `files_allowed` -> ESCALATE (do not create it).
- A needed runtime dependency is not in `deps_preapproved` -> ESCALATE (do not add it).

# Working notes (worker appends)
