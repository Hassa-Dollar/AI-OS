# Architecture Map — the Lead's entrypoint

> CLAUDE.md step 1 loads THIS file first. Keep it a compressed map, not the code.
> Target: a Lead (Opus) should orient from this page + the ADR index + the touched
> contracts in well under ~8K tokens. If you ever feel you must read the whole tree,
> this map is stale — fix the map, don't read everything (CLAUDE.md §1, manual P4).

## System in one paragraph
A minimal TypeScript/Node HTTP service, built incrementally by the AI-Dev-OS workforce.
`src/server.ts` is the process entrypoint; it starts an app built by the factory in `src/app.ts`.
HTTP routes live one-per-file in `src/routes/` and are mounted by the app factory. There is **no
web framework** — the standard-library `node:http` plus a tiny internal router (keeps the blast
radius small and dependencies near-zero). Cross-cutting rules live in `architecture/invariants.md`;
settled decisions in `architecture/adr/`. The first feature task adds `GET /health`.

## Module map
| Module (path) | Responsibility | Key contracts | Owner role |
|---|---|---|---|
| `src/server.ts` | process entrypoint; binds host/port, starts the app, handles shutdown | — | implementer |
| `src/app.ts` | app factory: builds the request handler + route registry | (none yet) | the Lead |
| `src/routes/*.ts` | one HTTP route per file; thin handlers that call services | (none yet) | implementer |

> **Status:** the `src/` skeleton is scaffolded by the Lead so feature tasks only add a route file.
> If `src/` is empty, that bootstrap step hasn't landed yet — it is the prerequisite for task `000`.

## Entry points
- Runtime entrypoint: `src/server.ts` → `createApp()` from `src/app.ts`.
- Build/run: `npm run dev` (watch), `npm run build` (`tsc`), `npm start` (run built output). See `docs/setup.md`.

## Invariants & decisions (do not contradict)
- Invariants: see [`invariants.md`](./invariants.md) — always hold; changing one needs an ADR.
- Decisions: see the ADR index in [`adr/`](./adr/) — start at `0001`.
- Contracts: see [`contracts/`](./contracts/) — load ONLY the ones a task touches.

## How to keep this current
The weekly architecture review (CLAUDE.md §6) reconciles this map against the code.
A merged task that adds/moves a module must update the table above in the same diff.
