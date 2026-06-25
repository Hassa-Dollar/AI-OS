#!/usr/bin/env bats
# Coherence guard (Step 4 / ADR-0018). verify-coherence.sh must FAIL when the repo disagrees with its
# generated docs (AUTO-INVENTORY) or its component/profile graph (.ai-os.yml <-> components/ <-> profiles/),
# and PASS when consistent — without tripping on hand-written prose. Each test pins a real failure mode.
# Run: scripts/test.sh

setup() {
  # shellcheck disable=SC1091
  source "${BATS_TEST_DIRNAME}/../_lib.sh"            # gen_inventory / block_inclusive / ai_os_components
  SCRIPTS="$(cd "${BATS_TEST_DIRNAME}/.." && pwd)"
  REPO="$(mktemp -d)"; cd "$REPO" || return 1
  git init -q
  mkdir -p components/api profiles/web-app/ts-hono-api architecture
  printf 'profile: web-app/ts-hono-api\n'           > components/api/.component.yml
  printf '{}\n'                                      > profiles/web-app/ts-hono-api/profile.json
  printf 'components:\n  api: web-app/ts-hono-api\n' > .ai-os.yml          # registry agrees with the above
  # a doc whose AUTO-INVENTORY block is freshly correct for the repo above (prose around a generated block)
  { printf '# Map\n\nhand-written intro\n\n'; gen_inventory; printf '\n## hand-written tail\n'; } \
    > architecture/README.md
}
teardown() { cd /; rm -rf "$REPO"; }

# --- check 1: generated inventory --------------------------------------------------------------------
@test "gen_inventory is deterministic + un-timestamped (the whole guard depends on it)" {
  [ "$(gen_inventory)" = "$(gen_inventory)" ]
  [[ "$(gen_inventory)" != *"handoff.sh @ "* ]]   # AUTO-STATE is 'handoff.sh @ <ts>'; inventory must not be
}

@test "clean repo: verify-coherence passes" {
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -eq 0 ]
}

@test "hand-edited generated block: verify-coherence fails" {
  sed -i '/AUTO-INVENTORY:BEGIN/a - `ghost` → profile `x` · stub (illegal hand-edit)' architecture/README.md
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -ne 0 ]
}

@test "component added without regenerating: verify-coherence fails" {
  mkdir -p components/web
  printf 'profile: web-app/react-vite\n' > components/web/.component.yml
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -ne 0 ]
}

@test "hand-written prose edit (outside the block) does NOT trip the guard" {
  printf '\nmore hand-written prose — perfectly legal\n' >> architecture/README.md
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -eq 0 ]
}

@test "block_inclusive returns the block inclusive of both markers" {
  run block_inclusive architecture/README.md AUTO-INVENTORY
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == *"AUTO-INVENTORY:BEGIN"* ]]
  [[ "${lines[${#lines[@]}-1]}" == *"AUTO-INVENTORY:END"* ]]
}

# --- check 2: component/profile graph integrity (Step 4.2) -------------------------------------------
@test "graph: .ai-os.yml registers a component with no directory → fails (rule 1)" {
  printf 'components:\n  api: web-app/ts-hono-api\n  ghost: web-app/ts-hono-api\n' > .ai-os.yml
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -ne 0 ]
  [[ "$output" == *ghost* ]]
}

@test "graph: .ai-os.yml profile that does not exist → fails (rule 2)" {
  printf 'components:\n  api: web-app/nope\n' > .ai-os.yml
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -ne 0 ]
}

@test "graph: orphan component dir not in .ai-os.yml → fails (rule 3)" {
  mkdir -p components/web
  printf 'profile: web-app/ts-hono-api\n' > components/web/.component.yml
  # regenerate the inventory block so check 1 passes — isolating the orphan (graph) rule
  { printf '# Map\n\nintro\n\n'; gen_inventory; printf '\n## tail\n'; } > architecture/README.md
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -ne 0 ]
  [[ "$output" == *web* ]]
}

@test "graph: .ai-os.yml vs .component.yml profile mismatch → fails (rule 4)" {
  mkdir -p profiles/web-app/react-vite; printf '{}\n' > profiles/web-app/react-vite/profile.json
  printf 'components:\n  api: web-app/react-vite\n' > .ai-os.yml   # registry says react-vite, component says ts-hono-api
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -ne 0 ]
  [[ "$output" == *mismatch* ]]
}
