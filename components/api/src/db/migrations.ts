import type { Database } from "better-sqlite3";

interface Migration {
  version: number;
  sql: string;
}

const migrations: ReadonlyArray<Migration> = [
  {
    version: 1,
    sql: `
      CREATE TABLE IF NOT EXISTS link (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        code TEXT NOT NULL UNIQUE,
        target_url TEXT NOT NULL,
        created_at INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_link_user_id ON link (user_id);

      CREATE TABLE IF NOT EXISTS click (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link_id INTEGER NOT NULL REFERENCES link (id) ON DELETE CASCADE,
        ts INTEGER NOT NULL,
        referrer TEXT,
        ua TEXT,
        ip_hash TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_click_link_id_ts ON click (link_id, ts);

      CREATE TABLE IF NOT EXISTS subscription (
        user_id TEXT PRIMARY KEY,
        stripe_customer_id TEXT,
        stripe_subscription_id TEXT,
        plan TEXT NOT NULL DEFAULT 'free',
        status TEXT,
        current_period_end INTEGER
      );
    `,
  },
];

function ensureMigrationsTable(db: Database): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version INTEGER PRIMARY KEY,
      applied_at INTEGER NOT NULL
    );
  `);
}

export function migrate(db: Database): void {
  ensureMigrationsTable(db);

  const applied = new Set<number>(
    db
      .prepare("SELECT version FROM schema_migrations")
      .all()
      .map((row) => (row as { version: number }).version),
  );

  for (const migration of migrations) {
    if (applied.has(migration.version)) continue;
    const apply = db.transaction(() => {
      db.exec(migration.sql);
      db.prepare(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
      ).run(migration.version, Date.now());
    });
    apply();
  }
}