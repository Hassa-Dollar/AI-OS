# Contract: profile schema

> Governed by ADR-0003. A profile is a reusable specialization template. Adding/altering the schema
> is HIGH leverage → Lead-owned, new ADR. **Scripts never branch on a profile name** — they read the
> canonical seam files and `profile.json` only.

## Directory layout
```
profiles/<family>/<variant>/        # e.g. profiles/web-app/ts-node-service/
├─ profile.json                     # bindings + thresholds + metadata (below)
├─ conventions.md                   # → copied to architecture/conventions.md (stack coding rules + stack invariants)
├─ ci-env.sh                        # → copied to scripts/ci-env.sh (lint/typecheck/test/coverage cmds)
├─ product-ci.yml                   # → copied to .github/workflows/product-ci.yml (profile-owned; OS checks live in os-ci.yml — ADR-0006)
└─ product-skeleton/                # → copied to components/<name>/ when scaffolding a component
```
Each leaf is **complete and self-contained**: no `extends:`, no merge, no runtime composition.
Taxonomy depth is fixed at 2 (`family/variant`). A `profiles/<family>/_shared/` of snippets may exist
for **authoring-time copy only** — never resolved at runtime.

## `profile.json`
```json
{
  "name": "web-app/ts-node-service",
  "description": "TypeScript on Node 22, node:http service (no framework). API/back-end surface.",
  "roles": {
    "implementer":           "opencode-go/glm-5.1",
    "implementer_secondary": "opencode-go/qwen3.7-plus",
    "autonomous":            "opencode-go/kimi-k2.7-code",
    "verifier":              "opencode-go/deepseek-v4-pro",
    "researcher":            "opencode-go/qwen3.7-max",
    "scribe":                "opencode-go/mimo-v2.5-pro"
  },
  "thresholds": { "max_files": 10, "max_lines": 300 }
}
```
- `roles` is a **flat dict**; a profile declares **only the roles its domain needs** (an embedded
  profile has no `multimodal`/frontend role, so none is ever assigned).
- The catalog is a **fixed set of 7** (ADR-0005). A profile re-binds roles among those 7 and may leave
  some **unbound** (no domain need); it never adds or swaps a model.
- Pins use the gateway slugs from `AGENTS.md` (the model **catalog**). The role→model **binding** lives
  here, not in `AGENTS.md`.

## How dispatch uses it
1. `dispatch.sh` reads the target component's `.component.yml → profile`, loads that profile's
   `profile.json`.
2. Implementer/verifier default from `roles` (a task spec may override per task).
3. **P8 is enforced regardless of source:** `family_of(verifier) != family_of(implementer)` or dispatch
   dies. (web-app/ts-node-service: implementer GLM = zhipu, verifier DeepSeek = deepseek ✓; rotate to
   Kimi = moonshot ✓.)

## Active-profile registry — `.ai-os.yml` (repo root)
```yaml
components:
  service: web-app/ts-node-service     # component name → active profile leaf
```
Written by `profile.sh apply`. Records which profile governs each component; lifecycle (lock / select /
add / migrate) per ADR-0003.
