# Task 002 — method-not-allowed: Completion Report

## Summary
When a request path matches at least one registered route but the HTTP method matches none, `createApp()` now responds `405 Method Not Allowed` with an `Allow` header listing the path's supported methods (deduplicated, sorted alphabetically, comma+space separated). Previously all unmatched requests returned `404`, which was misleading when the resource existed but the method did not.

## Changes
### `src/app.ts` (lines 17–30)
- After the exact `method + path` lookup fails, added a second check: `routes.filter(r => r.path === pathname)`.
- If any routes match the pathname, responds `405` with `Allow` header and body `{ "error": "method_not_allowed" }`.
- If no routes match the pathname, falls through to the existing `404` response (unchanged).

### `src/app.test.ts` (6 new test cases)
- **"responds 405 with Allow header when path matches but method does not"** — `POST /health` → 405, `Allow: GET`, body `{ "error": "method_not_allowed" }`.
- **"responds 405 with deduplicated sorted Allow for multi-method path"** — `DELETE /x` (with GET+PUT registered) → 405, `Allow: GET, PUT`.
- **"does NOT coerce HEAD to GET — HEAD on GET-only route is 405"** — `HEAD /health` → 405, `Allow: GET`.
- **"responds 405 for POST /health?x=1 (query stripped before method check)"** — query string is stripped before path matching, same as GET behavior.
- **"still 404s unknown path for any method (POST /nope)"** — no path match at all → 404.
- **"traversal /../health raises 404 never 405 (no normalization)"** — regression guard for task 001.

## Acceptance Criteria
- [x] `POST /health` → 405, body `{ "error": "method_not_allowed" }`, header `Allow: GET`
- [x] `GET /health` → 200 unchanged, and `GET /health?probe=1` → 200 (task-001 behavior intact)
- [x] `POST /health?x=1` → 405 (query stripped before matching)
- [x] Unknown path: `GET /nope` and `POST /nope` → 404 `{ "error": "not_found" }` (unchanged)
- [x] Traversal stays unmatched: `/../health` → 404, never 405/200
- [x] Multi-method: `DELETE /x` (GET+PUT registered) → 405 with `Allow: GET, PUT`
- [x] No HEAD→GET coercion: `HEAD /health` → 405 with `Allow: GET`
- [x] `src/app.test.ts` adds tests covering all above; existing tests pass unchanged
- [x] `npm run typecheck` passes
- [x] `npm run lint` passes
- [x] `npm test` all green (15/15)
- [x] Diff coverage ≥ 90% (all new lines covered; uncovered lines 33-34 are pre-existing error catch)

## Out of Scope — Not Touched
- No automatic OPTIONS handling, 501, HEAD→GET mapping, path params, wildcards, trailing-slash or dot-segment normalization
- No changes to `Route` interface, `src/routes/*`, `src/server.ts`, or dependencies
- No query parsing beyond stripping for the match

## Working Notes
- Implementation follows spec exactly: `filter` by path, then `new Set` → `sort` → `join(', ')` for the Allow header.
- The 404 branch is unchanged except it is now inside an `else` (reached only when no route matches the pathname at all).