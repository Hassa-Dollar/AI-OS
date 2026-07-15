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