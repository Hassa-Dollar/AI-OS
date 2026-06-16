# Install & first run

How to stand up the AI-Dev-OS scaffold in a repo. (Identity + the daily loop are in the root
[`README.md`](../README.md); the full system is `OPERATING_MANUAL.md`.)

## Prerequisites
- A git repo with a `main` branch, hosted on GitHub (branch protection on `main` is recommended).
- **OpenCode CLI** + an **OpenCode Go** subscription — the open-weight workforce (`opencode models`
  lists your slugs; match them in the active profile's `profile.json`).
- **Claude Pro** (Opus 4.8) for planning + the review gate (the Lead).
- **`gh`** (GitHub CLI), authenticated — PR-mode gate/land use it.
- Optional: **`gitleaks`** for secret scanning (auto-detected by `gate.sh`).

## Bootstrap
`bootstrap.sh` seeds the OS skeleton (idempotent — never overwrites an existing file) and applies a
**profile** to your first component:

```bash
bash bootstrap.sh --profile web-app/ts-node-service
git add -A && git commit -m "chore: bootstrap AI-Dev-OS"
```

A profile fills the four specialization seams (conventions, invariants, CI commands, product skeleton)
and the role→model bindings; the component it scaffolds lives in `components/<name>/` and is
self-contained (see `architecture/contracts/os-component-boundary.md`).

## The daily loop (two commands per task)
```bash
# 1. the Lead writes a spec straight into tasks/active/<id>-<slug>.md (schema: manual §6.6)
scripts/dispatch.sh <id>     # validates P8 + file-set disjointness, makes the branch, runs the worker
scripts/ship.sh <id>         # gate (CI + cross-family QA + risk router) → PR/auto-merge → land
# risk-flagged diffs stop at a DRAFT PR for the Opus gate; land.sh refuses to land drafts
scripts/rollback.sh <merge-tag> "reason"   # one-command revert if something regresses
```
Process/docs changes by the Lead: commit on a `chore/*` branch, then `scripts/pr.sh` (push → PR →
auto-merge → land). Don't use `ship.sh` for chore branches — its gate step requires a task spec.

## Configure for your stack
Specialization lives in the **profile**, not in the scripts:
- **Model slugs + role bindings** — `profiles/<family>/<variant>/profile.json` (match `opencode models`;
  pin versions, never "latest").
- **CI commands** — `profiles/<family>/<variant>/ci-env.sh` (consumed by `gate.sh`) and the matching
  `product-ci.yml` (OS-wide checks live in the OS-owned `os-ci.yml`, ADR-0006).
- **Risk thresholds** — `max_files` / `max_lines` in `profile.json` (tune weekly from the ledger;
  manual §8.5, §12.4).
- **Coding rules / invariants** — `conventions.md` + `invariants.md` in the profile.

## Notes
- `DRY_RUN=1` (or `--dry-run`) makes `dispatch`/`gate` run every check **without** invoking a model — use
  it to learn the flow.
- Enable the pre-push hook once: `git config core.hooksPath .githooks`.
- Editing a script through a file editor can strip its `+x` bit — `chmod +x scripts/*.sh` (or run via
  `bash scripts/<x>.sh`).
