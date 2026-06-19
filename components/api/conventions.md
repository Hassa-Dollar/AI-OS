# Coding conventions — web-app/ts-hono-api  (profile-provided; ADR-0003/0012)

> `profile.sh apply` copies this to `components/<name>/conventions.md` (the per-component path its workers
> read, ADR-0013). OS-level invariants are separate (`architecture/invariants.md`) and hold regardless of profile.

## Stack & tooling
- Language/runtime: **TypeScript 5.x on Node 22 LTS**, ESM, `tsconfig` `strict: true` (never relaxed).
- Web layer: **Hono** + `@hono/node-server`. Routing/middleware via Hono; no Express/Fastify.
- Auth: **Better Auth** (email+password + sessions). Do **not** hand-roll hashing, sessions, or CSRF —
  use the library. Auth changes are HUMAN-gated (reviews/checklist.md).
- DB: **better-sqlite3** (synchronous). All SQL **parameterized** (never string-interpolate input).
  Schema + migrations follow `architecture/contracts/shrink-db-schema.md` (versioned, idempotent runner).
- Validation: **zod** at every request boundary; reject with the contract's `INVALID_INPUT` error.
- Payments: **stripe** SDK; webhook verifies the raw body against `STRIPE_WEBHOOK_SECRET`.
- Lint/format: `npm run -s lint` (ESLint + `@typescript-eslint`); never hand-format; an inline
  `// eslint-disable` is an `ESCALATE`, not a fix.
- Tests: `npm run -s test` (Vitest); integration tests run the app in-process against a **temp SQLite
  file** and stub Stripe's network. New code requires tests; **diff coverage ≥ 90%** (`npm run -s coverage`).
- Types: `npm run -s typecheck` (`tsc --noEmit`) must pass; no `any`, no non-null `!` without a `// reason:`.

## Rules
- Implement to `architecture/contracts/shrink-api.md` exactly (paths, shapes, status codes, the error model).
- Secrets only from `process.env`; never log, echo, or commit a secret. If a task needs one not present →
  `ESCALATE`.
- Never store a raw client IP — store a **salted hash** (PII).
- Fail loud in dev; handle at the boundary in prod; never swallow exceptions.
- Every component is independently buildable: `npm ci && npm run -s ci` from inside `components/api`
  (the `ci` script = lint + typecheck + test + coverage). No repo-root build (extractability, ADR-0002).
