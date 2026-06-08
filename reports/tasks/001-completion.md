# Task 001 — router-pathname-match: Completion Report

## Summary
Fixed `createApp()` route matching to compare against the request URL's **pathname** (query string stripped) instead of the raw `req.url`. `GET /health?probe=1` now correctly reaches the `/health` handler.

## Changes
### `src/app.ts` (line 13-14)
- Replaced `r.path === req.url` with pathname extraction via `new URL(req.url ?? '/', ...)` followed by `r.path === pathname`.
- This strips the query string before matching while preserving exact-path semantics.

### `src/app.test.ts` (3 new test cases)
- **"matches route by pathname, ignoring query string"** — verifies `GET /health?probe=1` returns the same JSON as `GET /health`.
- **"does not match a near-miss path like /healthx against /health"** — verifies exact-path matching is preserved.
- **"does not 404 with query on unknown path"** — verifies `GET /nope?x=1` returns 404 `{ "error": "not_found" }`.

## Acceptance Criteria
- [x] `GET /health?probe=1` returns 200 with same JSON body as `GET /health`
- [x] `GET /health` still returns 200 (no regression)
- [x] `GET /nope?x=1` returns 404 `{ "error": "not_found" }`
- [x] `GET /healthx` returns 404 (does NOT match `/health`)
- [x] Tests added for query-string match, `/healthx` near-miss 404, and query on unknown path
- [x] `npm run typecheck` passes
- [x] `npm run lint` passes
- [x] `npm test` all green (7/7)
- [x] Diff coverage ≥ 90% (changed lines fully covered; pre-existing uncovered lines 22-23 are unrelated)

## Out of Scope — Not Touched
- No changes to `Route` interface, `src/routes/*`, or `src/server.ts`
- No new dependencies
- No path params, wildcards, regex, trailing-slash normalization, or HEAD→GET coercion

## Working Notes
- Used `new URL(req.url ?? '/', 'http://${req.headers.host ?? 'localhost'}')` to safely parse the request target. `new URL` handles any valid request-target including origin-form (`/path?query`), which Node's `http` module emits for `req.url`. The base is only used for resolution when `req.url` is missing; with a valid request target the pathname is extracted from the target itself.
- Lines 22-23 (error catch branch) remain uncovered — pre-existing, not touched by this diff.