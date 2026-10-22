// SH-2 hidden acceptance: CORS on every /api route + Better Auth trustedOrigins, both driven by WEB_ORIGIN.
import { beforeAll, describe, expect, it } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

const ORIGIN = "http://app.example.test";
type App = { request: (path: string, init?: RequestInit) => Response | Promise<Response> };
let app: App;

beforeAll(async () => {
  process.env.DATABASE_PATH = join(mkdtempSync(join(tmpdir(), "sh2-acc-")), "db.sqlite");
  process.env.BETTER_AUTH_SECRET = randomUUID();
  process.env.BETTER_AUTH_URL = "http://localhost:8787";
  process.env.WEB_ORIGIN = ORIGIN;
  const auth = await import("./auth.js");
  await auth.migrateAuthSchema();
  app = (await import("./app.js")).app as App;
});

const preflight = (path: string, origin: string) =>
  app.request(path, { method: "OPTIONS", headers: { Origin: origin, "Access-Control-Request-Method": "POST" } });

describe("SH-2 acceptance", () => {
  it("preflight /api/links echoes WEB_ORIGIN with credentials", async () => {
    const r = await preflight("/api/links", ORIGIN);
    expect(r.headers.get("access-control-allow-origin")).toBe(ORIGIN);
    expect(r.headers.get("access-control-allow-credentials")).toBe("true");
  });
  it("preflight from another origin is not echoed", async () => {
    const r = await preflight("/api/links", "http://evil.test");
    expect(r.headers.get("access-control-allow-origin")).not.toBe("http://evil.test");
  });
  it("auth routes still allow WEB_ORIGIN", async () => {
    const r = await preflight("/api/auth/sign-in/email", ORIGIN);
    expect(r.headers.get("access-control-allow-origin")).toBe(ORIGIN);
  });
  it("GET /api/me response carries CORS for WEB_ORIGIN", async () => {
    const r = await app.request("/api/me", { headers: { Origin: ORIGIN } });
    expect(r.headers.get("access-control-allow-origin")).toBe(ORIGIN);
  });
  it("sign-up from WEB_ORIGIN is accepted (trustedOrigins)", async () => {
    const r = await app.request("/api/auth/sign-up/email", {
      method: "POST",
      headers: { "content-type": "application/json", origin: ORIGIN },
      body: JSON.stringify({ name: "A", email: `a${Date.now()}@example.test`, password: "correct-horse-battery-9" }),
    });
    expect(r.status).toBe(200);
  });
  it("/healthz is unaffected (no CORS header)", async () => {
    const r = await app.request("/healthz", { headers: { Origin: ORIGIN } });
    expect(r.headers.get("access-control-allow-origin")).toBeNull();
  });
});
