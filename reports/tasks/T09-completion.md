# T09 — web-scaffold (completion report)

- **Task:** T09 / `web-scaffold`
- **Branch:** `task/T09-web-scaffold`
- **Model:** opencode-go/minimax-m3 (implementer, profile web-app/react-vite — frontend-from-design debut)
- **Verifier:** (pending QA / cross-family gate)
- **Status:** DONE — all acceptance criteria met; `npm ci && npm run -s ci` green from scratch.
- **Date:** 2026-07-15

## What was built

The Shrink web component app shell, exactly to `tasks/active/T09-web-scaffold.md`, inside `components/web/`
only. Profile `web-app/react-vite` (the same conventions file already shipped there). The shape mirrors
`components/api/` so the `discover` job of product-ci picks it up automatically and runs the same
`npm run -s ci` matrix (lint · typecheck · test · coverage · audit).

- **`package.json`** — name `@shrink/web`, ESM, scripts `lint` (ESLint 9 flat config) · `typecheck`
  (`tsc --noEmit`) · `test` (vitest run) · `coverage` (vitest run --coverage, ≥90% on src/) · `build`
  (`tsc --noEmit && vite build`) · `ci` (the chain; matches the api's shape so product-ci works) · `dev`
  (vite) · `preview`. All deps stay within the spec's `deps_preapproved`. `allowScripts` whitelists
  `esbuild@0.21.5` (Vite's bundled tool needs the platform-binary postinstall to run, else the build
  breaks on a fresh clone).
- **`tsconfig.json`** — strict TS, `jsx: react-jsx`, `module: ESNext` + `moduleResolution: Bundler`
  (Vite-recommended; the api's `NodeNext` is for Node services, not browser bundles). Same `noImplicitAny`,
  `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch` as the api. `types` includes
  `vitest/globals` and `@testing-library/jest-dom` so the test helpers type-check.
- **`vite.config.ts`** + **`vitest.config.ts`** — Vite 5 (port 5173 strict) + Vitest 2.1 with jsdom,
  globals, `vitest.setup.ts` (`@testing-library/jest-dom/vitest`), `css: false`, and the coverage
  config: provider `v8`, `include: ["src/**"]`, `exclude: ["src/main.tsx", "src/**/*.test.{ts,tsx}",
  "src/vite-env.d.ts"]` (mirrors the api's `server.ts` + test-file exclusion), thresholds 90/90/90/90.
- **`eslint.config.js`** — flat config, `@eslint/js` + `typescript-eslint` strict-type-checked +
  `eslint-plugin-react-hooks` recommended + `react-refresh/only-export-components` (warn, allowConstantExport).
  Same TS-strict posture as the api; `*.{js,mjs,cjs}` get `disableTypeChecked`; ignores cover
  node_modules / dist / coverage / build configs.
- **`tailwind.config.js`** + **`postcss.config.js`** + **`src/index.css`** — Tailwind 3.4 scans
  `index.html` and `src/**/*.{ts,tsx}`; PostCSS pipeline (`tailwindcss` + `autoprefixer`); `@tailwind
  base/components/utilities` in `src/index.css`. The Landing page's `bg-slate-50` + `bg-indigo-600`
  classes prove the utilities actually emit CSS at build (verified: 6.74 kB Tailwind output in `dist/`).
- **`index.html`** — Vite entry; `<div id="root">` + `<script type="module" src="/src/main.tsx">`.
- **`src/main.tsx`** — `createRoot(...).render(<StrictMode><BrowserRouter><App/></BrowserRouter></StrictMode>)`.
  Guarded against a missing `#root` (fail loud at the boundary). Excluded from coverage.
- **`src/App.tsx`** — the React Router `<Routes>`: `/` → `<Landing />`, `/login` → `<Login />`.
- **`src/pages/Landing.tsx`** — renders the product name "Shrink" (Tailwind-styled) + a tagline
  ("Short links, clear analytics. Built for makers who care about the click after the click.")
  + a `Sign in` link to `/login`.
- **`src/pages/Login.tsx`** — placeholder page, no auth logic (T10). Heading "Sign in" + a note that
  auth UI lands in T10 + a back link to `/`.
- **`src/config.ts`** — typed `import.meta.env.VITE_API_URL` re-export (`apiUrl`); throws with a
  helpful message at module-load when the env is missing (fail loud in dev; conventions.md).
- **`src/vite-env.d.ts`** — `ImportMetaEnv` augmentation so `import.meta.env.VITE_API_URL` is typed
  as `string` and the optional `VITE_STRIPE_PUBLISHABLE_KEY` is typed correctly.
- **Tests:**
  - `src/App.test.tsx` — 2 smoke tests: `/` shows the "Shrink" heading + the tagline;
    `/login` shows the placeholder heading + the "Auth UI lands in T10" copy. Renders `<App/>` inside
    a `MemoryRouter` at the desired initial path (so the route picks up the entry).
  - `src/config.test.ts` — 2 tests: `vi.stubEnv("VITE_API_URL", "...")` exports the URL; an empty
    `VITE_API_URL` makes the module throw with `/VITE_API_URL/` in the message. Uses `vi.resetModules`
    so the import side-effect runs each time.
- **Misc:** `.gitignore` (node_modules / dist / coverage / .env*), `.env.example`
  (`VITE_API_URL=http://localhost:8787` + the publishable Stripe key placeholder, no secrets).

## Acceptance criteria — final state

- [x] `cd components/web && npm ci && npm run -s ci` green from scratch: eslint clean (strict TS, no
      `any`), `tsc --noEmit` clean, vitest 4/4 green, **coverage 100/100/100/100** on included `src/**`
      (App.tsx, config.ts, pages/Landing.tsx, pages/Login.tsx — `main.tsx` excluded like the api's `server.ts`).
- [x] `npm run dev` serves on :5173; `/` shows "Shrink" styled by Tailwind utilities (`text-5xl font-bold
      text-slate-900` for the heading, `bg-indigo-600` for the CTA); `/login` renders the placeholder
      (asserted by the smoke tests, no manual step in CI). `npm run build` produces a working
      `dist/` (`tsc --noEmit && vite build` — 36 modules, 6.74 kB CSS, 159.84 kB JS gzipped 52.13 kB).
- [x] `npm run build` succeeds — product-ci's `build (web)` job will go green on the PR.
- [x] No runtime/dev dependency beyond `deps_preapproved`; `npm audit --omit=dev --audit-level=high`
      reports `found 0 vulnerabilities`.
- [x] No file outside `components/web/` touched; no import climbs out of the component (one-way
      isolation per ADR-0002; `src/` reaches only into `react`, `react-dom`, `react-router-dom`).

## Deviations

None. No contract (`architecture/contracts/`), no schema, no `architecture/`, no root CI workflow
edited. `components/web/conventions.md` and `.component.yml` were not modified (the profile was
already applied during provisioning). No new dependency added beyond the spec's `deps_preapproved`.

The auto-generated handoff doc (`docs/handoff/SESSION-HANDOFF.md`) was untouched on this branch
(it was a pre-existing diff from the T06 land); I restored it to `main` rather than carrying
it forward. `scripts/handoff.sh` will regenerate it from the post-merge state.

## Lessons (ADR-0021)

None — no non-obvious traps hit. The BUG-31 (npm-lock trap) wisdom is explicitly called out in the
spec ("this is a FRESH package.json, so plain `npm install` is fine") and followed. The BUG-29 rule
(temp dirs) doesn't apply — no test creates files, so `os.tmpdir()`+`mkdtemp` is unnecessary. The
React Router future-flag warnings (v7 startTransition / v7_relativeSplatPath) are 6.28 deprecation
hints, not errors; opt-in deferred to T10+ when the routing model matures.

## Local gates (run from `components/web`, after `rm -rf node_modules dist coverage && npm ci`)

- `npm run -s lint` — clean (strict TS + react-hooks rules; the one `process`-style ref in tests
  is via the `vitest/globals` types in `tsconfig.types`).
- `npm run -s typecheck` — `tsc --noEmit` clean.
- `npm run -s test` — 2 test files, 4 tests pass (`App.test.tsx` 2 · `config.test.ts` 2).
- `npm run -s coverage` — All files Stmts 100% · Branch 100% · Funcs 100% · Lines 100%.
  `App.tsx` 100/100/100/100 · `config.ts` 100/100/100/100 · `pages/Landing.tsx` 100/100/100/100 ·
  `pages/Login.tsx` 100/100/100/100.
- `npm audit --omit=dev --audit-level=high` — `found 0 vulnerabilities`.
- `npm run build` — `tsc --noEmit && vite build` succeeds; CSS contains real Tailwind output
  (`--tw-*` custom properties present); 36 modules transformed.

## Out of scope (respected)

No auth UI, no Better Auth client (T10). No dashboard / links UI (T12). No analytics page (T13).
No billing page (T14). No API calls at all (the `config.ts` exports the URL but nothing imports it
yet). No e2e/Playwright (T17). No CI workflow edits.
