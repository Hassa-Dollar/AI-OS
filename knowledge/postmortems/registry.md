# Bug registry — generated from the memory DB (do not hand-edit; ADR-0016)

| ID | sev | status | found | fixed | by | symptom |
|---|---|---|---|---|---|---|
| BUG-01 | med | fixed | 2026-06-22 | 2026-06-22 | agent:opus-lead | edits over the WSL mount strip the +x bit; git tracked it |
| BUG-02 | med | fixed | 2026-06-22 | 2026-06-22 | agent:opus-lead | deps-allowlist false-positive on a YAML-quoted scoped package |
| BUG-03 | high | fixed | 2026-06-22 | 2026-06-22 | agent:opus-lead | opencode: Argument list too long on a large diff |
| BUG-04 | med | fixed | 2026-06-22 | 2026-06-22 | agent:opus-lead | land.sh leaves the handoff dirty on main → next task rebase fails |
| BUG-05 | low | fixed | 2026-06-22 | 2026-06-22 | agent:opus-lead | gate preflight blamed a dirty handoff on 'worker forgot to commit' |
| BUG-06 | high | fixed | 2026-06-22 | 2026-06-22 | agent:opus-lead | npm audit --audit-level=high blocked on dev-tooling CVEs |
| BUG-07 | med | fixed | 2026-06-22 | 2026-06-22 | agent:opus-lead | a non-component (docs/research) task dies on gate component-resolution |
| BUG-08 | med | fixed | 2026-06-22 | 2026-06-22 | agent:opus-lead | no task-id uniqueness guard → Shrink ids collided with old demos |
| BUG-09 | low | fixed | 2026-06-22 | 2026-06-22 | agent:opus-lead | gate reused any non-empty verdict, even a partial one from a crash |
| BUG-10 | low | fixed | 2026-06-22 | 2026-06-22 | agent:opus-lead | dispatch also passed the worker prompt as one argv (same root as BUG-03) |
| BUG-11 | med | open | 2026-06-22 | — | agent:opus-lead | ship.sh from main can't find the task's spec (no active spec for id) |
| BUG-12 | low | open | 2026-06-22 | — | agent:opus-lead | land.sh diagnostics print: couldnt read which check failed |
| BUG-13 | med | fixed | 2026-06-22 | 2026-06-22 | agent:opus-lead | db.sh bug add --status open returned 1; bats test 3 failed; exit 0 did not help |
| BUG-14 | low | open | 2026-06-22 | — | agent:opus-lead | after a re-push, no checks reported; land.sh waited then timed out |
| BUG-15 | low | fixed | 2026-06-22 | 2026-06-22 | agent:opus-lead | db.sh printed wal on every invocation |
| BUG-16 | med | fixed | 2026-06-22 | 2026-06-22 | agent:opus-lead | state recent-events empty and export rows blank despite data present |
| BUG-17 | med | fixed | 2026-06-22 | 2026-06-22 | agent:opus-lead | autonomous capture wrote nothing when a script sourced _lib.sh without setting DIR |
| BUG-18 | low | fixed | 2026-06-23 | 2026-06-23 | agent:opus-lead | db.sh sync exited 126; the bats sync test failed |
| BUG-19 | med | fixed | 2026-06-27 | 2026-06-27 | human:hassa | opencode run treated the prompt as a filename (File not found) |
| BUG-20 | med | fixed | 2026-06-27 | 2026-06-27 | human:hassa | a worker/tool failure logged only 'non-zero exit', not the real error |
| BUG-21 | med | fixed | 2026-06-27 | 2026-06-27 | human:hassa | bats tests polluted the real memory DB with fake errors (actor system:bats-exec-test) |
| BUG-23 | high | fixed | 2026-07-14 | 2026-07-14 | agent:opus-lead | transient HTTP 408 on git push was swallowed (>/dev/null) — branch actually landed but the pipeline reported failure; separately a 4k-line lockfile inflated risk lines>MAX into a false Opus-gate flag |
| BUG-24 | med | fixed | 2026-07-14 | 2026-07-14 | agent:opus-lead | an Opus-approved draft PR never landed: the draft path did not archive the task spec nor arm/request the merge |
| BUG-25 | low | fixed | 2026-07-14 | 2026-07-14 | agent:opus-lead | land.sh on a draft-held (risk-flagged) PR exited via die — printed [err], logged a bogus error into the memory DB, made ship.sh exit non-zero on a perfectly normal flagged outcome |
| BUG-26 | med | fixed | 2026-07-14 | 2026-07-14 | agent:opus-lead | dispatch secret-scan flagged env-var REFERENCES (process.env.X, dollar-brace names, <PLACEHOLDER>) in a task spec as credentials and refused to dispatch |
| BUG-27 | med | fixed | 2026-07-14 | 2026-07-14 | agent:opus-lead | a model-omitting component spec failed to dispatch once the repo had 2+ components (multiple components — cannot pick a default) |
| BUG-28 | med | fixed | 2026-07-14 | 2026-07-14 | agent:opus-lead | doctor.sh hung forever on the opencode connectivity probe even with opencode installed and authed |
| BUG-29 | med | fixed | 2026-07-14 | 2026-07-14 | ci:github-clean-room | product-ci/build (api) failed on GitHub while local CI + both model verifiers passed: TypeError Cannot open database because the directory does not exist |
| BUG-30 | med | fixed | 2026-07-14 | 2026-07-14 | agent:opus-lead | gate.sh died with a P8 false-positive (verifier shares author family) on any model-omitting spec, right after dispatch had accepted it |

## Details

### BUG-01 — fixed (med) · agent:opus-lead
- symptom: edits over the WSL mount strip the +x bit; git tracked it
- root cause: 9p mount rewrites files at 644; core.fileMode=true recorded the flip
- fix: core.fileMode=false in bootstrap + restore; os-ci exec-bit guard
- guard: 

### BUG-02 — fixed (med) · agent:opus-lead
- symptom: deps-allowlist false-positive on a YAML-quoted scoped package
- root cause: fm_list did not strip surrounding YAML quotes
- fix: fm_list strips quotes at the root; lib.bats test
- guard: 

### BUG-03 — fixed (high) · agent:opus-lead
- symptom: opencode: Argument list too long on a large diff
- root cause: whole prompt (incl. diff) passed as one argv > MAX_ARG_STRLEN
- fix: pass diff+spec via -f file attachments; exclude lockfiles from review diff
- guard: 

### BUG-04 — fixed (med) · agent:opus-lead
- symptom: land.sh leaves the handoff dirty on main → next task rebase fails
- root cause: post-merge handoff cannot be committed to protected main; rides next PR
- fix: gate.sh restores the pending handoff at the start
- guard: 

### BUG-05 — fixed (low) · agent:opus-lead
- symptom: gate preflight blamed a dirty handoff on 'worker forgot to commit'
- root cause: preflight did not exclude the auto-generated handoff
- fix: handoff restored before the dirty check
- guard: 

### BUG-06 — fixed (high) · agent:opus-lead
- symptom: npm audit --audit-level=high blocked on dev-tooling CVEs
- root cause: audited all deps incl. dev tooling, not just runtime
- fix: npm audit --omit=dev (runtime deps only)
- guard: 

### BUG-07 — fixed (med) · agent:opus-lead
- symptom: a non-component (docs/research) task dies on gate component-resolution
- root cause: gate assumed every task targets exactly one component
- fix: lighter gate when files_allowed has no component; lib.bats component_of_spec
- guard: 

### BUG-08 — fixed (med) · agent:opus-lead
- symptom: no task-id uniqueness guard → Shrink ids collided with old demos
- root cause: new-task never checked active+completed for the id
- fix: new-task rejects a duplicate id; dispatch.bats test
- guard: 

### BUG-09 — fixed (low) · agent:opus-lead
- symptom: gate reused any non-empty verdict, even a partial one from a crash
- root cause: reuse keyed on file non-empty, not parseability
- fix: verdict_field + reuse only if RISK+VERDICT parse; lib.bats test
- guard: 

### BUG-10 — fixed (low) · agent:opus-lead
- symptom: dispatch also passed the worker prompt as one argv (same root as BUG-03)
- root cause: argv prompt-passing
- fix: attach the spec via -f
- guard: 

### BUG-11 — open (med) · agent:opus-lead
- symptom: ship.sh from main can't find the task's spec (no active spec for id)
- root cause: gate resolves the spec from the current worktree before checking out the task branch
- fix: (planned) resolve the spec from the task branch it is about to gate
- guard: 

### BUG-12 — open (low) · agent:opus-lead
- symptom: land.sh diagnostics print: couldnt read which check failed
- root cause: report_failed_checks keys on bucket==fail but gh statusCheckRollup uses conclusion=FAILURE
- fix: (planned) match ghs actual conclusion field; add a parser fixture test
- guard: 

### BUG-13 — fixed (med) · agent:opus-lead
- symptom: db.sh bug add --status open returned 1; bats test 3 failed; exit 0 did not help
- root cause: terminal [[ st==fixed ]] && q returns 1 when false; the if is the branch last cmd so set -e exits before exit 0 (BashFAQ105)
- fix: if/then/fi returns 0 on false; first attempt (exit 0 alone) was insufficient; exit 0 kept as belt-and-suspenders
- guard: db.bats: bug add --status open + update --status fixed must both exit 0

### BUG-14 — open (low) · agent:opus-lead
- symptom: after a re-push, no checks reported; land.sh waited then timed out
- root cause: GitHub sometimes does not spawn a run on a synchronize push; land.sh cannot tell no-run from pending, no recovery
- fix: (planned) detect zero runs for head SHA after grace then auto-retrigger; manual workaround now is gh pr close/reopen
- guard: 

### BUG-15 — fixed (low) · agent:opus-lead
- symptom: db.sh printed wal on every invocation
- root cause: PRAGMA journal_mode=WAL returns a row; schema applied on every call echoed it to stdout
- fix: redirect schema-apply stdout to /dev/null
- guard: none (cosmetic; stderr still surfaces real schema errors)

### BUG-16 — fixed (med) · agent:opus-lead
- symptom: state recent-events empty and export rows blank despite data present
- root cause: date +%s%3N emits 9-digit ns here (%3N ignored); now_ms stored ns so datetime(ts/1000) was out of range → NULL, and NULL || x = NULL blanked the row
- fix: now_ms builds ms from %s and %N (s*1000 + ns/1e6) with a numeric guard; coalesce(date,?) NULL-safety
- guard: db.bats: state + export rows render with a real year

### BUG-17 — fixed (med) · agent:opus-lead
- symptom: autonomous capture wrote nothing when a script sourced _lib.sh without setting DIR
- root cause: _capture used the callers $DIR to find db.sh; callers that never set DIR skipped capture
- fix: _lib.sh computes _AI_OS_LIB_DIR from BASH_SOURCE; _capture uses it
- guard: db.bats: capture works when the caller never set DIR

### BUG-18 — fixed (low) · agent:opus-lead
- symptom: db.sh sync exited 126; the bats sync test failed
- root cause: sync/ledger self-invoked "$DIR/db.sh" via direct exec; mount-stripped exec bit → permission denied (BUG-01 class)
- fix: invoke via bash "$DIR/db.sh" like _capture/ledger-append; +status assertion on export-detail test
- guard: db.bats: sync writes a file (exit 0)

### BUG-19 — fixed (med) · human:hassa
- symptom: opencode run treated the prompt as a filename (File not found)
- root cause: opencode -f is a greedy [array]; the trailing message was swallowed into the file list
- fix: message before the -f flags in dispatch.sh + gate.sh; add --dangerously-skip-permissions
- guard: 

### BUG-20 — fixed (med) · human:hassa
- symptom: a worker/tool failure logged only 'non-zero exit', not the real error
- root cause: the EXIT trap knew only the exit code; the failed command's output was never captured
- fix: dispatch.sh+gate.sh capture opencode output and die with its tail; ERR trap records the failing command (_lib.sh)
- guard: 

### BUG-21 — fixed (med) · human:hassa
- symptom: bats tests polluted the real memory DB with fake errors (actor system:bats-exec-test)
- root cause: lib.bats/dispatch.bats trigger die() without a temp AI_OS_DB, so _capture wrote the real DB
- fix: _capture skips the real DB under bats unless AI_OS_DB is set
- guard: 

### BUG-23 — fixed (high) · agent:opus-lead
- symptom: transient HTTP 408 on git push was swallowed (>/dev/null) — branch actually landed but the pipeline reported failure; separately a 4k-line lockfile inflated risk lines>MAX into a false Opus-gate flag
- root cause: push stderr suppressed, so a retryable transport error was indistinguishable from a real failure; risk metrics and review diff counted generated/vendored files
- fix: git_push_resilient (retry transient errors, die with verbatim stderr) + shared GENERATED_PATHSPEC excludes lockfiles/dist/coverage from reviewable_diff and risk_nfiles/risk_nlines
- guard: never >/dev/null a git push; review + risk metrics operate on authored changes only

### BUG-24 — fixed (med) · agent:opus-lead
- symptom: an Opus-approved draft PR never landed: the draft path did not archive the task spec nor arm/request the merge
- root cause: gate.sh only armed auto-merge on the auto-approve path; approve.sh marked ready but nothing requested the merge
- fix: approve.sh archives the spec on the branch + pushes + hands to land.sh; land.sh is the single chokepoint that REQUESTS the merge once checks are green
- guard: both approval paths converge on land.sh; ship.sh exercises the full traversal

### BUG-25 — fixed (low) · agent:opus-lead
- symptom: land.sh on a draft-held (risk-flagged) PR exited via die — printed [err], logged a bogus error into the memory DB, made ship.sh exit non-zero on a perfectly normal flagged outcome
- root cause: the draft hold is an expected router outcome, not a failure, but the code path treated every non-merge as fatal
- fix: clean capture-free stop: log the hold + the approve.sh next step, exit 0
- guard: expected pipeline outcomes must never write error events (keeps the memory DB signal clean)

### BUG-26 — fixed (med) · agent:opus-lead
- symptom: dispatch secret-scan flagged env-var REFERENCES (process.env.X, dollar-brace names, <PLACEHOLDER>) in a task spec as credentials and refused to dispatch
- root cause: the generic secret-pattern regex matched the very pattern ADR-0014 tells specs to use instead of secrets
- fix: filter reference shapes out of the candidate lines before applying the credential patterns
- guard: dispatch.bats pins an env-var-reference spec as NOT flagged; real key shapes still die

### BUG-27 — fixed (med) · agent:opus-lead
- symptom: a model-omitting component spec failed to dispatch once the repo had 2+ components (multiple components — cannot pick a default)
- root cause: role inheritance resolved the profile via component_dir (sole-component assumption) instead of the spec files_allowed
- fix: infer the component via component_of_spec inside the shared resolver
- guard: dispatch.bats two-component inheritance test; superseded by roles v2 single-source resolution (ADR-0022)

### BUG-28 — fixed (med) · agent:opus-lead
- symptom: doctor.sh hung forever on the opencode connectivity probe even with opencode installed and authed
- root cause: the probe invocation could await interactive input/permission with no timeout
- fix: time-bounded, non-interactive probe
- guard: doctor.bats asserts the probe is time-bounded

### BUG-29 — fixed (med) · ci:github-clean-room
- symptom: product-ci/build (api) failed on GitHub while local CI + both model verifiers passed: TypeError Cannot open database because the directory does not exist
- root cause: auth.test.ts hardcoded DB_PATH under /tmp/opencode/ — better-sqlite3 creates the file but not the parent dir; /tmp/opencode exists on every OpenCode-blessed host (dev box, dispatch sandbox, verifier) but not on a pristine runner, so the shared-env assumption was invisible to every correlated check
- fix: mkdtempSync(join(tmpdir(), prefix)) per run + rmSync cleanup (commit 08ee8cf); also isolates parallel runs
- guard: lesson banked (wisdom.db, scope os): clean-room CI is the decorrelated gate; product tests must never assume a pre-existing temp dir

### BUG-30 — fixed (med) · agent:opus-lead
- symptom: gate.sh died with a P8 false-positive (verifier shares author family) on any model-omitting spec, right after dispatch had accepted it
- root cause: BUG-27 fixed inheritance in dispatch only; gate re-read raw spec fields and saw empty roles
- fix: single shared resolve_roles in _lib.sh consumed by BOTH dispatch and gate
- guard: coherence + lib.bats pin the shared resolver; roles v2 (ADR-0022) made the profile the only source
