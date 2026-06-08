import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['src/**/*.ts'],
      // wiring files have no logic to cover; route files bring their own tests
      exclude: ['src/server.ts', 'src/routes/index.ts', '**/*.test.ts'],
      // Reported, not hard-gated: vitest measures GLOBAL coverage, but the rule
      // (AGENTS.md §4) is DIFF coverage ≥90% — enforce that in review / with a
      // diff-coverage tool, not a global threshold that false-fails a tiny base.
    },
  },
});
