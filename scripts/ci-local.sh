#!/usr/bin/env bash
# ci-local.sh — run the os-ci 'os' job locally BEFORE pushing, so failures surface without a PR
# round-trip (the push→fail→fix→push loop that BUG-13/BUG-18 cost us). Mirrors .github/workflows/os-ci.yml.
# Tools it can't find locally are SKIPPED with a note (CI still runs them). Invoke: bash scripts/ci-local.sh
set -uo pipefail   # deliberately NOT -e: run every check, aggregate, and report all failures in one pass
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)" || exit 1   # explicit: no `set -e` here (we aggregate), so guard cd (SC2164)

fails=0
ok()   { printf '\033[32m  ✓ %s\033[0m\n' "$1"; }
bad()  { printf '\033[31m  ✗ %s\033[0m\n' "$1"; fails=$((fails + 1)); }
skip() { printf '\033[33m  · skip: %s\033[0m\n' "$1"; }

log "ci-local — mirroring os-ci on '$(git branch --show-current 2>/dev/null || echo detached)'"

# 1) shellcheck (determinism layer)
if command -v shellcheck >/dev/null; then
  if shellcheck --severity=warning scripts/*.sh bootstrap.sh .githooks/pre-push; then ok "shellcheck"; else bad "shellcheck"; fi
else skip "shellcheck not installed"; fi

# 2) tracked scripts are executable in the index (committed mode 100755 — registry BUG-01)
bad_x="$(git ls-files -s -- 'scripts/*.sh' bootstrap.sh .githooks/pre-push \
  | awk '$1!="100755" && $4!="scripts/_lib.sh" && $4!="scripts/ci-env.sh"{print $4}')"
if [[ -z "$bad_x" ]]; then ok "exec-bit (committed 100755)"; else bad "exec-bit (fix: git update-index --chmod=+x $bad_x)"; fi

# 3) scripts invoke siblings via bash, not direct exec (exec-bit independence — BUG-18)
hits="$(grep -nE '(^[[:space:]]*|exec )"\$DIR/[A-Za-z._-]+\.sh"' scripts/*.sh || true)"
if [[ -z "$hits" ]]; then ok "sibling-exec via bash"; else bad "direct sibling-exec found:"; printf '%s\n' "$hits"; fi

# 4) component isolation — one-way boundary (ADR-0002)
iso=0; shopt -s nullglob
for c in components/*/; do
  [[ -d "${c}src" ]] || continue
  grep -RqE "['\"][^'\"]*\.\./[^'\"]*(scripts|architecture|prompts|agents|reviews|reports|components)/" "${c}src" 2>/dev/null && iso=1
done
if [[ $iso -eq 0 ]]; then ok "component-isolation"; else bad "component-isolation (a component's src climbs outside it)"; fi

# 5) coherence — generated doc blocks + component/profile graph (verify-no-diff + graph; Step 4 / ADR-0018)
if out="$(bash "$DIR/verify-coherence.sh" 2>&1)"; then ok "coherence (docs + graph)"; else bad "coherence (docs/graph drift)"; printf '%s\n' "$out"; fi

# 6) determinism-layer tests (bats)
if command -v bats >/dev/null && command -v sqlite3 >/dev/null; then
  if bash "$DIR/test.sh"; then ok "bats"; else bad "bats"; fi
else skip "bats/sqlite3 not installed"; fi

# 7) secret-scan (gitleaks) — optional locally; CI is authoritative
if command -v gitleaks >/dev/null; then
  if gitleaks detect --no-banner 2>/dev/null; then ok "gitleaks"; else bad "gitleaks (secret finding or error)"; fi
else skip "gitleaks not installed"; fi

echo
if [[ $fails -eq 0 ]]; then
  log "ci-local: ALL GREEN — safe to push"
else
  die "ci-local: $fails check(s) failed" "see the ✗ lines above" "fix them, then re-run: bash scripts/ci-local.sh"
fi
