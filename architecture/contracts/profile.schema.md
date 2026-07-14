# Contract: profile schema

> Governed by ADR-0003. A profile is a reusable specialization template. Adding/altering the schema
> is HIGH leverage → Lead-owned, new ADR. **Scripts never branch on a profile name** — they read the
> canonical seam files and `profile.json` only.

## Directory layout
```
profiles/<family>/<variant>/        # e.g. profiles/web-app/ts-hono-api/
├─ profile.json                     # bindings + thresholds + metadata (below)
├─ conventions.md                   # → copied to components/<name>/conventions.md (stack rules + invariants; ADR-0013)
├─ ci-env.sh                        # → copied to scripts/ci-env.sh (lint/typecheck/test/coverage cmds)
└─ product-skeleton/                # → copied to components/<name>/ when scaffolding a component
                                    # (product-ci.yml is OS-owned + generic now, NOT a profile file — ADR-0013)
```
Each leaf is **complete and self-contained**: no `extends:`, no merge, no runtime composition.
Taxonomy depth is fixed at 2 (`family/variant`). A `profiles/<family>/_shared/` of snippets may exist
for **authoring-time copy only** — never resolved at runtime.

## `profile.json`
```json
{
  "name": "web-app/ts-hono-api",
  "description": "TypeScript on Node 22 — Hono HTTP API (Better Auth, better-sqlite3, Stripe). Back-end surface.",
  "roles": {
    "implementer":           "opencode-go/glm-5.2",
    "implementer_secondary": "opencode-go/qwen3.7-plus",
    "autonomous":            "opencode-go/kimi-k2.7-code",
    "verifier":              "opencode-go/deepseek-v4-pro",
    "verifier_secondary":    "opencode-go/kimi-k2.7-code",
    "researcher":            "opencode-go/qwen3.7-max",
    "scribe":                "opencode-go/mimo-v2.5-pro"
  },
  "unbound": ["opencode-go/minimax-m3"],
  "thresholds": { "max_files": 10, "max_lines": 300 }
}
```
- `roles` is a **flat dict**; a profile declares **only the roles its domain needs** (an embedded
  profile has no `multimodal`/frontend role, so none is ever assigned). Keep it pretty-printed —
  **one binding per line** (the no-jq parsers in `_lib.sh` are line-based until OS-P1 lands).
- The catalog is a **fixed set of 7** with its families in **`architecture/catalog.json`** — the single
  machine-readable source (ADR-0005/0022); `AGENTS.md §1` is the human mirror, checked by coherence
  check 9. A profile re-binds roles among those 7 and may leave some **unbound**; it never adds or
  swaps a model.
- **This file is the SINGLE source of role→model** (ADR-0022). Task specs name a role
  (`owner_role:`), never a model; `verifier_secondary` must be cross-family from any author role that
  shares `verifier`'s family (coherence check 8 lints this — P8 stays structurally solvable).

## How dispatch uses it (roles v2, ADR-0022)
1. `dispatch.sh`/`gate.sh` share `resolve_roles`: the spec's target component (`.component.yml →
   profile`) supplies `profile.json`; `roles[owner_role]` (default `implementer`) is the author.
2. The verifier is `roles.verifier` — or `roles.verifier_secondary` when the author's family would
   collide, so P8 needs no per-spec bookkeeping.
3. A spec-level `model_override:`/`verifier_override:` beats the profile **only** with
   `override_reason:` (dispatch dies without it; the gate adds a `model-override` risk flag; coherence
   check 7 polices active specs). OS/chore specs (no component profile) carry explicit
   `model:`/`verifier_model:` instead.
4. **P8 is enforced regardless of source:** `family_of(verifier) != family_of(author)` or dispatch dies.

## Active-profile registry — `.ai-os.yml` (repo root)
```yaml
components:
  api: web-app/ts-hono-api             # component name → active profile leaf
```
Written by `profile.sh apply`. Records which profile governs each component; lifecycle (lock / select /
add / migrate) per ADR-0003.
