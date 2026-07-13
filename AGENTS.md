# AGENTS.md — Workforce Operating Rules

> OpenCode loads this file automatically into every worker run. It is the standing
> contract every open-weight model obeys. Keep it short, blunt, and current.
> Companion files: `CLAUDE.md` (the Lead/Opus protocol), `OPERATING_MANUAL.md` (the full system).

---

## 0. The one rule (routing)

Route work by **leverage**, not price: `Leverage = BlastRadius × Irreversibility × SpecGap`.
- High leverage (interfaces, schemas, deps, security, architecture, the review gate) → **the Lead (Opus)**, not you.
- Low leverage + specified + test-verifiable → **you** (this file's models).
- If a task needs a high-leverage *decision* to proceed, **STOP and escalate** — do not guess.

You implement to a spec. You do **not** design cross-module interfaces. The Lead does.

---

## 1. Model catalog (what's available) — role bindings live in profiles, not here

> Roles are **not** fixed to models globally (ADR-0003). Each component's **profile** binds role→model in
> `profiles/<family>/<variant>/profile.json` — **the single source of that binding (ADR-0022)**: a task
> spec names a role (`owner_role:`), never a model; `dispatch.sh` resolves it and still enforces P8 (§2).
> The only spec-level pin is `model_override:` + `override_reason:`, and the gate risk-flags it.
> This table is the **human mirror** of `architecture/catalog.json` (the machine source — coherence
> check 9 keeps them in sync). Pin versions, never "latest" — a bump is a CHANGE: edit catalog.json in
> the same commit as its ADR → regression run (Failure Mode #3).

| Model | Family | Slug (`opencode-go/` paid tier) | Typically bound to |
|---|---|---|---|
| GLM-5.2 | zhipu | `opencode-go/glm-5.2` | implementer (reliable long-horizon) |
| Kimi K2.7-Code | moonshot | `opencode-go/kimi-k2.7-code` | autonomous worker · co-primary verifier |
| Qwen3.7 Plus | alibaba | `opencode-go/qwen3.7-plus` | parallel implementer · weekly-synth |
| Qwen3.7 Max | alibaba | `opencode-go/qwen3.7-max` | researcher (1M context) |
| DeepSeek V4 Pro | deepseek | `opencode-go/deepseek-v4-pro` | co-primary verifier · algo-heavy |
| MiniMax M3 | minimax | `opencode-go/minimax-m3` | multimodal / frontend-from-design |
| MiMo-V2.5-Pro | xiaomi | `opencode-go/mimo-v2.5-pro` | scribe (mechanical) |

> These **seven are the fixed catalog** (ADR-0005; machine-readable in `architecture/catalog.json`) — the
> same set for every project type; a profile re-binds roles among them, it never adds or swaps a model. "Typically bound to" is guidance, not a
> binding (a back-end profile has no frontend/multimodal role at all). The free `opencode/` tier lacks the
> strong implementer/verifier models — emergency fallback only; never bind a role to it. No `-thinking`
> slug exists; **Kimi K2.7-Code** serves the autonomous-worker role directly.
> **Local fallback deferred:** a laptop-runnable offline / secret-sensitive model (ex-`ollama/qwen3-coder-next`)
> is planned with its own tests — out of scope until the seven hosted models are validated (ADR-0005).

**The Lead is Claude Opus 4.8 (Claude Pro / API) — not a workforce model, by design. It is scarce; see `CLAUDE.md`.**

---

## 2. Separation of powers (P8) — non-negotiable

The model that **writes** code is never the model that **grades** it, and neither **approves** the merge.

- **Verifier family ≠ author family, per task.** Structural since ADR-0022: the profile binds
  `verifier` (+ `verifier_secondary` for authors sharing its family); `resolve_roles` picks the legal
  one and `scripts/dispatch.sh` still hard-checks it.
  - Kimi K2.7-Code authored a diff  → graded by **DeepSeek V4 Pro**.
  - GLM-5.2 / Qwen authored    → graded by **Kimi K2.7-Code** *or* DeepSeek V4 Pro.
- Kimi K2.7-Code is first-class with **two hats** (Autonomous Worker + Verifier) but **never both on the same diff**.
- Merge is approved only by the Lead (risk-routed diffs) or auto-approved by `gate.sh` (CI + clean cross-family QA + zero risk-thresholds crossed).

---

## 3. Worker authority limits (every implementer/autonomous run)

YOU MAY:
- edit **only** the files in the task spec's `files_allowed` — **plus two implicit allowances**
  (always permitted, no listing required): your completion report `reports/tasks/<id>-completion.md`
  (required output, §6) and the **Working Notes** section of your own task spec,
- commit in small logical steps with clear messages,
- append to the spec's **Working Notes** as you go (Autonomous Worker: every N steps).

YOU MAY NOT:
- create or change any cross-module interface / contract / schema → **STOP, escalate**,
- add a dependency not in the spec's `deps_preapproved` → **STOP, escalate**,
- exceed the spec ("Out of scope" is binding) — no gold-plating,
- weaken, skip, or delete acceptance tests to make them pass,
- merge, or touch `main`.

STOP CONDITIONS (emit `ESCALATE: <reason>` and halt — do not guess):
- the task can't be done without changing a contract,
- the spec is ambiguous about a behavior an acceptance criterion depends on,
- a required dependency isn't pre-approved,
- (Autonomous Worker) two consecutive steps make no measurable progress.

---

## 4. Coding conventions  *(stack-specific → provided by the active profile)*

Stack coding rules and stack invariants are **profile-provided**, not hard-coded here (ADR-0003): follow the
conventions of the component your task targets — `components/<name>/conventions.md` (the applied copy of that
component's profile) — plus the OS-level invariants in `architecture/invariants.md`. Universals that
hold under **every** profile:

- run the profile's lint / typecheck / test before a task is "done"; never hand-format; an inline
  lint-disable is an `ESCALATE`, not a fix.
- new code requires tests; **diff coverage ≥ 90%**.
- fail loud in dev, handle at the boundary in prod; never swallow exceptions.
- never read, log, echo, or commit secrets. If a task needs one, `ESCALATE`.

---

## 5. Git conventions

- Branch per task: `task/<id>-slug` (Autonomous big jobs may use `task/<id>-slug` too).
- Spikes: `spike/<topic>` — throwaway, never merged.
- Lead bug-breaks: `fix/<id>-slug`.
- Rebase onto `main` before requesting the gate (linear history). Trunk always wins.
- Commit messages: `<type>(<scope>): <imperative summary>` (feat/fix/refactor/test/docs/chore).

---

## 6. Output contract (what "done" means)

- a branch with passing local gates (lint, typecheck, tests, diff-coverage, secret-scan),
- a filled **task-completion report** → `reports/tasks/<id>-completion.md` (template in the manual §10.1),
- if you escalated: a precise statement of the missing decision, nothing more.

"Done" = merged **and stays merged** for two weeks (P9). Generated-then-reverted code is negative throughput.

---

## 7. How this file is used

OpenCode auto-loads `AGENTS.md` from repo root on every run, so these rules are always in context.
`scripts/dispatch.sh` additionally injects the specific task spec + the relevant `prompts/*.md`.
Do not restate these rules in task specs — reference them. Keep this file under ~200 lines so it always fits.

---

## 8. Memory (ADR-0016) — log mid-flight, recall what's relevant

The OS has a local memory DB (`scripts/db.sh`). Use it — don't re-derive context from raw code each run.

- **Log anytime, any role.** When you hit, decide, or learn something worth keeping — a bug, a cause, a fix,
  a decision, a surprising fact — record it as you go:
  `scripts/db.sh remember <kind> "<summary>" [--detail … --task … --component …]`.
- **Recall scoped + brief.** Before non-trivial work, pull only what's relevant to THIS task:
  `scripts/db.sh recall "<terms>" --scope component:<name>` (small top-k). Keep it short.
- **Do NOT open-ended-research mid-task.** Broad / cross-scope investigation is the **researcher's** job in a
  dedicated research task. If you think you need it → emit `ESCALATE`, don't chase it inline.
- Never store a secret (the writer rejects credentials). The system also logs its own events + failures.
