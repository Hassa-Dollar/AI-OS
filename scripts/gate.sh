#!/usr/bin/env bash
# gate.sh — the review pipeline for one task branch (manual §9):
#   1. rebase onto main   2. CI gate   3. cross-family QA   4. risk router
#   5. auto-approve+merge  OR  queue for the Opus gate.
#
# Usage: gate.sh <task-id|branch> [--dry-run]
# Config (env, all optional — empty CI steps are skipped with a warning):
#   LINT_CMD TYPECHECK_CMD TEST_CMD COVERAGE_CMD SECRET_SCAN_CMD
#   MAX_FILES (default 10)  MAX_LINES (default 300)
#   SECURITY_REGEX (default 'auth|payment|secret|crypto|security|migrat')
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/_lib.sh"
cd "$(repo_root)"

arg="${1:?usage: gate.sh <task-id|branch> [--dry-run]}"
[[ "${2:-}" == "--dry-run" ]] && export DRY_RUN=1

# --- resolve branch + spec -------------------------------------------------
if git rev-parse --verify "$arg" >/dev/null 2>&1; then branch="$arg"; id="${arg##*/}"; id="${id%%-*}"
else id="$arg"; branch="$(git for-each-ref --format='%(refname:short)' refs/heads/ | grep -E "^task/${id}-" | head -1)"; fi
[[ -n "${branch:-}" ]] || die "no branch for '$arg'"
shopt -s nullglob
specs=( "tasks/active/${id}-"*.md "tasks/active/${id}.md" ); spec="${specs[0]:-}"
[[ -n "$spec" ]] || die "no active spec for id $id"
log "gating task $id on branch $branch (spec $spec)"

MAX_FILES="${MAX_FILES:-10}"; MAX_LINES="${MAX_LINES:-300}"
SECURITY_REGEX="${SECURITY_REGEX:-auth|payment|secret|crypto|security|migrat}"
SECRET_SCAN_CMD="${SECRET_SCAN_CMD:-$(command -v gitleaks >/dev/null 2>&1 && echo 'gitleaks detect --no-banner -v' || echo '')}"

# --- 1. rebase onto main (linear history; semantic conflict ⇒ escalate) -----
git checkout "$branch" >/dev/null 2>&1
if ! git rebase main; then
  git rebase --abort || true
  die "rebase conflict on $branch — likely a SEMANTIC conflict (contract drift). Escalate to the Lead (manual §8.3)."
fi

# --- 2. CI gate ------------------------------------------------------------
run_step() { local name="$1" cmd="$2"
  [[ -z "$cmd" ]] && { warn "CI: skip $name (no command set)"; return 0; }
  log "CI: $name -> $cmd"; bash -c "$cmd" || die "CI step '$name' FAILED — back to implementer."; }
run_step lint        "${LINT_CMD:-}"
run_step typecheck   "${TYPECHECK_CMD:-}"
run_step test        "${TEST_CMD:-}"
run_step coverage    "${COVERAGE_CMD:-}"
run_step secret-scan "${SECRET_SCAN_CMD:-}"
log "CI gate passed"

# --- diff stats (vs main) --------------------------------------------------
changed="$(git diff --name-only main..."$branch")"
nfiles="$(printf '%s\n' "$changed" | grep -c . || true)"
nlines="$(git diff --numstat main..."$branch" | awk '{a+=$1+$2} END{print a+0}')"

# --- 3. cross-family QA ----------------------------------------------------
author="$(fm_scalar "$spec" model)"; vmodel="$(fm_scalar "$spec" verifier_model)"
[[ "$(family_of "$author")" != "$(family_of "$vmodel")" ]] || die "P8 violation in spec: verifier shares author family."
mkdir -p reviews/verdicts reviews/queue
verdict="reviews/verdicts/${id}.txt"
run_verifier() {  # writes RISK/VERDICT to $verdict using the code-review prompt
  if [[ -s "$verdict" ]]; then warn "using existing verdict $verdict"; return 0; fi
  if [[ "${DRY_RUN:-0}" == "1" ]]; then printf 'RISK: low\nVERDICT: pass\nBLOCKING: []\n' > "$verdict"; return 0; fi
  command -v opencode >/dev/null 2>&1 || die "opencode CLI not found (or run --dry-run)"
  local d; d="$(mktemp)"; git diff main..."$branch" > "$d"
  opencode run --model "$vmodel" \
    "$(printf '%s\n\n--- DIFF ---\n%s\n\n--- SPEC ---\n%s' "$(cat prompts/code-review.md)" "$(cat "$d")" "$(cat "$spec")")" \
    > "$verdict"
  rm -f "$d"
}
log "QA: verifier=$vmodel (author=$author)"
run_verifier
risk="$(grep -iE '^RISK:'    "$verdict" | head -1 | sed -E 's/^[Rr][Ii][Ss][Kk]:[[:space:]]*//' | tr 'A-Z' 'a-z' | tr -d '[:space:]')"
vd="$(  grep -iE '^VERDICT:' "$verdict" | head -1 | sed -E 's/^[Vv][Ee][Rr][Dd][Ii][Cc][Tt]:[[:space:]]*//' | tr 'A-Z' 'a-z' | tr -d '[:space:]')"
risk="${risk:-high}"; vd="${vd:-fail}"
"$DIR/ledger-append.sh" qa "$id" "verifier=$vmodel risk=$risk verdict=$vd files=$nfiles lines=$nlines"
[[ "$vd" == "pass" ]] || die "QA VERDICT=fail — back to implementer (see $verdict)."

# --- 4. risk router --------------------------------------------------------
flags=()
printf '%s\n' "$changed" | grep -qE '^architecture/contracts/' && flags+=("touches-contract")
[[ -n "$(fm_list "$spec" depends_on_contracts)" ]] && printf '%s\n' "$changed" | grep -qE '^architecture/' && flags+=("touches-architecture")
[[ "$(fm_scalar "$spec" blast_radius)" == "high" ]] && flags+=("blast-radius-high")
(( nfiles > MAX_FILES )) && flags+=("files>$MAX_FILES")
(( nlines > MAX_LINES )) && flags+=("lines>$MAX_LINES")
printf '%s\n' "$changed" | grep -qiE "$SECURITY_REGEX" && flags+=("security-path")
printf '%s\n' "$changed" | grep -qiE '(^|/)(package\.json|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|requirements\.txt|pyproject\.toml|poetry\.lock|go\.(mod|sum)|Cargo\.(toml|lock)|Gemfile(\.lock)?)$' && flags+=("dependency-change")
[[ "$risk" == "high" ]] && flags+=("verifier-risk-high")

# --- 5. decide -------------------------------------------------------------
if (( ${#flags[@]} == 0 )); then
  log "risk router: CLEAR — auto-approving (CI + cross-family QA sufficient, manual §9.2)"
  git checkout main >/dev/null 2>&1
  git merge --no-ff "$branch" -m "merge(${id}): $(fm_scalar "$spec" slug)"
  tag="merge/${id}-$(date +%s)"; git tag "$tag"
  "$DIR/ledger-append.sh" auto-approve "$id" "merged tag=$tag"
  # archive the spec
  mkdir -p tasks/completed && git mv "$spec" "tasks/completed/$(basename "$spec")" 2>/dev/null || mv "$spec" "tasks/completed/"
  log "MERGED $branch -> main (tag $tag). Rollback: scripts/rollback.sh $tag"
else
  q="reviews/queue/${id}.md"
  {
    echo "# OPUS GATE REQUIRED — task $id"
    echo; echo "Branch: \`$branch\`  ·  files: $nfiles  ·  lines: $nlines  ·  verifier risk: $risk"
    echo; echo "## Risk flags (why this needs the Lead)"; for f in "${flags[@]}"; do echo "- $f"; done
    echo; echo "## QA verdict"; echo '```'; cat "$verdict"; echo '```'
    echo; echo "## Review with"; echo "Use prompts/code-review.md (Opus-gate addendum). Approve ⇒ \`git checkout main && git merge --no-ff $branch\`."
  } > "$q"
  "$DIR/ledger-append.sh" opus-gate "$id" "queued flags=${flags[*]}"
  log "risk router: FLAGGED (${flags[*]}) — queued for the Opus gate: $q"
  log "Opus is SCARCE: review this in the evening batch, not now."
fi
