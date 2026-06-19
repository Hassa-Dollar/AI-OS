# components/web — Shrink front-end

React single-page app for Shrink (URL shortener SaaS). **Profile:** `web-app/react-vite`.

**Stack:** React 18 · Vite · TypeScript · react-router-dom · Tailwind · Better Auth client · Vitest +
Testing Library.

**Consumes:** `architecture/contracts/shrink-api.md` over HTTP (`VITE_API_URL`). Never imports
`components/api` source (one-way isolation, ADR-0002).

This skeleton is intentionally minimal. **Task T09** scaffolds the real app: `package.json` (with the `ci`
script = lint + typecheck + test + coverage), Vite + React + TS config, Tailwind, the test setup, and the
app shell. Then auth UI (T10), shell/guard (T11), dashboard (T12), analytics (T13), and billing (T14).

Run locally (after T09): `npm ci && npm run -s ci` then `npm run dev`.
