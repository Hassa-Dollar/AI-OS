# T02 — db-layer (completion report)

- **Task:** T02 / `db-layer`
- **Branch:** `task/T02-db-layer`
- **Model:** opencode-go/glm-5.2 (implementer)
- **Status:** DONE — all acceptance criteria met; local gates green.

## What was built
Shrink persistence layer on `better-sqlite3` (v12, synchronous) inside `components/api`:

- `src/db/types.ts` — row types `Link`, `Click`, `Subscription`, and `type Plan = 'free' | 'pro'`.
- `src/db/migrations.ts` — versioned, idempotent migration runner. v1 creates `link`, `click`, `subscription` per `shrink-db-schema.md`; tracks applied versions in `schema_migrations(version INTEGER PK, applied_at INTEGER)`. Each migration runs inside a `db.transaction` so DDL + version-insert commit together. Idempotent via `IF NOT EXISTS` + skip-already-applied.
- `src/db/open.ts` — `openDb(filename?)`: `process.env.DATABASE_PATH ?? 'shrink.db'`, sets `journal_mode = WAL` + `foreign_keys = ON`, runs pending migrations, returns the typed handle. `:memory:` works.
- `src/db/repo.ts` — typed data access, every statement parameterized:
  - links: `insertLink` (returns inserted row incl. `id`), `getLinkByCode`, `listLinksByUser`, `deleteLinkByCodeForUser` (owner-scoped, `boolean`), `countLinksByUser`.
  - clicks: `insertClick`, `countClicksByLink`, `dailyClickSeries` (group by UTC day via `strftime('%Y-%m-%d', ts/1000, 'unixepoch')`, ASC).
  - subscription: `getSubscription`, `upsertSubscription` (`ON CONFLICT(user_id) DO UPDATE`), `getPlan` (`'pro'` iff row exists with `status ∈ {active, trialing}`, else `'free'`).
- Tests: `migrations.test.ts` (5), `repo.test.ts` (10).

## Contract decisions honored
- `link.user_id` and `subscription.user_id` are **logical** references (no `REFERENCES user(...)` clause) — Better Auth owns the `user` table in T03; keeps T02 testable in isolation. `click.link_id` **is** a real FK with `ON DELETE CASCADE`.
- No HTTP routes, no app/server wiring, no Better Auth, no Stripe. No POLICY enforcement (free-tier limit / analytics gate are route-layer T04–T06). `insertLink` only stores the provided `code`.

## Dependency / config changes
- `package.json`: added `better-sqlite3` to `dependencies`; added `@types/better-sqlite3` to `devDependencies`; extended the `ci` script to also run `npm audit --omit=dev --audit-level=high` (per task context).
- `package-lock.json`: regenerated for the new deps.
- No file outside `files_allowed` was modified.

## Local gates (run from `components/api`)
`npm run -s ci` is green:
- `eslint .` — clean (no `any`; `strictTypeChecked`).
- `tsc --noEmit` — clean.
- `vitest run` — 16/16 tests pass.
- coverage (thresholds 90 for lines/functions/branches/statements on `src/**`):
  - All files: Stmts 100% · Branch 92.3% · Funcs 100% · Lines 100%.
  - `src/db`: migrations 100/100/100/100, repo 100, open 100 lines, types 0 (pure type file, no runtime statements).
- `npm audit --omit=dev --audit-level=high` — `found 0 vulnerabilities`.

## Out of scope
Per spec: no HTTP routes, `src/app.ts`/`src/server.ts` untouched, no Better Auth or `user`/`session`/`account`/`verification` tables, no Stripe, no plan-limit/PRO enforcement, no short-code generation. T02 provides primitives only.

## Notes for downstream tasks
- T04+ should call `openDb()` at app start to get the shared handle; `foreign_keys = ON` is already set inside `openDb`, so the click→link cascade works for any connection opened via `openDb`.
- `getPlan` and `countLinksByUser` are the primitives the route layer (T04–T06) will compose for the 10-link free limit and the analytics `pro` gate.