#!/usr/bin/env bash
# doctor.sh — first-launch toolchain preflight for AI-Dev-OS (called by bootstrap.sh; run standalone anytime).
# Verifies every prerequisite, AUTO-INSTALLS what it safely can (apt tools + the opencode CLI via npm),
# GUIDES the rest, and proves OpenCode-Go works with a real `opencode run` probe (guided subscribe/connect on
# failure). Exit non-zero if a CRITICAL tool/auth is still missing; 0 (with warnings) if only quality tools.
# Flags: --no-install (check only) · --no-probe (skip the opencode run) · --probe-model <slug>.
#
# `set -uo pipefail` + arg parsing live INSIDE doctor_main so the script is safe to `source` in bats
# (doctor_main is guarded at the bottom and won't run on source — that's how the check logic is unit-tested).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"

DO_INSTALL=1; DO_PROBE=1; PROBE_MODEL="${AI_OS_PROBE_MODEL:-opencode-go/glm-5.2}"; PROBE_TIMEOUT="${AI_OS_PROBE_TIMEOUT:-120}"
ok=0; inst=0; crit_miss=0; qual_miss=0

_ok()   { printf '\033[32m  ✓ %s\033[0m\n' "${1:-}"; ok=$((ok+1)); }
_new()  { printf '\033[36m  ⤓ %s (installed)\033[0m\n' "${1:-}"; inst=$((inst+1)); }
_miss() { printf '\033[31m  ✗ %s — %s\033[0m\n' "${1:-}" "${3:-}" >&2
          if [[ "${2:-quality}" == critical ]]; then crit_miss=$((crit_miss+1)); else qual_miss=$((qual_miss+1)); fi; }

apt_install() {   # $1=pkg ; returns 0 only if installed now (grouped redirect dodges SC2024 on sudo)
  [[ "${DO_INSTALL:-1}" == 1 ]] || return 1
  command -v apt-get >/dev/null 2>&1 || return 1
  { sudo apt-get install -y "$1"; } >/dev/null 2>&1
}

# check_tool <cmd> <tier:critical|quality> <remediation> [apt-pkg]
check_tool() {
  local cmd="$1" tier="$2" rem="$3" pkg="${4:-}"
  if command -v "$cmd" >/dev/null 2>&1; then _ok "$cmd"; return 0; fi
  if [[ -n "$pkg" ]] && apt_install "$pkg" && command -v "$cmd" >/dev/null 2>&1; then _new "$cmd"; return 0; fi
  _miss "$cmd" "$tier" "$rem"; return 1
}

opencode_guide() {
  cat >&2 <<'G'
      OpenCode-Go isn't ready — enable the workforce:
        1. Install:   npm install -g opencode-ai
        2. Subscribe: create an account at opencode.ai, subscribe to "OpenCode Go", copy your API key
        3. Connect:   run `opencode` (opens the TUI) -> type /connect -> select "opencode go" -> paste the key
        4. Verify:    bash scripts/doctor.sh
G
}

doctor_main() {
  set -uo pipefail   # aggregate every check (NOT -e); options stay inside the run, not a sourcing test
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --no-install)  DO_INSTALL=0 ;;
      --no-probe)    DO_PROBE=0 ;;
      --probe-model) PROBE_MODEL="${2:?--probe-model needs a slug}"; shift ;;
      *) ;;
    esac
    shift
  done

  log "doctor — checking the AI-Dev-OS toolchain"

  # critical — the pipeline cannot run without these
  check_tool git     critical "install git"
  check_tool sqlite3 critical "sudo apt-get install -y sqlite3" sqlite3
  check_tool gh      critical "install GitHub CLI (https://github.com/cli/cli#installation), then: gh auth login" gh

  # quality — the ci-local mirror + product build
  check_tool shellcheck quality "sudo apt-get install -y shellcheck" shellcheck
  check_tool bats       quality "sudo apt-get install -y bats" bats
  check_tool node       quality "install Node 22 (nvm or nodesource) — needed for opencode + product builds"
  check_tool gitleaks   quality "install gitleaks (github.com/gitleaks/gitleaks/releases)"

  # opencode CLI — auto-install via npm (needs node), else guide
  if command -v opencode >/dev/null 2>&1; then
    _ok opencode
  elif [[ "$DO_INSTALL" == 1 ]] && command -v npm >/dev/null 2>&1 && npm install -g opencode-ai >/dev/null 2>&1 && command -v opencode >/dev/null 2>&1; then
    _new opencode
  else
    _miss opencode critical "npm install -g opencode-ai (needs Node)"
    opencode_guide
  fi

  # OpenCode-Go liveness — a real run by default; only if the CLI is present. BOUNDED + NON-INTERACTIVE:
  #   </dev/null                       — never block waiting on stdin,
  #   --dangerously-skip-permissions   — no TTY approval prompt (unattended),
  #   timeout $PROBE_TIMEOUT           — never hang forever. The old probe spun indefinitely on a hidden
  #                                      input/permission prompt even when opencode was installed + connected (BUG-28).
  if command -v opencode >/dev/null 2>&1; then
    if [[ "$DO_PROBE" == 1 ]]; then
      log "doctor — probing OpenCode-Go (≤${PROBE_TIMEOUT}s): opencode run $PROBE_MODEL"
      local rc=0
      timeout "$PROBE_TIMEOUT" opencode run --model "$PROBE_MODEL" --dangerously-skip-permissions \
        "Reply with exactly: ok" </dev/null >/dev/null 2>&1 || rc=$?
      if [[ "$rc" -eq 0 ]]; then
        _ok "OpenCode-Go reachable ($PROBE_MODEL)"
      elif [[ "$rc" -eq 124 ]]; then
        _miss "OpenCode-Go probe" critical "the run timed out after ${PROBE_TIMEOUT}s — it hung (no TTY, or not connected). Skip it with: bash scripts/doctor.sh --no-probe · or verify by hand: opencode run --model $PROBE_MODEL 'ok'"
        opencode_guide
      else
        _miss "OpenCode-Go auth" critical "the CLI is installed but the run failed (exit $rc) — likely not subscribed/connected"
        opencode_guide
      fi
    elif timeout 30 opencode models </dev/null >/dev/null 2>&1; then
      _ok "OpenCode-Go authed (models listed)"
    else
      _miss "OpenCode-Go auth" critical "opencode models failed — connect your key (see below)"
      opencode_guide
    fi
  fi

  # gh auth — only meaningful if gh is present
  if command -v gh >/dev/null 2>&1; then
    if gh auth status >/dev/null 2>&1; then _ok "gh authed"; else _miss "gh auth" critical "run: gh auth login"; fi
  fi

  echo >&2
  log "doctor: $ok ok · $inst installed · $((crit_miss + qual_miss)) missing (critical: $crit_miss)"
  if (( crit_miss > 0 )); then
    die "doctor: $crit_miss critical prerequisite(s) missing — the OS isn't ready" \
      "see the ✗ lines above" "install/auth them (or re-run after subscribing): bash scripts/doctor.sh"
  fi
  if (( qual_miss > 0 )); then warn "doctor: $qual_miss quality tool(s) missing — ci-local / product steps may skip until installed"; fi
  log "doctor: critical prerequisites OK"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then doctor_main "$@"; fi
