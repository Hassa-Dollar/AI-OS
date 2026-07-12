import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import type { Database as DB } from "better-sqlite3";
import { app } from "./app.js";
import { migrateAuthSchema, getAuth } from "./auth.js";
import { openDb } from "./db/open.js";
import { upsertSubscription } from "./db/repo.js";

// Per-run temp dir under os.tmpdir(), which always exists. The previous hardcoded
// "/tmp/opencode/..." only exists on hosts where OpenCode has run; the clean CI runner
// has no such dir, so better-sqlite3 threw "directory does not exist". mkdtemp also
// isolates parallel runs (closes the verifier's collision note).
const DB_DIR = mkdtempSync(join(tmpdir(), "t3-auth-"));
const DB_PATH = join(DB_DIR, "auth.test.db");
const WEB_ORIGIN = "http://localhost:5173";
const PASSWORD = "password12345";

function cookieJar() {
  const jar: Record<string, string> = {};
  const carry = (res: Response): void => {
    for (const c of res.headers.getSetCookie()) {
      const [nv] = c.split(";");
      const eq = nv.indexOf("=");
      if (eq > 0) jar[nv.slice(0, eq)] = nv.slice(eq + 1);
    }
  };
  const header = (): string =>
    Object.entries(jar)
      .map(([k, v]) => `${k}=${v}`)
      .join("; ");
  return { carry, header };
}

async function signUpAndIn(email: string): Promise<string> {
  const { carry, header } = cookieJar();
  const res = await app.request("/api/auth/sign-up/email", {
    method: "POST",
    headers: { "content-type": "application/json", origin: WEB_ORIGIN },
    body: JSON.stringify({ name: "Test User", email, password: PASSWORD }),
  });
  expect(res.status).toBe(200);
  carry(res);
  const signIn = await app.request("/api/auth/sign-in/email", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      origin: WEB_ORIGIN,
      cookie: header(),
    },
    body: JSON.stringify({ email, password: PASSWORD }),
  });
  expect(signIn.status).toBe(200);
  carry(signIn);
  return header();
}

describe("auth + GET /api/me", () => {
  let db: DB;

  beforeAll(async () => {
    process.env.DATABASE_PATH = DB_PATH;
    process.env.BETTER_AUTH_SECRET = randomUUID(); // runtime-generated — never commit a secret literal (§8/gitleaks)
    process.env.BETTER_AUTH_URL = "http://localhost:8787";
    db = openDb();
    await migrateAuthSchema();
  });

  afterAll(() => {
    db.close();
    rmSync(DB_DIR, { recursive: true, force: true }); // whole dir: db + -wal + -shm
  });

  it("sign-up then sign-in establishes a session; GET /api/me → 200 free", async () => {
    const email = `u1-${randomUUID()}@test.dev`;
    const cookie = await signUpAndIn(email);
    const res = await app.request("/api/me", { headers: { cookie } });
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      user: { id: string; email: string };
      plan: string;
    };
    expect(body.user.email).toBe(email);
    expect(body.user.id).toBeTruthy();
    expect(body.plan).toBe("free");
  });

  it("GET /api/me reflects plan: pro after an active subscription", async () => {
    const email = `u2-${randomUUID()}@test.dev`;
    const cookie = await signUpAndIn(email);

    const before = await app.request("/api/me", { headers: { cookie } });
    expect(before.status).toBe(200);
    const beforeBody = (await before.json()) as {
      user: { id: string };
      plan: string;
    };
    expect(beforeBody.plan).toBe("free");

    upsertSubscription(db, {
      user_id: beforeBody.user.id,
      stripe_customer_id: "cust_test",
      stripe_subscription_id: "sub_test",
      plan: "pro",
      status: "active",
      current_period_end: Date.now() + 86_400_000,
    });

    const after = await app.request("/api/me", { headers: { cookie } });
    expect(after.status).toBe(200);
    const afterBody = (await after.json()) as { plan: string };
    expect(afterBody.plan).toBe("pro");
  });

  it("GET /api/me with no session → 401 UNAUTHENTICATED", async () => {
    const res = await app.request("/api/me");
    expect(res.status).toBe(401);
    const body = (await res.json()) as {
      error: { code: string; message: string };
    };
    expect(body.error.code).toBe("UNAUTHENTICATED");
  });

  it("CORS allows the web origin with credentials on /api/auth/*", async () => {
    const res = await app.request("/api/auth/sign-in/email", {
      method: "OPTIONS",
      headers: {
        origin: WEB_ORIGIN,
        "access-control-request-method": "POST",
        "access-control-request-headers": "content-type",
      },
    });
    expect(res.status).toBe(204);
    expect(res.headers.get("access-control-allow-origin")).toBe(WEB_ORIGIN);
    expect(res.headers.get("access-control-allow-credentials")).toBe("true");
  });

  it("getAuth() throws if DATABASE_PATH is missing — no silent DB fallback", () => {
    const saved = process.env.DATABASE_PATH;
    delete process.env.DATABASE_PATH;
    try {
      expect(() => getAuth()).toThrow(/DATABASE_PATH is required/);
    } finally {
      process.env.DATABASE_PATH = saved;
    }
  });
});
