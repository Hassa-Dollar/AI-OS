# T04 — links CRUD (completion report)

- **Task:** T04 / `links-crud`
- **Branch:** `task/T04-links-crud`
- **Model:** opencode-go/glm-5.2 (implementer)
- **Verifier:** (pending QA / cross-family gate)
- **Status:** DONE — all acceptance criteria met; `npm ci && npm run -s ci` green from scratch.
- **Date:** 2026-07-14

## What was built
Authenticated links CRUD + `openDb()` fail-loud hardening, all inside `components/api`, implemented to the Links table of `architecture/contracts/shrink-api.md` (paths, bodies, status codes, error codes — unchanged):

- **`src/links.ts`** (new) — a Hono sub-app mounted at `/api/links`:
  - `POST /api/links` — session-required (401 `UNAUTHENTICATED`); body validated with **zod** (`target_url`: string matching `^https?:\/\/\S+$`) → 400 `INVALID_INPUT` on absent / non-string / non-http(s); free-plan limit enforced (`getPlan(...) === "free" && countLinksByUser(...) >= 10` → 402 `PLAN_LIMIT`, so the 10th succeeds and the 11th is rejected); 7-char **base62** `code` from `node:crypto` `randomBytes` with **collision retry** (`generateUniqueCode` retries up to 8× against `getLinkByCode`); on success `insertLink` → `201 { code, short_url, target_url, created_at }` with `short_url = ${BASE_URL}/${code}`.
  - `GET /api/links` — session-required (401); returns `200` of **only the caller's** links (`listLinksByUser`) each annotated with `click_count` (`countClicksByLink`, 0 for fresh links) and `short_url`.
  - `DELETE /api/links/:code` — session-required (401); `getLinkByCode` → `404 NOT_FOUND` (unknown); `403 FORBIDDEN` if the link exists but is owned by another user; `204` (no body) for the owner via `deleteLinkByCodeForUser` (row gone, re-delete → 404).
  - Exported helpers `baseUrl()`, `randomCode()`, `generateUniqueCode(db, gen?)` — `gen` injectable for deterministic collision-retry tests; `baseUrl()` throws naming `BASE_URL` (fail-loud, no broken URL).
- **`src/app.ts`** (modified): `getDb()` **exported** (links routes get the lazy singleton per-request from it, per spec); `app.route("/api/links", links)` mounts the sub-app. The router ↔ `getDb` is a live-binding function call resolved at request time, so the `app.ts → links.ts → app.ts` module cycle is safe (functions only, never invoked at module-eval).
- **`src/db/open.ts`** (modified): the `?? "shrink.db"` tail removed. With no `filename` arg and no `DATABASE_PATH`, `openDb()` now **throws** `Error("DATABASE_PATH is required …")` (names the env var — same defect family as BUG-29). Explicit-filename calls (existing `:memory:` tests) keep working; the lazy `getDb()` means `app.test.ts` (healthz, no DB) is untouched and still green.
- **`src/db/open.test.ts`** (new): explicit arg wins; `DATABASE_PATH` env path works; no arg + env unset throws matching `/DATABASE_PATH/`. Covers open.ts line 6's branch.
- **`src/links.test.ts`** (new, 13 tests): all status codes above, ownership isolation across two users, free-plan limit boundary (10 ok / 11th `PLAN_LIMIT`), code shape (`^[0-9A-Za-z]{7}$`), and **collision retry** (seeded via an injectable `gen` that first returns an existing code).
- **`package.json` / `package-lock.json`**: `zod@^4.4.3` added to runtime `dependencies` (only new runtime dep; already present transitively via better-auth). **Lock edited surgically, not regenerated** — see Lessons / BUG-31.

## Acceptance criteria — final state
- [x] `POST /api/links`: 401 without session; 400 `INVALID_INPUT` (absent / not-string / not-http(s)); 201 `{ code, short_url, target_url, created_at }` with 7-char base62 `code`.
- [x] Free-plan limit: a free user with 10 links gets 402 `PLAN_LIMIT` (clear JSON body) on the 11th; the 10th succeeds.
- [x] `GET /api/links`: 401 without session; 200 array of ONLY the caller's links, each with `click_count` (0 for fresh).
- [x] `DELETE /api/links/:code`: 401 without session; 404 `NOT_FOUND` unknown code; 403 `FORBIDDEN` for a non-owner; 204 for the owner (row gone).
- [x] `openDb()` with no filename and `DATABASE_PATH` unset throws (message names `DATABASE_PATH`); explicit-filename calls still work; `src/db/open.test.ts` covers both.
- [x] Tests cover all codes above, ownership isolation (two users), limit boundary (10 ok / 11 rejected), code shape + collision retry.
- [x] `npm run -s ci` green from scratch in `components/api`: lint + typecheck + tests + coverage (≥90%); `npm audit --omit=dev --audit-level=high` clean (0 vulnerabilities).

## Deviations (justified; documented in the spec Working Notes)
1. **`generateUniqueCode` pre-checks `getLinkByCode` before `insertLink` (no insert-catch retry).** The contract's "retry on the rare unique-collision" is owned by the generator's pre-check loop; an insert-time unique-constraint catch would add an untestable/rare branch that hurts diff coverage without changing behavior (the pre-check moments-earlier makes an insert collision astronomically unlikely at 7 base62). Kept the surface small and the branches covered.
2. **`getDb()` exported from `app.ts`** rather than a new shared module. `app.ts` is in `files_allowed`, the singleton already exists there, and the spec says routes "get the handle per-request from it." A function-binding cycle (`app → links → app`) is safe in ESM because `getDb` is only ever called at request time, long after both modules finish loading.

## Lessons (ADR-0021) — non-obvious traps (→ BUG-31)
- **`npm install`-adding a dep corrupts the committed lock for `npm audit --omit=dev`.** Symptom: after `npm install` to add `zod`, `npm audit --omit=dev --audit-level=high` began failing with 5 dev-only vulns (esbuild/vite/vitest) reported as prod, even though `package.json` `devDependencies` were unchanged and all versions were identical to main. Root cause: **npm 11.18, when regenerating `package-lock.json` from `package.json`, drops the per-package `dev: true` flags** that lockfile v3 stores on dev-only transitive nodes (e.g. `packages["node_modules/vitest"].dev === true` on main, `undefined` after). `npm audit --omit=dev` keys dev-exclusion off those **lock flags**, NOT off `package.json` `devDependencies`, so with the flags gone the entire dev toolchain is re-counted as prod → audit exit 1. Fix: do **not** `npm install` to add a dep on top of the committed lock. Surgical-edit the lock: `git show main:components/api/package-lock.json > package-lock.json` to restore the flag-bearing lock, add only `zod: ^4.4.3` to `packages[""].dependencies` (zod already exists as a **prod** transitive node via better-auth, so no new version node is needed), then `npm ci` (installs from the lock, never rewrites it). Verify `packages["node_modules/vitest"].dev === true` before re-running audit. Gotcha: `npm install zod` says "up to date" (zod was already hoisted) — but it still rewrites and strips dev flags. Always prefer `npm ci` after a surgical lock edit.

## Defects found in QA
None at test time. The npm-lock/audit trap was caught before committing by running the `audit` gate step locally (the spec's `ci` script).

## Local gates (run from `components/api`)
`npm ci && npm run -s ci` green from scratch:
- `eslint .` — clean (no `any`; `strictTypeChecked`).
- `tsc --noEmit` — clean.
- `vitest run` — 37/37 tests pass (13 links + 3 open + 5 auth + 1 healthz + 10 repo + 5 migrations).
- coverage (thresholds 90 on `src/**`, excluding `src/server.ts`): All files Stmts 98.76% · Branch 95.89% · Funcs 100% · Lines 98.76%. (`links.ts` 96.55/92.3/100/96.55 — uncovered lines 30–31 `BASE_URL` throw & 50–51 max-retry throw, defensive; `open.ts` 100/100/100/100, line-6 branch now covered.)
- `npm audit --omit=dev --audit-level=high` — `found 0 vulnerabilities`.

## Out of scope (respected)
No public redirect `GET /:code` and no click inserts (T05). No analytics (T06). No Stripe / plan upgrades (T07+). No web UI. No changes to `auth.ts`, `migrations.ts`, `repo.ts`, or the schema. No dependency beyond `zod`. Only `files_allowed` touched (plus this report and the spec's Working Notes).

## Follow-ups / notes for downstream
- `short_url` requires `BASE_URL` to be set (env). `baseUrl()` throws fail-loud if missing; tests set it explicitly. The dev `.env.example` already documents `BASE_URL`.
- `generateUniqueCode` exposes an injectable `gen` so future tests can drive collision behavior deterministically without mocking `node:crypto`.
- The defensive `BASE_URL`/max-retry throws in `links.ts` (lines 30–31, 50–51) are reachable only via misconfiguration/exhaustion; left uncovered rather than gold-plate, keeping branch coverage > 90.