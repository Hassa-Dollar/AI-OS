import Database from "better-sqlite3";
import type { Database as DB } from "better-sqlite3";
import { migrate } from "./migrations.js";

// Fail loud: a missing DB path must never silently fall back to a cwd-relative
// "shrink.db" (BUG-29 family). Either pass an explicit filename or set DATABASE_PATH.
export function openDb(filename?: string): DB {
  const path = filename ?? process.env.DATABASE_PATH;
  if (!path) {
    throw new Error(
      "DATABASE_PATH is required (set it in .env or pass an explicit filename)",
    );
  }
  const db = new Database(path);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
  migrate(db);
  return db;
}