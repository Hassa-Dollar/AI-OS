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
# Tolerant of markdown from verifier models: **RISK:** low, ## VERDICT: pass, VERDICT: **pass**, etc.
risk="$(grep -ioE 'RISK:[[:space:]*_#]*[A-Za-z]+'    "$verdict" | head -1 | sed -E 's/.*RISK:[[:space:]*_#]*//I'    | tr 'A-Z' 'a-z')"
vd="$(  grep -ioE 'VERDICT:[[:space:]*_#]*[A-Za-z]+' "$verdict" | head -1 | sed -E 's/.*VERDICT:[[:space:]*_#]*//I' | tr 'A-Z' 'a-z')"
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
# GATE_MERGE controls how an approved task lands on main:
#   pr    (default) push the branch + open a PR; GitHub CI + branch protection gate the merge
#   local           legacy: merge --no-ff into main locally, then you push
GATE_MERGE="${GATE_MERGE:-pr}"
slug="$(fm_scalar "$spec" slug)"
have_gh() { command -v gh >/dev/null 2>&1; }

if (( ${#flags[@]} == 0 )); then
  # ---- approved: CI green + clean cross-family QA + zero risk flags ----
  if [[ "$GATE_MERGE" == "local" ]]; then
    log "risk router: CLEAR — local auto-merge (GATE_MERGE=local)"
    git checkout main >/dev/null 2>&1
    git merge --no-ff "$branch" -m "merge(${id}): $slug"
    tag="merge/${id}-$(date +%s)"; git tag "$tag"
    mkdir -p tasks/completed && { git mv "$spec" "tasks/completed/$(basename "$spec")" 2>/dev/null || mv "$spec" "tasks/completed/"; }
    "$DIR/ledger-append.sh" auto-approve "$id" "merged tag=$tag"
    log "MERGED $branch -> main (tag $tag). Rollback: scripts/rollback.sh $tag"
  else
    log "risk router: CLEAR — opening auto-merge PR (server CI + branch protection do the final gate)"
    if [[ "${DRY_RUN:-0}" == "1" ]]; then log "DRY_RUN: would archive spec, push $branch, open an auto-merge PR -> main"; exit 0; fi
    have_gh || die "PR mode needs the GitHub CLI (gh): install it + run 'gh auth login', or rerun with GATE_MERGE=local."
    # archive the spec on the branch so it merges together with the task
    mkdir -p tasks/completed && git mv "$spec" "tasks/completed/$(basename "$spec")" 2>/dev/null \
      && git commit -q -m "chore(${id}): archive completed task spec" || true
    git push -u origin "$branch" >/dev/null 2>&1 || die "could not push $branch"
    pr_url="$(gh pr create --base main --head "$branch" --title "merge(${id}): $slug" \
      --body "Auto-approved by gate.sh — CI green, cross-family QA pass (verifier=$vmodel, risk=$risk), zero risk flags. Server CI + branch protection gate the merge." 2>&1)" \
      || die "gh pr create failed: $pr_url"
    gh pr merge "$branch" --auto --merge >/dev/null 2>&1 \
      && log "auto-merge armed — merges when required checks pass: $pr_url" \
      || warn "PR opened ($pr_url) — enable 'Allow auto-merge' in repo Settings, or merge it manually once checks pass."
    "$DIR/ledger-append.sh" auto-approve "$id" "pr=$pr_url"
  fi
else
  # ---- flagged: needs the scarce Opus gate ----
  if [[ "$GATE_MERGE" == "local" ]] || ! have_gh; then
    q="reviews/queue/${id}.md"
    {
      echo "# OPUS GATE REQUIRED — task $id"
      echo; echo "Branch: \`$branch\`  ·  files: $nfiles  ·  lines: $nlines  ·  verifier risk: $risk"
      echo; echo "## Risk flags (why this needs the Lead)"; for f in "${flags[@]}"; do echo "- $f"; done
      echo; echo "## QA verdict"; echo '```'; cat "$verdict"; echo '```'
      echo; echo "## Review with"; echo "Use prompts/code-review.md (Opus-gate addendum). Approve ⇒ open a PR for \`$branch\`, or (GATE_MERGE=local) \`git checkout main && git merge --no-ff $branch\`."
    } > "$q"
    "$DIR/ledger-append.sh" opus-gate "$id" "queued flags=${flags[*]}"
    log "risk router: FLAGGED (${flags[*]}) — queued for the Opus gate: $q"
  else
    log "risk router: FLAGGED (${flags[*]}) — opening a DRAFT PR for the Opus gate"
    if [[ "${DRY_RUN:-0}" == "1" ]]; then log "DRY_RUN: would push $branch and open a DRAFT PR (flags: ${flags[*]})"; exit 0; fi
    git push -u origin "$branch" >/dev/null 2>&1 || die "could not push $branch"
    body="$(printf 'OPUS GATE REQUIRED — review before merge.\n\nRisk flags: %s\nVerifier risk: %s · files: %s · lines: %s\n\nQA verdict:\n```\n%s\n```\n\nReview with prompts/code-review.md (Opus-gate addendum); when satisfied, mark ready and merge.' "${flags[*]}" "$risk" "$nfiles" "$nlines" "$(cat "$verdict")")"
    pr_url="$(gh pr create --draft --base main --head "$branch" --title "OPUS GATE (${id}): $slug" --body "$body" 2>&1)" \
      || die "gh pr create failed: $pr_url"
    "$DIR/ledger-append.sh" opus-gate "$id" "draft-pr=$pr_url flags=${flags[*]}"
    log "Opus gate: DRAFT PR opened — review in the evening batch: $pr_url"
  fi
fi
