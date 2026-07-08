import Database from "better-sqlite3";
import type { Database as DB } from "better-sqlite3";
import { betterAuth } from "better-auth";
import type { BetterAuthOptions } from "better-auth";
import { getMigrations } from "better-auth/db/migration";

export type Auth = ReturnType<typeof betterAuth>;

const WEB_ORIGIN = "http://localhost:5173";

function requireDbPath(): string {
  const path = process.env.DATABASE_PATH;
  if (!path) {
    throw new Error("DATABASE_PATH is required (set it in .env)");
  }
  return path;
}

function authOptions(db: DB): BetterAuthOptions {
  return {
    database: db,
    emailAndPassword: { enabled: true },
    secret: process.env.BETTER_AUTH_SECRET,
    baseURL: process.env.BETTER_AUTH_URL ?? "http://localhost:8787",
    trustedOrigins: [WEB_ORIGIN],
  };
}

let cached: { path: string; instance: Auth } | null = null;

export function getAuth(): Auth {
  const path = requireDbPath();
  if (cached && cached.path === path) return cached.instance;
  const instance = betterAuth(authOptions(new Database(path)));
  cached = { path, instance };
  return instance;
}

export async function migrateAuthSchema(): Promise<void> {
  const db = new Database(requireDbPath());
  try {
    db.pragma("journal_mode = WAL");
    db.pragma("foreign_keys = ON");
    const { runMigrations } = await getMigrations(authOptions(db));
    await runMigrations();
  } finally {
    db.close();
  }
}
