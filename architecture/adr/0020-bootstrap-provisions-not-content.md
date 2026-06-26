# ADR-0020: bootstrap.sh provisions a machine; it does not seed content

- **Status:** Accepted
- **Date:** 2026-06-26
- **Deciders:** Lead (Opus) + human operator

## Context
`bootstrap.sh` carried inline heredoc COPIES of ~15 files that also live canonically in the repo
(`.github/workflows/os-ci.yml`, every `agents/*.md` role card, the EXAMPLE task spec, `architecture/*`,
`scripts/ci-env.sh`, …). The AI-Dev-OS is distributed by cloning the whole repo, so those files always
already exist on clone and the copies (written only if absent) just rot. By the time we looked they had
diverged badly: the embedded `os-ci.yml` had only 3 steps with **un-SHA-pinned** actions (undoing the
supply-chain pin of #58) and none of the guards we since added; the role cards still hard-coded model names
(the staleness #87 removed — now failing check 5); the EXAMPLE used **off-catalog** slugs (`opencode/…` not
`opencode-go/…`); and it would resurrect `glossary.md` / `docs/setup.md` / `docs/usage.md`, deleted in
Fix 6. Hand-syncing two copies is exactly the manual-patch anti-pattern we reject.

Separately, a freshly cloned repo is NOT runnable until the **local, gitignored, per-machine** setup exists:
the memory DB (ADR-0016), git hooks, exec bits, `.env`, and a working toolchain (sqlite3, opencode+auth,
gh+auth, shellcheck, bats, node, gitleaks). Nothing owned that.

## Decision
`bootstrap.sh` is the **first-launch machine provisioner**, and it never copies canonical content.

- **Removed:** every content heredoc + the `wf` writer. The repo is the single source of those files.
- **bootstrap now does only what the repo can't carry:**
  1. the **directory skeleton** (tracked-but-empty working dirs, `.gitkeep`);
  2. **local/gitignored state** — `core.fileMode=false` (ADR-0010), `core.hooksPath=.githooks`,
     `chmod +x`, `db.sh init` (the memory DB), `.env` from `.env.example`;
  3. a **toolchain doctor** (`scripts/doctor.sh`) that verifies — auto-installing where it can, else
     guiding — the prerequisites, including a real `opencode run` liveness probe with guided OpenCode-Go
     setup. (Lands as a follow-up; bootstrap calls it when present.)
  4. optional **profile apply**.
- **Regression guard:** `scripts/test/bootstrap.bats` fails if `bootstrap.sh` re-embeds a canonical-file
  copy (no `<<'SEED'` heredoc, no `name: os-ci`, no workforce model token). Self-maintaining — the
  duplication cannot creep back unnoticed.

## Consequences
- Cloning + `bash bootstrap.sh --profile …` yields a runnable machine with no second, drifting copy of any
  OS file. `os-ci.yml`'s "bootstrap seeds it" note is removed.
- bootstrap grows a dependency on the local toolchain, surfaced (and largely fixed) by the doctor rather
  than failing cryptically later.

## Alternatives considered
- **Keep the copies and sync them (or generate + verify-no-diff).** Preserves a duplication we don't need —
  a clone already has the files. Rejected; deleting the second copy is the real fix.
- **Leave bootstrap as just `mkdir`.** Misses the real first-launch pain (no DB, no hooks, missing tools).
  Rejected — provisioning is bootstrap's reason to exist.
