---
id: T06
slug: analytics-endpoint
owner_role: implementer      # ts-hono-api → glm-5.2
branch: task/T06-analytics-endpoint
blast_radius: med
files_allowed:
  - components/api/src/analytics.ts
  - components/api/src/analytics.test.ts
  - components/api/src/app.ts
  - reports/tasks/T06-completion.md
depends_on_contracts:
  - architecture/contracts/shrink-api.md
  - architecture/contracts/shrink-db-schema.md
deps_preapproved: []
---

# Goal
The Pro-gated analytics endpoint per contract: `GET /api/links/:code/analytics` → owner-only totals +
daily time series; free plan gets 402 `PRO_REQUIRED`. Completes the free/pro API surface before Stripe.

# Context (compressed)
Contract row (shrink-api.md Links table): session required; owner only; success
`200 { code, total_clicks, series: [ { date: "YYYY-MM-DD", count } ] }`; errors 401 / 402
`PRO_REQUIRED` (free) / 403 / 404. Order the checks: 401 (no session) → 404 (unknown code) → 403
(not owner) → 402 (owner but free) → 200. REUSE, do not rewrite:
- `src/db/repo.ts`: `getLinkByCode`, `countClicksByLink`, `dailyClickSeries` (its output IS the
  contract's series shape — days with ≥1 click, ascending), `getPlan`, and for tests
  `upsertSubscription` (insert an active pro row to simulate a Pro user) + `insertClick` (backdated
  `ts` values to build a multi-day series).
- Session pattern + mounting: same as T04's `src/links.ts` (`getAuth().api.getSession`, mounted from
  `app.ts` via `app.route`). New module `src/analytics.ts`; keep `links.ts` untouched.
- Test wiring: per-file temp DB via `mkdtempSync(join(tmpdir(), …))` (BUG-29), `migrateAuthSchema()`,
  sign-up with Origin header (see `src/auth.test.ts`).

# Acceptance criteria  (executable)
- [ ] 401 without a session; 404 unknown code; 403 when another user owns the link; 402
      `PRO_REQUIRED` for the owner on the free plan (clear JSON body).
- [ ] Pro owner (subscription row upserted in test): 200 with `code`, `total_clicks` (matches
      inserted clicks), `series` of `{ date: "YYYY-MM-DD", count }` ascending — asserted against
      clicks inserted across ≥2 distinct days (backdated ts).
- [ ] A link with zero clicks (Pro owner): 200 with `total_clicks: 0`, `series: []`.
- [ ] `npm run -s ci` green from scratch in `components/api`; diff coverage ≥ 90%; audit clean.

# Out of scope  (binding)
- No Stripe/billing endpoints (T07/T08) — the test fabricates the subscription row directly.
- No changes to repo.ts, migrations, schema, auth, links, or redirect. No web UI. No new dependency.

# Stop conditions
- Contract seems wrong/incomplete for a criterion → STOP, escalate to Lead.
- A criterion seems to need repo.ts/schema changes → STOP, escalate.

# Working notes  (worker appends)
