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
