import { Hono } from "hono";
import type { Context } from "hono";
import { randomBytes } from "node:crypto";
import { z } from "zod";
import type { Database as DB } from "better-sqlite3";
import { getAuth } from "./auth.js";
import { getDb } from "./app.js";
import {
  countClicksByLink,
  countLinksByUser,
  deleteLinkByCodeForUser,
  getLinkByCode,
  getPlan,
  insertLink,
  listLinksByUser,
} from "./db/repo.js";

export const links = new Hono();

const BASE62 =
  "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
const CODE_LEN = 7;
const FREE_PLAN_LIMIT = 10;
const MAX_GEN_ATTEMPTS = 8;

// BASE_URL is required to build short_url; fail loud rather than emit a broken URL.
export function baseUrl(): string {
  const b = process.env.BASE_URL;
  if (!b) {
    throw new Error("BASE_URL is required (set it in .env)");
  }
  return b;
}

export function randomCode(): string {
  const bytes = randomBytes(CODE_LEN);
  let out = "";
  for (let i = 0; i < CODE_LEN; i++) {
    out += BASE62[bytes[i] % BASE62.length];
  }
  return out;
}

// Retry the rare unique-code collision; `gen` is injectable for deterministic tests.
export function generateUniqueCode(db: DB, gen: () => string = randomCode): string {
  for (let attempt = 0; attempt < MAX_GEN_ATTEMPTS; attempt++) {
    const code = gen();
    if (getLinkByCode(db, code) === undefined) return code;
  }
  throw new Error("INTERNAL: could not generate a unique link code");
}

function shortUrl(code: string): string {
  return `${baseUrl()}/${code}`;
}

const createSchema = z.object({
  target_url: z
    .string()
    .regex(/^https?:\/\/\S+$/, "must be a valid http or https URL"),
});

async function getSession(c: Context) {
  return getAuth().api.getSession({ headers: c.req.raw.headers });
}

const UNAUTHENTICATED = {
  error: { code: "UNAUTHENTICATED", message: "Authentication is required." },
};

links.post("/", async (c) => {
  const session = await getSession(c);
  if (!session) return c.json(UNAUTHENTICATED, 401);

  const parsed = createSchema.safeParse(
    await c.req.json().catch(() => undefined),
  );
  if (!parsed.success) {
    return c.json(
      { error: { code: "INVALID_INPUT", message: "target_url must be a valid http or https URL." } },
      400,
    );
  }

  const db = getDb();
  const userId = session.user.id;
  const plan = getPlan(db, userId);
  if (plan === "free" && countLinksByUser(db, userId) >= FREE_PLAN_LIMIT) {
    return c.json(
      { error: { code: "PLAN_LIMIT", message: "Free plan is limited to 10 links." } },
      402,
    );
  }

  const code = generateUniqueCode(db);
  const link = insertLink(db, {
    user_id: userId,
    code,
    target_url: parsed.data.target_url,
    created_at: Date.now(),
  });

  return c.json(
    {
      code: link.code,
      short_url: shortUrl(link.code),
      target_url: link.target_url,
      created_at: link.created_at,
    },
    201,
  );
});

links.get("/", async (c) => {
  const session = await getSession(c);
  if (!session) return c.json(UNAUTHENTICATED, 401);

  const db = getDb();
  const rows = listLinksByUser(db, session.user.id);
  const body = rows.map((r) => ({
    code: r.code,
    short_url: shortUrl(r.code),
    target_url: r.target_url,
    created_at: r.created_at,
    click_count: countClicksByLink(db, r.id),
  }));
  return c.json(body, 200);
});

links.delete("/:code", async (c) => {
  const session = await getSession(c);
  if (!session) return c.json(UNAUTHENTICATED, 401);

  const code = c.req.param("code");
  const db = getDb();
  const link = getLinkByCode(db, code);
  if (link === undefined) {
    return c.json(
      { error: { code: "NOT_FOUND", message: "No link with that code." } },
      404,
    );
  }
  if (link.user_id !== session.user.id) {
    return c.json(
      { error: { code: "FORBIDDEN", message: "You do not own this link." } },
      403,
    );
  }
  deleteLinkByCodeForUser(db, code, session.user.id);
  return c.body(null, 204);
});