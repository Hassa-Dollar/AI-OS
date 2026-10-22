+++
id = "SH-1"
title = "API boots for real: load .env, migrate the auth schema at startup, drop stray allowScripts"
files_allowed = ["components/api/src/server.ts", "components/api/src/server.test.ts", "components/api/package.json"]
deps_preapproved = []
contracts = ["docs/contracts/shrink-api.md"]
blast_radius = "medium"
kind = "bugfix"
budget_usd = 0.75
+++

## Goal
Make the API start correctly on a fresh machine. It must read its configuration from a `.env` file and create the
Better Auth tables before serving, so sign-up works on a brand-new database.

## Context
- `components/api/src/server.ts` only calls `serve()`. `migrateAuthSchema()` (in `src/auth.ts`) is never called outside
  the tests, so `POST /api/auth/sign-up/email` fails on a fresh database.
- Nothing loads `.env`. Node 22 has `process.loadEnvFile(path)` built in, so no dependency is needed.
- App tables are created lazily by `openDb()` (`src/db/open.ts`). Keep that behavior.
- `components/api/package.json` contains a pnpm-only `"allowScripts"` block that npm ignores.
- The vitest coverage config excludes `src/server.ts`, but its tests still run.

## Acceptance criteria
1. **`.env` loading:** when the server starts and a `.env` file exists in the process working directory, its variables
   are loaded before anything reads `process.env`. A missing `.env` is not an error.
2. **Migration at startup:** before listening, the server awaits `migrateAuthSchema()`. If it fails, the error is
   logged and the process exits with a non-zero code.
3. **End to end on a fresh database:** start from `components/api` with only a `.env` containing `PORT`,
   `DATABASE_PATH` (a path to a file that doesn't exist yet), `BETTER_AUTH_SECRET` and `BETTER_AUTH_URL`, using
   `npx tsx src/server.ts`. Then:
   - `GET /healthz` returns 200;
   - `POST /api/auth/sign-up/email` with JSON `{name, email, password}` and header `origin: http://localhost:5173`
     returns 200.
4. **No `allowScripts`:** `components/api/package.json` no longer contains an `allowScripts` block.
5. **Tested, and checks pass:**
   - Startup logic is unit-tested in `src/server.test.ts` without binding a real port. For example, export a
     `start()` function and keep the module side-effect-free when imported by tests.
   - Run from `components/api`, all four must pass: `npm run -s lint`, `npm run -s typecheck`, `npm run -s test`,
     `npm run -s coverage`.

## Out of scope
CORS or `WEB_ORIGIN` changes, new dependencies, and changes to the auth or database modules.

## Stop conditions
If the task cannot be done without editing files outside `files_allowed`, stop and reply `ESCALATE: <reason>`.
