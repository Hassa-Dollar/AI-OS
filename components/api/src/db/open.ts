import Database from "better-sqlite3";
import type { Database as DB } from "better-sqlite3";
import { migrate } from "./migrations.js";

export function openDb(filename?: string): DB {
  const path = filename ?? process.env.DATABASE_PATH ?? "shrink.db";
  const db = new Database(path);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
  migrate(db);
  return db;
}