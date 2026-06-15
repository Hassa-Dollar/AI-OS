---
id: "002"
slug: method-not-allowed
owner_role: implementer
model: opencode-go/glm-5.1
verifier_model: opencode-go/kimi-k2.7-code   # rotation: DeepSeek graded 000+001; zhipu ≠ moonshot (P8)
branch: task/002-method-not-allowed
blast_radius: med
files_allowed:
  - src/app.ts
  - src/app.test.ts
  - reports/tasks/002-completion.md   # required output (AGENTS.md §6)
depends_on_contracts: []
deps_preapproved: []
---

# Goal
When the request **pathname matches at least one route but the method matches none of them**,
`createApp` must respond `405` with an `Allow` header listing the path's registered methods —
instead of today's misleading `404`.

# Context (compressed)
`src/app.ts` `createApp()` dispatches by exact `method` + exact pathname (query stripped via
`split('?')` — deliberately NOT `new URL().pathname`, which normalizes dot-segments; this was
task 001 and must not regress). Today `POST /health` falls through to `404 { "error": "not_found" }`,
which lies to clients: the resource exists, the method doesn't. RFC 9110 §15.5.6 requires a 405
response to generate an `Allow` header.

Implementation shape: find all routes whose `path` equals the request pathname. If none → 404
(unchanged). If some exist but none matches `req.method` → `405`, `content-type: application/json`,
body `{ "error": "method_not_allowed" }`, and `Allow` = the matching routes' methods, deduplicated,
sorted alphabetically, joined with `", "`. The `Route` interface is public — do not change it.

# Acceptance criteria  (executable where possible)
- [ ] `POST /health` → `405`, body `{ "error": "method_not_allowed" }`, header `Allow: GET`.
- [ ] `GET /health` → `200` unchanged, and `GET /health?probe=1` → `200` (task-001 behavior intact).
- [ ] `POST /health?x=1` → `405` (query stripped before matching, same as GET path).
- [ ] Unknown path: `GET /nope` and `POST /nope` → `404 { "error": "not_found" }` (unchanged).
- [ ] Traversal stays unmatched: a raw request target `/../health` (any method) → `404`, never 405/200
      (no pathname normalization — regression guard for task 001).
- [ ] Multi-method paths: with routes `GET /x` and `PUT /x` registered, `DELETE /x` → `405` with
      `Allow: GET, PUT` (deduplicated, alphabetical, comma+space).
- [ ] No method coercion: `HEAD /health` → `405` with `Allow: GET` (HEAD is NOT auto-mapped to GET).
- [ ] `src/app.test.ts` adds tests covering all of the above; existing tests pass **unchanged**.
- [ ] `npm run typecheck` + `npm run lint` pass; diff coverage ≥ 90%; `npm test` all green.

# Out of scope  (binding — prevents gold-plating)
- No automatic `OPTIONS` handling, no `501`, no HEAD→GET mapping, no path params / wildcards /
  trailing-slash or dot-segment normalization.
- No changes to the `Route` interface, `src/routes/*`, `src/server.ts`, dependencies, or the 404 shape.
- No query parsing beyond stripping it for the match.

# Stop conditions  (escalate instead of guessing)
- If correct behavior seems to require changing the `Route` interface or any file outside
  `files_allowed` → STOP, emit `ESCALATE: <reason>`.
- If an acceptance criterion conflicts with an existing test → STOP, emit `ESCALATE: <reason>`
  (never weaken or delete existing tests).

# Working notes  (worker appends)
