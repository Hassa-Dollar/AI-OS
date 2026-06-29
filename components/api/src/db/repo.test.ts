import { describe, it, expect, beforeEach, afterEach } from "vitest";
import type { Database as DB } from "better-sqlite3";
import { openDb } from "./open.js";
import {
  countClicksByLink,
  countLinksByUser,
  dailyClickSeries,
  deleteLinkByCodeForUser,
  getLinkByCode,
  getPlan,
  getSubscription,
  insertClick,
  insertLink,
  listLinksByUser,
  upsertSubscription,
} from "./repo.js";

describe("repo", () => {
  let db: DB;

  beforeEach(() => {
    db = openDb(":memory:");
  });

  afterEach(() => {
    db.close();
  });

  it("inserts and reads a link", () => {
    const link = insertLink(db, {
      user_id: "u1",
      code: "abc1234",
      target_url: "https://example.com",
      created_at: 1_000,
    });
    expect(link.id).toBeGreaterThan(0);
    expect(link.user_id).toBe("u1");
    expect(link.code).toBe("abc1234");
    expect(getLinkByCode(db, "abc1234")).toMatchObject({ code: "abc1234" });
  });

  it("enforces UNIQUE(code)", () => {
    insertLink(db, {
      user_id: "u1",
      code: "dup",
      target_url: "https://a.com",
      created_at: 1,
    });
    expect(() =>
      insertLink(db, {
        user_id: "u2",
        code: "dup",
        target_url: "https://b.com",
        created_at: 2,
      }),
    ).toThrow();
  });

  it("counts links by user", () => {
    insertLink(db, {
      user_id: "u1",
      code: "c1",
      target_url: "https://a.com",
      created_at: 1,
    });
    insertLink(db, {
      user_id: "u1",
      code: "c2",
      target_url: "https://a.com",
      created_at: 2,
    });
    insertLink(db, {
      user_id: "u2",
      code: "c3",
      target_url: "https://a.com",
      created_at: 3,
    });
    expect(countLinksByUser(db, "u1")).toBe(2);
    expect(countLinksByUser(db, "u2")).toBe(1);
    expect(countLinksByUser(db, "uX")).toBe(0);
  });

  it("lists links by user", () => {
    insertLink(db, {
      user_id: "u1",
      code: "c1",
      target_url: "https://a.com",
      created_at: 1,
    });
    insertLink(db, {
      user_id: "u1",
      code: "c2",
      target_url: "https://a.com",
      created_at: 2,
    });
    expect(listLinksByUser(db, "u1").length).toBe(2);
  });

  it("deletes a link owner-scoped — only the owning user's row", () => {
    insertLink(db, {
      user_id: "u1",
      code: "c1",
      target_url: "https://a.com",
      created_at: 1,
    });
    expect(deleteLinkByCodeForUser(db, "c1", "u2")).toBe(false);
    expect(getLinkByCode(db, "c1")).toBeDefined();
    expect(deleteLinkByCodeForUser(db, "c1", "u1")).toBe(true);
    expect(getLinkByCode(db, "c1")).toBeUndefined();
  });

  it("cascades clicks when a link is deleted (foreign_keys = ON)", () => {
    const link = insertLink(db, {
      user_id: "u1",
      code: "c1",
      target_url: "https://a.com",
      created_at: 1,
    });
    insertClick(db, { link_id: link.id, ts: 2 });
    insertClick(db, { link_id: link.id, ts: 3 });
    expect(countClicksByLink(db, link.id)).toBe(2);
    db.prepare("DELETE FROM link WHERE id = ?").run(link.id);
    expect(countClicksByLink(db, link.id)).toBe(0);
  });

  it("dailyClickSeries buckets by UTC day ascending", () => {
    const link = insertLink(db, {
      user_id: "u1",
      code: "c1",
      target_url: "https://a.com",
      created_at: 1,
    });
    const day1 = Date.UTC(2026, 0, 1, 3, 0, 0);
    const day1Late = Date.UTC(2026, 0, 1, 23, 0, 0);
    const day2 = Date.UTC(2026, 0, 2, 1, 0, 0);
    insertClick(db, { link_id: link.id, ts: day1 });
    insertClick(db, { link_id: link.id, ts: day1Late });
    insertClick(db, { link_id: link.id, ts: day2 });
    const series = dailyClickSeries(db, link.id);
    expect(series).toEqual([
      { date: "2026-01-01", count: 2 },
      { date: "2026-01-02", count: 1 },
    ]);
  });

  it("plan derivation across no-row, canceled, active, trialing", () => {
    expect(getPlan(db, "nope")).toBe("free");
    upsertSubscription(db, {
      user_id: "u1",
      stripe_customer_id: null,
      stripe_subscription_id: null,
      plan: "free",
      status: "canceled",
      current_period_end: null,
    });
    expect(getPlan(db, "u1")).toBe("free");
    upsertSubscription(db, {
      user_id: "u2",
      stripe_customer_id: "cust",
      stripe_subscription_id: "sub",
      plan: "pro",
      status: "active",
      current_period_end: 9_999,
    });
    expect(getPlan(db, "u2")).toBe("pro");
    upsertSubscription(db, {
      user_id: "u3",
      stripe_customer_id: null,
      stripe_subscription_id: null,
      plan: "pro",
      status: "trialing",
      current_period_end: 9_999,
    });
    expect(getPlan(db, "u3")).toBe("pro");
  });

  it("upserts a subscription (insert then update)", () => {
    upsertSubscription(db, {
      user_id: "u1",
      stripe_customer_id: "c1",
      stripe_subscription_id: "s1",
      plan: "free",
      status: "inactive",
      current_period_end: null,
    });
    expect(getSubscription(db, "u1")).toMatchObject({ stripe_customer_id: "c1" });
    upsertSubscription(db, {
      user_id: "u1",
      stripe_customer_id: "c2",
      stripe_subscription_id: "s2",
      plan: "pro",
      status: "active",
      current_period_end: 5,
    });
    expect(getSubscription(db, "u1")).toMatchObject({
      user_id: "u1",
      stripe_customer_id: "c2",
      plan: "pro",
      status: "active",
    });
  });

  it("inserts a link with an arbitrary user_id and no user table present", () => {
    const table = db
      .prepare(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'user'",
      )
      .get();
    expect(table).toBeUndefined();
    const link = insertLink(db, {
      user_id: "any-arbitrary-id",
      code: "x",
      target_url: "https://a.com",
      created_at: 1,
    });
    expect(link.user_id).toBe("any-arbitrary-id");
  });
});