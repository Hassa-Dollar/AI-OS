import { afterEach, describe, expect, it, vi } from "vitest";

describe("config", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("exports the configured API URL when VITE_API_URL is set", async () => {
    vi.stubEnv("VITE_API_URL", "http://example.test:8787");
    const { config } = await import("./config.js");
    expect(config.apiUrl).toBe("http://example.test:8787");
  });

  it("throws when VITE_API_URL is not set", async () => {
    vi.stubEnv("VITE_API_URL", "");
    await expect(import("./config.js")).rejects.toThrow(/VITE_API_URL/);
  });
});
