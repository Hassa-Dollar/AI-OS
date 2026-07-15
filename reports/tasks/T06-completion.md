# T06 — analytics endpoint (completion report)

- **Task:** T06 / `analytics-endpoint`
- **Branch:** `task/T06-analytics-endpoint`
- **Model:** opencode-go/glm-5.2 (implementer)
- **Verifier:** (pending QA / cross-family gate)
- **Status:** DONE — all acceptance criteria met; `npm ci && npm run -s ci` green from scratch.
- **Date:** 2026-07-15

## What was built
The Pro-gated `GET /api/links/:code/analytics` endpoint per the Links table of `architecture/contracts/shrink-api.md` (path, body, status codes, error codes — unchanged), inside `components/api`:

- **`src/analytics.ts`** (new) — a Hono sub-app mounted at `/api/links` (`app.route("/api/links", analytics)`) exposing a single `GET /:code/analytics` route. Check order matches the spec exactly: `401 UNAUTHENTICATED` (no session) → `404 NOT_FOUND` (unknown code) → `403 FORBIDDEN` (link exists but not owner) → `402 PRO_REQUIRED` (owner but free plan) → `200`. Reuses — does not rewrite — `getAuth().api.getSession` (session pattern from T04's `links.ts`), `getDb()` (lazy app singleton), and `getLinkByCode`, `getPlan`, `countClicksByLink`, `dailyClickSeries` from `src/db/repo.ts`. The repo's `dailyClickSeries` output **is** the contract's series shape (days with ≥1 click, ascending, `strftime('%Y-%m-%d', …, 'unixepoch')` UTC), so it is returned verbatim; a zero-click link yields `series: []` naturally. Success body: `{ code, total_clicks, series }`.
- **`src/app.ts`** (modified): import + `app.route("/api/links", analytics)` mounted **after** `links`. Two sub-apps share the `/api/links` prefix cleanly because their routes are disjoint (`analytics` only registers `GET /:code/analytics`; no param/method collision with `links`' `POST /`, `GET /`, `DELETE /:code`). `links.ts` untouched.
- **`src/analytics.test.ts`** (new, 6 tests): per-file temp DB via `mkdtempSync(join(tmpdir(), …))` (BUG-29); `migrateAuthSchema()`; sign-up with `Origin: http://localhost:5173` (matches `auth.test.ts`). Covers every status code and the two Pro 200 paths:
  - 401 without session; 404 unknown code; 403 intruder (another owner's link); 402 `PRO_REQUIRED` for the owner on free (clear JSON body, message matches `/pro/i`).
  - Pro owner (subscription row fabricated directly via `INSERT INTO subscription … active`): 200 with `code`, `total_clicks` matching inserted clicks, and `series` ascending across **2 distinct UTC days** (backdated `ts` via `Date.UTC(2026, 5, 10, …)` and `Date.UTC(2026, 5, 11, …)` → `[{ "2026-06-10", 2 }, { "2026-06-11", 1 }]`), asserting both bucketing and ascending order.
  - Pro owner with zero clicks: 200 `total_clicks: 0`, `series: []`.

## Acceptance criteria — final state
- [x] 401 without a session; 404 unknown code; 403 when another user owns the link; 402 `PRO_REQUIRED` for the owner on the free plan (clear JSON body).
- [x] Pro owner (subscription row upserted in test): 200 with `code`, `total_clicks` (matches inserted clicks), `series` of `{ date: "YYYY-MM-DD", count }` ascending — asserted against clicks inserted across ≥2 distinct days (backdated `ts`).
- [x] A link with zero clicks (Pro owner): 200 with `total_clicks: 0`, `series: []`.
- [x] `npm run -s ci` green from scratch in `components/api`; diff coverage ≥ 90% (`analytics.ts` 100/100/100/100); audit clean.

## Deviations
None. No contract, repo, schema, migration, auth, links, or redirect file changed. No new dependency. Only `files_allowed` touched (plus this report and the spec's Working Notes).

## Lessons (ADR-0021)
None — no non-obvious traps. The spec was explicit that `dailyClickSeries` already yields the contract's series shape, so the endpoint is a thin orchestration over existing repo functions (the same design the contract intended).

## Local gates (run from `components/api`)
`npm ci && npm run -s ci` green from scratch:
- `eslint .` — clean (no `any`; the one test `link!.id` non-null was avoided by narrowing with an `undefined` guard throw, satisfying `no-non-null-assertion`).
- `tsc --noEmit` — clean.
- `vitest run` — 55/55 tests pass (6 analytics + prior suite unaffected). Test files 8 passed.
- coverage: All files Stmts 98.56% · Branch 95.95% · Funcs 100% · Lines 98.56%. **`analytics.ts` 100/100/100/100.** `app.ts` 100/100/100/100.
- `npm audit --omit=dev --audit-level=high` — `found 0 vulnerabilities`.

## Out of scope (respected)
No Stripe/billing endpoints (T07/T08); the test fabricates the subscription row directly. No changes to `repo.ts`, migrations, schema, `auth.ts`, `links.ts`, or `redirect.ts`. No web UI. No new dependency.