import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts'],
      // wiring files have no logic to cover; route files must bring their own tests
      exclude: ['src/server.ts', 'src/routes/index.ts', '**/*.test.ts'],
      thresholds: { lines: 90, functions: 90, branches: 90, statements: 90 },
    },
  },
});
