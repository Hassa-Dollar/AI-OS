# ADR-0010: Stop tracking the working-tree exec bit (`core.fileMode false`)

- **Status:** Accepted
- **Date:** 2026-06-18
- **Deciders:** Lead (Opus) + human operator

## Context
The repo lives on ext4 under WSL, where git tracks the Unix executable bit (`core.fileMode=true`). Edits
that reach the files through the Windows `\\wsl.localhost` 9P mount rewrite each file at mode `644`,
dropping the `+x`. Git then records a `100755 -> 100644` mode flip on every edited script, and a pipeline
script committed as `644` is non-runnable (`scripts/dispatch.sh` / `gate.sh` → "Permission denied") — and
a `644` git hook is silently skipped. This recurred on every script edit (most recently the three scripts
in PR #23).

## Decision
- Set **`git config core.fileMode false`** (local, per-clone) and have **`bootstrap.sh` set it on every
  clone**, so git ignores the *working-tree* exec bit. Committed blob modes remain authoritative.
- One-time repair of the modes already clobbered to `644`:
  `git update-index --chmod=+x scripts/*.sh bootstrap.sh`.
- Scope kept **minimal** — chosen over also adding a CI mode-guard or a pre-commit auto-heal hook. This
  stops the churn at the source; the server-side gates already backstop correctness.

## Security analysis (the change was gated on this)
`core.fileMode=false` is a **local working-tree comparison toggle** — it changes nothing about file
contents, history, commit hashes, what GitHub stores/serves, auth, secrets, or network behavior, and it
is the *default* on Windows git for exactly this reason. The project's authoritative security gates are
all **server-side and mode-independent**: `os-ci` runs `gitleaks` + shellcheck + the isolation check as
GitHub Actions steps (which execute regardless of any file's exec bit), and branch protection requires
those checks. The local `.githooks/pre-push` hook is fast-feedback only, not the boundary — and
`core.fileMode=false` actually *protects* its committed `755` from being clobbered by an edit, since git
keeps the index mode rather than downgrading it. Intentional mode changes are still made explicitly
(`git update-index --chmod=+x`) and remain **visible in the PR diff** for review, so nothing can be made
executable silently. Residual gap: a brand-new script added without `--chmod=+x` would commit as `644`;
that is an ergonomic slip caught by the script simply not running, with the server-side gates as backstop.
**Verdict: safe — no security boundary is weakened.**

## Consequences
- Editing a script no longer produces phantom mode diffs; committed scripts stay `755` for clones + CI.
- A local `chmod +x scripts/*.sh` (or re-running `bootstrap.sh`) makes edited scripts runnable and is now
  invisible to git.
- New scripts must be made executable explicitly (`git update-index --chmod=+x <file>`).

## Alternatives considered
- **os-ci committed-mode guard** (assert `100755`): stronger, catches the new-file case — deferred to keep
  this minimal; revisit if a `644` script ever slips through.
- **pre-commit auto-heal hook** (`chmod +x` at commit): zero manual chmod, but another hook to maintain.
- **Leave as-is**: rejected — recurring breakage of the determinism layer on every script edit.
