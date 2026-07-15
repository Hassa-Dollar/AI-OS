#!/usr/bin/env bash
# gate.sh — the review pipeline for one task branch (manual §9):
#   1. rebase onto main   2. CI gate   3. cross-family QA   4. risk router
#   5. auto-approve+merge  OR  queue for the Lead gate.
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
specs=(); for s in "tasks/active/${id}-"*.md "tasks/active/${id}.md"; do [[ -f "$s" ]] && specs+=("$s"); done
spec="${specs[0]:-}"
[[ -n "$spec" ]] || die "no active spec for id $id" \
  "no file tasks/active/${id}-*.md or tasks/active/${id}.md exists" \
  "check the id, or create the spec: scripts/new-task.sh $id <slug>"
log "gating task $id on branch $branch (spec $spec)"

# Local CI commands: self-source the repo defaults — ci-env.sh respects already-set env vars.
# (Without this, lint/typecheck/test/coverage silently skip unless the shell sourced it manually.)
[[ -f "$DIR/ci-env.sh" ]] && source "$DIR/ci-env.sh"

# resolve the component this task targets — prefer the spec's files_allowed (ADR-0013) so a multi-component
# repo needs no COMPONENT= hint; fall back to the sole component. CI/build run INSIDE it (ADR-0002).
# A task that targets no component (docs / research / OS chore) gets a LIGHTER gate below — component
# build/isolation/deps/dangerous-API are skipped; boundary audit + secret-scan + QA + risk router still run.
comp="$(component_of_spec "$spec")"
if [[ -n "$comp" ]]; then log "component: $comp"; else log "no component in files_allowed — OS/docs task (lighter gate)"; fi

MAX_FILES="${MAX_FILES:-10}"; MAX_LINES="${MAX_LINES:-300}"
SECURITY_REGEX="${SECURITY_REGEX:-auth|payment|secret|crypto|security|migrat}"
SECRET_SCAN_CMD="${SECRET_SCAN_CMD:-$(command -v gitleaks >/dev/null 2>&1 && echo 'gitleaks detect --no-banner -v' || echo '')}"

# --- 0. preflight: worktree must be clean ------------------------------------
# The auto-generated handoff (land.sh leaves it pending to ride the next PR) must never block a gate —
# discard it; it is regenerated post-merge (registry BUG-04/05).
git restore docs/handoff/SESSION-HANDOFF.md 2>/dev/null || true
# Distinguishes "worker forgot to commit" from a real semantic conflict — they need
# different fixes, and the old flow blamed the wrong one (misleading escalation).
if [[ -n "$(git status --porcelain)" ]]; then
  git status --short >&2
  die "worktree is DIRTY — worker output is not fully committed. Fix: git checkout $branch && git add -A && git commit. This is NOT a semantic conflict; do not escalate."
fi

# --- 1. rebase onto main (linear history; semantic conflict ⇒ escalate) -----
git checkout "$branch" >/dev/null 2>&1 || die "could not checkout $branch"
if ! git rebase main; then
  git rebase --abort || true
  die "rebase CONFLICT on $branch (worktree was clean, so this is a real content/semantic conflict with main — likely contract drift). Escalate to the Lead (manual §8.3)."
fi

# --- 2. CI gate ------------------------------------------------------------
run_step() { local name="$1" cmd="$2"
  [[ -z "$cmd" ]] && { warn "CI: skip $name (no command set)" "no command configured for '$name'" "set the matching *_CMD in scripts/ci-env.sh (or the active profile's ci-env.sh)"; return 0; }
  log "CI: $name -> (${comp:-repo-root}) $cmd"
  ( { [[ -z "$comp" ]] || cd "$comp"; } && bash -c "$cmd" ) || die "CI step '$name' FAILED" "the $name command exited non-zero in ${comp:-repo root}" "reproduce: (cd ${comp:-.} && $cmd) — fix, commit on the branch, re-run gate"; }
if [[ -n "$comp" ]]; then          # component build steps only when the task targets a component
  run_step lint      "${LINT_CMD:-}"
  run_step typecheck "${TYPECHECK_CMD:-}"
  run_step test      "${TEST_CMD:-}"
  run_step coverage  "${COVERAGE_CMD:-}"
  run_step audit     "${AUDIT_CMD:-}"     # AC8: no high/critical RUNTIME advisories (matters at T02+ deps)
fi
run_step secret-scan "${SECRET_SCAN_CMD:-}"   # repo-wide; always
log "CI gate passed"

# --- diff stats (vs main) --------------------------------------------------
# `changed` is the FULL file list — boundary audit + flag path-greps must still see the lockfile/package.json.
# The risk METRICS exclude generated/vendored paths (risk_nfiles/risk_nlines) so a 4k-line lockfile can't
# inflate the diff into a false "lines>MAX" Lead-gate flag (BUG-23).
changed="$(git diff --name-only main..."$branch")"
nfiles="$(risk_nfiles main "$branch")"
nlines="$(risk_nlines main "$branch")"

# --- guardrail (ADR-0002): boundary audit — every changed file must be authorized ----
# Stops a worker/autonomous run from quietly editing files the spec didn't grant (another task's
# area, or the OS). Allowed = files_allowed + the spec itself + reports/tasks/* + tasks/completed/*.
allowed="$(fm_list "$spec" files_allowed)"; escapes=""
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  path_allowed "$f" "$allowed" && continue   # exact match, or a trailing-slash dir grant (ADR-0028)
  [[ "$f" == "$spec" || "$f" == reports/tasks/* || "$f" == tasks/completed/* ]] && continue
  escapes+="$f "
done <<< "$changed"
if [[ -n "$escapes" ]]; then
  bash "$DIR/ledger-append.sh" guardrail "$id" "escaped_files=$escapes"
  die "diff touches files outside files_allowed: $escapes" \
    "the worker edited files the spec didn't authorize (AGENTS.md §3 / ADR-0002 boundary)" \
    "revert them (git checkout main -- <files>), or if intended add them to the spec's files_allowed and re-gate"
fi

# --- guardrail (ADR-0002): component isolation — source must not climb out ----------
# Heuristic but loud: a relative import that uses ../ to reach an OS dir or a sibling component.
if [[ -n "$comp" && -d "$comp/src" ]]; then
  bad="$(grep -RInE "['\"][^'\"]*\.\./[^'\"]*(scripts|architecture|prompts|agents|reviews|reports|components)/" "$comp/src" 2>/dev/null || true)"
  [[ -z "$bad" ]] || die "component source reaches outside $comp" \
    "an import climbs out to the OS or a sibling component (one-way rule, ADR-0002):
$(printf '%s' "$bad" | head -3)" \
    "keep the component self-contained; cross-component access needs a contract in architecture/contracts/"
fi

# --- guardrail (ADR-0014): a worker may only ADD runtime deps the spec pre-approved ------------
pkg="$comp/package.json"
if [[ -n "$comp" && -f "$pkg" ]] && command -v node >/dev/null 2>&1; then
  _runtime_deps() { node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const p=JSON.parse(s);process.stdout.write(Object.keys(p.dependencies||{}).join("\n"))}catch(e){}})'; }
  after="$(_runtime_deps < "$pkg")"
  before="$(git show "main:$pkg" 2>/dev/null | _runtime_deps || true)"
  approved="$(fm_list "$spec" deps_preapproved)"   # fm_list strips YAML quotes at the root now (registry BUG-02)
  unapproved=""
  while IFS= read -r d; do
    [[ -z "$d" ]] && continue
    printf '%s\n' "$before"   | grep -qxF "$d" && continue
    printf '%s\n' "$approved" | grep -qxF "$d" && continue
    unapproved+="$d "
  done <<< "$after"
  [[ -z "$unapproved" ]] || { bash "$DIR/ledger-append.sh" guardrail "$id" "unapproved_deps=$unapproved"; \
    die "runtime dependency added without pre-approval: $unapproved" \
      "a worker added a package not in the spec's deps_preapproved (supply-chain guard, ADR-0014 / AGENTS.md §3)" \
      "if intended, add it to deps_preapproved in $spec and re-gate; otherwise it must be removed"; }
  # ADR-0026 suppression eligibility: the Lead already approved these deps at SPEC time, so a verified
  # pre-approved ADDITION is not news. Compute the FULL dep-entry delta (dependencies + devDependencies,
  # name@version): eligible only if the delta is additions-only and every added NAME is pre-approved —
  # a version change or removal shows up as a departed entry and disqualifies; lockfile-only churn
  # (no entry added) also disqualifies (that's drift, not an approved addition).
  _dep_entries() { node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const p=JSON.parse(s);for(const sec of["dependencies","devDependencies"])for(const[k,v]of Object.entries(p[sec]||{}))console.log(sec+" "+k+"@"+v)}catch(e){}})'; }
  a_ent="$(_dep_entries < "$pkg" | sort)"
  b_ent="$(git show "main:$pkg" 2>/dev/null | _dep_entries | sort || true)"
  gone_ent="$(comm -23 <(printf '%s\n' "$b_ent") <(printf '%s\n' "$a_ent") | grep . || true)"
  added_ent="$(comm -13 <(printf '%s\n' "$b_ent") <(printf '%s\n' "$a_ent") | grep . || true)"
  bad_add=""
  while read -r _sec nv; do
    [[ -z "$nv" ]] && continue
    n="${nv%@*}"   # strip from the LAST @ so scoped names (@scope/pkg@^1.0) keep their scope
    printf '%s\n' "$approved" | grep -qxF "$n" || bad_add+="$n "
  done <<< "$added_ent"
  dep_suppress_ok=0
  [[ -z "$gone_ent" && -z "$bad_add" && -n "$added_ent" ]] && dep_suppress_ok=1
fi

# --- guardrail (ADR-0014): ban dynamic-execution APIs in component source ----------------------
if [[ -n "$comp" && -d "$comp/src" ]]; then
  danger="$(grep -RInE '\beval[[:space:]]*\(|\bnew[[:space:]]+Function[[:space:]]*\(|child_process' "$comp/src" 2>/dev/null || true)"
  [[ -z "$danger" ]] || die "dangerous dynamic-execution API in component source" \
    "eval / new Function / child_process are banned in product code (ADR-0014):
$(printf '%s' "$danger" | head -3)" \
    "remove it; if a child process is genuinely required, STOP and escalate to the Lead for an ADR"
fi

# --- 3. cross-family QA ----------------------------------------------------
IFS=$'\t' read -r author vmodel < <(resolve_roles "$spec")   # shared resolver — inherit profile roles like dispatch (BUG-30)
[[ "$(family_of "$author")" != "$(family_of "$vmodel")" ]] || die "P8 violation in spec: verifier shares author family."
assert_in_catalog "$author" "model (spec)"; assert_in_catalog "$vmodel" "verifier_model (spec)"
mkdir -p reviews/verdicts reviews/queue
verdict="reviews/verdicts/${id}.txt"
run_verifier() {  # writes RISK/VERDICT to $verdict using the code-review prompt
  # reuse a prior verdict only if it actually parses (RISK + VERDICT present) — a partial file from a
  # crashed run must not be taken as a real review (registry BUG-09).
  if [[ -s "$verdict" ]] && grep -qiE '^[[:space:]>*_#]*RISK:' "$verdict" && grep -qiE '^[[:space:]>*_#]*VERDICT:' "$verdict"; then
    warn "using existing verdict $verdict"; return 0
  fi
  rm -f "$verdict"
  if [[ "${DRY_RUN:-0}" == "1" ]]; then printf 'RISK: low\nVERDICT: pass\nBLOCKING: []\n' > "$verdict"; return 0; fi
  command -v opencode >/dev/null 2>&1 || die "opencode CLI not found (or run --dry-run)"
  # Pass large content as ATTACHED FILES (-f), never as one argv string — root fix for the single-arg
  # limit (registry BUG-03). Lockfiles stay excluded from the review diff (the verifier reviews source +
  # package.json, not the mechanical lockfile).
  local d; d="$(mktemp)"
  reviewable_diff main "$branch" > "$d"   # generated/vendored excluded (shared GENERATED_PATHSPEC, BUG-23)
  # ADR-0019: confine any DB write during the verifier run to this task's component + identity (the verifier
  # is read-only by prompt — defense-in-depth). Component tasks only; an OS task runs unconfined.
  local idenv=()
  [[ -n "${comp:-}" ]] && idenv=("AI_OS_ACTOR=agent:$vmodel" "AI_OS_ROLE=verifier" "AI_OS_COMPONENT=${comp#components/}" "AI_OS_TASK=$id")
  # `-f` is a GREEDY [array] option — the message MUST precede the -f flags or it is swallowed as a file.
  # stdout -> verdict (parsed); stderr -> verr so a failure logs the REAL opencode error, not "non-zero exit".
  local verr; verr="$(mktemp)"
  if ! env "${idenv[@]}" opencode run --model "$vmodel" --dangerously-skip-permissions \
    "$(cat prompts/code-review.md)

The diff under review and the task spec are ATTACHED as files. Output ONLY the verdict in the OUTPUT CONTRACT shape above." \
    -f "$d" -f "$spec" > "$verdict" 2>"$verr"; then
    cat "$verr" >&2
    die "opencode verifier FAILED (task $id, model $vmodel)" "$(tail -n 6 "$verr")" \
      "check opencode auth (scripts/doctor.sh) + the model slug; no verdict was produced"
  fi
  rm -f "$d" "$verr"
}
log "QA: verifier=$vmodel (author=$author)"
run_verifier
# Enforce the verifier read-only rule MECHANICALLY (prompts/code-review.md): QA must leave the
# worktree byte-identical. reviews/* is gitignored, so writing the verdict never trips this.
# (The reviewed diff is main...branch — committed state — so the verdict itself stays valid.)
if [[ -n "$(git status --porcelain)" ]]; then
  git status --short >&2
  die "verifier MODIFIED the worktree — separation of powers violated (AGENTS.md §2). Discard: git checkout -- . && git clean -fd — then re-run gate.sh (the verdict is kept and reused)."
fi
# Verdict parsing lives in _lib (verdict_field): line-anchored, markdown-tolerant, last-match-wins,
# unit-tested (ADR-0009 / registry BUG-09). A missing field is fail-closed (high / fail).
risk="$(verdict_field "$verdict" RISK)";    risk="${risk:-high}"
vd="$(verdict_field "$verdict" VERDICT)";   vd="${vd:-fail}"
bash "$DIR/ledger-append.sh" qa "$id" "verifier=$vmodel risk=$risk verdict=$vd files=$nfiles lines=$nlines"
[[ "$vd" == "pass" ]] || die "QA VERDICT=fail — back to implementer (see $verdict)."

# --- 4. risk router --------------------------------------------------------
flags=()
printf '%s\n' "$changed" | grep -qE '^architecture/contracts/' && flags+=("touches-contract")
[[ -n "$(fm_list "$spec" depends_on_contracts)" ]] && printf '%s\n' "$changed" | grep -qE '^architecture/' && flags+=("touches-architecture")
[[ "$(fm_scalar "$spec" blast_radius)" == "high" ]] && flags+=("blast-radius-high")
(( nfiles > MAX_FILES )) && flags+=("files>$MAX_FILES")
(( nlines > MAX_LINES )) && flags+=("lines>$MAX_LINES")
printf '%s\n' "$changed" | grep -qiE "$SECURITY_REGEX" && flags+=("security-path")
dep_manifests="$(printf '%s\n' "$changed" | grep -iE '(^|/)(package\.json|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|requirements\.txt|pyproject\.toml|poetry\.lock|go\.(mod|sum)|Cargo\.(toml|lock)|Gemfile(\.lock)?)$' || true)"
if [[ -n "$dep_manifests" ]]; then
  # ADR-0026: suppress the flag when the ADR-0014 guard verified an additions-only, fully pre-approved
  # delta AND the manifest changes stay within THIS component's package.json + lockfile. Anything else
  # (other manifests, removals, version changes, lock-only churn) still routes to the Lead.
  extra_manifests="$(printf '%s\n' "$dep_manifests" | grep -vxF "$comp/package.json" | grep -vxF "$comp/package-lock.json" || true)"
  if [[ "${dep_suppress_ok:-0}" == "1" && -z "$extra_manifests" ]]; then
    log "risk router: dependency-change SUPPRESSED — additions ⊆ deps_preapproved, verified by the ADR-0014 guard (ADR-0026)"
  else
    flags+=("dependency-change")
  fi
fi
[[ "$risk" == "high" ]] && flags+=("verifier-risk-high")
# a model pin on a profile-governed spec is an audited exception (ADR-0022) — always show it to the Lead
[[ -n "$(profile_of_spec "$spec")" && -n "$(override_of_spec "$spec")" ]] && flags+=("model-override")

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
    bash "$DIR/ledger-append.sh" auto-approve "$id" "merged tag=$tag"
    log "MERGED $branch -> main (tag $tag). Rollback: scripts/rollback.sh $tag"
  else
    log "risk router: CLEAR — opening auto-merge PR (server CI + branch protection do the final gate)"
    if [[ "${DRY_RUN:-0}" == "1" ]]; then log "DRY_RUN: would archive spec, push $branch, open an auto-merge PR -> main"; exit 0; fi
    have_gh || die "PR mode needs the GitHub CLI (gh): install it + run 'gh auth login', or rerun with GATE_MERGE=local."
    # archive the spec on the branch so it merges together with the task
    mkdir -p tasks/completed && git mv "$spec" "tasks/completed/$(basename "$spec")" 2>/dev/null \
      && git commit -q -m "chore(${id}): archive completed task spec" || true
    git_push_resilient -u origin "$branch"
    pr_url="$(gh pr create --base main --head "$branch" --title "merge(${id}): $slug" \
      --body "Auto-approved by gate.sh — CI green, cross-family QA pass (verifier=$vmodel, risk=$risk), zero risk flags. Server CI + branch protection gate the merge." 2>&1)" \
      || die "gh pr create failed: $pr_url"
    gh pr merge "$branch" --auto --merge >/dev/null 2>&1 \
      && log "auto-merge armed — merges when required checks pass: $pr_url" \
      || warn "PR opened ($pr_url) — enable 'Allow auto-merge' in repo Settings, or merge it manually once checks pass."
    bash "$DIR/ledger-append.sh" auto-approve "$id" "pr=$pr_url"
  fi
  rm -f "$verdict"   # verdict consumed on approve — drop it so a later re-run can't reuse a stale review
else
  # ---- flagged: route to the right reviewer (ADR-0026 tiers) ----
  # LEAD tier = judgment flags (contract/architecture/blast/security/override/verifier-risk/deps).
  # OPERATOR tier = size-only flags (files>/lines>) on a spec the Lead already wrote — the operator
  # skims the QA verdict and approves; the Lead's scarce attention is not spent. HUMAN-REQUIRED
  # (reviews/checklist.md) is unchanged and sits above both.
  tier=OPERATOR
  for f in "${flags[@]}"; do
    case "$f" in files\>*|lines\>*) ;; *) tier=LEAD ;; esac
  done
  if [[ "$tier" == "OPERATOR" ]]; then
    review_line="OPERATOR may approve (ADR-0026): skim the QA verdict, then run scripts/approve.sh ${id} — Lead review not required."
  else
    review_line="Review with prompts/code-review.md (Lead-gate addendum); when satisfied: scripts/approve.sh ${id}."
  fi
  if [[ "$GATE_MERGE" == "local" ]] || ! have_gh; then
    q="reviews/queue/${id}.md"
    {
      echo "# ${tier} GATE REQUIRED — task $id"
      echo; echo "Branch: \`$branch\`  ·  files: $nfiles  ·  lines: $nlines  ·  verifier risk: $risk"
      echo; echo "## Risk flags (why this was routed)"; for f in "${flags[@]}"; do echo "- $f"; done
      echo; echo "## QA verdict"; echo '```'; cat "$verdict"; echo '```'
      echo; echo "## Review with"; echo "$review_line Approve ⇒ open a PR for \`$branch\`, or (GATE_MERGE=local) \`git checkout main && git merge --no-ff $branch\`."
    } > "$q"
    bash "$DIR/ledger-append.sh" opus-gate "$id" "queued tier=$tier flags=${flags[*]}"
    log "risk router: FLAGGED (${flags[*]}) — queued for the ${tier} gate: $q"
  else
    log "risk router: FLAGGED (${flags[*]}) — opening a DRAFT PR for the ${tier} gate"
    if [[ "${DRY_RUN:-0}" == "1" ]]; then log "DRY_RUN: would push $branch and open a ${tier} GATE draft PR (flags: ${flags[*]})"; exit 0; fi
    git_push_resilient -u origin "$branch"
    body="$(printf '%s GATE REQUIRED — review before merge.\n\nRisk flags: %s\nVerifier risk: %s · files: %s · lines: %s\n\n%s\n\nQA verdict:\n```\n%s\n```' "$tier" "${flags[*]}" "$risk" "$nfiles" "$nlines" "$review_line" "$(cat "$verdict")")"
    pr_url="$(gh pr create --draft --base main --head "$branch" --title "${tier} GATE (${id}): $slug" --body "$body" 2>&1)" \
      || die "gh pr create failed: $pr_url"
    bash "$DIR/ledger-append.sh" opus-gate "$id" "draft-pr=$pr_url tier=$tier flags=${flags[*]}"
    log "${tier} gate: DRAFT PR opened — $pr_url"
  fi
fi
