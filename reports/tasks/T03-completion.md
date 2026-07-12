# T03 — better-auth (completion report)

- **Task:** T03 / `better-auth`
- **Branch:** `task/T03-better-auth`
- **Model:** opencode-go/glm-5.2 (implementer)
- **Verifier:** (pending QA / cross-family gate)
- **Status:** DONE — all acceptance criteria met; `npm ci && npm run -s ci` green from scratch.
- **Date:** 2026-07-02

## What was built
Email+password authentication with sessions on the same better-sqlite3 database, mounted in the Hono app, exposing the contract's single auth wrapper `GET /api/me`. Inside `components/api`:

- **`src/auth.ts`** (new):
  - `getAuth()` — lazy, per-`DATABASE_PATH`-cached singleton returning a configured `betterAuth` instance: `emailAndPassword.enabled`, `secret` + `baseURL` from env, `database` = `new Database(DATABASE_PATH)`, `trustedOrigins: ["http://localhost:5173"]`. **Throws** `DATABASE_PATH is required` if the var is missing (fail-loud; no silent DB fallback).
  - `migrateAuthSchema()` — deterministic, network-free, non-interactive schema init: opens a dedicated better-sqlite3 handle to `DATABASE_PATH` (WAL + `foreign_keys`), calls `getMigrations(authOptions(db)).runMigrations()` (the public `better-auth/db/migration` export), then closes the handle. Idempotent.
- **`src/app.ts`** (modified): CORS on `/api/auth/*` (origin `http://localhost:5173`, `credentials: true`, headers/methods per snippet); Better Auth mounted via `app.on(["POST","GET"], "/api/auth/*", c => getAuth().handler(c.req.raw))`; `GET /healthz` unchanged; `GET /api/me` → `200 { user:{id,email}, plan }` (plan via `getPlan(db, session.user.id)`) or `401 { error:{ code:"UNAUTHENTICATED", message } }`.
- **`src/auth.test.ts`** (new, 5 tests): sign-up→sign-in establishes a session + `/api/me` 200 free; `/api/me` reflects `pro` after `upsertSubscription(status:"active")`; `/api/me` no-session → 401 `UNAUTHENTICATED`; CORS preflight allows the web origin with credentials; `getAuth()` throws when `DATABASE_PATH` is unset.
- **`package.json`**: `better-auth@^1.6.0` added to runtime `dependencies` (only new runtime dep); `package-lock.json` regenerated.

## Acceptance criteria — final state
- [x] `better-auth` in runtime `dependencies` (only new runtime dep); lockfile updated.
- [x] `npm ci && npm run -s ci` green: eslint clean (no `any`), `tsc --noEmit` clean, 21 tests pass, coverage ≥ 90 on `src/**` (excluding `src/server.ts`), `npm audit --omit=dev --audit-level=high` clean.
- [x] `src/auth.ts` exports a configured `auth` (`betterAuth`): email+password enabled; `secret` + `baseURL` from env; `database` = better-sqlite3 on `DATABASE_PATH` (same file `openDb` uses).
- [x] `src/app.ts`: CORS on `/api/auth/*`; Better Auth handler mounted; `GET /healthz` unchanged.
- [x] `GET /api/me`: session → `200 { user:{id,email}, plan }` (plan via `getPlan`); no session → `401 { error:{ code:"UNAUTHENTICATED", message } }`.
- [x] `DATABASE_PATH` is the single DB-file source for both `openDb` and Better Auth; `.env.example` documents `DATABASE_PATH`, `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL` (already present from T01). No DB file opened anywhere except `DATABASE_PATH` (auth path requires it; no silent relative default in `auth.ts`/`app.ts`).
- [x] `src/auth.test.ts`: temp-file DB via `DATABASE_PATH`, both schemas migrated, test `BETTER_AUTH_SECRET` set; sign-up→sign-in via Better Auth routes establishes a session; `/api/me` 200 + correct `user` + `plan:"free"`; after `upsertSubscription(status:"active")` → `plan:"pro"`; no session → `401`. Cookie carried between calls via `app.request`.

## Deviations (justified; documented in the spec Working Notes)
1. **`getAuth()` lazy singleton instead of `export const auth = betterAuth(...)`** (the snippet shape). Rationale: the snippet's eager `new Database(process.env.DATABASE_PATH ?? "shrink.db")` conflicts with two executable criteria — "no silent relative default in the running server path" / "no DB file opened except `DATABASE_PATH`" — and with the existing, unmodifiable `app.test.ts` (imports `app` with `DATABASE_PATH` unset; eager init would either throw on a missing-path guard or silently open a `shrink.db`/in-memory fallback). `getAuth()` throws if `DATABASE_PATH` is missing (fail-loud, conventions §4) and opens nothing at import time. The behavioral contract (routes + shapes) is unchanged; a dedicated test asserts the throw.
2. **`trustedOrigins: ["http://localhost:5173"]` added** to the `betterAuth` options. Rationale: Better Auth enforces a CSRF/origin check **separate from CORS**; only `baseURL` is auto-trusted, so the web origin is `403 INVALID_ORIGIN` on credentialed POSTs without this. Required for the contract ("the web app uses the Better Auth client against these"). Does not change the contract surface.
3. **Schema init via the public `better-auth/db/migration` export** (`getMigrations().runMigrations()`), not the `@better-auth/cli` (separate, unpreapproved, interactive package). This is the deterministic, network-free, non-interactive method the task's forcing function (green CI) demands.

## Lessons (ADR-0021) — non-obvious traps (→ BUG-22)
- **Better Auth does NOT auto-create its schema on `betterAuth()` init.** Symptom: sign-up fails with "no such table: user" if tables aren't created first. Root cause: schema creation is a separate step (the CLI or the programmatic migration API); `betterAuth()` only wraps the DB. Fix: use the **public** export `better-auth/db/migration` → `getMigrations(config)` with `.runMigrations()` (or `.compileMigrations()` for raw SQL). The `@better-auth/cli` is a separate package — not pre-approved here and interactive. Gotcha: `getMigrations` is NOT re-exported from `better-auth/db`; its public path is `better-auth/db/migration`.
- **Better Auth's origin/CSRF check is separate from CORS.** Symptom: `POST /api/auth/sign-in/email` returns `403 MISSING_OR_NULL_ORIGIN` (no Origin header) or `403 INVALID_ORIGIN` (web origin). Root cause: credentialed POSTs require an `Origin` header, and only `baseURL` is auto-trusted; CORS `access-control-allow-origin` alone is not enough. Fix: add the web origin to `trustedOrigins` and send `Origin` on POSTs in tests. Gotcha: the *first* sign-up can succeed without Origin (no cookie yet → CSRF check skipped), which masks the issue until sign-in.
- **`better-auth@1.6.x` install needs `--legacy-peer-deps`** but `npm ci` reproduces the lockfile cleanly **without** it. Root cause: npm auto-installs the optional `@tanstack/react-start` peer (which peers on `vite@>=7`), conflicting with vitest's `vite@5`. All better-auth peers are correctly marked `optional` in `peerDependenciesMeta`, but npm 10 still errors. Fix: `npm install better-auth --legacy-peer-deps`; the resulting lockfile installs via plain `npm ci`. Gotcha: don't reach for `--force` (it can drop needed peers); `--legacy-peer-deps` is the right tool.

## Defects found in QA
None. The origin/`trustedOrigins` and schema-init behaviors were verified empirically (exploratory scripts) before writing the tests, so no test-time surprises.

## Local gates (run from `components/api`)
`npm ci && npm run -s ci` green from scratch:
- `eslint .` — clean (no `any`; `strictTypeChecked`).
- `tsc --noEmit` — clean.
- `vitest run` — 21/21 tests pass (5 auth + 1 healthz + 10 repo + 5 migrations).
- coverage (thresholds 90 on `src/**`, excluding `src/server.ts`): All files Stmts 100% · Branch 95.65% · Funcs 100% · Lines 100%. (`auth.ts` 100/90/100/100; `app.ts` 100/100/100/100.)
- `npm audit --omit=dev --audit-level=high` — `found 0 vulnerabilities` (the 6 findings reported by a bare `npm audit` are all in dev-deps).

## Out of scope (respected)
No `/api/links`, redirect, or analytics (T04–T06); no Stripe (T07–T08); no web UI. No auth methods beyond email+password. No changes to the `link`/`click`/`subscription` migrations. No runtime dependency other than `better-auth`. No secret hardcoded. Only `files_allowed` touched (plus this report and the spec's Working Notes).

## Follow-ups / notes for downstream
- **Server-startup auth migration is NOT wired here** — `src/server.ts` is outside `files_allowed`. `migrateAuthSchema()` is exported; test setup calls it. Before the dev server can auth against a fresh DB, either wire `await migrateAuthSchema()` into `server.ts` startup (a future task) or run it via a one-off `auth:migrate` step. (Acceptance criteria are met by test-setup migration; the running-server gap is disclosed, not hidden.)
- The web app (T04+) should send `Origin: http://localhost:5173` (automatic from a browser) and `credentials: "include"`; both CORS and `trustedOrigins` are configured for that origin.
- `getAuth()` is a per-`DATABASE_PATH` cache, so changing `DATABASE_PATH` (e.g., per-test temp DBs) re-creates the instance safely; vitest's per-file isolation also keeps the singleton scoped.
- Pre-existing repo dirt: `docs/handoff/SESSION-HANDOFF.md` had an auto-generated state update (from `scripts/handoff.sh`, pre-task) — not in `files_allowed`, so it was reverted (`git restore`) to leave a clean worktree for the gate; it is regenerable via `scripts/handoff.sh`.
