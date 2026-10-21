# ADR-0030: Target-repo model — AI-OS is a tool; each product keeps its own state

- **Status:** Accepted
- **Date:** 2026-10-21
- **Deciders:** Lead + human operator

## Context
In v1, products were components inside this public repo. That had three costs:
- Products were public.
- OS history and product history were mixed.
- Embedded toolchains that want to own a repo's root layout could not fit.

The ledger and memory were machine-local and got lost. The handoff and coherence machinery committed generated files
to `main`, and that caused conflicts (BUG-04).

## Decision
AI-OS is a tool pointed at a **target repo**. State is split three ways:

| Where | What | Why |
|---|---|---|
| Tool repo (public) | `aios/` package, `prompts/`, `profiles/`, `roster.toml`, ADRs, contracts | Shared by every project; contains no project data |
| Target repo, committed | `.aios/project.toml` and `.aios/tasks/<id>.md` (human-written); `.aios/records/<id>.json` (aios-written) | Durable, travels with the product, reviewable |
| Machine (never committed) | `~/.config/aios/` (config, credentials 0600), `~/.cache/aios/` (catalog), `~/.local/state/aios/<project>/runs/` (logs, trajectories), `~/.local/share/aios/` (worktrees, pinned tool, harness) | Private, re-fetchable or disposable |

**Rules**
1. **What gets committed.** Only per-task files are ever committed: one spec and one record per task. Parallel task
   branches therefore cannot conflict.
   - Records hold the routing decision, the attempts (model, steps, tokens, dollars, exit status), the verdict summary,
     flags, the tier, the approval note, lessons and the tool and harness versions.
   - Records never hold prompts, transcripts, absolute paths or usernames.
2. **Summaries are computed when read.** Status, brief, report and savings are calculated from `origin/<default>`, so no
   generated file is ever committed.
3. **State comes from git.** Each task's state follows from what git already shows:

   | Git shows | Task state |
   |---|---|
   | spec without a record | ready |
   | live `aios/<id>` worktree | in flight |
   | record on the default branch | done |
   | record removed by a revert | rolled back |

   The last row gives P9 ("stays merged") for free.
4. **Nothing is pushed directly to a protected default branch.**
   - Specs land through `aios plan`, as a `plan/*` branch merged by PR.
   - Records are committed on the task branch before the merge. An approval is just another commit on that branch.
   - The merge commit is the land event. A rollback is a revert PR.
5. **aios never writes to the operator's main checkout.**
6. **Worktree lifecycle.** Each attempt goes through these steps:
   1. Fetch, then create `worktree add -b aios/<id> <wt> origin/<default>`.
   2. Run the profile's `setup` in a sandbox that has network but no home directory.
   3. Run the harness in a sandbox with no network.
   4. **aios makes the commit.**
   5. Run the gate in the same worktree, under a lock.
   6. Land, then remove the worktree.

   Untracked files such as `.env` are never copied into a worktree, because whatever a worker can read may reach a
   model provider.
7. **Conventions.** The target's own `AGENTS.md`, if present, goes into the worker prompt. Precedence is:
   - for process: spec > aios protocol > repo `AGENTS.md`;
   - for code style: repo `AGENTS.md` > profile.

   aios writes nothing into the target for its own sake.
8. **Monorepos.** Each `[[components]]` entry declares `name`, `path`, `profile` and `checks`, and a file maps to the
   component with the longest matching path prefix.
   - Touching more than one component raises a flag rather than stopping the task.
   - A component with no checks fails closed unless it declares `checks = []` with a reason.
9. **Forges.** Two are supported: `github` (an explicit merge once checks are green) and `local` (`merge --no-ff` into a
   clean tree). Others are added only when a target needs them.
10. **Versioning.** `project.toml` carries `schema`. The tool refuses newer schemas, still reads the previous one, and
    upgrades through `aios migrate` as a PR. Records are immutable once merged and carry `record_schema`.
11. **Dogfooding.** AI-OS is itself a target. The tool that runs is a pinned clone at a release tag, never the
    development checkout. AI-OS marks its own gate, harness and forge code as `sensitive`, which raises a LEAD flag.
12. **Privacy.** A `[privacy]` section sets `data_collection = "deny"` (the default), `zdr`, `deny_vendors` and
    `max_tier`. It is enforced on every model call. Routing runs locally, so specs never leave the machine to be routed.

## Consequences
- **Easier.**
  - Products can be private while the tool stays public.
  - Losing a machine loses nothing durable.
  - Parallel tasks never conflict.
  - Embedded toolchains keep their native repo layout.
- **Harder.**
  - Cross-project statistics must be gathered by reading several repos. A local cache is allowed; it's rebuilt from
    records.
- **Contracts created:** `project.schema.md`, `spec.schema.md`, `record.schema.md`.

## Alternatives considered
- **Keep the monorepo with extraction** (v1). Products stay public, and history gets mixed.
- **A central database for state.** That is a single point of loss, and it is exactly what v1 lost.
