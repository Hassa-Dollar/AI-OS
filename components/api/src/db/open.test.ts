import { describe, it, expect, afterEach } from "vitest";
import { openDb } from "./open.js";

describe("openDb", () => {
  const savedPath = process.env.DATABASE_PATH;
  afterEach(() => {
    if (savedPath === undefined) delete process.env.DATABASE_PATH;
    else process.env.DATABASE_PATH = savedPath;
  });

  it("opens an explicit :memory: db (filename arg wins)", () => {
    delete process.env.DATABASE_PATH; // prove the arg wins even with env unset
    const db = openDb(":memory:");
    expect(db.open).toBe(true);
    db.close();
  });

  it("opens via DATABASE_PATH env when no filename arg is given", () => {
    process.env.DATABASE_PATH = ":memory:";
    const db = openDb();
    expect(db.open).toBe(true);
    db.close();
  });

  it("throws (naming DATABASE_PATH) with no arg and DATABASE_PATH unset", () => {
    delete process.env.DATABASE_PATH;
    expect(() => openDb()).toThrow(/DATABASE_PATH/);
  });
});