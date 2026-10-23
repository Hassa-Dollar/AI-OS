# Architecture map — the Lead's entrypoint

Read this page first, then the [ADR index](adr/README.md), then only the contracts your work touches.

## What lives where
| Path | What |
|---|---|
| `aios/` | The orchestrator: stdlib-only Python ≥ 3.11 (ADR-0029). The line budget is enforced in CI |
| `aios/prompts/`, `aios/models.toml`, `aios/calibration/` | The worker and reviewer instructions; the model policy (quality levels, measured blocks, family groupings; **no list of allowed models**, ADR-0034); the known changes every reviewer must judge correctly |
| `architecture/adr/` | Decisions. ADR-0029 is the v2 baseline |
| `architecture/contracts/` | Formats the code must honor: `spec`, `project`, `record`, `models`, `machine` |
| `docs/` | `OVERVIEW.md` (plain-language tour: start here), `doctrine.md` (principles), `LEAD.md` (Lead protocol), `INSTALL.md`, `lessons.md` (each lesson and the rule that enforces it) |
| `docs/history/` | The v1 bug registry, the determinism postmortem, and the design sketch |
| `.aios/` | AI-OS's own task specs and records. AI-OS dogfoods itself as a target repo |

## The loop (one task)
1. **Spec.** A spec lands on the default branch through `aios plan`.
2. **Route.** Clef reads the task. A decision table then sets the review level (gate) and the task's level (junior, mid or
   senior), and fills each role from the live catalog: the implementer is the cheapest model at that level, and the
   reviewer is the cheapest calibrated model from another family. The choice is recorded (ADR-0031, ADR-0034).
3. **Sandboxed work.** In a fresh worktree, the component's setup runs with network but no home directory. The harness
   then runs with no network, no home directory and no keys (ADR-0032).
4. **Commit and gate.** aios commits the work. The gate runs:
   - the component's checks;
   - the boundary audit;
   - the dependency guard;
   - a review by a model from another family, bound to the patch-id. A `fail` only counts when a second review
     confirms it (ADR-0034 section 6).

   It then sets the review level: AUTO, OPERATOR, LEAD or HUMAN.
5. **Record and land.** The record (`.aios/records/<id>.json`) is committed on the branch, and the land is a PR merge
   (or a local merge).

## Where state lives
See ADR-0030. In short:
- **Specs and records** are committed in the target repo, one file per task.
- **Everything else** is machine-local and disposable.
- **Summaries** are computed from git when they are read.
