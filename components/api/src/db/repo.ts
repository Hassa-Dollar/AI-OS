import type { Database as DB } from "better-sqlite3";
import type { Link, Plan, Subscription } from "./types.js";

export interface NewLink {
  user_id: string;
  code: string;
  target_url: string;
  created_at: number;
}

export interface NewClick {
  link_id: number;
  ts: number;
  referrer?: string | null;
  ua?: string | null;
  ip_hash?: string | null;
}

interface DailyClickRow {
  date: string;
  count: number;
}

export function insertLink(db: DB, link: NewLink): Link {
  const info = db
    .prepare(
      "INSERT INTO link (user_id, code, target_url, created_at) VALUES (?, ?, ?, ?)",
    )
    .run(link.user_id, link.code, link.target_url, link.created_at);
  const row = db
    .prepare("SELECT * FROM link WHERE id = ?")
    .get(info.lastInsertRowid) as Link;
  return row;
}

export function getLinkByCode(db: DB, code: string): Link | undefined {
  const row = db
    .prepare("SELECT * FROM link WHERE code = ?")
    .get(code) as Link | undefined;
  return row;
}

export function listLinksByUser(db: DB, user_id: string): Link[] {
  return db
    .prepare("SELECT * FROM link WHERE user_id = ? ORDER BY id")
    .all(user_id) as Link[];
}

export function countLinksByUser(db: DB, user_id: string): number {
  const row = db
    .prepare("SELECT COUNT(*) AS n FROM link WHERE user_id = ?")
    .get(user_id) as { n: number };
  return row.n;
}

export function deleteLinkByCodeForUser(
  db: DB,
  code: string,
  user_id: string,
): boolean {
  const info = db
    .prepare("DELETE FROM link WHERE code = ? AND user_id = ?")
    .run(code, user_id);
  return info.changes > 0;
}

export function insertClick(db: DB, click: NewClick): void {
  db.prepare(
    "INSERT INTO click (link_id, ts, referrer, ua, ip_hash) VALUES (?, ?, ?, ?, ?)",
  ).run(
    click.link_id,
    click.ts,
    click.referrer ?? null,
    click.ua ?? null,
    click.ip_hash ?? null,
  );
}

export function countClicksByLink(db: DB, link_id: number): number {
  const row = db
    .prepare("SELECT COUNT(*) AS n FROM click WHERE link_id = ?")
    .get(link_id) as { n: number };
  return row.n;
}

export function dailyClickSeries(
  db: DB,
  link_id: number,
): { date: string; count: number }[] {
  const rows = db
    .prepare(
      `SELECT strftime('%Y-%m-%d', ts / 1000, 'unixepoch') AS date,
              COUNT(*) AS count
         FROM click
        WHERE link_id = ?
        GROUP BY date
        ORDER BY date ASC`,
    )
    .all(link_id) as DailyClickRow[];
  return rows.map(({ date, count }) => ({ date, count }));
}

export function getSubscription(
  db: DB,
  user_id: string,
): Subscription | undefined {
  return db
    .prepare("SELECT * FROM subscription WHERE user_id = ?")
    .get(user_id) as Subscription | undefined;
}

export function upsertSubscription(db: DB, sub: Subscription): void {
  db.prepare(
    `INSERT INTO subscription
       (user_id, stripe_customer_id, stripe_subscription_id, plan, status, current_period_end)
     VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(user_id) DO UPDATE SET
       stripe_customer_id = excluded.stripe_customer_id,
       stripe_subscription_id = excluded.stripe_subscription_id,
       plan = excluded.plan,
       status = excluded.status,
       current_period_end = excluded.current_period_end`,
  ).run(
    sub.user_id,
    sub.stripe_customer_id,
    sub.stripe_subscription_id,
    sub.plan,
    sub.status,
    sub.current_period_end,
  );
}

export function getPlan(db: DB, user_id: string): Plan {
  const row = db
    .prepare("SELECT status FROM subscription WHERE user_id = ?")
    .get(user_id) as { status: string | null } | undefined;
  if (row !== undefined && (row.status === "active" || row.status === "trialing")) {
    return "pro";
  }
  return "free";
}