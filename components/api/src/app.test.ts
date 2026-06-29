import { describe, expect, it } from "vitest";
import { app } from "./app.js";

describe("GET /healthz", () => {
  it("returns 200 with { status: 'ok' }", async () => {
    const res = await app.request("/healthz");
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("application/json");
    const body = (await res.json()) as { status: string };
    expect(body).toEqual({ status: "ok" });
  });
});