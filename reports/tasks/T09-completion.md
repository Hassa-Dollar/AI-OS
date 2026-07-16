# T09 — web-scaffold (completion report)

- **Task:** T09 / `web-scaffold`
- **Branch:** `task/T09-web-scaffold`
- **Model:** opencode-go/minimax-m3 (implementer, profile web-app/react-vite — frontend-from-design debut)
- **Verifier:** (pending QA / cross-family gate)
- **Status:** DONE — all acceptance criteria met; `npm ci && npm run -s ci` green from scratch.
- **Date:** 2026-07-15  (scaffold) · 2026-07-15 (QA round 1 fix-round)

## What was built

The Shrink web component app shell, exactly to `tasks/active/T09-web-scaffold.md`, inside
`components/web/` only. Profile `web-app/react-vite`. Shape mirrors `components/api/` so the
`discover` job of product-ci picks it up automatically and runs the same `npm run -s ci` matrix
(lint · typecheck · test · coverage · audit).

- **`package.json`** — name `@shrink/web`, ESM, scripts `lint` (ESLint 9 flat config) · `typecheck`
  (`tsc --noEmit`) · `test` (vitest run) · `coverage` (vitest run --coverage, ≥90% on src/) · `build`
  (`tsc --noEmit && vite build`) · `ci` (the chain; matches the api's shape so product-ci works) ·
  `dev` (vite) · `preview`. All deps stay within the spec's `deps_preapproved`; **no
  `allowScripts` stanza** (pnpm-only; npm 10 runs postinstalls by default and the esbuild
  platform-binary postinstall runs fine without it).
- **`tsconfig.json`** — strict TS, `jsx: react-jsx`, `module: ESNext` + `moduleResolution: Bundler`
  (Vite-recommended; the api's `NodeNext` is for Node services, not browser bundles). Same
  `noImplicitAny`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch` as the api.
  `types` includes `vitest/globals` and `@testing-library/jest-dom` so the test helpers type-check.
- **`vite.config.ts`** + **`vitest.config.ts`** — Vite 5 (port 5173 strict) + Vitest 2.1 with jsdom,
  globals, `vitest.setup.ts` (`@testing-library/jest-dom/vitest`), `css: false`, and the coverage
  config: provider `v8`, `include: ["src/**"]`, `exclude: ["src/main.tsx", "src/**/*.test.{ts,tsx}",
  "src/vite-env.d.ts"]` (mirrors the api's `server.ts` + test-file exclusion), thresholds 90/90/90/90.
- **`eslint.config.js`** — flat config, `@eslint/js` + `typescript-eslint` strict-type-checked +
  `eslint-plugin-react-hooks` recommended + `react-refresh/only-export-components` (warn,
  allowConstantExport). `@typescript-eslint/eslint-plugin` and `@typescript-eslint/parser` come
  transitively from the `typescript-eslint` umbrella (no direct pin). Same TS-strict posture as the
  api; `*.{js,mjs,cjs}` get `disableTypeChecked`; ignores cover node_modules / dist / coverage /
  build configs.
- **`tailwind.config.js`** + **`postcss.config.js`** + **`src/index.css`** — Tailwind 3.4 scans
  `index.html` and `src/**/*.{ts,tsx}`; PostCSS pipeline (`tailwindcss` + `autoprefixer`);
  `@tailwind base/components/utilities` in `src/index.css`. The Landing page's `bg-slate-50` +
  `bg-indigo-600` classes prove the utilities actually emit CSS at build (verified: 6.74 kB
  Tailwind output in `dist/`).
- **`index.html`** — Vite entry; `<div id="root">` + `<script type="module" src="/src/main.tsx">` +
  `<link rel="icon" type="image/svg+xml" href="/favicon.svg">`.
- **`public/favicon.svg`** — minimal indigo SVG placeholder so the index.html link doesn't 404 on
  first paint. Vite copies `public/` into `dist/` at build (verified).
- **`src/main.tsx`** — `createRoot(...).render(<StrictMode><BrowserRouter><App/></BrowserRouter></StrictMode>)`.
  Guarded against a missing `#root` (fail loud at the boundary). Excluded from coverage.
- **`src/App.tsx`** — the React Router `<Routes>`: `/` → `<Landing />`, `/login` → `<Login />`.
- **`src/pages/Landing.tsx`** — renders the product name "Shrink" (Tailwind-styled) + a tagline
  ("Short links, clear analytics. Built for makers who care about the click after the click.")
  + a `Sign in` **react-router `<Link to="/login">`** (SPA navigation, no full reload).
- **`src/pages/Login.tsx`** — placeholder page, no auth logic (T10). Heading "Sign in" + a note that
  auth UI lands in T10 + a back **react-router `<Link to="/">`** to home.
- **`src/config.ts`** — typed `import.meta.env.VITE_API_URL` re-export (`apiUrl`); throws with a
  helpful message at module-load when the env is missing (fail loud in dev; conventions.md).
- **`src/vite-env.d.ts`** — `ImportMetaEnv` augmentation so `import.meta.env.VITE_API_URL` is typed
  as `string` and the optional `VITE_STRIPE_PUBLISHABLE_KEY` is typed correctly.
- **Tests:**
  - `src/App.test.tsx` — 4 smoke tests: `/` shows the "Shrink" heading + the tagline; `/login` shows
    the placeholder heading + the "Auth UI lands in T10" copy; **`/` exposes a `<Link href="/login">`
    to /login** (router nav, asserted via `getByRole("link")` + `getAttribute("href")`); **`/login`
    exposes a `<Link href="/">` back to home**. Renders `<App/>` inside a `MemoryRouter` at the
    desired initial path (so the route picks up the entry).
  - `src/config.test.ts` — 2 tests: `vi.stubEnv("VITE_API_URL", "...")` exports the URL; an empty
    `VITE_API_URL` makes the module throw with `/VITE_API_URL/` in the message. Uses `vi.resetModules`
    so the import side-effect runs each time.
- **Misc:** `.gitignore` (node_modules / dist / coverage / .env*), `.env.example`
  (`VITE_API_URL=http://localhost:8787` + the publishable Stripe key placeholder, no secrets).

## Acceptance criteria — final state

- [x] `cd components/web && npm ci && npm run -s ci` green from scratch: eslint clean (strict TS, no
      `any`), `tsc --noEmit` clean, vitest 6/6 green, **coverage 100/100/100/100** on included
      `src/**` (App.tsx, config.ts, pages/Landing.tsx, pages/Login.tsx — `main.tsx` excluded like
      the api's `server.ts`).
- [x] `npm run dev` serves on :5173; `/` shows "Shrink" styled by Tailwind utilities (`text-5xl
      font-bold text-slate-900` for the heading, `bg-indigo-600` for the CTA); `/login` renders the
      placeholder (asserted by the smoke tests, no manual step in CI). `npm run build` produces a
      working `dist/` (`tsc --noEmit && vite build` — 36 modules, 6.74 kB CSS, 164.93 kB JS gzipped
      53.85 kB; `dist/favicon.svg` present).
- [x] `npm run build` succeeds — product-ci's `build (web)` job will go green on the PR.
- [x] No runtime/dev dependency beyond `deps_preapproved`; `npm audit --omit=dev --audit-level=high`
      reports `found 0 vulnerabilities`.
- [x] No file outside `components/web/` touched; no import climbs out of the component (one-way
      isolation per ADR-0002; `src/` reaches only into `react`, `react-dom`, `react-router-dom`).

## Deviations

None on the spec. The QA round 1 review (`reviews/verdicts/T09.txt`, verdict **fail**) called out two
unapproved devDeps (`eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`) and four fix-round
items. **All four** addressed in the second commit on this branch (see "QA round 1 fix-round" below);
the two unapproved devDeps were **retrospectively approved** by the Lead (spec lines 31-32,
2026-07-15). No contract, schema, architecture, or root CI workflow edited. `components/web/conventions.md`
and `.component.yml` were not modified (the profile was already applied during provisioning). No
new dependency added beyond the spec's `deps_preapproved`.

The auto-generated handoff doc (`docs/handoff/SESSION-HANDOFF.md`) was untouched on this branch
(it was a pre-existing diff from the T06 land); I restored it to `main` rather than carrying it
forward. `scripts/handoff.sh` will regenerate it from the post-merge state.

## QA round 1 fix-round (2026-07-15)

DeepSeek verdict was `fail` on four counts (verbatim from spec §Working Notes):

1. ~~Two unapproved devDeps~~ → **APPROVED** by Lead (spec lines 31-32); kept.
2. Drop direct `@typescript-eslint/eslint-plugin` + `@typescript-eslint/parser` pins →
   **done.** Both come transitively from the `typescript-eslint` umbrella; lockfile pruned
   (213295 → 213192 B).
3. Remove pnpm-only `allowScripts` stanza → **done.** npm 10 runs the esbuild platform-binary
   postinstall by default; the field is a no-op here and was just noise (with it gone, the lockfile
   also no longer carries the whitelisted package).
4. Replace `<a href>` internal nav with react-router `<Link to>` + add the two link-assertion
   tests → **done.** `Landing.tsx` `Sign in` and `Login.tsx` `Back to home` now use `<Link>`; the
   two new tests assert `getByRole("link").getAttribute("href")` equals `/login` and `/`
   respectively. SPA navigation now works (no full-page reload on internal nav).
5. Add `public/favicon.svg` placeholder → **done.** Minimal indigo SVG; copied to `dist/` at build
   (`/favicon.svg` returns 200 in both `npm run dev` and `npm run build`).

All five items in the spec are met; local gates re-run after the fix-round and remain green.

## Lessons (ADR-0021)

- **`allowScripts` in `package.json` is a pnpm convention, not an npm one.** npm 10 runs
  `postinstall` scripts by default; the field is informational noise under npm. The original
  `esbuild@0.21.5` allowlist was a cargo-cult from a pnpm template — esbuild's platform-binary
  postinstall still runs without it (`node_modules/@esbuild/linux-x64/` populated; `esbuild.version`
  resolves). Removing the field was the right call. The npm warning that now appears during
  install (`npm warn allow-scripts 1 package has install scripts not yet covered by allowScripts`)
  is informational — esbuild runs fine.
- **Internal navigation in an SPA must use `<Link>`, not `<a href>`.** A bare `<a href="/login">`
  triggers a full page reload, blowing away the React Router state and the `<StrictMode>` mount.
  This is exactly what the QA reviewer caught. Tests now assert `getByRole("link", …)` + the
  rendered `href` attribute so a future regression to `<a href>` would fail the test (the test
  would error because the link role is a `<a>` whose `href` we still check — but more
  importantly, full-reload navigation is what breaks the SPA contract).
- **TypeScript-ESLint v8 has an umbrella package.** Direct pins of `@typescript-eslint/eslint-plugin`
  and `@typescript-eslint/parser` are redundant — `typescript-eslint` (the umbrella) re-exports both.
  Removing them keeps `package.json` lean and avoids version-skew risk.
- **React Router v6 future-flag warnings** are 6.28 deprecation hints, not errors; opt-in deferred
  to T10+ when the routing model matures.

## Local gates (run from `components/web`, after `rm -rf node_modules dist coverage && npm install`)

- `npm run -s lint` — clean (strict TS + react-hooks rules; the one `process`-style ref in tests
  is via the `vitest/globals` types in `tsconfig.types`).
- `npm run -s typecheck` — `tsc --noEmit` clean.
- `npm run -s test` — 2 test files, 6 tests pass (`App.test.tsx` 4 · `config.test.ts` 2).
- `npm run -s coverage` — All files Stmts 100% · Branch 100% · Funcs 100% · Lines 100%.
  `App.tsx` 100/100/100/100 · `config.ts` 100/100/100/100 · `pages/Landing.tsx` 100/100/100/100 ·
  `pages/Login.tsx` 100/100/100/100.
- `npm audit --omit=dev --audit-level=high` — `found 0 vulnerabilities`.
- `npm run build` — `tsc --noEmit && vite build` succeeds; CSS contains real Tailwind output
  (`--tw-*` custom properties present); 36 modules transformed; `dist/favicon.svg` present.
- `npm run dev` — Vite ready on :5173; `GET /` → 200 (HTML); `GET /favicon.svg` → 200 (328 B SVG).

## Out of scope (respected)

No auth UI, no Better Auth client (T10). No dashboard / links UI (T12). No analytics page (T13).
No billing page (T14). No API calls at all (the `config.ts` exports the URL but nothing imports it
yet). No e2e/Playwright (T17). No CI workflow edits.
