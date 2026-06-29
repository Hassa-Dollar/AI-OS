import { describe, it, expect } from "vitest";
import Database from "better-sqlite3";
import type { Database as DB } from "better-sqlite3";
import { migrate } from "./migrations.js";
import { openDb } from "./open.js";

function tableNames(db: DB): string[] {
  const rows = db
    .prepare(
      "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name",
    )
    .all() as { name: string }[];
  return rows.map((r) => r.name);
}

describe("migrations", () => {
  it("creates the app tables and schema_migrations", () => {
    const db = new Database(":memory:");
    db.pragma("foreign_keys = ON");
    migrate(db);
    const tables = tableNames(db);
    expect(tables).toContain("link");
    expect(tables).toContain("click");
    expect(tables).toContain("subscription");
    expect(tables).toContain("schema_migrations");
    db.close();
  });

  it("records migration v1 in schema_migrations", () => {
    const db = new Database(":memory:");
    migrate(db);
    const row = db
      .prepare("SELECT version FROM schema_migrations")
      .get() as { version: number };
    expect(row.version).toBe(1);
    db.close();
  });

  it("is idempotent — running migrate twice is a no-op", () => {
    const db = new Database(":memory:");
    migrate(db);
    migrate(db);
    const versions = db
      .prepare("SELECT version FROM schema_migrations ORDER BY version")
      .all() as { version: number }[];
    expect(versions.length).toBe(1);
    expect(versions[0].version).toBe(1);
    db.close();
  });

  it("openDb(':memory:') runs migrations and returns a handle", () => {
    const db = openDb(":memory:");
    const tables = tableNames(db);
    expect(tables).toContain("link");
    expect(tables).toContain("click");
    expect(tables).toContain("subscription");
    db.close();
  });

  it("enables foreign keys", () => {
    const db = openDb(":memory:");
    const fk = db.pragma("foreign_keys", { simple: true });
    expect(fk).toBe(1);
    db.close();
  });
});