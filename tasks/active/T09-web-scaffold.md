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
