---
id: T09
slug: web-scaffold
owner_role: implementer      # react-vite profile → minimax-m3 (frontend-from-design debut)
branch: task/T09-web-scaffold
blast_radius: med
files_allowed:
  - components/web/
  - reports/tasks/T09-completion.md
depends_on_contracts:
  - architecture/contracts/shrink-api.md
deps_preapproved:
  - react
  - react-dom
  - react-router-dom
  - vite
  - "@vitejs/plugin-react"
  - tailwindcss
  - autoprefixer
  - postcss
  - typescript
  - vitest
  - jsdom
  - "@testing-library/react"
  - "@testing-library/jest-dom"
  - "@types/react"
  - "@types/react-dom"
  - eslint
  - typescript-eslint
  - "@vitest/coverage-v8"
---

# Goal
Scaffold the Shrink web component: Vite + React + TS + react-router + Tailwind, with the same CI
discipline as the api component — `npm run -s ci` (lint, typecheck, tests, coverage) green from
scratch, and product-ci discovering/building it.

# Context (compressed)
`components/web/` is provisioned (README, `conventions.md` — the applied react-vite profile copy,
`.component.yml`) but has no app yet. Follow `components/web/conventions.md`; mirror the SHAPE of
`components/api/package.json`'s scripts (`lint`, `typecheck`, `test`, `ci`) so product-ci (ADR-0013
discover job) picks it up automatically — that is the forcing function, like T01 was for the api.
- App skeleton: `src/main.tsx` + `src/App.tsx` + router with two routes — `/` (landing: renders the
  product name "Shrink" + a tagline) and `/login` (placeholder page, NO auth logic — T10 owns auth).
  Tailwind wired (postcss config + directives in `src/index.css`); a visible utility class proves it.
- Tests: vitest + jsdom + @testing-library/react; smoke tests per route (landing renders "Shrink";
  /login renders its placeholder). Coverage thresholds per conventions (≥90% on src/**, exclude
  main.tsx like the api excludes server.ts).
- `VITE_API_URL` (see `.env.example`) may appear in a typed config module but NOTHING calls the API
  yet (T10+). Never hardcode secrets; env only.
- Component isolation (ADR-0002): no imports reaching outside `components/web/`.
- BUG-29 rule: any test temp files via `os.tmpdir()`+`mkdtemp` — never a hardcoded /tmp path.
- npm-lock trap (wisdom BUG-31): this is a FRESH package.json, so plain `npm install` is fine here —
  the trap applies when ADDING deps to an existing lockfile later.

# Acceptance criteria  (executable)
- [ ] `cd components/web && npm ci && npm run -s ci` green from scratch: eslint clean (strict TS,
      no `any`), `tsc --noEmit` clean, vitest green, coverage ≥90% on included `src/**`.
- [ ] `npm run dev` serves; `/` shows "Shrink" styled by a Tailwind utility; `/login` renders the
      placeholder (assert via tests — no manual step in CI).
- [ ] `npm run build` (vite build + tsc) succeeds — product-ci `build (web)` goes green on the PR.
- [ ] No runtime/dev dependency beyond `deps_preapproved`; `npm audit --omit=dev --audit-level=high`
      clean.
- [ ] No file outside `components/web/` (+ your report) touched; no import escapes the component.

# Out of scope  (binding)
- No auth UI or Better Auth client (T10). No dashboard/links UI (T12). No analytics page (T13).
- No billing page (T14). No API calls at all. No e2e/Playwright (T17). No CI workflow edits.

# Stop conditions
- A needed dependency isn't listed above → STOP, escalate (do not substitute).
- conventions.md conflicts with an acceptance criterion → STOP, escalate.
- Anything seems to require touching files outside `components/web/` → STOP, escalate.

# Working notes  (worker appends)

## 2026-07-15  minimax-m3 (T09 implementer)

- Scaffolded the Vite + React 18 + TS + Tailwind app per the spec. All files inside `components/web/`
  (plus this Working Notes + the completion report). No file outside `components/web/` touched
  (the auto-generated handoff doc was deliberately restored to main; handoff.sh regenerates it post-merge).
- Local gates (run from `components/web` after `rm -rf node_modules dist coverage && npm ci`):
  - `npm run -s lint` — clean (strict TS + react-hooks).
  - `npm run -s typecheck` — clean.
  - `npm run -s test` — 4/4 pass (2 route smoke + 2 config).
  - `npm run -s coverage` — 100/100/100/100 (all files); main.tsx excluded as required.
  - `npm audit --omit=dev --audit-level=high` — 0 vulns.
  - `npm run build` — `tsc --noEmit && vite build` → 36 modules → dist/ (≈160 kB JS, ≈7 kB CSS, gzipped 52/2 kB).
  - `npm run dev` — Vite ready in ≈140 ms on :5173 (HTTP 200, root HTML served).
- Tooling notes: `allowScripts.esbuild@0.21.5 = true` so the platform-binary postinstall runs
  (Vite needs it; without it, build is broken). Lockfile created via plain `npm install` (fresh
  `package.json`, BUG-31 trap does not apply).
- Decisions taken within the spec (no contract change):
  - `tsconfig.json` uses `module: ESNext` + `moduleResolution: Bundler` (Vite-recommended; the api
    uses `NodeNext` because it's a Node service, not a browser bundle). Same strict flags.
  - Vitest config is split from Vite config (cleaner; `mergeConfig` extends the vite plugins).
  - `vitest.setup.ts` imports `@testing-library/jest-dom/vitest` so `toBeInTheDocument()` is available
    globally; declared in `tsconfig.types` so `process.env`-style vitest globals type-check.
  - `src/config.ts` throws at module-load when `VITE_API_URL` is missing — guard at the boundary,
    never swallow (conventions.md "fail loud in dev"). The throw is tested in `config.test.ts`.
  - Routes: `/` → `<Landing />` (Tailwind `bg-slate-50`, `text-5xl`, `bg-indigo-600` button —
    proves Tailwind is wired) and `/login` → `<Login />` placeholder (no auth logic — T10).
  - No `fetch`, no Better Auth client, no API call (T10+ own those).
  - All deps in `deps_preapproved`. No new dep added.

## Lessons (ADR-0021) — see completion report §Lessons
