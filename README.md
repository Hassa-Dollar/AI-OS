# AI-Dev-OS Scaffolding

Drop-in starter for the system described in `AI_Dev_OS_Operating_Manual.md`.
Copy the contents of this folder into the **root of your git repo**.

## What's here
```
AGENTS.md          workforce rules (OpenCode auto-loads this) — model pins, P8, authority limits
CLAUDE.md          the Lead (Opus) protocol — compressed context, planning, review gate, budget
.gitignore         ignores live telemetry (reports/metrics/ledger.csv) + secrets
prompts/           the six reusable prompts (task-exec, code-review, bug, research, arch, docs)
scripts/           dispatch.sh · gate.sh · rollback.sh · new-task.sh · ledger-append.sh · _lib.sh
```

## Prerequisites
- a git repo with a `main` branch
- OpenCode CLI + an OpenCode Go subscription (`opencode models` to see your slugs)
- Claude Pro (Opus 4.8) for planning + the review gate
- optional: `gitleaks` for secret scanning (auto-detected by gate.sh)

## First run (Phase 1, manual)
```bash
# 1. set your CI commands once (export in your shell or a .envrc)
export LINT_CMD="npm run lint"  TYPECHECK_CMD="npm run typecheck"  TEST_CMD="npm test"

# 2. create a task spec, then edit files_allowed + acceptance criteria
scripts/new-task.sh 001 add-health-endpoint opencode-go/glm-5.1 opencode-go/kimi-k2.6

# 3. dispatch it (validates P8 + file-set disjointness, makes the branch, runs the worker)
scripts/dispatch.sh 001            # add --dry-run to validate without calling a model

# 4. gate it: CI -> cross-family QA -> risk router -> auto-merge OR queue for the Opus gate
scripts/gate.sh 001                # low-risk merges; contract/security/large diffs queue to reviews/queue/

# 5. if something regresses
scripts/rollback.sh <merge-tag> "reason"
```

## Customize these
- **Model slugs** in `AGENTS.md` — match `opencode models` exactly; pin versions (never "latest").
- **CI commands** — env vars consumed by `gate.sh` (`LINT_CMD`, `TYPECHECK_CMD`, `TEST_CMD`, `COVERAGE_CMD`, `SECRET_SCAN_CMD`).
- **Risk thresholds** in `gate.sh` — `MAX_FILES` (10), `MAX_LINES` (300), `SECURITY_REGEX`. Tune weekly from the ledger (manual §8.5, §12.4).
- **Coding conventions / invariants** in `AGENTS.md` §4 and `architecture/invariants.md`.

## Invariants the scripts enforce (verified)
- P8: the Verifier is never the author's model family (dispatch refuses violations; new-task auto-fixes).
- P2/P3: no two active task branches may share a file (`files_allowed` must be disjoint).
- The risk router auto-approves only CI-green + clean cross-family QA + zero risk flags; everything
  else (contract/schema/security/new-dep/large/high-blast) is queued for the scarce Opus gate.
- One task = one `--no-ff` merge commit = one-command rollback.

`DRY_RUN=1` makes dispatch/gate run every check without invoking a model — use it to learn the flow.
