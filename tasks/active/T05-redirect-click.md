---
id: T05
slug: redirect-click
owner_role: implementer_secondary   # qwen3.7-plus per profile (ADR-0022) — spreads the workforce
branch: task/T05-redirect-click
blast_radius: med
files_allowed:
  - components/api/src/redirect.ts
  - components/api/src/redirect.test.ts
  - components/api/src/app.ts
  - .env.example
  - reports/tasks/T05-completion.md
depends_on_contracts:
  - architecture/contracts/shrink-api.md
  - architecture/contracts/shrink-db-schema.md
deps_preapproved: []      # node:crypto only — any package is a STOP condition
---

# Goal
The public redirect: `GET /:code` → 302 to the link's target and records a `click` row (ts, referrer,
UA, salted IP hash — never a raw IP). 404 for unknown codes. The only unauthenticated app route.

# Context (compressed)
Contract: Redirect table of `architecture/contracts/shrink-api.md` + the `click` table in
`shrink-db-schema.md`. Reserved top-level paths that are NEVER codes: `api`, `healthz`, `assets`,
`favicon.ico`. Existing pieces to REUSE (no repo/migration changes):
- `src/db/repo.ts`: `getLinkByCode`, `insertClick` (see `NewClick` in `src/db/types.ts`),
  `countClicksByLink` — clicks recorded here must raise `click_count` in T04's `GET /api/links`.
- `src/app.ts`: mount the route module (like T04's `app.route(...)`) — order it so `/api/*`,
  `/healthz` and the reserved set are matched first; a same-length reserved word (e.g. `healthz`)
  must never be treated as a code. `getDb()` is the DB handle source.
- IP privacy (PII hard rule, ADR-0014/checklist): `ip_hash = sha256(IP_HASH_SALT + client_ip)` via
  `node:crypto`; client IP from the first `x-forwarded-for` entry, else the socket address; if
  `IP_HASH_SALT` is unset, throw (fail loud, conventions §4 — same pattern as `DATABASE_PATH` in
  `src/db/open.ts`). Add `IP_HASH_SALT` to `.env.example` with a comment, VALUE LEFT EMPTY.
- Test wiring: per-file temp DB via `mkdtempSync(join(tmpdir(), …))` (BUG-29 — never a hardcoded
  /tmp path); create a link via the repo directly (no auth needed for fixtures).

# Acceptance criteria  (executable)
- [ ] `GET /:code` for an existing link → 302 with `Location: <target_url>`, empty body; a `click`
      row is inserted with `link_id`, epoch-ms `ts`, `referrer`/`ua` from headers (null when absent),
      and `ip_hash` ≠ the raw IP (test asserts the raw IP string appears NOWHERE in the DB file/rows).
- [ ] Unknown code → 404 `NOT_FOUND`; NO click row inserted.
- [ ] Reserved paths unaffected: `/healthz` still 200, `/api/me` still routed, `/favicon.ico` → 404
      without a click row.
- [ ] Two hits on the same code → T04's `GET /api/links` shows `click_count` = 2 for the owner
      (integration test across both features).
- [ ] `IP_HASH_SALT` unset → recording path throws (route test with env cleared); `.env.example`
      documents the variable (empty value).
- [ ] `npm run -s ci` green from scratch in `components/api`; diff coverage ≥ 90%; audit clean.

# Out of scope  (binding)
- No analytics endpoint/series (T06). No rate limiting. No caching. No auth on the redirect. No
  changes to repo.ts, migrations, schema, auth, or links routes. No new dependency.

# Stop conditions
- Contract seems wrong/incomplete for a criterion → STOP, escalate to Lead.
- A criterion seems to need repo.ts/schema changes → STOP, escalate.
- Any dependency beyond node stdlib seems needed → STOP, escalate.

# Working notes  (worker appends)
