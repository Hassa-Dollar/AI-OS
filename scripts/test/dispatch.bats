#!/usr/bin/env bats
# Integration tests: dispatch.sh --dry-run + new-task.sh against a throwaway fixture repo (registry §3).
# --dry-run validates everything (catalog, P8, secret-scan, component boundary) WITHOUT running a model.
# Every command is run via `bash -c '... 2>&1'` so the [ai-os] messages (written to stderr) are captured.

load helpers

@test "dispatch --dry-run: a valid spec passes validation" {
  make_repo
  write_spec 905 opencode-go/glm-5.2 opencode-go/deepseek-v4-pro
  run bash -c 'bash scripts/dispatch.sh 905 --dry-run 2>&1'
  [ "$status" -eq 0 ]
  [[ "$output" == *"validation passed"* ]]
}

@test "dispatch --dry-run: off-catalog model is rejected (ADR-0009)" {
  make_repo
  write_spec 901 opencode-go/glm-5.1 opencode-go/deepseek-v4-pro
  run bash -c 'bash scripts/dispatch.sh 901 --dry-run 2>&1'
  [ "$status" -ne 0 ]
  [[ "$output" == *"off-catalog"* ]]
}

@test "dispatch --dry-run: P8 violation (same family) is rejected" {
  make_repo
  write_spec 903 opencode-go/qwen3.7-max opencode-go/qwen3.7-plus   # both alibaba
  run bash -c 'bash scripts/dispatch.sh 903 --dry-run 2>&1'
  [ "$status" -ne 0 ]
  [[ "$output" == *"P8"* ]]
}

@test "dispatch --dry-run: files_allowed spanning two components is rejected (ADR-0002)" {
  make_repo
  cat > tasks/active/904-x.md <<'EOF'
---
id: "904"
slug: x
model: opencode-go/glm-5.2
verifier_model: opencode-go/deepseek-v4-pro
files_allowed:
  - components/api/src/a.ts
  - components/web/src/b.ts
---
# Goal
x
EOF
  run bash -c 'bash scripts/dispatch.sh 904 --dry-run 2>&1'
  [ "$status" -ne 0 ]
  [[ "$output" == *"multiple components"* ]]
}

@test "dispatch --dry-run: a secret in the spec is rejected (ADR-0014)" {
  make_repo
  # build the fake key at runtime so no key-shaped literal is ever committed (gitleaks-safe)
  fake="sk_test_$(printf 'a%.0s' $(seq 1 24))"
  cat > tasks/active/902-x.md <<EOF
---
id: "902"
slug: x
model: opencode-go/glm-5.2
verifier_model: opencode-go/deepseek-v4-pro
files_allowed:
  - components/api/src/x.ts
---
# Goal
STRIPE_SECRET_KEY=$fake
EOF
  run bash -c 'bash scripts/dispatch.sh 902 --dry-run 2>&1'
  [ "$status" -ne 0 ]
  [[ "$output" == *"secret"* ]]
}

@test "dispatch --dry-run: an env-var REFERENCE is NOT flagged as a secret (BUG-26)" {
  make_repo
  cat > tasks/active/907-x.md <<'EOF'
---
id: "907"
slug: x
model: opencode-go/glm-5.2
verifier_model: opencode-go/deepseek-v4-pro
files_allowed:
  - components/api/src/x.ts
---
# Goal
Configure auth with secret: process.env.BETTER_AUTH_SECRET and password: process.env.DB_PASSWORD
EOF
  run bash -c 'bash scripts/dispatch.sh 907 --dry-run 2>&1'
  [ "$status" -eq 0 ]
  [[ "$output" == *"validation passed"* ]]
}

@test "new-task: a duplicate id (already in completed) is rejected (BUG-08)" {
  make_repo
  : > tasks/completed/906-old.md
  run bash -c 'bash scripts/new-task.sh 906 newslug 2>&1'
  [ "$status" -ne 0 ]
  [[ "$output" == *"already used"* ]]
}

@test "dispatch --dry-run: omitted models inherit from the profile, even with 2 components (BUG-27)" {
  make_repo
  mkdir -p components/api components/web profiles/web-app/ts-hono-api
  printf 'profile: web-app/ts-hono-api\n' > components/api/.component.yml
  printf 'profile: web-app/react-vite\n'  > components/web/.component.yml
  printf '{"roles":{"implementer":"opencode-go/glm-5.2","verifier":"opencode-go/deepseek-v4-pro"}}\n' \
    > profiles/web-app/ts-hono-api/profile.json
  cat > tasks/active/908-x.md <<'EOF'
---
id: "908"
slug: x
branch: task/908-x
files_allowed:
  - components/api/src/x.ts
deps_preapproved: []
---
# Goal
placeholder
EOF
  run bash -c 'bash scripts/dispatch.sh 908 --dry-run 2>&1'
  [ "$status" -eq 0 ]
  [[ "$output" == *"model=opencode-go/glm-5.2"* ]]   # inherited from the profile (the spec omits it)
  [[ "$output" == *"validation passed"* ]]
}

@test "dispatch --dry-run: owner_role resolves the author from the profile (roles v2, ADR-0022)" {
  make_repo
  mkdir -p components/api profiles/web-app/ts-hono-api
  printf 'profile: web-app/ts-hono-api\n' > components/api/.component.yml
  printf '{"roles":{"implementer":"opencode-go/glm-5.2","autonomous":"opencode-go/kimi-k2.7-code","verifier":"opencode-go/deepseek-v4-pro"}}\n' \
    > profiles/web-app/ts-hono-api/profile.json
  cat > tasks/active/909-x.md <<'EOF'
---
id: "909"
slug: x
owner_role: autonomous
branch: task/909-x
files_allowed:
  - components/api/src/x.ts
deps_preapproved: []
---
# Goal
placeholder
EOF
  run bash -c 'bash scripts/dispatch.sh 909 --dry-run 2>&1'
  [ "$status" -eq 0 ]
  [[ "$output" == *"owner_role=autonomous"* ]]
  [[ "$output" == *"model=opencode-go/kimi-k2.7-code"* ]]
  [[ "$output" == *"validation passed"* ]]
}

@test "dispatch --dry-run: a model pin on a profile-governed spec without override_reason is rejected (ADR-0022)" {
  make_repo
  mkdir -p components/api profiles/web-app/ts-hono-api
  printf 'profile: web-app/ts-hono-api\n' > components/api/.component.yml
  printf '{"roles":{"implementer":"opencode-go/glm-5.2","verifier":"opencode-go/deepseek-v4-pro"}}\n' \
    > profiles/web-app/ts-hono-api/profile.json
  cat > tasks/active/910-x.md <<'EOF'
---
id: "910"
slug: x
model: opencode-go/kimi-k2.7-code
verifier_model: opencode-go/deepseek-v4-pro
branch: task/910-x
files_allowed:
  - components/api/src/x.ts
deps_preapproved: []
---
# Goal
placeholder
EOF
  run bash -c 'bash scripts/dispatch.sh 910 --dry-run 2>&1'
  [ "$status" -ne 0 ]
  [[ "$output" == *"override_reason"* ]]
}

@test "dispatch --dry-run: an unbound owner_role dies loud, naming the role (ADR-0022)" {
  make_repo
  mkdir -p components/api profiles/web-app/ts-hono-api
  printf 'profile: web-app/ts-hono-api\n' > components/api/.component.yml
  printf '{"roles":{"implementer":"opencode-go/glm-5.2","verifier":"opencode-go/deepseek-v4-pro"}}\n' \
    > profiles/web-app/ts-hono-api/profile.json
  cat > tasks/active/911-x.md <<'EOF'
---
id: "911"
slug: x
owner_role: multimodal
branch: task/911-x
files_allowed:
  - components/api/src/x.ts
deps_preapproved: []
---
# Goal
placeholder
EOF
  run bash -c 'bash scripts/dispatch.sh 911 --dry-run 2>&1'
  [ "$status" -ne 0 ]
  [[ "$output" == *"multimodal"* ]]
}
