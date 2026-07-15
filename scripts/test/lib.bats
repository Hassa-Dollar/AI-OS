#!/usr/bin/env bats
# Unit tests for scripts/_lib.sh — the pure determinism-layer helpers (registry §3 harness).
# Run: scripts/test.sh   (CI: os-ci "determinism-layer tests" step). Each test pins a behavior a real
# bug got wrong, so the bug can't silently return.

setup() {
  # shellcheck disable=SC1091
  source "${BATS_TEST_DIRNAME}/../_lib.sh"
}

@test "family_of: the 7 catalog slugs map to the expected families (+ unknown)" {
  [ "$(family_of opencode-go/glm-5.2)"         = zhipu ]
  [ "$(family_of opencode-go/kimi-k2.7-code)"  = moonshot ]
  [ "$(family_of opencode-go/qwen3.7-plus)"    = alibaba ]
  [ "$(family_of opencode-go/qwen3.7-max)"     = alibaba ]
  [ "$(family_of opencode-go/deepseek-v4-pro)" = deepseek ]
  [ "$(family_of opencode-go/minimax-m3)"      = minimax ]
  [ "$(family_of opencode-go/mimo-v2.5-pro)"   = xiaomi ]
  [ "$(family_of whatever-else)"               = unknown ]
}

@test "fm_list strips surrounding YAML quotes incl. scoped pkgs (registry BUG-02)" {
  f="$(mktemp)"
  printf -- '---\ndeps_preapproved:\n  - hono\n  - "@hono/node-server"\n  - '\''zod'\''\n---\n' > "$f"
  run fm_list "$f" deps_preapproved
  [ "${lines[0]}" = "hono" ]
  [ "${lines[1]}" = "@hono/node-server" ]
  [ "${lines[2]}" = "zod" ]
  rm -f "$f"
}

@test "fm_scalar reads a top-level value and strips an inline comment" {
  f="$(mktemp)"
  printf -- '---\nmodel: opencode-go/glm-5.2   # the implementer\n---\n' > "$f"
  [ "$(fm_scalar "$f" model)" = "opencode-go/glm-5.2" ]
  rm -f "$f"
}

@test "yaml_scalar reads a fence-less yaml key, stripping comment + quotes (.component.yml; Step 1)" {
  f="$(mktemp)"
  printf -- '# profile governing this component\nprofile: web-app/ts-hono-api   # inline note\n' > "$f"
  [ "$(yaml_scalar "$f" profile)" = "web-app/ts-hono-api" ]
  printf -- 'profile: "quoted-value"\n' > "$f"
  [ "$(yaml_scalar "$f" profile)" = "quoted-value" ]
  rm -f "$f"
}

@test "ai_os_components parses name->profile pairs, stripping an inline comment (Step 4.2)" {
  f="$(mktemp)"
  printf 'components:\n  web: web-app/react-vite\n  api: web-app/ts-hono-api   # the API\n' > "$f"
  run ai_os_components "$f"
  [ "${lines[0]}" = "web web-app/react-vite" ]
  [ "${lines[1]}" = "api web-app/ts-hono-api" ]
  rm -f "$f"
}

@test "dead_links_in flags missing relative links; ignores urls, anchors, titles (Step 4.3)" {
  d="$(mktemp -d)"
  mkdir "$d/sub"
  printf 'real\n' > "$d/sub/exists.md"
  printf '%s\n' '[a](sub/exists.md)' '[b](sub/missing.md)' '[c](https://x.com)' '[d](#sec)' '[e](sub/exists.md "t")' > "$d/doc.md"
  run dead_links_in "$d/doc.md"
  [ "$status" -eq 0 ]
  [ "${#lines[@]}" -eq 1 ]
  [ "${lines[0]}" = "sub/missing.md" ]
  rm -rf "$d"
}

@test "assert_in_catalog accepts a catalog slug and rejects a superseded one" {
  run assert_in_catalog opencode-go/glm-5.2
  [ "$status" -eq 0 ]
  run assert_in_catalog opencode-go/glm-5.1
  [ "$status" -ne 0 ]
}

@test "component_of_spec: none / one / spans-many (registry BUG-07)" {
  f="$(mktemp)"
  printf -- '---\nfiles_allowed:\n  - docs/x.md\n---\n' > "$f"
  run component_of_spec "$f"; [ "$status" -eq 0 ]; [ -z "$output" ]
  printf -- '---\nfiles_allowed:\n  - components/api/src/x.ts\n  - components/api/x.test.ts\n---\n' > "$f"
  run component_of_spec "$f"; [ "$output" = "components/api" ]
  printf -- '---\nfiles_allowed:\n  - components/api/x.ts\n  - components/web/y.ts\n---\n' > "$f"
  run component_of_spec "$f"; [ "$status" -ne 0 ]
  rm -f "$f"
}

@test "verdict_field: line-anchored, last-match-wins, markdown-tolerant (ADR-0009/BUG-09)" {
  f="$(mktemp)"
  printf '%s\n' "discussion: the risk: here must be ignored" "## RISK: **med**" "notes" "VERDICT: pass" > "$f"
  [ "$(verdict_field "$f" RISK)" = med ]
  [ "$(verdict_field "$f" VERDICT)" = pass ]
  rm -f "$f"
}

@test "resolve_roles: inherits unset model/verifier from the component's profile (BUG-27/30)" {
  d="$(mktemp -d)"
  mkdir -p "$d/components/api" "$d/profiles/web-app/ts-hono-api"
  printf 'profile: web-app/ts-hono-api\n' > "$d/components/api/.component.yml"
  printf '{"roles":{"implementer":"opencode-go/glm-5.2","verifier":"opencode-go/deepseek-v4-pro"}}\n' \
    > "$d/profiles/web-app/ts-hono-api/profile.json"
  printf -- '---\nid: "T"\nfiles_allowed:\n  - components/api/src/x.ts\n---\n# Goal\nx\n' > "$d/spec.md"
  result="$( cd "$d" && resolve_roles spec.md )"
  [ "$result" = "opencode-go/glm-5.2"$'\t'"opencode-go/deepseek-v4-pro" ]
  rm -rf "$d"
}

@test "resolve_roles: explicit spec pins win over the profile" {
  d="$(mktemp -d)"
  mkdir -p "$d/components/api" "$d/profiles/web-app/ts-hono-api"
  printf 'profile: web-app/ts-hono-api\n' > "$d/components/api/.component.yml"
  printf '{"roles":{"implementer":"opencode-go/glm-5.2","verifier":"opencode-go/deepseek-v4-pro"}}\n' \
    > "$d/profiles/web-app/ts-hono-api/profile.json"
  printf -- '---\nid: "T"\nmodel: opencode-go/kimi-k2.7-code\nverifier_model: opencode-go/deepseek-v4-pro\nfiles_allowed:\n  - components/api/src/x.ts\n---\n# Goal\nx\n' > "$d/spec.md"
  result="$( cd "$d" && resolve_roles spec.md )"
  [ "$result" = "opencode-go/kimi-k2.7-code"$'\t'"opencode-go/deepseek-v4-pro" ]
  rm -rf "$d"
}

@test "resolve_roles v2: owner_role picks the author from the profile (ADR-0022)" {
  d="$(mktemp -d)"
  mkdir -p "$d/components/api" "$d/profiles/web-app/ts-hono-api"
  printf 'profile: web-app/ts-hono-api\n' > "$d/components/api/.component.yml"
  printf '{"roles":{"implementer":"opencode-go/glm-5.2","autonomous":"opencode-go/kimi-k2.7-code","verifier":"opencode-go/deepseek-v4-pro"}}\n' \
    > "$d/profiles/web-app/ts-hono-api/profile.json"
  printf -- '---\nid: "T"\nowner_role: autonomous\nfiles_allowed:\n  - components/api/src/x.ts\n---\n# Goal\nx\n' > "$d/spec.md"
  result="$( cd "$d" && resolve_roles spec.md )"
  [ "$result" = "opencode-go/kimi-k2.7-code"$'\t'"opencode-go/deepseek-v4-pro" ]
  rm -rf "$d"
}

@test "resolve_roles v2: author sharing the verifier's family falls to verifier_secondary (P8 structural, ADR-0022)" {
  d="$(mktemp -d)"
  mkdir -p "$d/components/api" "$d/profiles/web-app/ts-hono-api"
  printf 'profile: web-app/ts-hono-api\n' > "$d/components/api/.component.yml"
  printf '{"roles":{"implementer":"opencode-go/glm-5.2","verifier":"opencode-go/deepseek-v4-pro","verifier_secondary":"opencode-go/kimi-k2.7-code"}}\n' \
    > "$d/profiles/web-app/ts-hono-api/profile.json"
  printf -- '---\nid: "T"\nmodel_override: opencode-go/deepseek-v4-pro\noverride_reason: algo-heavy\nfiles_allowed:\n  - components/api/src/x.ts\n---\n# Goal\nx\n' > "$d/spec.md"
  result="$( cd "$d" && resolve_roles spec.md )"
  [ "$result" = "opencode-go/deepseek-v4-pro"$'\t'"opencode-go/kimi-k2.7-code" ]
  rm -rf "$d"
}

@test "override_of_spec lists pin fields; profile_of_spec finds the governing profile (ADR-0022)" {
  d="$(mktemp -d)"
  mkdir -p "$d/components/api" "$d/profiles/web-app/ts-hono-api"
  printf 'profile: web-app/ts-hono-api\n' > "$d/components/api/.component.yml"
  printf '{"roles":{"implementer":"opencode-go/glm-5.2"}}\n' > "$d/profiles/web-app/ts-hono-api/profile.json"
  printf -- '---\nid: "T"\nmodel_override: opencode-go/kimi-k2.7-code\nfiles_allowed:\n  - components/api/src/x.ts\n---\n# Goal\nx\n' > "$d/spec.md"
  [ "$( cd "$d" && override_of_spec spec.md )" = "model_override" ]
  [ "$( cd "$d" && profile_of_spec spec.md )" = "profiles/web-app/ts-hono-api/profile.json" ]
  printf -- '---\nid: "T"\nfiles_allowed:\n  - docs/x.md\n---\n# Goal\nx\n' > "$d/spec.md"
  [ -z "$( cd "$d" && profile_of_spec spec.md )" ]   # OS/chore spec: no profile
  rm -rf "$d"
}

@test "json_roles emits role/slug pairs from a pretty-printed profile.json; unbound[] is not a role" {
  f="$(mktemp)"
  printf '{\n  "roles": {\n    "implementer": "opencode-go/glm-5.2",\n    "verifier":    "opencode-go/deepseek-v4-pro"\n  },\n  "unbound": ["opencode-go/minimax-m3"]\n}\n' > "$f"
  run json_roles "$f"
  [ "${#lines[@]}" -eq 2 ]
  [ "${lines[0]}" = "implementer"$'\t'"opencode-go/glm-5.2" ]
  [ "${lines[1]}" = "verifier"$'\t'"opencode-go/deepseek-v4-pro" ]
  rm -f "$f"
}

@test "path_allowed: exact match + trailing-slash dir grant; bare dir name grants nothing (ADR-0028)" {
  allowed=$'scripts/os\nscripts/test/\ndocs/x.md'
  path_allowed "docs/x.md" "$allowed"
  path_allowed "scripts/os" "$allowed"                 # exact file
  path_allowed "scripts/test/status.bats" "$allowed"   # under the dir grant
  ! path_allowed "scripts/os/status.py" "$allowed"     # "scripts/os" has no slash -> not a grant
  ! path_allowed "scripts/test" "$allowed"             # the dir itself as a file: not exact-listed
  ! path_allowed "docs/x.md.bak" "$allowed"            # no prefix leak on exact entries
}

@test "filesets_clash: exact, file-under-dir (both directions), dir-under-dir; disjoint sets stay silent (ADR-0028)" {
  [ -z "$(filesets_clash $'a/b.ts\nc/' $'x/y.ts\nz/')" ]
  [ "$(filesets_clash $'a/b.ts' $'a/b.ts')" = "a/b.ts" ]           # exact
  [ "$(filesets_clash $'scripts/os/' $'scripts/os/x.py')" = "scripts/os/x.py" ]  # file under A's dir
  [ "$(filesets_clash $'scripts/os/x.py' $'scripts/os/')" = "scripts/os/" ]      # dir over B's file
  [ "$(filesets_clash $'scripts/' $'scripts/os/')" = "scripts/os/" ]             # dir contains dir
  [ -z "$(filesets_clash $'scripts/osx/a.py' $'scripts/os/')" ]    # prefix must respect the slash
}
