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

@test "adding src/ to a component does NOT drift the inventory (status != structure, pre-T01)" {
  mkdir -p components/api/src
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -eq 0 ]
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

# --- check 3: dead relative links (Step 4.3) --------------------------------------------------------
@test "links: a relative link to a missing file fails" {
  printf '\nSee [gone](does-not-exist.md).\n' >> architecture/README.md
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -ne 0 ]
  [[ "$output" == *does-not-exist.md* ]]
}

@test "links: valid relative links + external URLs + anchors pass" {
  printf '\n[self](README.md) and [ext](https://x.com) and [a](#top).\n' >> architecture/README.md
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -eq 0 ]
}

@test "links: ADRs are exempt (history may cite removed files)" {
  mkdir -p architecture/adr
  printf '# ADR-0001\n\nrefers to [old](removed-file.md)\n' > architecture/adr/0001-x.md
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -eq 0 ]
}

# --- check 4: stub / placeholder docs (Step 4.4) ----------------------------------------------------
@test "stub: an empty / comment-only doc fails" {
  mkdir -p docs
  printf '   \n<!-- just a comment -->\n\n' > docs/empty.md
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -ne 0 ]
  [[ "$output" == *empty.md* ]]
}

@test "stub: an explicit <!-- STUB --> marker fails" {
  mkdir -p docs
  printf '# Real Title\n\nSome content.\n<!-- STUB -->\n' > docs/wip.md
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -ne 0 ]
  [[ "$output" == *wip.md* ]]
}

@test "stub: a heading-only doc with no body is allowed (safe, not flagged)" {
  mkdir -p docs
  printf '# Just A Heading\n' > docs/short.md
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -eq 0 ]
}

# --- check 5: role docs name no workforce model (Step 4 / #87) ---------------------------------------
@test "roles: a role card that names a workforce model fails (check 5)" {
  mkdir -p agents
  printf '# Role: Implementer — GLM-5.2 (default)\n\nbody\n' > agents/implementer.md
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -ne 0 ]
  [[ "$output" == *implementer.md* ]]
}

@test "roles: model-agnostic role docs pass; the Lead's Opus mention is allowed (check 5)" {
  mkdir -p agents prompts
  printf '# Role: Implementer\n\nmodel bound per-profile (profile.json).\n' > agents/implementer.md
  printf '# Role: Lead — Claude Opus 4.8\n\nthe Lead is fixed.\n'          > agents/lead.md
  printf '# Prompt: Task Execution\n\nROLE: you are {{model}}.\n'          > prompts/task-execution.md
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -eq 0 ]
}

# --- check 7: component specs name a role; a model pin needs override_reason (ADR-0022) -------------
@test "spec pinning a model without override_reason → fails (check 7, ADR-0022)" {
  printf '{"roles":{"implementer":"opencode-go/glm-5.2","verifier":"opencode-go/deepseek-v4-pro"}}\n' \
    > profiles/web-app/ts-hono-api/profile.json
  mkdir -p tasks/active
  cat > tasks/active/T99-x.md <<'SPEC'
---
id: "T99"
slug: x
model: opencode-go/glm-5.2
verifier_model: opencode-go/deepseek-v4-pro
files_allowed:
  - components/api/src/x.ts
---
# Goal
x
SPEC
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -ne 0 ]
  [[ "$output" == *"without override_reason"* ]]
}

@test "spec that names only owner_role (profile resolves the models) → passes check 7" {
  printf '{"roles":{"implementer":"opencode-go/glm-5.2","verifier":"opencode-go/deepseek-v4-pro"}}\n' \
    > profiles/web-app/ts-hono-api/profile.json
  mkdir -p tasks/active
  cat > tasks/active/T99-x.md <<'SPEC'
---
id: "T99"
slug: x
owner_role: implementer
files_allowed:
  - components/api/src/x.ts
---
# Goal
x
SPEC
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -eq 0 ]
}

@test "spec pin WITH override_reason → passes check 7 (audited exception, ADR-0022)" {
  printf '{"roles":{"implementer":"opencode-go/glm-5.2","verifier":"opencode-go/deepseek-v4-pro"}}\n' \
    > profiles/web-app/ts-hono-api/profile.json
  mkdir -p tasks/active
  cat > tasks/active/T99-x.md <<'SPEC'
---
id: "T99"
slug: x
model_override: opencode-go/deepseek-v4-pro
verifier_override: opencode-go/kimi-k2.7-code
override_reason: algo-heavy task, want deepseek as author
files_allowed:
  - components/api/src/x.ts
---
# Goal
x
SPEC
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -eq 0 ]
}

# --- check 8: profile lint — bindings on-catalog, P8 solvable (ADR-0022) ----------------------------
@test "profile binding an off-catalog slug → fails (check 8)" {
  printf '{\n  "roles": {\n    "implementer": "opencode-go/glm-5.1",\n    "verifier": "opencode-go/deepseek-v4-pro"\n  }\n}\n' \
    > profiles/web-app/ts-hono-api/profile.json
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -ne 0 ]
  [[ "$output" == *"off-catalog"* ]]
}

@test "profile whose author role shares the verifier family with no verifier_secondary → fails (check 8)" {
  printf '{\n  "roles": {\n    "implementer": "opencode-go/deepseek-v4-pro",\n    "verifier": "opencode-go/deepseek-v4-pro"\n  }\n}\n' \
    > profiles/web-app/ts-hono-api/profile.json
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -ne 0 ]
  [[ "$output" == *"P8 unsolvable"* ]]
}

@test "profile with a cross-family verifier_secondary covering a same-family author → passes (check 8)" {
  printf '{\n  "roles": {\n    "implementer": "opencode-go/deepseek-v4-pro",\n    "verifier": "opencode-go/deepseek-v4-pro",\n    "verifier_secondary": "opencode-go/kimi-k2.7-code"\n  }\n}\n' \
    > profiles/web-app/ts-hono-api/profile.json
  run bash "$SCRIPTS/verify-coherence.sh"
  [ "$status" -eq 0 ]
}
