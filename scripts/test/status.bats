#!/usr/bin/env bats
# status.bats — black-box test for `scripts/os status` (OS-V1).
# Drives the real executable against a throwaway fixture repo (one queued + one
# finished task), checks the table + --json output, and verifies status is
# READ-ONLY (byte-identical worktree, HEAD, and tree — no git/gh mutation).

load helpers

# a finished-task fixture: a spec in tasks/active/ + a land ledger row + a worker
# log with an exit-0 run footer (so derive_state => `done`).
make_finished_task() {
  cat > tasks/active/998-done.md <<'EOF'
---
id: "998"
slug: done
model: opencode-go/glm-5.2
verifier_model: opencode-go/deepseek-v4-pro
branch: task/998-done
files_allowed:
  - components/api/src/x.ts
deps_preapproved: []
---
# Goal
x
EOF
  mkdir -p reports/metrics
  printf 'ts,event,task_id,branch,actor,note\n' > reports/metrics/ledger.csv
  printf '2026-07-15T10:00:00Z,dispatch,998,task/998-done,robot,model=opencode-go/glm-5.2\n' >> reports/metrics/ledger.csv
  printf '2026-07-15T10:30:00Z,land,998,main,robot,branch=task/998-done main=deadbeef\n' >> reports/metrics/ledger.csv
  mkdir -p logs
  {
    printf '=== 2026-07-15T10:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\n'
    printf 'worker did the work\n'
    printf '=== exit 0 2026-07-15T10:20:00Z ===\n'
  } > logs/998.log
}

@test "status: one queued + one finished task; table + JSON; always exit 0" {
  make_repo
  write_spec 999 opencode-go/glm-5.2 opencode-go/deepseek-v4-pro   # queued (no ledger event)
  make_finished_task                                            # -> done
  run bash -c 'python3 scripts/os status 2>&1'
  [ "$status" -eq 0 ]
  [[ "$output" == *"998"* && "$output" == *"999"* ]]
  [[ "$output" == *done* ]]
  [[ "$output" == *queued* ]]
  # the agent column resolves the spec's model slug (opencode-go/ stripped) + role
  [[ "$output" == *"glm-5.2/implementer"* ]]
  run bash -c 'python3 scripts/os status --json 2>&1'
  [ "$status" -eq 0 ]
  # JSON parses and carries the same two rows + derived states
  python3 - "$output" <<'PY'
import json, sys
payload = sys.argv[1]
rows = json.loads(payload)
by_id = {r["id"]: r for r in rows}
assert set(by_id) == {"998", "999"}, set(by_id)
assert by_id["998"]["state"] == "done", by_id["998"]
assert by_id["999"]["state"] == "queued", by_id["999"]
assert by_id["998"]["agent"] == "glm-5.2/implementer", by_id["998"]
assert by_id["998"]["log"] == "logs/998.log", by_id["998"]
assert by_id["998"]["last_line"].startswith("worker did the work") or \
       by_id["998"]["last_line"] == "worker did the work", by_id["998"]
print("json ok")
PY
}

@test "status is READ-ONLY: byte-identical worktree + tree (no git/gh mutation)" {
  make_repo
  write_spec 999 opencode-go/glm-5.2 opencode-go/deepseek-v4-pro
  make_finished_task
  printf 'logs/\n' > .gitignore        # mirror the real repo: logs/ is gitignored (OS-V1)
  git add -A; git commit -qm fixtures
  before_p="$(git status --porcelain)"
  before_head="$(git rev-parse HEAD)"
  before_tree="$(git ls-files -s | sha256sum | cut -d' ' -f1)"
  before_blob="$(git rev-parse 'HEAD:tasks/active/998-done.md')"
  run bash -c 'python3 scripts/os status >/dev/null 2>&1; python3 scripts/os status --json >/dev/null 2>&1'
  [ "$status" -eq 0 ]
  [ "$(git status --porcelain)" = "$before_p" ]
  [ "$(git rev-parse HEAD)" = "$before_head" ]
  [ "$(git ls-files -s | sha256sum | cut -d' ' -f1)" = "$before_tree" ]
  # a tracked subject blob is unchanged
  [ "$(git rev-parse 'HEAD:tasks/active/998-done.md')" = "$before_blob" ]
  # logs/ stays gitignored (status never tracks or removes it)
  git check-ignore logs/998.log
}

@test "status: python unittest suite passes against the copied CLI (AC#3 coverage)" {
  make_repo
  mkdir -p scripts/test
  cp "$REPO_UT/scripts/test/test_status.py" "$FIX/scripts/test/test_status.py"
  run python3 scripts/test/test_status.py
  [ "$status" -eq 0 ]
  [[ "$output" == *"OK"* ]]
}

@test "status: --json parses to a list of row objects even with no tasks" {
  make_repo   # no specs, no branches, no ledger
  run bash -c 'python3 scripts/os status --json'
  [ "$status" -eq 0 ]
  python3 - "$output" <<'PY'
import json, sys
rows = json.loads(sys.argv[1])
assert isinstance(rows, list) and rows == [], rows
print("empty ok")
PY
}

@test "status: a worker exit footer with non-zero code derives failed" {
  make_repo
  write_spec 997 opencode-go/glm-5.2 opencode-go/deepseek-v4-pro
  mkdir -p reports/metrics
  printf 'ts,event,task_id,branch,actor,note\n' > reports/metrics/ledger.csv
  printf '2026-07-15T11:00:00Z,dispatch,997,task/997-x,robot,model=opencode-go/glm-5.2\n' >> reports/metrics/ledger.csv
  mkdir -p logs
  {
    printf '=== 2026-07-15T11:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\n'
    printf 'boom\n'
    printf '=== exit 137 2026-07-15T11:05:00Z ===\n'
  } > logs/997.log
  run bash -c 'python3 scripts/os status --json'
  [ "$status" -eq 0 ]
  python3 - "$output" <<'PY'
import json, sys
rows = json.loads(sys.argv[1])
assert any(r["id"] == "997" and r["state"] == "failed" for r in rows), rows
print("failed ok")
PY
}

@test "status: width fits COLUMNS=80 + --wide full + ANSI stripped from LAST_LINE" {
  make_repo
  write_spec 996 opencode-go/glm-5.2 opencode-go/deepseek-v4-pro
  mkdir -p reports/metrics logs
  printf 'ts,event,task_id,branch,actor,note\n' > reports/metrics/ledger.csv
  printf '2026-07-15T11:00:00Z,dispatch,996,task/996-x,robot,model=opencode-go/glm-5.2\n' >> reports/metrics/ledger.csv
  {
    printf '=== 2026-07-15T11:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\n'
    # a bare [0m ANSI leak (the artifact the operator reported) inside LAST_LINE
    printf 'compiling things done\x1b[0m and a very long trailing tail that overflows narrow terminals xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n'
    printf '=== exit 0 2026-07-15T11:10:00Z ===\n'
  } > logs/996.log
  # default (COLUMNS=80): every output line fits 80, ANSI is stripped (no escape
  # bytes), and the [0m leak is gone; the long LAST_LINE is priority-truncated.
  run bash -c 'COLUMNS=80 python3 scripts/os status'
  [ "$status" -eq 0 ]
  [[ "$output" != *$'\x1b'* ]]                                   # no ANSI escape bytes leak
  [[ "$output" == *"compiling"* ]]                               # the stripped prefix survives
  max=0; while IFS= read -r ln; do [ "${#ln}" -gt "$max" ] && max="${#ln}"; done <<<"$output"
  [ "$max" -le 80 ]
  # --wide keeps the full long line (no truncation), still ANSI-stripped
  run bash -c 'COLUMNS=80 python3 scripts/os status --wide'
  [ "$status" -eq 0 ]
  [[ "$output" == *"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"* ]]
  [[ "$output" == *"compiling things done and a very long trailing tail"* ]]
  [[ "$output" != *$'\x1b'* ]]
}

@test "status: --watch parses and emits one refresh cycle" {
  make_repo
  write_spec 995 opencode-go/glm-5.2 opencode-go/deepseek-v4-pro
  run bash -c 'COLUMNS=120 timeout 2 python3 scripts/os status --watch --watch-interval 1 2>&1'
  [ "$status" -eq 124 ]   # timeout(1) signals 124 on expiry -> the watch loop ran
  [[ "$output" == *"995"* ]]
}

@test "status: re-dispatched task (two run pairs) shows running then waiting-gate" {
  make_repo
  write_spec 994 opencode-go/glm-5.2 opencode-go/deepseek-v4-pro
  mkdir -p reports/metrics logs
  printf 'ts,event,task_id,branch,actor,note\n' > reports/metrics/ledger.csv
  printf '2026-07-15T10:00:00Z,dispatch,994,task/994-x,robot,model=opencode-go/glm-5.2\n' >> reports/metrics/ledger.csv
  printf '2026-07-15T11:00:00Z,dispatch,994,task/994-x,robot,model=opencode-go/glm-5.2\n' >> reports/metrics/ledger.csv
  {
    printf '=== 2026-07-15T10:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\n'
    printf 'first attempt\n'
    printf '=== exit 0 2026-07-15T10:10:00Z ===\n'
    printf '=== 2026-07-15T11:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\n'
    printf 'fix round in flight\n'
  } > logs/994.log
  run bash -c 'python3 scripts/os status --json'
  [ "$status" -eq 0 ]
  python3 - "$output" <<'PY'
import json, sys
rows = json.loads(sys.argv[1])
r = next(x for x in rows if x["id"] == "994")
assert r["state"] == "running", r
print("multi-run running ok")
PY
  # now finish the second run -> waiting-gate
  printf '=== exit 0 2026-07-15T11:10:00Z ===\n' >> logs/994.log
  run bash -c 'python3 scripts/os status --json'
  python3 - "$output" <<'PY'
import json, sys
rows = json.loads(sys.argv[1])
r = next(x for x in rows if x["id"] == "994")
assert r["state"] == "waiting-gate", r
print("multi-run waiting-gate ok")
PY
}

@test "status: agent column shows model/role from the LAST run header (verifier for gate.sh)" {
  make_repo
  write_spec 993 opencode-go/glm-5.2 opencode-go/deepseek-v4-pro
  mkdir -p reports/metrics logs
  printf 'ts,event,task_id,branch,actor,note\n' > reports/metrics/ledger.csv
  printf '2026-07-15T10:00:00Z,dispatch,993,task/993-x,robot,model=opencode-go/glm-5.2\n' >> reports/metrics/ledger.csv
  {
    printf '=== 2026-07-15T10:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\n'
    printf 'worker ok\n'
    printf '=== exit 0 2026-07-15T10:10:00Z ===\n'
    printf '=== 2026-07-15T10:11:00Z gate.sh model=opencode-go/deepseek-v4-pro ===\n'
  } > logs/993.log
  run bash -c 'python3 scripts/os status --json'
  [ "$status" -eq 0 ]
  python3 - "$output" <<'PY'
import json, sys
rows = json.loads(sys.argv[1])
r = next(x for x in rows if x["id"] == "993")
assert r["agent"] == "deepseek-v4-pro/verifier", r
assert r["state"] == "verifying", r
print("agent-from-header ok")
PY
}

@test "os verdict <id>: reads reviews/verdicts + ledger tier/flags, post-land fall back to log QA" {
  make_repo
  write_spec 992 opencode-go/glm-5.2 opencode-go/deepseek-v4-pro
  mkdir -p reports/metrics reviews/verdicts logs
  printf 'ts,event,task_id,branch,actor,note\n' > reports/metrics/ledger.csv
  printf '2026-07-15T10:00:00Z,dispatch,992,task/992-x,robot,model=x\n' >> reports/metrics/ledger.csv
  printf '2026-07-15T10:30:00Z,qa,992,task/992-x,robot,verifier=opencode-go/deepseek-v4-pro risk=low verdict=pass\n' >> reports/metrics/ledger.csv
  printf '2026-07-15T10:31:00Z,opus-gate,992,task/992-x,robot,"draft-pr=https://github.com/o/r/pull/1 tier=LEAD flags=touches-contract security-path"\n' >> reports/metrics/ledger.csv
  printf 'VERDICT: pass\nRISK: low\nNOTES: cross-family QA clean\n' > reviews/verdicts/992.txt
  run bash -c 'python3 scripts/os verdict 992'
  [ "$status" -eq 0 ]
  [[ "$output" == *"VERDICT: pass"* ]]
  [[ "$output" == *"risk=low"* ]]
  [[ "$output" == *"tier=LEAD"* ]]
  [[ "$output" == *"flags=touches-contract security-path"* ]]
  [[ "$output" == *"pull/1"* ]]
  # post-land: remove the verdict file -> fall back to the log's gate.sh QA block
  rm reviews/verdicts/992.txt
  {
    printf '=== 2026-07-15T10:11:00Z gate.sh model=opencode-go/deepseek-v4-pro ===\n'
    printf 'VERDICT: pass\nRISK: low\nNOTES: from log\n'
    printf '=== exit 0 2026-07-15T10:29:00Z ===\n'
  } >> logs/992.log
  printf '2026-07-15T10:40:00Z,land,992,main,robot,branch=task/992-x main=deadbeef\n' >> reports/metrics/ledger.csv
  run bash -c 'python3 scripts/os verdict 992'
  [ "$status" -eq 0 ]
  [[ "$output" == *"NOTES: from log"* ]]
  [[ "$output" == *"landed"* ]]
  # neither verdict nor qa -> exit 0 with a clear message
  rm -f reviews/verdicts/991.txt
  run bash -c 'python3 scripts/os verdict 991'
  [ "$status" -eq 0 ]
  [[ "$output" == *"No verdict recorded"* ]]
}

@test "os stop <id> kills the pidfile'd worker, appends stopped footer, status shows stopped; resume prints the command" {
  make_repo
  write_spec 991 opencode-go/glm-5.2 opencode-go/deepseek-v4-pro
  mkdir -p reports/metrics logs
  printf 'ts,event,task_id,branch,actor,note\n' > reports/metrics/ledger.csv
  printf '2026-07-15T10:00:00Z,dispatch,991,task/991-x,robot,model=x\n' >> reports/metrics/ledger.csv
  printf '=== 2026-07-15T10:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\n' > logs/991.log
  # a fake live worker: argv[0] rewritten to `opencode` so `os stop`'s
  # /proc/<pid>/cmdline identity check sees an opencode process and allows the
  # SIGTERM (Lead gate OS-V1.1: stop must never SIGTERM a non-opencode PID).
  bash -c 'exec -a opencode sleep 30' & fake_pid=$!
  printf '%s\n' "$fake_pid" > logs/991.pid
  run bash -c 'python3 scripts/os stop 991'
  [ "$status" -eq 0 ]
  [[ "$output" == *"stopped task 991"* ]]
  [[ "$output" == *"generation stream cannot be paused"* ]]
  # the fake worker was actually killed
  ! kill -0 "$fake_pid" 2>/dev/null
  # the log gained a stopped terminator
  [[ "$(cat logs/991.log)" == *"=== stopped"* ]]
  # status now derives `stopped`
  run bash -c 'python3 scripts/os status --json'
  [ "$status" -eq 0 ]
  python3 - "$output" <<'PY'
import json, sys
rows = json.loads(sys.argv[1])
r = next(x for x in rows if x["id"] == "991")
assert r["state"] == "stopped", r
print("stopped ok")
PY
  # resume prints the re-dispatch command, does NOT auto-dispatch (no branch实战 in fixtures)
  run bash -c 'python3 scripts/os resume 991'
  [ "$status" -eq 0 ]
  [[ "$output" == *"scripts/dispatch.sh 991"* ]]
  [[ "$output" != *"dispatching"* ]]
}

@test "os tail --all follows two fixture logs concurrently with correct prefixes" {
  make_repo
  mkdir -p logs
  printf '=== 2026-07-15T10:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\n' > logs/AAA.log
  printf 'impl A line one\n' >> logs/AAA.log
  printf '=== 2026-07-15T10:01:00Z dispatch.sh model=opencode-go/kimi-k2.7-code ===\n' > logs/BBB.log
  printf 'impl B line one\n' >> logs/BBB.log
  # the initial snapshot pass prints both prefixed lines (deterministic; follow then
  # runs in the background under the timeout)
  run bash -c 'timeout 1.5 python3 scripts/os tail --all 2>&1'
  [ "$status" -eq 124 ]            # expired in the follow loop after the snapshot
  [[ "$output" == *"[AAA·implementer·glm-5.2] impl A line one"* ]]
  [[ "$output" == *"[BBB·implementer·kimi-k2.7-code] impl B line one"* ]]
}

@test "stop with no pidfile exits cleanly and explains" {
  make_repo
  write_spec 990 opencode-go/glm-5.2 opencode-go/deepseek-v4-pro
  run bash -c 'python3 scripts/os stop 990'
  [ "$status" -eq 1 ]
  [[ "$output" == *"no pidfile"* ]]
}

@test "stop refuses a non-opencode PID (stale/recycled pidfile): no kill, no footer, pidfile kept" {
  # a live but NON-opencode process (plain sleep) recorded in the pidfile. The
  # /proc/<pid>/cmdline identity check must refuse: exit 1, do NOT SIGTERM, do
  # NOT append a stopped footer, do NOT remove the pidfile (operator removes it).
  make_repo
  write_spec 992 opencode-go/glm-5.2 opencode-go/deepseek-v4-pro
  mkdir -p reports/metrics logs
  printf 'ts,event,task_id,branch,actor,note\n' > reports/metrics/ledger.csv
  printf '2026-07-15T10:00:00Z,dispatch,992,task/992-x,robot,model=x\n' >> reports/metrics/ledger.csv
  printf '=== 2026-07-15T10:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\n' > logs/992.log
  sleep 30 & fake_pid=$!
  _cleanup() { kill "$fake_pid" 2>/dev/null || true; wait "$fake_pid" 2>/dev/null || true; }
  trap _cleanup EXIT
  printf '%s\n' "$fake_pid" > logs/992.pid
  run bash -c 'python3 scripts/os stop 992'
  [ "$status" -eq 1 ]
  [[ "$output" == *"stale pidfile"* ]]
  [[ "$output" == *"not an opencode worker"* ]]
  # the innocent sleep is STILL ALIVE
  kill -0 "$fake_pid" 2>/dev/null
  # the pidfile is preserved (operator must remove it) and NO stopped footer
  [[ -f logs/992.pid ]]
  [[ "$(cat logs/992.log)" != *"=== stopped"* ]]
  _cleanup
  trap - EXIT
}
