#!/usr/bin/env bash
# bootstrap.sh — make a freshly-cloned AI-Dev-OS runnable on THIS machine (first-launch setup).
#
# Cloning the repo gives you the whole tree (architecture/, agents/, prompts/, scripts/, …). bootstrap does
# ONLY what the repo can't carry — the local, gitignored, per-machine setup:
#   1. the directory skeleton (tracked-but-empty working dirs),
#   2. local state: memory DB (gitignored), git hooks, exec bits, .env from .env.example,
#   3. a toolchain doctor (scripts/doctor.sh): verify/auto-install the prerequisites — sqlite3, opencode
#      (+auth), gh (+auth), shellcheck, bats, node, gitleaks — incl. a real `opencode run` liveness probe
#      + guided OpenCode-Go setup,
#   4. optional profile apply.
# It NEVER seeds content copies of canonical files — those only diverge (ADR-0020; analysis Fix 7).
#
# Idempotent + safe to re-run. Run once at the repo root after cloning:  bash bootstrap.sh [--profile <f/v>]
set -euo pipefail

# --- args ------------------------------------------------------------------
PROFILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:?--profile needs <family/variant>}"; shift 2 ;;
    *) echo "[bootstrap][warn] ignoring unknown arg: $1"; shift ;;
  esac
done

# --- locate repo root (git if available, else cwd) -------------------------
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then ROOT="$PWD"; echo "[bootstrap][warn] not a git repo yet; using $ROOT"; fi
cd "$ROOT"

c_made=0; c_skip=0
made() { printf '  \033[32m+ %s\033[0m\n' "$1"; c_made=$((c_made+1)); }
skip() { printf '  \033[90m· %s\033[0m\n' "$1"; c_skip=$((c_skip+1)); }
# keep <dir...> — ensure dir exists; drop a .gitkeep so git tracks it while empty.
keep() { local d; for d in "$@"; do mkdir -p "$d"; if [[ -z "$(ls -A "$d" 2>/dev/null)" ]]; then : > "$d/.gitkeep"; made "$d/.gitkeep"; else skip "$d/ (non-empty)"; fi; done; }

echo "[bootstrap] first-launch setup for AI-Dev-OS in: $ROOT"

# --- 1. directory skeleton (tracked working dirs; .gitkeep where empty) -----------------------------
keep tasks/backlog tasks/active tasks/completed
keep reports/daily reports/weekly reports/tasks reports/bugs reports/metrics
keep reviews/queue reviews/verdicts
keep knowledge/patterns knowledge/postmortems knowledge/external
keep docs/runbooks

# --- 2. local / per-machine git config + state (gitignored; never committed) ------------------------
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # WSL 9P / Windows editors drop the exec bit on rewrite (ADR-0010); ignore the WORKTREE bit on this clone.
  git config core.fileMode false && echo "  git config core.fileMode=false"
  # route git to the repo's hooks so pre-push runs ci-local before every push (.githooks/pre-push).
  [[ -d .githooks ]] && git config core.hooksPath .githooks && echo "  git config core.hooksPath=.githooks"
fi
# make the pipeline scripts executable on this clone (committed modes stay authoritative for CI/clones).
if compgen -G "scripts/*.sh" >/dev/null; then chmod +x scripts/*.sh bootstrap.sh 2>/dev/null && echo "  chmod +x scripts/*.sh bootstrap.sh"; fi
# the memory DB is local + gitignored (ADR-0016) — create it from the schema so the first write works.
if [[ -f scripts/db.sh ]] && command -v sqlite3 >/dev/null 2>&1; then
  bash scripts/db.sh init >/dev/null 2>&1 && echo "  memory DB ready (reports/metrics/memory.db)" \
    || echo "[bootstrap][warn] could not init memory DB — run: bash scripts/db.sh init"
else
  echo "[bootstrap][warn] sqlite3 missing — memory DB not initialized (the doctor installs it; or: sudo apt-get install -y sqlite3)"
fi
# component env: seed a local .env from the example if present (gitignored; fill in real values).
if [[ -f .env.example && ! -f .env ]]; then cp .env.example .env; made ".env (from .env.example — fill it in)"; fi

# --- 3. toolchain doctor (scripts/doctor.sh) --------------------------------------------------------
if [[ -f scripts/doctor.sh ]]; then
  bash scripts/doctor.sh || echo "[bootstrap][warn] doctor reported missing prerequisites (see above)"
else
  echo "[bootstrap] toolchain doctor not present yet (scripts/doctor.sh) — skipping preflight"
fi

# --- 4. apply a profile if requested ----------------------------------------------------------------
if [[ -n "$PROFILE" ]]; then
  if [[ -f scripts/profile.sh ]]; then
    echo "[bootstrap] applying profile: $PROFILE"
    bash scripts/profile.sh apply "$PROFILE" || echo "[bootstrap][warn] profile apply failed — run: scripts/profile.sh apply $PROFILE"
  else
    echo "[bootstrap][warn] scripts/profile.sh missing — skipped --profile $PROFILE"
  fi
fi

echo
echo "[bootstrap] done — $c_made created, $c_skip kept."
echo "[bootstrap] next: if anything new was created, commit it (git add -A && git commit -m 'chore: bootstrap'); then plan a task."
