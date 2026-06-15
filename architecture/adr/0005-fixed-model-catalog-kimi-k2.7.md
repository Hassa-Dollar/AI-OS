# ADR-0005: Fixed model catalog + Kimi K2.7-code; profiles bind roles, not the set

- **Status:** Accepted
- **Date:** 2026-06-14
- **Deciders:** Lead (Opus) + human operator

## Context
ADR-0003 introduced per-profile role→model bindings and, loosely, let a profile vary *which* models it
used. The operator has tightened this: the workforce **model set is fixed** — the same models are pinned
for every project type; only the role→model *bindings* change per profile. Separately, Moonshot shipped
**Kimi K2.7-code**, superseding K2.6. Per Failure Mode #3 (§14), a model version bump is a CHANGE that
warrants an ADR + a regression window — never a silent swap.

## Decision
- **The catalog is exactly these seven OpenCode-Go models, fixed across all project types:**

  | Model | Family | Slug |
  |---|---|---|
  | GLM-5.1 | zhipu | `opencode-go/glm-5.1` |
  | Kimi K2.7-code | moonshot | `opencode-go/kimi-k2.7-code` |
  | DeepSeek V4 Pro | deepseek | `opencode-go/deepseek-v4-pro` |
  | Qwen3.7 Max | alibaba | `opencode-go/qwen3.7-max` |
  | Qwen3.7 Plus | alibaba | `opencode-go/qwen3.7-plus` |
  | MiniMax M3 | minimax | `opencode-go/minimax-m3` |
  | MiMo-V2.5-Pro | xiaomi | `opencode-go/mimo-v2.5-pro` |

  A profile may **not** add or substitute a different model — it may only re-bind roles among these seven.
- **Kimi K2.6 → Kimi K2.7-code** (`opencode-go/kimi-k2.6` → `opencode-go/kimi-k2.7-code`). It keeps its
  hats (autonomous worker + co-primary verifier). `family_of()` still maps `*kimi*` → `moonshot`, so **P8
  is unaffected**. Treat the first sprint on K2.7-code as a regression window — watch first-pass-QA rate
  and escaped defects in the ledger.
- **Profiles bind only the roles their domain needs** ("bind what the domain needs"). The seven stay
  pinned and available; a profile assigns the subset it uses. Example — a backend service binds
  implementer / verifier / researcher / scribe / autonomous / 2nd-implementer, but **not** the multimodal
  model (no UI work). An unbound model is still in the catalog, just idle for that project.
- **`AGENTS.md §1` is the catalog** (the seven, with families/slugs/strengths); **role bindings live in
  each `profiles/<family>/<variant>/profile.json`** (refines ADR-0003). The handoff presents the catalog
  and shows roles as *profile-bound* (new SVG) — never a global model→role table.
- **Local fallback deferred.** A laptop-runnable offline / secret-sensitive model (ex-`ollama/qwen3-coder-next`)
  is out of scope until the seven hosted models are validated; it will get its own ADR and its own tests.

## Consequences
- Reproducibility: every project draws from the same pinned set; no per-project model drift.
- `family_of()` and the P8 separation-of-powers logic are unchanged by the Kimi bump.
- By operator choice, historical task records were rewritten to the new slug — audit text now reads
  `kimi-k2.7-code` even where K2.6 actually ran (noted here for the record).
- Adding a model to the catalog is itself an ADR (it changes the fixed set).

## Alternatives considered
- **Every profile binds all seven:** forces artificial roles (a multimodal model on a backend-only
  project). Rejected — idle-but-available is cleaner.
- **Per-profile model sets (ADR-0003 read loosely):** invites per-project drift and breaks the
  "same pinned set everywhere" guarantee. Superseded by this ADR.
