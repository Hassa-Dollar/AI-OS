import { Hono } from "hono";
import type { Context } from "hono";
import { getAuth } from "./auth.js";
import { getDb } from "./app.js";
import {
  countClicksByLink,
  dailyClickSeries,
  getLinkByCode,
  getPlan,
} from "./db/repo.js";

export const analytics = new Hono();

async function getSession(c: Context) {
  return getAuth().api.getSession({ headers: c.req.raw.headers });
}

const UNAUTHENTICATED = {
  error: { code: "UNAUTHENTICATED", message: "Authentication is required." },
};

analytics.get("/:code/analytics", async (c) => {
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

  const plan = getPlan(db, session.user.id);
  if (plan !== "pro") {
    return c.json(
      {
        error: {
          code: "PRO_REQUIRED",
          message: "Analytics is a Pro feature. Upgrade to Pro.",
        },
      },
      402,
    );
  }

  const total_clicks = countClicksByLink(db, link.id);
  const series = dailyClickSeries(db, link.id);
  return c.json({ code: link.code, total_clicks, series }, 200);
});