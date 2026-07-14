---
id: T04
slug: links-crud
owner_role: implementer    # profile web-app/ts-hono-api binds the model (ADR-0022)
branch: task/T04-links-crud
blast_radius: med
files_allowed:
  - components/api/src/links.ts
  - components/api/src/links.test.ts
  - components/api/src/app.ts
  - components/api/src/db/open.ts
  - components/api/src/db/open.test.ts
  - components/api/package.json
  - components/api/package-lock.json
  - reports/tasks/T04-completion.md
depends_on_contracts:
  - architecture/contracts/shrink-api.md
  - architecture/contracts/shrink-db-schema.md
deps_preapproved:
  - zod
---

# Goal
Authenticated links CRUD per the contract: `POST /api/links` (zod-validated, unique code, free-plan
limit 10), `GET /api/links` (caller's links + click_count), `DELETE /api/links/:code` (owner only) —
and `openDb()` fails loud instead of silently opening `shrink.db`.

# Context (compressed)
The Links table of `architecture/contracts/shrink-api.md` is the exact surface (paths, bodies, status
codes, error codes) — implement to it, do not reinterpret it. Everything below the routes already
exists from T02/T03; REUSE, do not rewrite:
- `src/db/repo.ts`: `insertLink`, `getLinkByCode`, `listLinksByUser`, `countLinksByUser`,
  `deleteLinkByCodeForUser`, `countClicksByLink`, `getPlan` (all take the `DB` handle).
- Session pattern: copy how `GET /api/me` in `src/app.ts` calls
  `getAuth().api.getSession({ headers: c.req.raw.headers })` and 401s on null. `app.ts` has a lazy
  `getDb()` singleton — routes get the handle per-request from it.
- Test wiring: `src/auth.test.ts` shows the working pattern — per-file temp DB via
  `mkdtempSync(join(tmpdir(), …))` (NEVER a hardcoded /tmp path — BUG-29), `migrateAuthSchema()`,
  sign-up/sign-in with an `Origin` header to obtain a session cookie.
Put the routes in a new `src/links.ts` mounted from `app.ts`. Generate `code` as 7-char base62 from
`node:crypto` (`randomBytes`), retry on the rare unique-collision. `short_url` = `${BASE_URL}/${code}`
(env, see `.env.example`; in tests set `BASE_URL` explicitly).
`openDb()` hardening (same defect family as BUG-29): remove the `?? "shrink.db"` fallback — with no
`filename` arg and no `DATABASE_PATH`, throw a clear Error naming the env var. The lazy `getDb()`
means `app.test.ts` (healthz, no DB) must keep passing unchanged.

# Acceptance criteria  (executable)
- [ ] `POST /api/links`: 401 without a session; 400 `INVALID_INPUT` when `target_url` is absent, not a
      string, or not http/https (zod); 201 `{ code, short_url, target_url, created_at }` on success
      with a 7-char base62 `code`.
- [ ] Free-plan limit: a free user with 10 links gets 402 `PLAN_LIMIT` (clear JSON body) on the 11th;
      the 10th itself succeeds.
- [ ] `GET /api/links`: 401 without a session; 200 array of ONLY the caller's links, each with
      `click_count` (0 for fresh links).
- [ ] `DELETE /api/links/:code`: 401 without a session; 404 `NOT_FOUND` unknown code; 403 `FORBIDDEN`
      when another user owns it; 204 for the owner (row gone).
- [ ] `openDb()` with no filename and `DATABASE_PATH` unset throws (message names `DATABASE_PATH`);
      explicit-filename calls (the existing tests) still work; `src/db/open.test.ts` covers both.
- [ ] tests cover: all codes above, ownership isolation (two users), limit boundary (10 ok / 11 rejected),
      code shape + uniqueness on collision retry.
- [ ] `npm run -s ci` green from scratch in `components/api`: lint + typecheck + tests; diff coverage
      ≥ 90% (open.ts line 6 branch now covered); `npm audit --omit=dev --audit-level=high` clean.

# Out of scope  (binding — prevents gold-plating)
- No public redirect `GET /:code` and no click inserts (T05). No analytics endpoint (T06). No Stripe
  or plan upgrades (T07+). No web UI. No changes to auth.ts, migrations, repo.ts, or the schema.
- No dependency beyond `zod`.

# Stop conditions  (escalate instead of guessing)
- If the contract's Links table seems wrong or incomplete for any criterion → STOP, escalate to Lead.
- If a needed behavior requires touching repo.ts/migrations → STOP, escalate (contract boundary).
- If a needed dependency isn't `zod` → STOP, escalate.

# Working notes  (worker appends)
