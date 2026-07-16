import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config.js";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: "jsdom",
      include: ["src/**/*.test.{ts,tsx}"],
      exclude: ["node_modules", "dist", "coverage"],
      setupFiles: ["./vitest.setup.ts"],
      css: false,
      coverage: {
        provider: "v8",
        include: ["src/**"],
        exclude: [
          "src/main.tsx",
          "src/**/*.test.{ts,tsx}",
          "src/vite-env.d.ts",
        ],
        thresholds: {
          lines: 90,
          functions: 90,
          branches: 90,
          statements: 90,
        },
      },
    },
  }),
);
