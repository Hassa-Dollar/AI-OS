---
id: "T03"
slug: better-auth
owner_role: implementer
branch: task/T03-better-auth
blast_radius: high
files_allowed:
  - components/api/package.json
  - components/api/package-lock.json
  - components/api/src/auth.ts
  - components/api/src/app.ts
  - components/api/src/auth.test.ts
  - .env.example
depends_on_contracts:
  - architecture/contracts/shrink-api.md
  - architecture/contracts/shrink-db-schema.md
deps_preapproved:
  - better-auth
---

# Goal
Add authentication to `components/api` with **Better Auth** (email+password + sessions) on the same
better-sqlite3 database, mounted in the Hono app, and expose the one auth wrapper the contract defines:
`GET /api/me`. Better Auth owns the `user`/`session`/`account`/`verification` tables (its own schema); the
T02 migrations own `link`/`click`/`subscription`. CORS allows the web origin with credentials. Nothing else.

# Context (compressed)
- Profile `web-app/ts-hono-api` (`components/api/conventions.md`): TS `strict`, ESM `NodeNext`, secrets only
  from env. T01/T02 exist: Hono `app` (`src/app.ts`, `GET /healthz`), `openDb()` (`src/db/open.ts`: WAL +
  `foreign_keys`, runs our migrations), `repo` (`src/db/repo.ts` incl. `getPlan(db, user_id): 'free'|'pro'`).
- **Contract `shrink-api.md`:** Better Auth owns `/api/auth/*` (signup/login/logout/session) — do NOT
  re-implement; treat its sub-paths as its documented surface. Our only wrapper:
  `GET /api/me` (session) → `200 { user: { id, email }, plan: "free"|"pro" }`; no session → `401`
  `{ error: { code: "UNAUTHENTICATED", message } }` (contract error model). Plan via `getPlan()` (T02).
  CORS allows the web dev origin `http://localhost:5173` **with credentials**.
- **Contract `shrink-db-schema.md`:** Better Auth tables are created by Better Auth's own init (this task);
  our app tables already exist and use a **logical** `user_id` (no hard FK), so schema ordering is independent.
- **Better Auth v1.6.x — API verified via Context7 (use exactly this shape):**
  ```ts
  // src/auth.ts
  import { betterAuth } from "better-auth";
  import Database from "better-sqlite3";
  export const auth = betterAuth({
    database: new Database(process.env.DATABASE_PATH ?? "shrink.db"), // SAME file openDb uses
    emailAndPassword: { enabled: true },
    secret: process.env.BETTER_AUTH_SECRET,            // from env — NEVER hardcode (ADR-0014 / §8)
    baseURL: process.env.BETTER_AUTH_URL ?? "http://localhost:8787",
  });
  ```
  ```ts
  // src/app.ts — CORS + mount + session wrapper
  import { cors } from "hono/cors";
  import { auth } from "./auth.js";
  app.use("/api/auth/*", cors({ origin: "http://localhost:5173", credentials: true,
    allowHeaders: ["Content-Type","Authorization"], allowMethods: ["POST","GET","OPTIONS"] }));
  app.on(["POST","GET"], "/api/auth/*", (c) => auth.handler(c.req.raw));
  // GET /api/me:
  const session = await auth.api.getSession({ headers: c.req.raw.headers });
  // no session → 401 UNAUTHENTICATED; else 200 { user: { id, email }, plan: getPlan(db, session.user.id) }
  ```
  - Better Auth email routes (for the test): `POST /api/auth/sign-up/email { name, email, password }`,
    `POST /api/auth/sign-in/email { email, password }`; the session is a cookie on the response.
  - Better Auth opens its OWN connection to `DATABASE_PATH` (separate handle, same file as `openDb` — fine
    under WAL; different tables).
- **Schema setup (the one mechanical risk):** Better Auth's tables must exist on `DATABASE_PATH` so
  `npm ci && npm run -s ci` is green with **no network/interactive step**. Establish them deterministically
  (e.g. an `auth:migrate` script via the Better Auth CLI run in test setup against a temp DB, or generate +
  apply its SQL). **You choose the method — green CI is the forcing function.** If it cannot be made
  deterministic in CI, `ESCALATE` rather than guess.

# Acceptance criteria (executable)
- [ ] `package.json`: add `better-auth` to runtime `dependencies` (only new runtime dep); lockfile updated.
- [ ] `npm ci && npm run -s ci` green from inside `components/api`: eslint clean (no `any`), `tsc --noEmit`
      clean, tests pass, coverage ≥ **90** on `src/**` (excluding `src/server.ts`), `npm audit --omit=dev
      --audit-level=high` clean.
- [ ] `src/auth.ts` exports a configured `auth` (`betterAuth`): email+password enabled; `secret` + `baseURL`
      from env; `database` = better-sqlite3 on `process.env.DATABASE_PATH` (the SAME file `openDb` uses).
- [ ] `src/app.ts`: CORS on `/api/auth/*` (origin `http://localhost:5173`, `credentials: true`); Better
      Auth handler mounted via `app.on(["POST","GET"], "/api/auth/*", c => auth.handler(c.req.raw))`;
      `GET /healthz` unchanged.
- [ ] `GET /api/me`: valid session → `200 { user: { id, email }, plan }` (plan via `getPlan`); no session →
      `401 { error: { code: "UNAUTHENTICATED", message } }`.
- [ ] `DATABASE_PATH` is the single DB-file source for BOTH `openDb` and Better Auth; `.env.example`
      documents `DATABASE_PATH`, `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL`. No DB file is opened anywhere
      except `DATABASE_PATH` (no silent relative default in the running server path).
- [ ] `src/auth.test.ts` (temp-file DB via `DATABASE_PATH`, both schemas migrated, a test
      `BETTER_AUTH_SECRET` set): sign-up then sign-in via the Better Auth routes establishes a session;
      `GET /api/me` with that session → `200` + correct `user` + `plan: "free"`; after
      `upsertSubscription(status:"active")` for that user → `/api/me` `plan: "pro"`; `GET /api/me` with no
      session → `401`. (Use `app.request`; carry the session cookie between calls.)

# Out of scope (binding — no gold-plating)
- No `/api/links`, redirect, or analytics (T04–T06); no Stripe (T07–T08); no web UI.
- No auth methods beyond email+password (no social / magic-link / passkey / 2FA).
- No changes to the `link`/`click`/`subscription` migrations (T02 owns them).
- No runtime dependency other than `better-auth`. NEVER hardcode a secret. Touch only `files_allowed`.

# Stop conditions (emit `ESCALATE: <reason>` and halt — do not guess)
- Better Auth's current API differs from the snippets above in a way that changes the contract surface.
- Its schema can't be established deterministically for `npm run -s ci` without a network/interactive step.
- `shrink-api.md` looks wrong/insufficient for `/api/me` or `/api/auth/*`.
- A runtime dependency beyond `better-auth` is genuinely required.

# Working notes (worker appends)

## Decisions (glm-5.2, T03)

- **Schema init method (the one mechanical risk):** Better Auth does NOT auto-create
  `user`/`session`/`account`/`verification` on `betterAuth()` init, and `@better-auth/cli`
  is a separate, unpreapproved, interactive package. Deterministic, network-free, non-interactive
  path found: the **public** export `better-auth/db/migration` → `getMigrations(config)` with
  `.runMigrations()` (and `.compileMigrations()` for the raw SQL). `auth.ts` exports
  `migrateAuthSchema()` that opens a *dedicated* better-sqlite3 handle to `DATABASE_PATH`
  (WAL + `foreign_keys`), runs `getMigrations(authOptions(db)).runMigrations()`, and closes it.
  Idempotent (diffs existing schema; no-op when tables exist). Green CI confirmed.
- **`trustedOrigins` is required (deviation-from-snippet, in-scope):** Better Auth enforces a
  CSRF/origin check **separate from CORS**. Only `baseURL` (`http://localhost:8787`) is
  auto-trusted; the web origin `http://localhost:5173` is rejected with `403 INVALID_ORIGIN`
  on credentialed POSTs unless added to `trustedOrigins`. Without it the web app cannot auth
  (contract: "the web app uses the Better Auth client against these"). Added
  `trustedOrigins: ["http://localhost:5173"]` to the `betterAuth` options. Does not change the
  contract surface. Tests send `Origin: http://localhost:5173` on sign-up/sign-in.
- **`auth` is lazy via `getAuth()` (deviation from `export const auth` snippet):** the snippet's
  `export const auth = betterAuth({ database: new Database(process.env.DATABASE_PATH ?? "shrink.db") })`
  conflicts with two executable criteria: (a) "no silent relative default in the running server
  path" / "No DB file is opened anywhere except DATABASE_PATH", and (b) the existing, unmodifiable
  `app.test.ts` imports `app` with `DATABASE_PATH` *unset* (eager init would either crash on a
  missing-path throw or silently open a `shrink.db`/in-memory fallback). `getAuth()` is a
  per-`DATABASE_PATH`-cached singleton that **throws** `DATABASE_PATH is required` if the var is
  missing (fail-loud, §4) and opens nothing at import time. `app.ts` uses `getAuth().handler` /
  `getAuth().api.getSession`. Behavioral contract (routes + shapes) is unchanged; covered by a
  dedicated test asserting `getAuth()` throws when `DATABASE_PATH` is unset.
- **`/api/me` plan lookup** uses `getPlan(db, session.user.id)` (T02) via a lazily-cached
  `openDb()` handle in `app.ts` (`getDb()`); only reached after a session exists (so
  `DATABASE_PATH` is set), never on the no-session 401 path.
- **`.env.example`** already documents `DATABASE_PATH`, `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL`
  (plus `WEB_ORIGIN`); no change required.
- **Install:** `npm install better-auth@^1.6.0 --legacy-peer-deps` (npm auto-installs the optional
  `@tanstack/react-start` peer whose `vite@>=7` conflicts with vitest's `vite@5`); `npm ci`
  reproduces the lockfile cleanly **without** the flag. Pinned `^1.6.0` (resolves 1.6.23).
  `npm audit --omit=dev --audit-level=high` clean (the 6 audit findings are all dev-deps).
- **Server-startup auth migration is NOT wired here** (`server.ts` is outside `files_allowed`).
  `migrateAuthSchema()` is exported for explicit use (test setup now; a dev `auth:migrate` step
  or `server.ts` wiring is a follow-up). Acceptance criteria are met by test-setup migration.
- **Bug BUG-22** logged (schema-init method + trustedOrigins + install note) for reuse.
- `npm ci && npm run -s ci` green from scratch: lint clean, `tsc --noEmit` clean, 21 tests pass,
  coverage 100/95.65/100/100 (≥90), `npm audit --omit=dev --audit-level=high` 0.

