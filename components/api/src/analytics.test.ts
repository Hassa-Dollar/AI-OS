import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { app } from "./app.js";
import { migrateAuthSchema } from "./auth.js";
import { openDb } from "./db/open.js";
import { getLinkByCode } from "./db/repo.js";

const WEB_ORIGIN = "http://localhost:5173";
const BASE_URL = "http://localhost:8787";
const PASSWORD = "password12345";
// Always a fresh temp dir under os.tmpdir() — never a hardcoded /tmp path (BUG-29).
const DB_DIR = mkdtempSync(join(tmpdir(), "t6-analytics-"));
const DB_PATH = join(DB_DIR, "analytics.test.db");

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

async function createLink(cookie: string, target: string): Promise<string> {
  const res = await app.request("/api/links", {
    method: "POST",
    headers: { "content-type": "application/json", cookie },
    body: JSON.stringify({ target_url: target }),
  });
  expect(res.status).toBe(201);
  const body = (await res.json()) as { code: string };
  return body.code;
}

async function userId(cookie: string): Promise<string> {
  const me = await app.request("/api/me", { headers: { cookie } });
  expect(me.status).toBe(200);
  const body = (await me.json()) as { user: { id: string } };
  return body.user.id;
}

describe("GET /api/links/:code/analytics", () => {
  beforeAll(async () => {
    process.env.DATABASE_PATH = DB_PATH;
    process.env.BASE_URL = BASE_URL;
    process.env.BETTER_AUTH_SECRET = randomUUID();
    process.env.BETTER_AUTH_URL = "http://localhost:8787";
    const db = openDb();
    await migrateAuthSchema();
    db.close();
  });

  afterAll(() => {
    rmSync(DB_DIR, { recursive: true, force: true }); // db + -wal + -shm
  });

  it("401 without a session", async () => {
    const res = await app.request("/api/links/whatever/analytics");
    expect(res.status).toBe(401);
    const body = (await res.json()) as { error: { code: string } };
    expect(body.error.code).toBe("UNAUTHENTICATED");
  });

  it("404 NOT_FOUND for an unknown code", async () => {
    const cookie = await signUpAndIn(`a-${randomUUID()}@test.dev`);
    const res = await app.request("/api/links/NOPE000/analytics", {
      headers: { cookie },
    });
    expect(res.status).toBe(404);
    const body = (await res.json()) as { error: { code: string } };
    expect(body.error.code).toBe("NOT_FOUND");
  });

  it("403 FORBIDDEN when another user owns the link", async () => {
    const owner = await signUpAndIn(`b-${randomUUID()}@test.dev`);
    const intruder = await signUpAndIn(`c-${randomUUID()}@test.dev`);
    const code = await createLink(owner, "https://example.com/own");

    const res = await app.request(`/api/links/${code}/analytics`, {
      headers: { cookie: intruder },
    });
    expect(res.status).toBe(403);
    const body = (await res.json()) as { error: { code: string } };
    expect(body.error.code).toBe("FORBIDDEN");
  });

  it("402 PRO_REQUIRED for the owner on the free plan (clear JSON body)", async () => {
    const owner = await signUpAndIn(`d-${randomUUID()}@test.dev`);
    const code = await createLink(owner, "https://example.com/free");

    const res = await app.request(`/api/links/${code}/analytics`, {
      headers: { cookie: owner },
    });
    expect(res.status).toBe(402);
    const body = (await res.json()) as { error: { code: string; message: string } };
    expect(body.error.code).toBe("PRO_REQUIRED");
    expect(body.error.message).toMatch(/pro/i);
  });

  it("Pro owner: 200 with code, total_clicks, and ascending multi-day series", async () => {
    const cookie = await signUpAndIn(`e-${randomUUID()}@test.dev`);
    const uid = await userId(cookie);
    const code = await createLink(cookie, "https://example.com/pro");

    const db = openDb();
    const link = getLinkByCode(db, code);
    if (link === undefined) throw new Error("setup link missing");

    // Activate a Pro subscription for this user (test fabricates the row directly).
    db.prepare(
      `INSERT INTO subscription (user_id, stripe_customer_id, stripe_subscription_id, plan, status, current_period_end)
       VALUES (?, ?, ?, ?, ?, ?)`,
    ).run(uid, "cust_test", "sub_test", "pro", "active", Date.now() + 86_400_000);

    // Backdated clicks spanning 2 distinct UTC days; counts must reflect exactly.
    const day1A = Date.UTC(2026, 5, 10, 2, 0, 0);
    const day1B = Date.UTC(2026, 5, 10, 23, 30, 0);
    const day2 = Date.UTC(2026, 5, 11, 5, 0, 0);
    for (const ts of [day1A, day1B, day2]) {
      db.prepare(
        "INSERT INTO click (link_id, ts, referrer, ua, ip_hash) VALUES (?, ?, ?, ?, ?)",
      ).run(link.id, ts, null, null, null);
    }
    db.close();

    const res = await app.request(`/api/links/${code}/analytics`, {
      headers: { cookie },
    });
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      code: string;
      total_clicks: number;
      series: { date: string; count: number }[];
    };
    expect(body.code).toBe(code);
    expect(body.total_clicks).toBe(3);
    expect(body.series).toEqual([
      { date: "2026-06-10", count: 2 },
      { date: "2026-06-11", count: 1 },
    ]);
    // ascending by date
    const dates = body.series.map((s) => s.date);
    expect([...dates].sort()).toEqual(dates);
  });

  it("Pro owner with zero clicks: 200 with total_clicks 0 and empty series", async () => {
    const cookie = await signUpAndIn(`f-${randomUUID()}@test.dev`);
    const uid = await userId(cookie);
    const code = await createLink(cookie, "https://example.com/empty");

    const db = openDb();
    db.prepare(
      `INSERT INTO subscription (user_id, stripe_customer_id, stripe_subscription_id, plan, status, current_period_end)
       VALUES (?, ?, ?, ?, ?, ?)`,
    ).run(uid, "cust_test", "sub_test", "pro", "active", Date.now() + 86_400_000);
    db.close();

    const res = await app.request(`/api/links/${code}/analytics`, {
      headers: { cookie },
    });
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      code: string;
      total_clicks: number;
      series: { date: string; count: number }[];
    };
    expect(body.code).toBe(code);
    expect(body.total_clicks).toBe(0);
    expect(body.series).toEqual([]);
  });
});