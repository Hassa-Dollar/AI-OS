# Coding conventions — web-app/ts-node-service  (profile-provided; ADR-0003)

> `profile.sh apply` copies this to `architecture/conventions.md` (the canonical path workers read).
> Workers follow these for any task in a component governed by this profile. OS-level invariants are
> separate (`architecture/invariants.md`) and hold regardless of profile.

## Stack & tooling
- Language/runtime: **TypeScript 5.x on Node 22 LTS**, ESM modules, `tsconfig` `strict: true` (never relaxed).
- Lint/format: `npm run lint` (ESLint + `@typescript-eslint`); never hand-format; never disable a rule
  inline — an `// eslint-disable` is an `ESCALATE`, not a fix.
- Tests: `npm test` (Vitest); new code requires tests; **diff coverage ≥ 90%** (`npm run coverage`).
- Types: `npm run typecheck` (`tsc --noEmit`) must pass; no `any` and no non-null `!` without a `// reason:` comment.

## Stack invariants (always hold for this profile)
1. Timestamps are UTC, ISO-8601 (or integer epoch-ms). Never format, store, or compare in local time.
2. Money and quantities are integer minor-units (e.g. cents); never floats.
3. Route handlers stay thin: no direct DB, filesystem, or network I/O inside a handler — parse input,
   call a service/repository, shape the response.
4. `tsconfig` strict mode is never relaxed; no `any` / non-null `!` without a `// reason:` comment.

## Errors & secrets
- Fail loud in dev; handle at the boundary in prod; never swallow exceptions.
- Never read, log, echo, or commit secrets. If a task needs one, `ESCALATE`.
