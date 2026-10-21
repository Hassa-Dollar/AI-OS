# Architecture map — the Lead's entrypoint

Read this page first, then the [ADR index](adr/README.md), then only the contracts your work touches.

## What lives where
| Path | What |
|---|---|
| `aios/` | The orchestrator: stdlib-only Python ≥ 3.11 (ADR-0029). The line budget is enforced in CI |
| `aios/prompts/`, `aios/profiles/`, `aios/roster.toml` | Worker and verifier prompts; per-stack profiles (setup, checks, generated paths, sandbox binds); approved models by tier |
| `architecture/adr/` | Decisions. ADR-0029 is the v2 baseline |
| `architecture/contracts/` | Formats the code must honor: `spec`, `project`, `record`, `roster` |
| `docs/` | `doctrine.md` (principles), `LEAD.md` (Lead protocol), `INSTALL.md`, `lessons.md` (v1 lessons → enforcement) |
| `docs/history/` | The v1 bug registry, the determinism postmortem, and the design sketch |
| `.aios/` | AI-OS's own task specs and records. AI-OS dogfoods itself as a target repo |

## The loop (one task)
1. **Spec.** A spec lands on the default branch through `aios plan`.
2. **Route.** The router (Clef, then a decision table) picks the tier, author, verifier and gate, and records the choice (ADR-0031).
3. **Sandboxed work.** In a fresh worktree, the profile's setup runs with network but no home directory. The harness
   then runs with no network, no home directory and no keys (ADR-0032).
4. **Commit and gate.** aios commits the work. The gate runs:
   - the component's checks;
   - the boundary audit;
   - the dependency guard;
   - a cross-family verifier, whose verdict is bound to the patch-id.

   It then picks a tier: AUTO, OPERATOR, LEAD or HUMAN.
5. **Record and land.** The record (`.aios/records/<id>.json`) is committed on the branch, and the land is a PR merge
   (or a local merge).

## Where state lives
See ADR-0030. In short:
- **Specs and records** are committed in the target repo, one file per task.
- **Everything else** is machine-local and disposable.
- **Summaries** are computed from git when they are read.
