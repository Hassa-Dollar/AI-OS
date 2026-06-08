import tseslint from 'typescript-eslint';

// Flat config (ESLint 9). Type-aware rules off for speed; recommended TS rules on src.
export default tseslint.config(
  { ignores: ['dist/**', 'coverage/**', 'node_modules/**'] },
  {
    files: ['src/**/*.ts'],
    extends: [...tseslint.configs.recommended],
  },
);
