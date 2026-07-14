import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { app } from "./app.js";
import { migrateAuthSchema } from "./auth.js";
import { openDb } from "./db/open.js";
import { insertLink } from "./db/repo.js";
import { generateUniqueCode, randomCode } from "./links.js";

const WEB_ORIGIN = "http://localhost:5173";
const BASE_URL = "http://localhost:8787";
const PASSWORD = "password12345";
// Always a fresh temp dir under os.tmpdir() — never a hardcoded /tmp path (BUG-29).
const DB_DIR = mkdtempSync(join(tmpdir(), "t4-links-"));
const DB_PATH = join(DB_DIR, "links.test.db");

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

function authHeaders(cookie: string) {
  return { "content-type": "application/json", cookie };
}

describe("links CRUD", () => {
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

  describe("POST /api/links", () => {
    it("401 without a session", async () => {
      const res = await app.request("/api/links", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ target_url: "https://example.com" }),
      });
      expect(res.status).toBe(401);
      const body = (await res.json()) as { error: { code: string } };
      expect(body.error.code).toBe("UNAUTHENTICATED");
    });

    it("400 INVALID_INPUT when target_url is absent", async () => {
      const cookie = await signUpAndIn(`a-${randomUUID()}@test.dev`);
      const res = await app.request("/api/links", {
        method: "POST",
        headers: authHeaders(cookie),
        body: JSON.stringify({}),
      });
      expect(res.status).toBe(400);
      const body = (await res.json()) as { error: { code: string } };
      expect(body.error.code).toBe("INVALID_INPUT");
    });

    it("400 INVALID_INPUT when target_url is not a string", async () => {
      const cookie = await signUpAndIn(`b-${randomUUID()}@test.dev`);
      const res = await app.request("/api/links", {
        method: "POST",
        headers: authHeaders(cookie),
        body: JSON.stringify({ target_url: 123 }),
      });
      expect(res.status).toBe(400);
      const body = (await res.json()) as { error: { code: string } };
      expect(body.error.code).toBe("INVALID_INPUT");
    });

    it("400 INVALID_INPUT when target_url is not http/https", async () => {
      const cookie = await signUpAndIn(`c-${randomUUID()}@test.dev`);
      const res = await app.request("/api/links", {
        method: "POST",
        headers: authHeaders(cookie),
        body: JSON.stringify({ target_url: "ftp://example.com" }),
      });
      expect(res.status).toBe(400);
      const body = (await res.json()) as { error: { code: string } };
      expect(body.error.code).toBe("INVALID_INPUT");
    });

    it("201 with a 7-char base62 code, short_url, target_url, created_at", async () => {
      const cookie = await signUpAndIn(`d-${randomUUID()}@test.dev`);
      const res = await app.request("/api/links", {
        method: "POST",
        headers: authHeaders(cookie),
        body: JSON.stringify({ target_url: "https://example.com/p" }),
      });
      expect(res.status).toBe(201);
      const body = (await res.json()) as {
        code: string;
        short_url: string;
        target_url: string;
        created_at: number;
      };
      expect(body.code).toMatch(/^[0-9A-Za-z]{7}$/);
      expect(body.short_url).toBe(`${BASE_URL}/${body.code}`);
      expect(body.target_url).toBe("https://example.com/p");
      expect(body.created_at).toBeGreaterThan(0);
    });
  });

  describe("free-plan limit boundary", () => {
    it("the 10th link succeeds and the 11th gets 402 PLAN_LIMIT", async () => {
      const cookie = await signUpAndIn(`e-${randomUUID()}@test.dev`);
      for (let i = 0; i < 10; i++) {
        const res = await app.request("/api/links", {
          method: "POST",
          headers: authHeaders(cookie),
          body: JSON.stringify({ target_url: `https://example.com/${String(i)}` }),
        });
        expect(res.status).toBe(201);
      }
      const eleventh = await app.request("/api/links", {
        method: "POST",
        headers: authHeaders(cookie),
        body: JSON.stringify({ target_url: "https://example.com/11" }),
      });
      expect(eleventh.status).toBe(402);
      const body = (await eleventh.json()) as { error: { code: string } };
      expect(body.error.code).toBe("PLAN_LIMIT");
    });
  });

  describe("GET /api/links", () => {
    it("401 without a session", async () => {
      const res = await app.request("/api/links");
      expect(res.status).toBe(401);
    });

    it("returns only the caller's links, each with click_count (0 for fresh); isolates users", async () => {
      const userA = await signUpAndIn(`f-${randomUUID()}@test.dev`);
      const userB = await signUpAndIn(`g-${randomUUID()}@test.dev`);

      // user A creates two links; user B creates one
      for (let i = 0; i < 2; i++) {
        await app.request("/api/links", {
          method: "POST",
          headers: authHeaders(userA),
          body: JSON.stringify({ target_url: `https://a.example/${String(i)}` }),
        });
      }
      const created = await app.request("/api/links", {
        method: "POST",
        headers: authHeaders(userB),
        body: JSON.stringify({ target_url: "https://b.example/" }),
      });
      const createdBody = (await created.json()) as { code: string };

      const aRes = await app.request("/api/links", { headers: { cookie: userA } });
      expect(aRes.status).toBe(200);
      const aLinks = (await aRes.json()) as {
        code: string;
        short_url: string;
        target_url: string;
        created_at: number;
        click_count: number;
      }[];
      expect(aLinks).toHaveLength(2);
      expect(aLinks.every((l) => l.click_count === 0)).toBe(true);
      expect(aLinks.every((l) => l.target_url.startsWith("https://a.example"))).toBe(true);

      const bRes = await app.request("/api/links", { headers: { cookie: userB } });
      expect(bRes.status).toBe(200);
      const bLinks = (await bRes.json()) as { code: string }[];
      expect(bLinks).toHaveLength(1);
      expect(bLinks[0].code).toBe(createdBody.code);
    });
  });

  describe("DELETE /api/links/:code", () => {
    it("401 without a session", async () => {
      const res = await app.request("/api/links/whatever", { method: "DELETE" });
      expect(res.status).toBe(401);
    });

    it("404 NOT_FOUND for an unknown code", async () => {
      const cookie = await signUpAndIn(`h-${randomUUID()}@test.dev`);
      const res = await app.request("/api/links/NOPE000", {
        method: "DELETE",
        headers: { cookie },
      });
      expect(res.status).toBe(404);
      const body = (await res.json()) as { error: { code: string } };
      expect(body.error.code).toBe("NOT_FOUND");
    });

    it("403 FORBIDDEN when another user owns the link, 204 for the owner (row gone)", async () => {
      const owner = await signUpAndIn(`i-${randomUUID()}@test.dev`);
      const intruder = await signUpAndIn(`j-${randomUUID()}@test.dev`);
      const created = await app.request("/api/links", {
        method: "POST",
        headers: authHeaders(owner),
        body: JSON.stringify({ target_url: "https://example.com/own" }),
      });
      expect(created.status).toBe(201);
      const { code } = (await created.json()) as { code: string };

      const forbidden = await app.request(`/api/links/${code}`, {
        method: "DELETE",
        headers: { cookie: intruder },
      });
      expect(forbidden.status).toBe(403);
      const fBody = (await forbidden.json()) as { error: { code: string } };
      expect(fBody.error.code).toBe("FORBIDDEN");

      // still present (intruder delete was refused)
      const own = await app.request("/api/links", { headers: { cookie: owner } });
      const ownBody = (await own.json()) as { code: string }[];
      expect(ownBody.some((l) => l.code === code)).toBe(true);

      const ok = await app.request(`/api/links/${code}`, {
        method: "DELETE",
        headers: { cookie: owner },
      });
      expect(ok.status).toBe(204);
      expect(await ok.text()).toBe("");

      // row is gone
      const after = await app.request("/api/links", { headers: { cookie: owner } });
      const afterBody = (await after.json()) as { code: string }[];
      expect(afterBody.some((l) => l.code === code)).toBe(false);

      // owner re-deleting their own (now-gone) code → 404
      const again = await app.request(`/api/links/${code}`, {
        method: "DELETE",
        headers: { cookie: owner },
      });
      expect(again.status).toBe(404);
    });
  });

  describe("code generation", () => {
    it("randomCode is 7 base62 chars", () => {
      for (let i = 0; i < 20; i++) {
        expect(randomCode()).toMatch(/^[0-9A-Za-z]{7}$/);
      }
    });

    it("generateUniqueCode retries past an existing code (collision retry)", () => {
      const db = openDb(":memory:");
      try {
        insertLink(db, {
          user_id: "seed",
          code: "AAAAAAA",
          target_url: "https://x.example",
          created_at: 1,
        });
        const queue = ["AAAAAAA", "BBBBBBB"];
        const code = generateUniqueCode(db, () => {
          const next = queue.shift();
          if (next === undefined) throw new Error("test exhausted");
          return next;
        });
        expect(code).toBe("BBBBBBB");
      } finally {
        db.close();
      }
    });
  });
});