import { Hono } from "hono";
import { cors } from "hono/cors";
import type { Database as DB } from "better-sqlite3";
import { getAuth } from "./auth.js";
import { openDb } from "./db/open.js";
import { getPlan } from "./db/repo.js";
import { links } from "./links.js";
import { redirect } from "./redirect.js";

export const app = new Hono();

let appDb: DB | null = null;
export function getDb(): DB {
  if (appDb) return appDb;
  appDb = openDb();
  return appDb;
}

app.get("/healthz", (c) => c.json({ status: "ok" }, 200));

app.use(
  "/api/auth/*",
  cors({
    origin: "http://localhost:5173",
    credentials: true,
    allowHeaders: ["Content-Type", "Authorization"],
    allowMethods: ["POST", "GET", "OPTIONS"],
  }),
);

app.on(["POST", "GET"], "/api/auth/*", (c) => getAuth().handler(c.req.raw));

app.get("/api/me", async (c) => {
  const session = await getAuth().api.getSession({ headers: c.req.raw.headers });
  if (!session) {
    return c.json(
      { error: { code: "UNAUTHENTICATED", message: "Authentication is required." } },
      401,
    );
  }
  const plan = getPlan(getDb(), session.user.id);
  return c.json(
    { user: { id: session.user.id, email: session.user.email }, plan },
    200,
  );
});

app.route("/api/links", links);

app.route("/", redirect);
