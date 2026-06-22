#!/usr/bin/env bats
# Tests for the memory DB (scripts/db.sh) + autonomous capture (ADR-0016). Each test uses a throwaway DB
# via AI_OS_DB (bats auto-cleans BATS_TEST_TMPDIR). Requires sqlite3 (installed in the os-ci bats step).

setup() {
  REPO="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
  export AI_OS_DB="$BATS_TEST_TMPDIR/memory.db"
}

@test "remember → recall finds the event" {
  bash "$REPO/scripts/db.sh" remember observation "the widget exploded on boundary input" --task 042 >/dev/null
  run bash "$REPO/scripts/db.sh" recall "widget exploded"
  [ "$status" -eq 0 ]
  [[ "$output" == *"widget exploded"* ]]
}

@test "learn → recall finds the knowledge" {
  bash "$REPO/scripts/db.sh" learn pattern "retry with backoff" "wrap flaky calls in exponential backoff" --tags retry >/dev/null
  run bash "$REPO/scripts/db.sh" recall "backoff"
  [[ "$output" == *"retry with backoff"* ]]
}

@test "bug add/update shows in state and export" {
  bash "$REPO/scripts/db.sh" bug add BUG-999 --severity high --status open --symptom "thing breaks on input" >/dev/null
  run bash "$REPO/scripts/db.sh" state
  [[ "$output" == *"BUG-999"* ]]
  bash "$REPO/scripts/db.sh" bug update BUG-999 --status fixed --fixed-pr 99 >/dev/null
  run bash "$REPO/scripts/db.sh" export registry
  [[ "$output" == *"BUG-999"* ]]
  [[ "$output" == *"fixed"* ]]
}

@test "write path refuses a secret (ADR-0014)" {
  fake="sk_test_$(printf 'a%.0s' $(seq 1 24))"
  run bash "$REPO/scripts/db.sh" remember observation "leak $fake"
  [ "$status" -ne 0 ]
  [[ "$output" == *"secret"* ]]
}

@test "recall --scope returns the component + os, not other components" {
  bash "$REPO/scripts/db.sh" remember observation "api thing alpha" --component api >/dev/null
  bash "$REPO/scripts/db.sh" remember observation "web thing alpha" --component web >/dev/null
  run bash "$REPO/scripts/db.sh" recall "alpha" --scope component:api
  [[ "$output" == *"api thing"* ]]
  [[ "$output" != *"web thing"* ]]
}

@test "autonomous capture: a script's die() writes an episodic error (no AI in the loop)" {
  cat > "$BATS_TEST_TMPDIR/boom.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
DIR="$REPO/scripts"; source "\$DIR/_lib.sh"
cd "$REPO"
die "boom for the capture test" "a cause" "a remedy"
EOF
  run bash "$BATS_TEST_TMPDIR/boom.sh"
  [ "$status" -ne 0 ]
  run bash "$REPO/scripts/db.sh" recall "boom for the capture test" --kind error
  [[ "$output" == *"boom for the capture test"* ]]
}

@test "now_ms is epoch ms so datetime() renders, not NULL (BUG-16)" {
  bash "$REPO/scripts/db.sh" remember observation "ts render check" >/dev/null
  run bash "$REPO/scripts/db.sh" state
  [[ "$output" == *"ts render check"* ]]          # blank row if datetime() were NULL (the ns-timestamp bug)
  [[ "$output" == *"$(date -u +%Y)-"* ]]          # and the row carries a real date
}

@test "export registry renders dated rows (BUG-16: ms timestamps + NULL-safe date)" {
  bash "$REPO/scripts/db.sh" bug add BUG-TS --severity low --status open --symptom "ts export check" >/dev/null
  run bash "$REPO/scripts/db.sh" export registry
  [[ "$output" == *"BUG-TS"* ]]
  [[ "$output" == *"$(date -u +%Y)-"* ]]          # a real found-date (was blank under the ns-timestamp bug)
}

@test "autonomous capture works when the caller never set DIR (BUG-17)" {
  cat > "$BATS_TEST_TMPDIR/nodir.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
source "$REPO/scripts/_lib.sh"
cd "$REPO"
die "nodir capture test" "a cause" "a remedy"
EOF
  run bash "$BATS_TEST_TMPDIR/nodir.sh"
  [ "$status" -ne 0 ]
  run bash "$REPO/scripts/db.sh" recall "nodir capture test" --kind error
  [[ "$output" == *"nodir capture test"* ]]
}

@test "bug provenance: found_by defaults from AI_OS_ACTOR and shows in export (ADR-0017)" {
  AI_OS_ACTOR=agent:test-model bash "$REPO/scripts/db.sh" bug add BUG-PV --status open --symptom "prov check" >/dev/null
  run bash "$REPO/scripts/db.sh" export registry
  [[ "$output" == *"BUG-PV"* ]]
  [[ "$output" == *"agent:test-model"* ]]
}

@test "bug provenance: --found-by overrides the actor default (ADR-0017)" {
  bash "$REPO/scripts/db.sh" bug add BUG-PV2 --status open --found-by system:somescript --symptom x >/dev/null
  run bash "$REPO/scripts/db.sh" export registry
  [[ "$output" == *"system:somescript"* ]]
}

@test "migration adds found_by to a pre-existing (v1) bug table (ADR-0017)" {
  # simulate a DB created before ADR-0017: the v1 bug table, no found_by column
  sqlite3 "$AI_OS_DB" "CREATE TABLE bug(id TEXT PRIMARY KEY, found_ts INTEGER NOT NULL, fixed_ts INTEGER, severity TEXT, status TEXT NOT NULL, scope TEXT NOT NULL DEFAULT 'os', symptom TEXT, root_cause TEXT, fix TEXT, guard TEXT, fixed_pr TEXT);"
  run bash "$REPO/scripts/db.sh" bug add BUG-MIG --status open --found-by human:tester --symptom "migrate me"
  [ "$status" -eq 0 ]
  run bash "$REPO/scripts/db.sh" export registry
  [[ "$output" == *"BUG-MIG"* ]]
  [[ "$output" == *"human:tester"* ]]
}
