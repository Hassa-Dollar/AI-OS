import { Hono } from "hono";
import type { Context } from "hono";
import { createHash } from "node:crypto";
import { getDb } from "./app.js";
import { getLinkByCode, insertClick } from "./db/repo.js";

export const redirect = new Hono();

const RESERVED_PATHS = new Set(["api", "healthz", "assets", "favicon.ico"]);

function requireIpHashSalt(): string {
  const salt = process.env.IP_HASH_SALT;
  if (!salt) {
    throw new Error("IP_HASH_SALT is required (set it in .env)");
  }
  return salt;
}

function getClientIp(c: Context): string {
  const xff = c.req.header("x-forwarded-for");
  if (xff) {
    return xff.split(",")[0].trim();
  }
  return "127.0.0.1";
}

function hashIp(salt: string, ip: string): string {
  return createHash("sha256").update(salt + ip).digest("hex");
}

redirect.get("/:code", (c) => {
  const code = c.req.param("code");

  if (RESERVED_PATHS.has(code)) {
    return c.json(
      { error: { code: "NOT_FOUND", message: "Not found." } },
      404,
    );
  }

  const db = getDb();
  const link = getLinkByCode(db, code);
  if (!link) {
    return c.json(
      { error: { code: "NOT_FOUND", message: "No link with that code." } },
      404,
    );
  }

  const salt = requireIpHashSalt();
  const clientIp = getClientIp(c);
  const ipHash = hashIp(salt, clientIp);

  const referrer = c.req.header("referer") ?? null;
  const ua = c.req.header("user-agent") ?? null;

  insertClick(db, {
    link_id: link.id,
    ts: Date.now(),
    referrer,
    ua,
    ip_hash: ipHash,
  });

  return c.redirect(link.target_url, 302);
});
