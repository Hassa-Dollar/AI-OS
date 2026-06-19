# Coding conventions — web-app/react-vite  (profile-provided; ADR-0003/0011)

> `profile.sh apply` copies this to `components/<name>/conventions.md` (the per-component path its workers
> read, ADR-0013). OS-level invariants are separate (`architecture/invariants.md`) and hold regardless of profile.

## Stack & tooling
- Language/runtime: **TypeScript 5.x**, **React 18**, **Vite**, ESM, `tsconfig` `strict: true`.
- Routing: **react-router-dom**. Styling: **Tailwind** utility classes (no sprawling inline styles).
- Data: `fetch` with `credentials: "include"` to the API base from `import.meta.env.VITE_API_URL`.
  Talk to the API **only** through `architecture/contracts/shrink-api.md` — never import `components/api`
  source (one-way isolation, ADR-0002).
- Auth: the **Better Auth client** against `/api/auth/*`; never re-implement auth logic client-side.
- State: React hooks + context; no heavy global-state library.
- Lint/format: `npm run -s lint` (ESLint + `@typescript-eslint` + react-hooks rules); never hand-format;
  an inline `// eslint-disable` is an `ESCALATE`, not a fix.
- Tests: `npm run -s test` (Vitest + Testing Library + jsdom); **mock `fetch`** — no real network in tests.
  New code requires tests; **diff coverage ≥ 90%** (`npm run -s coverage`).
- Types: `npm run -s typecheck` (`tsc --noEmit`) must pass; no `any`, no non-null `!` without `// reason:`.

## Rules
- **Server is the enforcement point.** Mirror plan-gating in the UI (hide/offer-upgrade), but never rely on
  the client for limits/Pro-gating — the API returns `402` and the UI handles it gracefully.
- Accessible, semantic HTML (labels, roles, focus); forms keyboard-usable.
- No secrets in the client. The only env is `VITE_API_URL` (+ any **publishable** Stripe key, never the
  secret key).
- Independently buildable: `npm ci && npm run -s ci` from inside `components/web` (extractability, ADR-0002).

## Security (ADR-0014 — enforced at the gate)
- **Dependencies:** add a runtime dependency ONLY if it is in the spec's `deps_preapproved`; otherwise
  `ESCALATE` (the gate rejects unapproved runtime deps).
- **No dynamic execution:** never use `eval`, `new Function`, or `child_process` (the gate blocks them).
- **Secrets:** the client gets only `VITE_*` public values (e.g. the Stripe *publishable* key) — never a
  secret key, token, or password. The server is the enforcement point for all gating.
