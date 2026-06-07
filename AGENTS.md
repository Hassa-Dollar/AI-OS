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

## 1. Model pins (exact versions — never "latest")

> Use the exact slugs your gateway reports (`opencode models`). Update deliberately:
> a version bump is a CHANGE → run the regression suite + write an ADR (see Failure Mode #3).

| Role / hat | Model (pin) | OpenCode slug (adjust to your gateway) |
|---|---|---|
| Implementer (primary) | GLM-5.1 | `opencode/glm-5.1` |
| **Autonomous Worker / agentic (primary)** | **Kimi K2.6 Thinking** | `opencode/kimi-k2.6-thinking` |
| Implementer-2 / parallel / cheap | Qwen3.7 Plus | `opencode/qwen3.7-plus` |
| Verifier / QA (rotate A) | **Kimi K2.6** | `opencode/kimi-k2.6` |
| Verifier / QA (rotate B) | DeepSeek V4 Pro | `opencode/deepseek-v4-pro` |
| Researcher / 1M-context spike | Qwen3.7 Max | `opencode/qwen3.7-max` |
| Multimodal / frontend-from-design | MiniMax M3 | `opencode/minimax-m3` |
| Scribe — mechanical (docstrings/changelogs/template fill) | MiMo-V2.5-Pro | `opencode/mimo-v2.5-pro` |
| Scribe — weekly-summary synthesis (then Opus sign-off) | Qwen3.7 Plus | `opencode/qwen3.7-plus` |
| Offline / secret-sensitive fallback | local Qwen3-Coder-Next | `ollama/qwen3-coder-next` |

**The Lead is Claude Opus 4.8 (Claude Pro / API) — not in this table on purpose. It is scarce; see `CLAUDE.md`.**

---

## 2. Separation of powers (P8) — non-negotiable

The model that **writes** code is never the model that **grades** it, and neither **approves** the merge.

- **Verifier family ≠ author family, per task.** `scripts/dispatch.sh` enforces this.
  - Kimi K2.6 authored a diff  → graded by **DeepSeek V4 Pro**.
  - GLM-5.1 / Qwen authored    → graded by **Kimi K2.6** *or* DeepSeek V4 Pro.
- Kimi K2.6 is first-class with **two hats** (Autonomous Worker + Verifier) but **never both on the same diff**.
- Merge is approved only by the Lead (risk-routed diffs) or auto-approved by `gate.sh` (CI + clean cross-family QA + zero risk-thresholds crossed).

---

## 3. Worker authority limits (every implementer/autonomous run)

YOU MAY:
- edit **only** the files in the task spec's `files_allowed`,
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

## 4. Coding conventions  *(customize these to your stack — examples shown)*

- Language/runtime: <fill in, e.g. TypeScript 5.x, Node 22, strict mode>.
- Formatting/lint: run `<lint cmd>`; never hand-format; never disable a lint rule inline.
- Tests: `<test cmd>`; new code requires tests; diff coverage ≥ 90%.
- Types: `<typecheck cmd>` must pass; no `any`/`unsafe` casts without a comment + reason.
- Architecture invariants (always hold — see `architecture/invariants.md`):
  - money is integer minor-units (cents); never floats.
  - all timestamps are UTC ISO-8601.
  - handlers never touch the DB directly — go through the repository layer.
- Errors: fail loud in dev, handled at the boundary in prod; never swallow exceptions.
- Secrets: never read, log, echo, or commit secrets. If a task needs one, `ESCALATE`.

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
