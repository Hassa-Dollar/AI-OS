---
id: "001"
slug: router-pathname-match
owner_role: implementer
model: opencode-go/glm-5.1
verifier_model: opencode-go/deepseek-v4-pro   # different family than author (P8)
branch: task/001-router-pathname-match
blast_radius: med
files_allowed:
  - src/app.ts
  - src/app.test.ts
depends_on_contracts: []
deps_preapproved: []
---

# Goal
`createApp` must dispatch on the request URL's **path only**, ignoring the query string, so
`GET /health?probe=1` reaches the `/health` handler. Today it 404s.

# Context (compressed)
`src/app.ts` `createApp()` matches `r.path === req.url`. For an incoming request `req.url` is the raw
request target and **includes the query string** (e.g. `/health?probe=1`), so any request carrying a
query never matches a route and 404s. Fix the matcher to compare each route's `path` against the
request's **pathname** (query stripped). Matching must stay exact on the pathname.

Constraints: the `Route` interface is the public shape — do **not** change it. Do **not** touch
`src/routes/*` (routes self-register there) or `src/server.ts`. Node 22, `node:http` only, no new
dependencies. Method matching stays exact. See architecture/README.md.

# Acceptance criteria  (executable where possible)
- [ ] `GET /health?probe=1` returns 200 with the same JSON body as `GET /health`.
- [ ] `GET /health` still returns 200 (no regression).
- [ ] An unknown path with a query (`GET /nope?x=1`) returns 404 `{ "error": "not_found" }`.
- [ ] Exact-path matching is preserved: `GET /healthx` returns 404 (must NOT match `/health`).
- [ ] `src/app.test.ts` adds tests covering: the query-string match, the `/healthx` near-miss 404, and a query on an unknown path. Existing `createApp` tests still pass unchanged.
- [ ] `npm run typecheck` and `npm run lint` pass; diff coverage ≥ 90%; `npm test` all green.

# Out of scope  (binding — prevents gold-plating)
- No path params, wildcards, regex routes, or trailing-slash normalization — exact pathname match only.
- No method coercion (e.g. HEAD→GET). No query parsing beyond stripping it for the match.
- No changes to `Route`, `src/routes/*`, `src/server.ts`, or dependencies.

# Stop conditions  (escalate instead of guessing)
- If the fix appears to require changing the `Route` interface or any route file → STOP, emit `ESCALATE: <reason>`.
- If `new URL(req.url ?? '/', base)` can throw on a realistic request target you cannot safely guard → STOP, emit `ESCALATE: <reason>`.

# Working notes  (worker appends)
