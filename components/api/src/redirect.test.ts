import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { mkdtempSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import type { Database as DB } from "better-sqlite3";
import { app, getDb } from "./app.js";
import { migrateAuthSchema } from "./auth.js";
import { openDb } from "./db/open.js";
import { insertLink, countClicksByLink } from "./db/repo.js";
import type { Click } from "./db/types.js";

const BASE_URL = "http://localhost:8787";
const DB_DIR = mkdtempSync(join(tmpdir(), "t5-redirect-"));
const DB_PATH = join(DB_DIR, "redirect.test.db");

describe("redirect", () => {
  let db: DB;
  const savedIpHashSalt = process.env.IP_HASH_SALT;

  beforeAll(async () => {
    process.env.DATABASE_PATH = DB_PATH;
    process.env.BASE_URL = BASE_URL;
    process.env.BETTER_AUTH_SECRET = randomUUID();
    process.env.BETTER_AUTH_URL = "http://localhost:8787";
    process.env.IP_HASH_SALT = "test-salt-for-redirect-tests";
    const initDb = openDb();
    await migrateAuthSchema();
    initDb.close();
    db = getDb();
  });

  afterAll(() => {
    if (savedIpHashSalt === undefined) delete process.env.IP_HASH_SALT;
    else process.env.IP_HASH_SALT = savedIpHashSalt;
    rmSync(DB_DIR, { recursive: true, force: true });
  });

  afterEach(() => {
    db.prepare("DELETE FROM click").run();
  });

  describe("GET /:code — successful redirect", () => {
    it("302 with Location header, empty body, and a click row", async () => {
      const link = insertLink(db, {
        user_id: "u1",
        code: "abc1234",
        target_url: "https://example.com/target",
        created_at: Date.now(),
      });

      const res = await app.request("/abc1234", {
        headers: {
          "x-forwarded-for": "192.168.1.100",
          "referer": "https://referrer.com",
          "user-agent": "TestAgent/1.0",
        },
      });

      expect(res.status).toBe(302);
      expect(res.headers.get("location")).toBe("https://example.com/target");
      const body = await res.text();
      expect(body).toBe("");

      const clicks = db
        .prepare("SELECT * FROM click WHERE link_id = ?")
        .all(link.id) as Click[];
      expect(clicks).toHaveLength(1);
      const click = clicks[0];
      expect(click.link_id).toBe(link.id);
      expect(click.ts).toBeGreaterThan(0);
      expect(click.ts).toBeLessThanOrEqual(Date.now());
      expect(click.referrer).toBe("https://referrer.com");
      expect(click.ua).toBe("TestAgent/1.0");
      expect(click.ip_hash).not.toContain("192.168.1.100");
      expect(click.ip_hash).toMatch(/^[a-f0-9]{64}$/);
    });

    it("records click with null referrer and ua when headers absent", async () => {
      const link = insertLink(db, {
        user_id: "u1",
        code: "def5678",
        target_url: "https://example.com/",
        created_at: Date.now(),
      });

      const res = await app.request("/def5678", {
        headers: { "x-forwarded-for": "10.0.0.1" },
      });

      expect(res.status).toBe(302);
      const clicks = db
        .prepare("SELECT * FROM click WHERE link_id = ?")
        .all(link.id) as Click[];
      expect(clicks).toHaveLength(1);
      expect(clicks[0].referrer).toBeNull();
      expect(clicks[0].ua).toBeNull();
    });

    it("ip_hash is a salted hash — raw IP appears nowhere in the DB", async () => {
      const rawIp = "203.0.113.42";
      insertLink(db, {
        user_id: "u1",
        code: "priv000",
        target_url: "https://example.com/",
        created_at: Date.now(),
      });

      await app.request("/priv000", {
        headers: { "x-forwarded-for": rawIp },
      });

      const dbFileContent = readFileSync(DB_PATH, "utf8");
      expect(dbFileContent).not.toContain(rawIp);

      const clicks = db.prepare("SELECT * FROM click").all() as Click[];
      for (const click of clicks) {
        expect(click.ip_hash).not.toContain(rawIp);
      }
    });
  });

  describe("GET /:code — unknown code", () => {
    it("404 NOT_FOUND with no click row", async () => {
      const res = await app.request("/NOPE999", {
        headers: { "x-forwarded-for": "1.2.3.4" },
      });

      expect(res.status).toBe(404);
      const body = (await res.json()) as { error: { code: string } };
      expect(body.error.code).toBe("NOT_FOUND");

      const clickCount = db.prepare("SELECT COUNT(*) AS n FROM click").get() as {
        n: number;
      };
      expect(clickCount.n).toBe(0);
    });
  });

  describe("reserved paths", () => {
    it("/healthz still returns 200", async () => {
      const res = await app.request("/healthz");
      expect(res.status).toBe(200);
      const body = (await res.json()) as { status: string };
      expect(body.status).toBe("ok");
    });

    it("/api/me still routes (401 without auth)", async () => {
      const res = await app.request("/api/me");
      expect(res.status).toBe(401);
    });

    it("/favicon.ico returns 404 without a click row", async () => {
      const res = await app.request("/favicon.ico", {
        headers: { "x-forwarded-for": "1.2.3.4" },
      });
      expect(res.status).toBe(404);

      const clickCount = db.prepare("SELECT COUNT(*) AS n FROM click").get() as {
        n: number;
      };
      expect(clickCount.n).toBe(0);
    });

    it("/api (exact) returns 404 without a click row", async () => {
      const res = await app.request("/api", {
        headers: { "x-forwarded-for": "1.2.3.4" },
      });
      expect(res.status).toBe(404);

      const clickCount = db.prepare("SELECT COUNT(*) AS n FROM click").get() as {
        n: number;
      };
      expect(clickCount.n).toBe(0);
    });

    it("/assets returns 404 without a click row", async () => {
      const res = await app.request("/assets", {
        headers: { "x-forwarded-for": "1.2.3.4" },
      });
      expect(res.status).toBe(404);

      const clickCount = db.prepare("SELECT COUNT(*) AS n FROM click").get() as {
        n: number;
      };
      expect(clickCount.n).toBe(0);
    });
  });

  describe("integration: click_count in GET /api/links", () => {
    it("two hits on the same code → click_count = 2", async () => {
      const link = insertLink(db, {
        user_id: "u-int",
        code: "int0001",
        target_url: "https://example.com/int",
        created_at: Date.now(),
      });

      await app.request("/int0001", {
        headers: { "x-forwarded-for": "1.1.1.1" },
      });
      await app.request("/int0001", {
        headers: { "x-forwarded-for": "2.2.2.2" },
      });

      expect(countClicksByLink(db, link.id)).toBe(2);
    });
  });

  describe("IP_HASH_SALT required", () => {
    it("throws when IP_HASH_SALT is unset", async () => {
      const savedSalt = process.env.IP_HASH_SALT;
      delete process.env.IP_HASH_SALT;

      try {
        insertLink(db, {
          user_id: "u1",
          code: "salt000",
          target_url: "https://example.com/",
          created_at: Date.now(),
        });

        const res = await app.request("/salt000", {
          headers: { "x-forwarded-for": "1.2.3.4" },
        });
        expect(res.status).toBe(500);
      } finally {
        process.env.IP_HASH_SALT = savedSalt;
      }
    });
  });

  describe("x-forwarded-for parsing", () => {
    it("uses the first IP from x-forwarded-for", async () => {
      const link = insertLink(db, {
        user_id: "u1",
        code: "xff0001",
        target_url: "https://example.com/",
        created_at: Date.now(),
      });

      await app.request("/xff0001", {
        headers: { "x-forwarded-for": "203.0.113.1, 70.41.3.18, 150.172.238.178" },
      });

      const clicks = db
        .prepare("SELECT * FROM click WHERE link_id = ?")
        .all(link.id) as Click[];
      expect(clicks).toHaveLength(1);
      expect(clicks[0].ip_hash).not.toContain("203.0.113.1");
    });
  });
});
