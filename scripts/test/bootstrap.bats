#!/usr/bin/env bats
# Guard for ADR-0020 / analysis Fix 7: bootstrap.sh provisions a machine and must NOT re-embed copies of
# canonical repo files (a clone already has them; copies diverge). Static checks — no run needed.
# Run: scripts/test.sh

setup() { BOOTSTRAP="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)/bootstrap.sh"; }

@test "bootstrap.sh embeds no content heredocs (no wf writer / SEED blocks)" {
  [ -f "$BOOTSTRAP" ]
  ! grep -qE "<<'SEED'|^[[:space:]]*wf " "$BOOTSTRAP"
}

@test "bootstrap.sh embeds no copy of canonical OS files (os-ci / role models / off-catalog example)" {
  ! grep -qiE 'name: os-ci|gitleaks-action|\b(glm|kimi|qwen|deepseek|mimo|minimax)\b|opencode/glm' "$BOOTSTRAP"
}
