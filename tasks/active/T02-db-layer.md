---
id: "T02"
slug: db-layer
owner_role: implementer
model: opencode-go/glm-5.2
verifier_model: opencode-go/deepseek-v4-pro   # P8: zhipu author != deepseek verifier
branch: task/T02-db-layer
blast_radius: medium
files_allowed:
  - components/api/package.json
  - components/api/package-lock.json
  - components/api/src/db/open.ts
  - components/api/src/db/migrations.ts
  - components/api/src/db/repo.ts
  - components/api/src/db/types.ts
  - components/api/src/db/migrations.test.ts
  - components/api/src/db/repo.test.ts
depends_on_contracts:
  - architecture/contracts/shrink-db-schema.md
deps_preapproved:
  - better-sqlite3
---

# Goal
Build the `components/api` persistence layer for Shrink on `better-sqlite3` (v12, synchronous): a
versioned, idempotent **migration runner** that creates the app tables from `shrink-db-schema.md`, plus a
**typed data-access module** (`repo`) the later HTTP tasks (T04–T06) build on. Pure data layer — **no HTTP
routes, no app/server wiring, no Better Auth, no Stripe.** Fully testable in isolation against an in-memory
DB. This is the foundation T03+ depend on. Nothing more.

# Context (compressed)
- Profile `web-app/ts-hono-api` governs this component (`components/api/conventions.md`: TS `strict`, ESM,
  secrets only from env). Read it first. The scaffold from T01 already gives you `package.json`, `tsconfig`
  (`strict`, `module`/`moduleResolution` = `NodeNext`, `target` ES2022, `verbatimModuleSyntax`), `vitest`
  (coverage `include: ['src/**']`, threshold **90**), eslint (`strictTypeChecked`), and `npm run -s ci`.
- The component stays **independently buildable**: `npm ci && npm run -s ci` from INSIDE `components/api`.
  `npm run -s ci` now also runs `npm audit --omit=dev --audit-level=high` (must be clean).
- **better-sqlite3 (v12.6.2)**, synchronous API, confirmed import + idioms:
  - `import Database from 'better-sqlite3'` (default import; works under NodeNext + `esModuleInterop`).
    Add `@types/better-sqlite3` as a **devDependency** (community types; type the handle as
    `import type { Database as DB } from 'better-sqlite3'`).
  - Open: `const db = new Database(filename)`. In-memory for tests: `new Database(':memory:')`.
  - Pragmas: `db.pragma('journal_mode = WAL')` and **`db.pragma('foreign_keys = ON')`** (required so the
    click→link cascade works; SQLite has FKs OFF by default).
  - DDL: `db.exec(multiStatementSql)`. Queries: `db.prepare(sql).run|get|all(...)`. Atomic multi-step
    writes: `db.transaction(fn)` (auto commit/rollback).
- **Data shapes — `architecture/contracts/shrink-db-schema.md` is the source of truth.** App tables this
  task owns: `link`, `click`, `subscription`, plus a `schema_migrations` tracking table. Times are epoch ms
  (`INTEGER`).
- **`user_id` is a LOGICAL reference, NOT a hard SQLite FK** (Lead decision): Better Auth owns/creates the
  `user` table in T03 via its own init, so at T02 there is no `user` table. Declare `link.user_id TEXT NOT
  NULL` and `subscription.user_id TEXT PRIMARY KEY` with **no** `REFERENCES user(...)` clause — the relation
  is enforced at the app layer later. This also keeps T02 testable in isolation (insert a link with any
  `user_id` string). `click.link_id` **is** a real FK: `REFERENCES link(id) ON DELETE CASCADE`.

# Acceptance criteria (executable)
- [ ] `package.json`: add `better-sqlite3` to runtime `dependencies` (only new runtime dep) and
      `@types/better-sqlite3` to `devDependencies`. `package-lock.json` updated so `npm ci` works.
- [ ] `npm ci && npm run -s ci` is green from inside `components/api`: eslint clean (no `any`,
      `strictTypeChecked`), `tsc --noEmit` clean, tests pass, coverage ≥ **90** on the new `src/db/**`,
      `npm audit --omit=dev --audit-level=high` clean.
- [ ] `src/db/open.ts` exports `openDb(filename?: string)` that: opens the DB (default filename from
      `process.env.DATABASE_PATH ?? 'shrink.db'`), sets `journal_mode = WAL` and `foreign_keys = ON`, runs
      all pending migrations, and returns the typed `Database` handle. `openDb(':memory:')` works.
- [ ] `src/db/migrations.ts`: a runner that ensures `schema_migrations(version INTEGER PRIMARY KEY,
      applied_at INTEGER NOT NULL)`, then applies an **ordered** list of migrations whose `version` is not
      yet recorded, **each inside a transaction** (DDL + its `schema_migrations` insert commit together).
      **Idempotent**: fresh DB → all tables created; running again → no error and no duplicate work.
- [ ] Migration v1 creates, per the contract exactly:
      `link(id INTEGER PK AUTOINCREMENT, user_id TEXT NOT NULL, code TEXT NOT NULL UNIQUE, target_url TEXT
      NOT NULL, created_at INTEGER NOT NULL)` with `INDEX(user_id)`;
      `click(id INTEGER PK AUTOINCREMENT, link_id INTEGER NOT NULL REFERENCES link(id) ON DELETE CASCADE,
      ts INTEGER NOT NULL, referrer TEXT, ua TEXT, ip_hash TEXT)` with `INDEX(link_id, ts)`;
      `subscription(user_id TEXT PRIMARY KEY, stripe_customer_id TEXT, stripe_subscription_id TEXT,
      plan TEXT NOT NULL DEFAULT 'free', status TEXT, current_period_end INTEGER)`.
- [ ] `src/db/types.ts`: exported row types `Link`, `Click`, `Subscription`, and `type Plan = 'free' |
      'pro'`, matching the columns.
- [ ] `src/db/repo.ts`: typed functions (each takes the `Database` handle as the first arg; parameterized
      statements only — never string-interpolate input):
      - links: `insertLink(db, {user_id, code, target_url, created_at}): Link` (returns the inserted row
        incl. `id`); `getLinkByCode(db, code): Link | undefined`; `listLinksByUser(db, user_id): Link[]`;
        `deleteLinkByCodeForUser(db, code, user_id): boolean` (owner-scoped; true iff a row was deleted);
        `countLinksByUser(db, user_id): number`.
      - clicks: `insertClick(db, {link_id, ts, referrer, ua, ip_hash}): void`;
        `countClicksByLink(db, link_id): number`;
        `dailyClickSeries(db, link_id): { date: string; count: number }[]` — group by UTC day via
        `strftime('%Y-%m-%d', ts/1000, 'unixepoch')`, ordered ascending.
      - subscription: `getSubscription(db, user_id): Subscription | undefined`;
        `upsertSubscription(db, sub): void` (`INSERT … ON CONFLICT(user_id) DO UPDATE`);
        `getPlan(db, user_id): Plan` — returns `'pro'` **iff** a `subscription` row exists with
        `status IN ('active','trialing')`, else `'free'` (contract "Plan derivation").
- [ ] `src/db/migrations.test.ts`: migrations create the schema; running `openDb(':memory:')` (or `migrate`)
      twice is a no-op (idempotent); `schema_migrations` records v1.
- [ ] `src/db/repo.test.ts` (in-memory): insert→read a link; UNIQUE(code) is enforced; `countLinksByUser`;
      owner-scoped delete; **cascade** — inserting clicks then `DELETE FROM link` removes the clicks
      (proves `foreign_keys = ON`); `dailyClickSeries` buckets by day; plan derivation across no-row /
      `canceled` (→ free) and `active`/`trialing` (→ pro); a link inserts fine with an arbitrary `user_id`
      string and **no** `user` table present (proves the no-hard-FK decision).

# Out of scope (binding — no gold-plating)
- No HTTP routes, no edits to `src/app.ts` / `src/server.ts` (wiring the DB into the app is T04). No Better
  Auth and no `user`/`session`/`account`/`verification` tables (T03 — Better Auth's own init). No Stripe.
- No POLICY enforcement here: the free-tier 10-link limit and the analytics `pro` gate are route-layer
  (T04–T06). T02 provides the primitives only (`countLinksByUser`, `getPlan`) — it does not reject.
- No short-code generation (that is the `POST /api/links` route, T04 — `insertLink` just stores the `code`).
- No runtime dependency other than `better-sqlite3`. Do NOT touch any file outside `files_allowed`.

# Stop conditions (emit `ESCALATE: <reason>` and halt — do not guess)
- `shrink-db-schema.md` looks wrong or insufficient → ESCALATE (contracts are Lead-owned).
- A config/file genuinely needed is not in `files_allowed` (e.g. you think `vitest.config.ts` must change)
  → ESCALATE (do not create/edit it).
- A needed runtime dependency is not in `deps_preapproved` → ESCALATE (do not add it).

# Working notes (worker appends)
