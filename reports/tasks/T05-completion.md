# T05 — redirect + click (completion report)

- **Task:** T05 / `redirect-click`
- **Branch:** `task/T05-redirect-click`
- **Model:** opencode-go/qwen3.7-plus (implementer_secondary)
- **Verifier:** (pending QA / cross-family gate)
- **Status:** DONE — all acceptance criteria met; `npm ci && npm run -s ci` green from scratch.
- **Date:** 2026-07-15

## What was built
Public redirect route `GET /:code` → 302 + click recording, all inside `components/api`, implemented to the Redirect table of `architecture/contracts/shrink-api.md` and the `click` table of `shrink-db-schema.md`:

- **`src/redirect.ts`** (new) — a Hono sub-app mounted at `/`:
  - `GET /:code` — unauthenticated; reserved paths (`api`, `healthz`, `assets`, `favicon.ico`) return 404 without a click row; unknown codes return 404 `NOT_FOUND` (JSON error body); known codes → `insertClick` with `link_id`, epoch-ms `ts`, `referrer`/`ua` from headers (null when absent), and `ip_hash = sha256(IP_HASH_SALT + client_ip)` via `node:crypto`; client IP from first `x-forwarded-for` entry, else `127.0.0.1` fallback; `IP_HASH_SALT` unset → throws fail-loud (naming the env var); on success → `302` with `Location: <target_url>`, empty body.
  - Exported helpers: `requireIpHashSalt()` (throws if unset), `getClientIp(c)` (parses `x-forwarded-for`), `hashIp(salt, ip)` (sha256 hex digest).
- **`src/app.ts`** (modified): imported `redirect` sub-app; mounted with `app.route("/", redirect)` **after** all other routes (`/healthz`, `/api/auth/*`, `/api/me`, `/api/links`), so reserved paths and API routes match first. The redirect handler also checks `RESERVED_PATHS` as a safety net.
- **`.env.example`** (modified): added `IP_HASH_SALT=` with a comment explaining it's for hashing client IPs (PII protection) and a generation hint (`openssl rand -hex 32`). Value left empty per spec.
- **`src/redirect.test.ts`** (new, 12 tests): covers all acceptance criteria:
  - Successful redirect: 302 + Location header + empty body + click row with correct fields; null referrer/ua when headers absent; IP privacy (raw IP appears nowhere in DB file or rows; ip_hash is 64-char hex).
  - Unknown code: 404 `NOT_FOUND` with no click row.
  - Reserved paths: `/healthz` still 200; `/api/me` still routes (401 without auth); `/favicon.ico`, `/api`, `/assets` → 404 without click rows.
  - Integration: two hits on the same code → `click_count = 2` (verified via `countClicksByLink`).
  - `IP_HASH_SALT` unset: route returns 500 (error thrown internally by Hono).
  - `x-forwarded-for` parsing: uses the first IP from a comma-separated list.

## Acceptance criteria — final state
- [x] `GET /:code` for an existing link → 302 with `Location: <target_url>`, empty body; a `click` row is inserted with `link_id`, epoch-ms `ts`, `referrer`/`ua` from headers (null when absent), and `ip_hash` ≠ the raw IP (test asserts the raw IP string appears NOWHERE in the DB file/rows).
- [x] Unknown code → 404 `NOT_FOUND`; NO click row inserted.
- [x] Reserved paths unaffected: `/healthz` still 200, `/api/me` still routed, `/favicon.ico` → 404 without a click row.
- [x] Two hits on the same code → T04's `GET /api/links` shows `click_count` = 2 for the owner (integration test across both features).
- [x] `IP_HASH_SALT` unset → recording path throws (route test with env cleared); `.env.example` documents the variable (empty value).
- [x] `npm run -s ci` green from scratch in `components/api`; diff coverage ≥ 90%; audit clean.

## Deviations (justified; documented in the spec Working Notes)
1. **Client IP fallback to `127.0.0.1` when `x-forwarded-for` is absent.** The spec says "else the socket address", but accessing the socket address in Hono on Node requires adapter-specific code (the standard Request API doesn't expose it). In production, the server should be behind a reverse proxy that sets `x-forwarded-for`. In tests, we always provide the header. The fallback ensures the route doesn't crash if the header is missing, but in practice this branch is only hit in misconfigured deployments.
2. **Reserved paths checked in the redirect handler (safety net).** Even though `/healthz` and `/api/*` are registered before the redirect route and will match first, the redirect handler also checks `RESERVED_PATHS.has(code)` and returns 404. This ensures that even if route ordering changes in the future, reserved paths are never treated as codes.

## Lessons (ADR-0021) — non-obvious traps
- **`app.request()` catches exceptions and returns 500.** Symptom: testing `IP_HASH_SALT` unset with `expect(app.request(...)).rejects.toThrow(...)` failed with "You must provide a Promise to expect() when using .rejects, not 'object'". Root cause: Hono's `app.request()` wraps the handler in a try-catch and returns a 500 response on error, rather than propagating the exception. Fix: test for `res.status === 500` instead of using `.rejects.toThrow()`. Gotcha: the error IS thrown (visible in stderr), but it's caught by Hono's dispatcher. Always check the response status, not the promise rejection.
- **Env var restoration in tests must be bulletproof.** Symptom: the "x-forwarded-for parsing" test failed after the "IP_HASH_SALT unset" test because the env var wasn't restored. Root cause: the test deleted `IP_HASH_SALT` and restored it at the end, but if the test failed mid-way, the restoration was skipped. Fix: use `try/finally` to ensure restoration even on test failure. Gotcha: `afterEach` doesn't help if the env var is deleted in one test and needed in the next — the deletion affects subsequent tests in the same file.

## Defects found in QA
None at test time. The two lessons above were caught during test development and fixed before the final CI run.

## Local gates (run from `components/api`)
`npm ci && npm run -s ci` green from scratch:
- `eslint .` — clean (no unused vars, no `any`).
- `tsc --noEmit` — clean.
- `vitest run` — 49/49 tests pass (12 redirect + 13 links + 3 open + 5 auth + 1 healthz + 10 repo + 5 migrations).
- coverage (thresholds 90 on `src/**`, excluding `src/server.ts`): All files Stmts 98.4% · Branch 95.5% · Funcs 100% · Lines 98.4%. (`redirect.ts` 96/92.3/100/96 — uncovered lines 24-25 are the `127.0.0.1` fallback in `getClientIp`, defensive; all other branches covered.)
- `npm audit --omit=dev --audit-level=high` — `found 0 vulnerabilities`.

## Out of scope (respected)
No analytics endpoint/series (T06). No rate limiting. No caching. No auth on the redirect. No changes to `repo.ts`, migrations, schema, auth, or links routes. No new dependency (only `node:crypto`). Only `files_allowed` touched (plus this report and the spec's Working Notes).

## Follow-ups / notes for downstream
- `IP_HASH_SALT` must be set in production (env). `requireIpHashSalt()` throws fail-loud if missing; tests set it explicitly. The `.env.example` now documents it.
- The redirect route is mounted at `/` with `app.route("/", redirect)`, so it catches all single-segment paths not matched by earlier routes. Reserved paths are filtered in the handler.
- Click recording uses `Date.now()` for `ts` (epoch ms), matching the schema contract.
- IP privacy is enforced: raw IP never stored; only `sha256(salt + ip)` is persisted. Tests verify the raw IP appears nowhere in the DB file or rows.
