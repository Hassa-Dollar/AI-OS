# Architecture Map — the Lead's entrypoint

> CLAUDE.md step 1 loads THIS file first. Keep it a compressed map, not the code.
> Target: a Lead (Opus) should orient from this page + the ADR index + the touched
> contracts in well under ~8K tokens. If you ever feel you must read the whole tree,
> this map is stale — fix the map, don't read everything (CLAUDE.md §1, manual P4).

**This directory = the system's _decisions and truth_** — ADRs, contracts, invariants, glossary (the
*why*). For *how to use / operate* the system see `docs/`; for cross-cutting *wisdom* (patterns,
postmortems, distilled research) see `knowledge/`.

## System in one paragraph
A minimal TypeScript/Node HTTP service — the first **component**, `components/service/`, governed by the
`web-app/ts-node-service` profile (`.component.yml`). `components/service/src/server.ts` is the process
entrypoint; it starts an app built by the factory in `src/app.ts`. HTTP routes live one-per-file in
`src/routes/` and are mounted by the app factory. There is **no web framework** — standard-library
`node:http` plus a tiny internal router. The component is **self-contained and extractable** (ADR-0002):
the OS reaches in, never the reverse. Cross-cutting OS rules live in `architecture/invariants.md`; settled
decisions in `architecture/adr/`.

## Module map
| Module (path) | Responsibility | Key contracts | Owner role |
|---|---|---|---|
| `components/service/` | the deliverable; self-contained + extractable; profile in `.component.yml` | `contracts/os-component-boundary.md` | implementer |
| `components/service/src/server.ts` | process entrypoint; binds host/port, starts the app, handles shutdown | — | implementer |
| `components/service/src/app.ts` | app factory: builds the request handler + route registry | (none yet) | the Lead |
| `components/service/src/routes/*.ts` | one HTTP route per file; thin handlers that call services | (none yet) | implementer |

> **Status:** the service skeleton lives in `components/service/` (moved there in T-D). Add another
> deliverable as a new `components/<name>/` from a profile — never alongside this one in the same dir.

## Entry points
- Runtime entrypoint: `components/service/src/server.ts` → `createApp()` from `./app`.
- Build/run: `cd components/service && npm run dev` (watch) · `npm start` · `npm test`. See `docs/INSTALL.md`.

## Invariants & decisions (do not contradict)
- Invariants: see [`invariants.md`](./invariants.md) — always hold; changing one needs an ADR.
- Decisions: see the ADR index in [`adr/`](./adr/) — start at `0001`.
- Contracts: see [`contracts/`](./contracts/) — load ONLY the ones a task touches.

## How to keep this current
The weekly architecture review (CLAUDE.md §6) reconciles this map against the code.
A merged task that adds/moves a module must update the table above in the same diff.
