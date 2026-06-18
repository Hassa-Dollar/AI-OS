# The Solo AI-Dev-OS — Operating Manual

**Compressed doctrine.** Stack: Claude Opus 4.8 (the Lead) + OpenCode Go open-weight workforce. ~$30/mo.

## 0. How to read this
The **live, authoritative** layer is the ADRs (`architecture/adr/`), the contracts (`architecture/contracts/`),
`AGENTS.md`, `CLAUDE.md`, and the handoff (`docs/handoff/SESSION-HANDOFF.md`). This manual is the compressed
**why** behind them — where it and an ADR ever differ, **the ADR wins**. Three keystones: the **Routing
Function** (§2.1), **spec-first** (§6), and the **Opus budget** (§12).

## 1. Executive summary
The binding constraint isn't writing code (open-weight models do that at flat-rate volume) — it's **decision
quality + coordination**. So: one scarce **Lead** (Opus 4.8) spends its limited messages only at leverage
points (architecture, contracts, the review gate, hard bugs); a cheap **open-weight workforce** (OpenCode Go)
does implement / verify / research / document at volume; they coordinate through **git + files** (specs,
contracts, an append-only report ledger), never a live agent bus. You buy Opus *decisions* ($20 Pro) +
workforce *throughput* ($10 Go). Upgrade to Max only when the ledger proves the gate is the bottleneck (§12.4).

## 2. Core principles (the constitution)
### 2.1 P1 — Route by leverage, not price (the Routing Function)
`LEVERAGE = BlastRadius × Irreversibility × SpecGap`. High → **Opus** (decide / design / review-gate). Low +
specified + test-verifiable → **workforce**. High SpecGap → Opus closes the gap (writes a spec), then a worker
executes. **Opus's product is specs & contracts, not bulk code.**

- **P2** Prefer intelligence over agent count (1 implementer + 1 verifier per task; add a worker only with a disjoint file set).
- **P3** Coordinate through artifacts (git, `/tasks`, `/reviews`, `/reports`), not live chat.
- **P4** Maximize context *quality*, minimize *quantity* (curated ~8K beats raw 800K).
- **P5** One owner of coherence (the Lead), persisted as ADRs + contracts.
- **P6** The spec is the unit of work — self-contained (a worker needs nothing else).
- **P7** Verification is cheaper than generation — over-invest in cheap checks (tests, a 2nd model).
- **P8** Diversity: the model that writes never grades — **verifier ≠ author family**.
- **P9** "Useful output" = merged-and-stays-merged (≈2 weeks), not lines.
- **P10** Determinism where you can (scripts), intelligence where you must.
- **P11** Graceful degradation + reversibility (one-command rollback; reproducible from the spec).

## 3. System architecture
| Component | Identity | Role |
|---|---|---|
| Human | you | direction · irreversible calls · taste |
| Lead | Claude Opus 4.8 | plans · contracts · review gate · breaks hard bugs (scarce) |
| Workforce | OpenCode Go open-weight models | implement / verify / research / document (volume) |
| Git | trunk + short task branches | the coordination bus + rollback |
| Task queue | `tasks/active/*.md` | specs under execution |
| Review pipeline | `reviews/` + CI gates | where diffs are graded |
| Report ledger | `reports/**` (append-only) | durable memory; feeds the next plan |

Loop: **plan → spec → execute → verify-cheap → gate (threshold) → merge → report → (feeds next plan)**.
Diagram: `docs/handoff/ai-dev-os-build-loop.svg`.

## 4. Model selection
The workforce is a **fixed 7-model catalog** (ADR-0005); a **profile** binds roles → models per project type
(ADR-0003) and never changes the set. Pin exact versions — a bump is a CHANGE (ADR + regression; ADR-0005/0007).

| Model | Family | Typical role |
|---|---|---|
| GLM-5.2 | zhipu | implementer (default) |
| Kimi K2.7-Code | moonshot | autonomous worker · co-primary verifier |
| DeepSeek V4 Pro | deepseek | co-primary verifier · algorithm-heavy |
| Qwen3.7 Max | alibaba | researcher (1M context) |
| Qwen3.7 Plus | alibaba | 2nd implementer · weekly synthesis |
| MiniMax M3 | minimax | multimodal / frontend-from-design |
| MiMo-V2.5-Pro | xiaomi | scribe (mechanical) |

The **Lead is Opus 4.8** (not a workforce model). Role→model bindings live in
`profiles/<family>/<variant>/profile.json`; the catalog + families are in `AGENTS.md §1`. Match a model to the
task's *difficulty class*, not its prestige.

## 5. Agent design — roles are **hats**, not standing daemons
Zero-or-one instance of a hat is active at a time, instantiated by handing a model + prompt + spec to OpenCode.

- **Lead** (Opus): decompose intent → specs; own contracts/ADRs; run the review gate; break stuck bugs. Never types CRUD.
- **Implementer / Autonomous Worker**: one spec → one branch → passing gates + a completion report. The autonomous variant (Kimi K2.7-Code) handles big bounded jobs with tighter stop conditions.
- **Verifier / QA** (different family, P8): write/extend tests, break the code, emit RISK + VERDICT. Never edits the implementation.
- **Researcher**: decision-ready memos, not data dumps.

### 5.6 Scribe (stakes-tiered)
Mechanical writing (docstrings, changelogs, template-fill) on MiMo; the **weekly summary** drafted by Qwen3.7
Plus + **Opus sign-off**; judgment reports (bug / research / ADR / arch-review) authored by the role that owns
the judgment — the Scribe only formats. So no weak model ever solely authors anything Opus depends on.

- **DevOps**: the determinism layer (`scripts/`, CI) — code, not a model (P10).

### 5.8 Separation of powers
Implementer writes → different-family Verifier grades → Lead/gate approves → scripts merge.

## 6. Context & memory (load the smallest tier that suffices, P4)
Four tiers: **agent** (`/agents/*.md` + `AGENTS.md` — role identity), **project** (`/architecture` — ADRs,
contracts, invariants, conventions, glossary), **task** (`tasks/active/<id>.md` — the spec + working notes),
**report** (`/reports/**` — append-only outcomes).

### 6.6 The task-spec schema (the most important file format)
```markdown
---
id: 014
slug: rate-limit-login
owner_role: implementer
model: opencode-go/glm-5.2
verifier_model: opencode-go/deepseek-v4-pro   # different family (P8)
branch: task/014-rate-limit-login
blast_radius: low            # low|med|high  (high ⇒ the Lead designed the contract)
files_allowed:               # hard authority boundary; all within ONE component (ADR-0002)
  - components/<name>/src/...
  - reports/tasks/014-completion.md
depends_on_contracts: []
deps_preapproved: []
---
# Goal — one sentence: what must be true when this is done.
# Context (compressed) — 3–6 sentences; link contracts, don't inline the repo.
# Acceptance criteria — executable (e.g. 429 after 5 fails/60s; tests cover under/at/over/reset; diff coverage ≥ 90%).
# Out of scope — binding; prevents gold-plating.
# Stop conditions — when to ESCALATE not guess (needs a contract change / ambiguous criterion / dep not pre-approved).
# Working notes — the worker appends.
```
`scripts/new-task.sh` scaffolds this.

## 7. Repository structure
### 7.1 The tree
```
AGENTS.md  CLAUDE.md  OPERATING_MANUAL.md  bootstrap.sh  .ai-os.yml
agents/        role cards (who each role is)
prompts/       the six reusable prompts (§11)
scripts/       determinism layer: dispatch · gate · land · ship · pr · handoff · profile · rollback · new-task · ledger-append · _lib · ci-env
architecture/  adr/ · contracts/ · invariants.md (OS-level) · conventions.md (profile-applied) · glossary.md · README.md (map)
profiles/<family>/<variant>/   templates: profile.json · conventions.md · ci-env.sh · product-ci.yml · product-skeleton/
components/<name>/   the deliverable(s): self-contained + extractable; .component.yml names its profile
reviews/  reports/  tasks/{backlog,active,completed}/  knowledge/  docs/
.github/workflows/   os-ci.yml (OS-owned) · product-ci.yml (profile-owned)   — ADR-0006
```
### 7.2 / 7.3 — why one repo
Each top-level dir has one job (see its README); the OS scaffolding and the product(s) live in **one repo** so
git is the single coordination bus and Opus can correlate a regression with the ADR that caused it.

## 8. Branching & operating cycles
Trunk-based; **1 spec = 1 `task/<id>-slug` branch = 1 `--no-ff` merge** (so rollback is one command).
`spike/<topic>` is throwaway; `fix/<id>` is for Lead bug-breaks.

### 8.2 File ownership
A file is in **at most one** active branch's `files_allowed`, and a task's `files_allowed` stays within **one
component** (ADR-0002). `dispatch.sh` enforces both up front; the gate runs a post-CI boundary audit + isolation check.

### 8.3 Conflict resolution
Mechanical (rebase the branch onto trunk; trunk always wins). Semantic (contract drift) → **escalate to the
Lead**, who updates the contract + ADR and re-issues affected specs. Workers never resolve a semantic conflict.

### 8.4 Daily cycle
Opus touches the day **twice on purpose** — morning PLAN (emit 3–6 specs + any ADR/contract) and evening GATE
(batch-review only risk-routed diffs) — plus once on demand (a stuck bug). Everything between is workforce + scripts.

### 8.5 Weekly cycle
Sprint review (weekly summary = Qwen3.7 Plus draft + Opus sign-off); **architecture review** (reconcile code vs
ADRs/contracts — never skip); tech-debt triage; doc review; **performance review** — read `ledger.csv` and tune
the two knobs (model-per-task-class + the risk threshold).

## 9. Review pipeline, approval & rollback
CI → cross-family QA → risk router → **auto-approve** (most diffs) **or the Opus gate** (any threshold crossed:
contract/schema/security/new-dep/large/high-blast). CI is **two workflows** (ADR-0006): **os-ci** (shellcheck,
secret-scan, component-isolation — OS-owned) + **product-ci** (the component's build/test — profile-owned).

### 9.4 Standing checklist
Authoritative copy: `reviews/checklist.md`. **Automated:** lint/type/test, diff-coverage ≥ 90%, secret-scan,
diff ⊆ `files_allowed` within one component, no un-pre-approved dependency. **Opus gate** (risk-routed):
contract/invariant adherence, right-sized abstraction, no scope creep, sane failure modes, reversible.
**HUMAN-REQUIRED** (never auto): auth/payments/secrets/PII, prod data migration, public-API/contract break,
irreversible spend.

### 9.5 Rollback
`scripts/rollback.sh <merge-tag>` → `git revert -m 1` + a rollback tag + the ledger reason. One merge = one
logical change ⇒ back to a known-good state in < 2 min.

## 10. Reporting
Append-only, machine-readable headers; feeds planning + the weekly review. The Scribe fills mechanical reports;
judgment reports are authored by their owning role (§5.6).

### 10.1 Task-completion report (`reports/tasks/<id>-completion.md`)
Header (`type · id · model · verifier · result · opus_gate · first_pass_qa · diff · date`) + What was built ·
Acceptance criteria final state · Deviations · Defects found in QA · Follow-ups. Ledger events:
`dispatch | qa | auto-approve | opus-gate | land | rollback | guardrail`.

## 11. Prompt library (`prompts/`, versioned)
Six load-bearing prompts, each with a role anchor + minimum context + an explicit output contract + stop
conditions: `task-execution`, `code-review` (+ Opus-gate addendum), `bug-investigation`, `research`,
`architecture-analysis`, `doc-generation`. Fix a recurring failure **in the prompt**, not by re-correcting in chat.

## 12. Cost — ration Opus *attention*, not dollars
Dollars are ~flat (~$30/mo); the scarce input is Opus messages. **Always Opus:** planning, contract/schema/ADR
design, dependency adoption, the risk-gate, stuck bugs, security boundaries. **Never Opus:** CRUD, test writing,
mechanical refactors, report-typing, log-grepping, reading large doc sets.

### 12.4 The Opus budget ledger
One row per Opus message; weekly compute **Opus-msgs-per-merged-task**: `<4` healthy · `4–8` normal · `8–12`
raise the risk threshold / improve specs · `>12` you're using Opus as a worker (audit). Hitting the Pro cap on
*genuine gate reviews of high-risk diffs* (not stray debugging) is the only trigger to upgrade to Max 5x.

## 13. Automation roadmap
| | Phase 1 — Manual | Phase 2 — Semi-auto (**we are here**) | Phase 3 — Autonomous |
|---|---|---|---|
| dispatch | you | `dispatch.sh` | orchestrator |
| verify | you trigger QA | `gate.sh` + Verifier | orchestrator |
| merge | you approve | scripts (within envelope) | scripts (policy envelope) |
| Opus | by hand (Pro app) | API: plan + gated reviews | scheduled + exceptions |

Don't skip phases — each teaches the failure modes you must script around in the next. Separation of powers
(§5.8) and the HUMAN-REQUIRED stops hold at every phase.

## 14. Failure modes (wire detection for the ★ system-killers)
| Mode | Mitigation |
|---|---|
| ★ Architecture drift | weekly arch review (§8.5); contracts Lead-owned (P5) |
| ★ Spec drift (vague specs) | enforce the schema (§6.6); track first-pass-QA; if < 60%, fix specs first |
| ★ Silent model drift on a bump | pin versions; a bump = ADR + regression (ADR-0005/0007) |
| ★ Reward hacking (tests gamed) | P8 different-family verifier; the gate spot-checks test *quality* |
| ★ Opus budget exhaustion | the budget ledger (§12.4); raise the threshold; reserve ~15 msgs/day |
| ★ Secret leakage | `gitleaks` in os-ci (blocking); never put secrets in specs |
| Two workers, one file | `dispatch.sh` rejects intersecting / cross-component `files_allowed` (§8.2) |
| Escaped defects | adversarial QA (§11); diff-coverage; each escape updates the checklist |
| Over / under-escalation | tune the risk threshold weekly from the ledger |
| Dependency hallucination | `deps_preapproved` allowlist; CI resolves deps |
| Cross-component leak | the one-way isolation guard in os-ci (ADR-0002) |
| Knowledge loss on reset | everything lives in files (ADRs, `/knowledge`, the handoff) |

## 15. Final recommendation — the stack
$20 Claude Pro (Opus = the Lead) + $10 OpenCode Go (the fixed 7-model workforce, roles bound per profile). One
repo; trunk-based; spec-first; P8 everywhere; determinism in `scripts/`; coherence owned in `architecture/`.
Stay at Phase 2 until the ledger proves you should move.
