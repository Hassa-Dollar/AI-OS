# Contract: shrink-db-schema (SQLite)

> Data shapes for Shrink. Owned by the Lead; `components/api` is the only writer. SQLite via
> `better-sqlite3`, WAL mode on. Times are epoch milliseconds (`INTEGER`). Governs ADR-0011.

## Better Auth managed tables (do NOT hand-edit)
Better Auth creates and owns `user`, `session`, `account`, `verification` via its schema/migration tooling.
Treat them as opaque; reference `user.id` by foreign key only. Generate them with the Better Auth CLI/init
during T03; never hand-roll or alter their columns.

## App tables (owned by the migration runner, T02)

### `link`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `user_id` | TEXT NOT NULL | FK → `user.id` (Better Auth) |
| `code` | TEXT NOT NULL UNIQUE | short code (base62, ~7 chars) |
| `target_url` | TEXT NOT NULL | validated http/https |
| `created_at` | INTEGER NOT NULL | epoch ms |

Indexes: `UNIQUE(code)`, `INDEX(user_id)`.

### `click`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `link_id` | INTEGER NOT NULL | FK → `link.id` (ON DELETE CASCADE) |
| `ts` | INTEGER NOT NULL | epoch ms |
| `referrer` | TEXT | nullable |
| `ua` | TEXT | user-agent, nullable |
| `ip_hash` | TEXT | **salted** hash of IP — never store raw IP (PII) |

Indexes: `INDEX(link_id, ts)`.

### `subscription`
| Column | Type | Notes |
|---|---|---|
| `user_id` | TEXT PK | FK → `user.id` |
| `stripe_customer_id` | TEXT | nullable until first checkout |
| `stripe_subscription_id` | TEXT | nullable |
| `plan` | TEXT NOT NULL DEFAULT 'free' | `'free'` \| `'pro'` |
| `status` | TEXT | Stripe status (`active`, `trialing`, `canceled`, …); nullable |
| `current_period_end` | INTEGER | epoch ms, nullable |

## Derived rules
- **Plan derivation:** a user is `pro` **iff** a `subscription` row exists with `status ∈ {active, trialing}`;
  otherwise `free`. `/api/me.plan` returns this.
- **Free limit:** a `free` user may own at most **10** `link` rows (`POST /api/links` → `402 PLAN_LIMIT`).
- **Analytics gate:** analytics endpoints require `pro` (`402 PRO_REQUIRED` for free).
- **Cascade:** deleting a `link` deletes its `click` rows.

## Migrations
A versioned, idempotent runner (T02): applies ordered SQL, tracks applied versions in a
`schema_migrations` table, safe to re-run (fresh DB → all tables; re-run → no-op). Better Auth tables are
created by Better Auth's own init, ordered before app migrations that FK to `user`.
