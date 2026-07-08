#!/usr/bin/env bats
# Tests for scripts/doctor.sh (#82b / ADR-0020). Source the script — doctor_main is guarded so it won't run —
# and unit-test the check logic deterministically: no apt/npm, no network. Run: scripts/test.sh

setup() {
  # shellcheck disable=SC1091
  source "${BATS_TEST_DIRNAME}/../doctor.sh"
  DO_INSTALL=0; DO_PROBE=0                          # never apt/npm or hit the network in tests
  export AI_OS_DB="$BATS_TEST_TMPDIR/memory.db"     # the e2e die()->capture writes here, not the real DB
}

@test "doctor check_tool: a present tool is ✓ and returns 0" {
  ok=0
  check_tool bash critical "n/a" >/dev/null
  [ "$ok" -eq 1 ]
}

@test "doctor check_tool: a missing tool is ✗, non-zero, and prints its remediation" {
  run check_tool __ai_os_no_such_cmd__ critical "install the thing"
  [ "$status" -ne 0 ]
  [[ "$output" == *"install the thing"* ]]
}

@test "doctor: missing critical vs quality routes to the right counter" {
  crit_miss=0; qual_miss=0
  check_tool __ai_os_no_such_cmd__ critical "x" 2>/dev/null || true
  check_tool __ai_os_no_such_cmd__ quality  "x" 2>/dev/null || true
  [ "$crit_miss" -eq 1 ]
  [ "$qual_miss" -eq 1 ]
}

@test "doctor runs end-to-end (--no-install --no-probe) and prints a summary" {
  run bash "${BATS_TEST_DIRNAME}/../doctor.sh" --no-install --no-probe
  [[ "$output" == *"doctor:"* ]]
}

@test "doctor: the opencode probe is time-bounded — never hangs (BUG-28)" {
  local fakebin="$BATS_TEST_TMPDIR/bin"; mkdir -p "$fakebin"
  printf '#!/usr/bin/env bash\nsleep 30\n' > "$fakebin/opencode"   # a run that would block
  chmod +x "$fakebin/opencode"
  # 1s probe budget + the fake opencode first on PATH: doctor MUST return promptly and flag the timeout,
  # not hang for 30s. (If the timeout wrapper were missing, `run` would block on the sleep.)
  run env AI_OS_PROBE_TIMEOUT=1 PATH="$fakebin:$PATH" bash "${BATS_TEST_DIRNAME}/../doctor.sh" --no-install
  [[ "$output" == *"timed out"* ]]
}
