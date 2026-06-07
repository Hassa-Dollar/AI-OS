# Architecture Map — the Lead's entrypoint

> CLAUDE.md step 1 loads THIS file first. Keep it a compressed map, not the code.
> Target: a Lead (Opus) should orient from this page + the ADR index + the touched
> contracts in well under ~8K tokens. If you ever feel you must read the whole tree,
> this map is stale — fix the map, don't read everything (CLAUDE.md §1, manual P4).

## System in one paragraph
<What this product is and the single responsibility of each top-level module. 4–6 sentences.>

## Module map
| Module (path) | Responsibility | Key contracts it owns/consumes | Owner role |
|---|---|---|---|
| `src/...` | <what> | `architecture/contracts/<name>.yaml` | implementer |

## Entry points
- Runtime entrypoint(s): <e.g. src/server.ts → bootstraps HTTP server>
- Build/run: <commands; or point to docs/setup.md>

## Invariants & decisions (do not contradict)
- Invariants: see [`invariants.md`](./invariants.md) — always hold; changing one needs an ADR.
- Decisions: see the ADR index in [`adr/`](./adr/) — start at `0001`.
- Contracts: see [`contracts/`](./contracts/) — load ONLY the ones a task touches.

## How to keep this current
The weekly architecture review (CLAUDE.md §6) reconciles this map against the code.
A merged task that adds/moves a module must update the table above in the same diff.
