+++
id = "SH-2"
title = "CORS and Better Auth trusted origins come from WEB_ORIGIN and cover every /api route"
files_allowed = ["components/api/src/app.ts", "components/api/src/auth.ts", "components/api/src/app.test.ts", "components/api/src/auth.test.ts", "components/api/src/cors.test.ts"]
deps_preapproved = []
contracts = ["docs/contracts/shrink-api.md"]
blast_radius = "medium"
kind = "bugfix"
budget_usd = 0.75
+++

## Goal
The web app must be able to call every `/api/*` route from its own origin, with credentials. The allowed origin is
configured through `WEB_ORIGIN`, not hardcoded.

## Context
- `src/app.ts` applies `cors()` only to `/api/auth/*`, and the origin is hardcoded to `http://localhost:5173`.
- `src/auth.ts` hardcodes `const WEB_ORIGIN = "http://localhost:5173"` for Better Auth `trustedOrigins`.
- `.env.example` documents `WEB_ORIGIN`, but nothing reads it.
- The contract (`docs/contracts/shrink-api.md`) says: "CORS allows the web origin with credentials."

## Acceptance criteria
1. **One source of truth:** the allowed origin is read from `process.env.WEB_ORIGIN`, defaulting to
   `http://localhost:5173` when unset or empty.
2. **CORS on all `/api/*` routes:** this includes `/api/auth/*`, `/api/me` and `/api/links*`. The middleware allows
   exactly that origin, with `credentials: true`, methods `GET, POST, PATCH, DELETE, OPTIONS`, and headers
   `Content-Type, Authorization`.
3. **Preflight behavior:** a preflight `OPTIONS /api/links` with `Origin: <WEB_ORIGIN>` returns
   `Access-Control-Allow-Origin: <WEB_ORIGIN>` and `Access-Control-Allow-Credentials: true`. A preflight from any other
   origin must not get that origin echoed back.
4. **Better Auth `trustedOrigins`** uses the same value.
5. **Non-API routes are unaffected:** `/healthz` and the public redirect `/:code`.
6. **Tested, and checks pass:**
   - New or updated tests cover criteria 1–4, including the default value.
   - Run from `components/api`, all four must pass: `npm run -s lint`, `npm run -s typecheck`, `npm run -s test`,
     `npm run -s coverage` (thresholds are 90%).

## Out of scope
Server startup and `.env` loading, new dependencies, and any change to the HTTP contract.

## Stop conditions
If the task cannot be done without editing files outside `files_allowed`, stop and reply `ESCALATE: <reason>`.
