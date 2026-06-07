# The Solo AI Development Operating System

### An Operational Manual for a One-Person Software Organization

**Version 1.0 — June 2026**
**Stack:** Claude Opus 4.8 (Lead/Architect) + OpenCode Go open-weight models (Workforce)
**Budget:** ~$30/month (Claude Pro $20 + OpenCode Go $10)
**Author's stance:** CTO / AI systems architect / agent researcher writing for an engineer.

---

## 0. How to read this document

This is an operating manual, not an essay. It is meant to live at the root of your repo as `OPERATING_MANUAL.md` and be executed. Sections 3–12 are procedures; sections 13–15 are strategy. If you implement only three things from this document, implement the **Routing Function** (§2.1), the **Spec-First handoff** (§6 + §11), and the **Opus Budget Ledger** (§12). Everything else is in service of those three.

A note on the organizing principle, because it inverts the most common mistake. **This system is not organized around maximizing free model usage.** Optimizing for "requests consumed on the cheap tier" is resource-centric design — it maximizes the wrong variable and quietly degrades architecture. We organize around **decision-value per dollar**: the premium model is placed at the highest-leverage points of the workflow (the points that constrain the most future work and are the most expensive to reverse), not at the points where it is used most often. A single Opus review that prevents a week-long architectural mistake outscores 100 free worker requests. The premium model is a scalpel, not a workhorse.

---

## 1. Executive Summary

### 1.1 The thesis

In 2026 the binding constraint on a solo developer is no longer the *cost of writing code* — open-weight models (GLM-5.1, Qwen3.7, DeepSeek V4 Pro, Kimi K2.6) generate correct, well-specified code at effectively unlimited volume for $10/month through OpenCode Go. The binding constraint is **decision quality and coordination overhead**: knowing *what* to build, keeping the architecture coherent across months, and catching the small number of high-blast-radius mistakes before they compound.

Therefore the system allocates exactly two classes of resource:

1. **Intelligence at the leverage points** — Claude Opus 4.8, deployed as a single "Lead" brain that does architecture, interface/contract design, the review gate, stuck-debugging, and integration decisions. It is *scarce by design* (Claude Pro caps Opus at roughly 45 messages per 5-hour window plus a weekly ceiling), and we treat that scarcity as a feature that forces leverage discipline.
2. **Throughput at the labor points** — a small, role-differentiated pool of open-weight workers running inside OpenCode, executing well-specified, test-verifiable tasks on isolated git branches at high volume and near-zero marginal cost.

The connective tissue between them is **specifications, contracts, and an append-only report ledger** — not a live multi-agent message bus. Coordination happens through git and through structured files on disk, because in a solo system the coordination layer must be inspectable, diffable, and durable for months.

### 1.2 The shape of the system in one paragraph

The human sets direction. Opus, once per cycle, reads a *compressed* view of the repo (architecture docs + interface contracts + the report ledger, not the whole tree) and emits a sprint of self-contained **task specs** with acceptance criteria. Open-weight workers pick up one task per git branch and implement to spec; a *different* open-weight model writes/runs tests and does adversarial QA. Work that passes local gates is queued. Opus reviews the queue **in batch**, but only diffs that cross a risk threshold get Opus's full attention — everything else is approved on the strength of passing tests plus cheap peer review. Approved work merges to trunk. An open-weight scribe writes the reports. The cycle repeats. Over months, the deterministic parts (dispatch, test gates, report generation, threshold routing) get automated; Opus and the human stay in the loop only at irreversible decision points.

### 1.3 Why this beats the obvious alternatives

| Alternative design | Why it loses |
|---|---|
| **Big permanent agent swarm** (6+ always-on agents) | Coordination overhead grows superlinearly; agents edit the same files; you pay (in tokens and in your attention) to referee them. Intelligence is concentrated in frontier models — adding cheap agents adds noise, not throughput. |
| **"Use Opus for everything"** | Blows the Pro Opus cap by mid-morning; you spend $200/mo on Max to do work a $10 open model does identically when the spec is good. Negative ROI on reversible tasks. |
| **"Use open models for everything, no premium tier"** | Architecture drifts. Nobody owns coherence. Month 3 you have 40 inconsistent modules and a test suite that passes while the system is wrong. You saved $20/mo and lost a month. |
| **This system (1 Lead + small worker pool + spec/contract layer)** | Premium intelligence sits only at leverage points; throughput is cheap and parallel; coherence is owned by one brain and persisted in contracts; coordination is git, not a message bus. |

### 1.4 What you are actually buying with $30/month

- **$20 — Claude Pro (Opus 4.8 access).** Not "a chatbot." You are buying a rationed quantity of the highest-quality *decisions* and *reviews* available. Spend it like a CFO spends capex.
- **$10 — OpenCode Go.** Effectively unlimited, reliable access to ~14 open-weight frontier coding models (GLM, Kimi, Qwen, DeepSeek, MiniMax, MiMo). This is your engineering payroll. It is the cheapest hire you will ever make.

If and only if the Opus *review gate* becomes your bottleneck (you will see it in the ledger — see §12.4), upgrade to **Max 5x ($100)**. Do not upgrade preemptively; let the ledger prove the bottleneck first.

---

## 2. Core Design Principles

These eleven principles are the constitution. Every later procedure is downstream of them. When a procedure and a principle conflict, the principle wins and the procedure is a bug.

### 2.1 P1 — Route by leverage, not by price (the Routing Function)

The central decision in this entire system is: *for a given unit of work, which model does it?* Do not answer "the cheapest one that can." Answer with the **Routing Function**, scored on three axes:

```
LEVERAGE SCORE  =  BlastRadius  ×  Irreversibility  ×  SpecGap

  BlastRadius     how many *future* decisions does this constrain?
                  (interface/schema/dependency = high; one pure function = low)
  Irreversibility how expensive is it to undo once merged & built upon?
                  (DB migration, public API = high; internal refactor = low)
  SpecGap         how much ambiguity remains about what "correct" means?
                  (fuzzy product/architecture question = high;
                   "implement this signature, pass these tests" = ~0)

ROUTE:
  LEVERAGE high   -> Claude Opus 4.8           (decide / design / review-gate)
  LEVERAGE low    -> open-weight worker        (implement / test / document)
  SpecGap high    -> Opus FIRST (close the gap), THEN open worker executes
```

The single most important consequence: **Opus's primary product is not code — it is high-quality, low-ambiguity specifications and the contracts that bound them.** Worker output quality is capped by spec quality. So you spend scarce intelligence manufacturing specs and verifying against them, and you spend cheap throughput satisfying them.

### 2.2 P2 — Prefer intelligence over agent count

One excellent decision beats ten mediocre ones racing each other. The default worker count is **one implementer + one verifier per task**, not a swarm. Add a worker only when you can name the *independent, non-overlapping* file set it will own. If you cannot draw that boundary, you do not have a second task — you have one task and an illusion of parallelism that will cost you a merge conflict.

### 2.3 P3 — Minimize coordination overhead; coordinate through artifacts, not conversations

Agents do not talk to each other in real time. They read and write **files**: task specs, contracts, reports. This makes coordination durable (survives months and session resets), inspectable (you can `git blame` a decision), and cheap (no tokens spent on agents negotiating). The coordination layer is git + the `/tasks`, `/reviews`, `/reports` directories. If you find yourself wanting a live agent-to-agent channel, you have a task-boundary problem (see P2).

### 2.4 P4 — Maximize context quality, minimize context quantity

A 1M-token context window is a liability, not a feature, if you fill it with the whole repo. Models dilute and lose the thread ("context rot"). Opus reads a **compressed** repo view (architecture map + relevant contracts + recent report ledger), and each worker reads **only its task spec plus the specific contracts it touches**. Curated 8K tokens beats raw 800K every time. Context is a designed payload, not a dump.

### 2.5 P5 — Preserve architectural consistency through owned contracts

Exactly one entity owns coherence: the Lead (Opus). Coherence is *persisted*, not remembered, as **Architecture Decision Records (ADRs)** and **interface contracts** under `/architecture`. Workers may not invent cross-module interfaces; they consume contracts. Any change to a contract is a high-leverage decision and goes to Opus by definition (P1).

### 2.6 P6 — Specifications are the unit of work, and they are self-contained

A task spec is a closed package: context, the contract(s) it implements, explicit acceptance criteria (preferably executable tests), authority limits, and stop conditions. A worker handed a spec needs nothing else — not the chat history, not your intent in your head, not another agent. This is what lets a stateless $10 model produce senior-engineer output and what lets the system survive a laptop reboot mid-sprint.

### 2.7 P7 — Verification is cheaper than generation; exploit the asymmetry

It is far cheaper to *check* that code meets a spec than to *write* correct code from a fuzzy intent. So we over-invest in cheap verification (tests, types, a second open model doing adversarial review) and reserve expensive verification (Opus review) only for diffs where cheap verification is insufficient — i.e., high-leverage diffs. Most code should never be seen by Opus; it should be *proven* correct by tests Opus designed the acceptance criteria for.

### 2.8 P8 — Model diversity is a feature; never let one model both write and grade its own work

The implementer and the verifier must be **different model families**. A model is blind to its own systematic errors and will happily certify them. GLM implements, DeepSeek or Kimi verifies. This single rule catches a large fraction of subtle defects for free.

### 2.9 P9 — Optimize cost per unit of *useful* output, and define "useful" as merged-and-stays-merged

Throughput is not "lines generated" or "requests spent." It is **merged commits that are not reverted within two weeks.** A worker that generates 2,000 lines you throw away has negative throughput (it consumed your review attention). Every metric in §10 ties back to this definition.

### 2.10 P10 — Determinism where you can, intelligence where you must

Anything expressible as a script (formatting, lint, test execution, dispatch, report templating, threshold checks) must be a script, not a model call. Models are for irreducible judgment. This keeps cost down, removes a class of non-determinism, and makes the system auditable.

### 2.11 P11 — Design for graceful degradation and reversibility

Assume any model call can fail, hallucinate, or change behavior on a version bump. Every merge must be revertable in one command (§9.5). Every worker run must be reproducible from its spec. The human must be able to take over any step manually. The system never reaches a state where only one specific model version can keep it running.

---

## 3. System Architecture

### 3.1 The components

| Component | Identity (2026) | Role in one line |
|---|---|---|
| **Human Operator** | You | Product/business direction, final authority on irreversible calls, taste. |
| **Lead** | Claude Opus 4.8 (via Claude Pro) | The CTO brain: plans, designs contracts, runs the review gate, breaks hard bugs. Scarce. |
| **Implementer** | GLM-5.1 (primary) / Qwen3.7 (secondary) — OpenCode Go | Writes code to spec on a branch. High volume. |
| **Verifier / QA** | DeepSeek V4 Pro or Kimi K2.6 — OpenCode Go | Writes & runs tests, adversarial review, bug repro. *Different family from implementer.* |
| **Researcher** | Qwen3.7 Max (1M ctx) / DeepSeek V4 Pro — OpenCode Go | Library evals, doc spikes, decision memos for the Lead. |
| **Scribe** | MiMo-V2.5-Pro (mechanical) · Qwen3.7 Plus (weekly synthesis) — OpenCode Go | Changelogs, docstrings, template fill (MiMo). The weekly-summary rollup is tiered up to Qwen3.7 Plus + an Opus sign-off. *Formats* — never authors — judgment reports. |
| **Local model (optional)** | Qwen3-Coder-Next or GLM-5 (quantized, via Ollama/llama.cpp) | Offline fallback, secret-sensitive snippets, instant autocomplete, $0. See §3.4. |
| **Git** | Trunk + short-lived task branches | The coordination bus and the rollback mechanism. |
| **Task Queue** | `/tasks/active/*.md` | Specs awaiting/under execution. |
| **Review Pipeline** | `/reviews/queue/*` + CI gates | Where diffs are graded before merge. |
| **Report Ledger** | `/reports/**` (append-only) | Durable memory of outcomes; feeds weekly review & learning loop. |

### 3.2 The architecture diagram (information flow)

```
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                              HUMAN OPERATOR (you)                              │
 │   product direction • business goals • final call on irreversible decisions    │
 └───────────────┬──────────────────────────────────────────────▲────────────────┘
                 │ intent, priorities, approvals                 │ status, escalations
                 ▼                                               │
 ┌──────────────────────────────────────────────────────────────┴────────────────┐
 │                        LEAD  —  CLAUDE OPUS 4.8  (scarce)                       │
 │   reads COMPRESSED repo view (not whole tree):                                 │
 │     • /architecture (ADRs + contracts)   • /reports ledger (last cycle)         │
 │   PRODUCES:                                                                     │
 │     ┌─ sprint plan ──┐  ┌─ task specs + acceptance criteria ─┐  ┌─ contracts ─┐ │
 │     │ priorities,    │  │ self-contained, 1 branch each      │  │ interfaces, │ │
 │     │ risk ranking   │  │ authority limits, stop conditions  │  │ schemas,ADR │ │
 │     └──────┬─────────┘  └──────────────┬─────────────────────┘  └──────┬──────┘ │
 │   ALSO: review GATE (batch, threshold-gated) • stuck-bug breaker • integration  │
 └────────────────────────┬───────────────────────────────────┬────▲──────┬───────┘
                          │ writes specs                      │    │ gate │ writes
                          ▼                                   │    │      ▼ ADRs
                 ┌──────────────────┐                         │    │  ┌─────────────┐
                 │   TASK QUEUE     │  /tasks/active/*.md      │    │  │/architecture│
                 │  (specs on disk) │                         │    │  │  ADRs +     │
                 └────────┬─────────┘                         │    │  │  contracts  │
        dispatch (1 spec → 1 branch; P2/P3)                   │    │  └─────────────┘
                          ▼                                   │    │
 ┌───────────────────────────────────────────────────────┐   │    │
 │              OPEN-WEIGHT WORKFORCE (OpenCode Go)        │   │    │
 │                                                        │   │    │
 │   ┌────────────────┐        ┌──────────────────────┐   │   │    │
 │   │  IMPLEMENTER   │  code  │   VERIFIER / QA       │   │   │    │
 │   │  GLM-5.1       │───────▶│  DeepSeek V4 / Kimi   │   │   │    │
 │   │  (writes to    │  diff  │  (tests, adversarial  │   │   │    │
 │   │   spec)        │◀───────│   review) — DIFFERENT │   │   │    │
 │   └───────┬────────┘ fix req│   FAMILY (P8)         │   │   │    │
 │           │                 └──────────┬───────────┘   │   │    │
 │   ┌───────┴───────┐    ┌───────────────┴──────────┐    │   │    │
 │   │  RESEARCHER   │    │        SCRIBE            │    │   │    │
 │   │ Qwen3.7 Max   │    │  MiMo / MiniMax          │    │   │    │
 │   │ (memos→Lead)  │    │  (reports, docstrings)   │    │   │    │
 │   └───────────────┘    └──────────────────────────┘    │   │    │
 └───────────────┬────────────────────────────────────────┘   │    │
                 │ each worker on its own branch  task/<id>-x  │    │
                 ▼                                             │    │
 ┌───────────────────────────────────────────────────────┐    │    │
 │                     GIT (coordination bus)             │    │    │
 │   trunk (main) ──●──●──●──────────────────●──●──▶      │    │    │
 │                   \        task branches  /            │    │    │
 │      task/12-auth  ●──●──●─(rebase)──────●  (merge ▲ gate)   │    │
 │      task/13-cache ●──●──●───────────────●            │    │    │
 └───────────────┬───────────────────────────────────────┘    │    │
                 │ branch + passing CI + QA report             │    │
                 ▼                                             │    │
 ┌───────────────────────────────────────────────────────┐    │    │
 │                 REVIEW PIPELINE                        │    │    │
 │   CI gate (lint,type,test,coverage,secret-scan) ──┐   │    │    │
 │                                                    ▼   │    │    │
 │   risk router:  diff crosses threshold?  ──YES──▶ Opus GATE ─┘    │
 │                                          ──NO───▶ auto-approve     │
 │                                              (tests+peer suffice)  │
 └───────────────┬───────────────────────────────────────┘         │
                 │ approved → merge to trunk → tag                  │
                 ▼                                                  │
 ┌───────────────────────────────────────────────────────┐         │
 │            REPORT LEDGER  /reports/** (append-only)     │────────┘
 │   task-completion • bug-investigation • arch-review     │  feeds next
 │   • research-summary • weekly-summary   (Scribe writes) │  Opus cycle
 └───────────────────────────────────────────────────────┘  (closes loop)
```

### 3.3 Reading the flow

The loop is **plan → spec → execute → verify-cheap → gate (threshold) → merge → report → (report feeds next plan)**. Two arrows matter most. First, the **compression arrow** into the Lead: Opus never reads the whole repo; it reads `/architecture` + the report ledger, which is what keeps each planning call inside the Pro budget and inside the model's effective attention (P4). Second, the **risk-router fork** before the Opus gate: most diffs go `NO → auto-approve` on the strength of CI + a different-family QA pass (P7, P8); only threshold-crossing diffs spend scarce Opus review. Those two arrows are where the "decision-value per dollar" principle physically lives in the architecture.

### 3.4 On local models — when they earn their place

Run a local model only if it pays for one of three specific jobs; otherwise OpenCode Go already dominates it on quality:

1. **Secret-sensitive work** — code or logs you will not send to any hosted provider (credentials, proprietary algorithms, regulated data). A quantized Qwen3-Coder-Next or GLM-5 on Ollama keeps it on your machine.
2. **Latency-critical autocomplete** — sub-200ms inline completion where a round-trip to a hosted model is too slow.
3. **Offline / outage continuity (P11)** — when your network or OpenCode is down, a local 14–32B coder keeps you moving at reduced quality.

Do **not** use a local model as a primary implementer if you have OpenCode Go — a 7900XTX-class GPU running a quantized 32B is strictly worse than GLM-5.1 at a marginal cost difference of pennies. Local is a *resilience and privacy* tool, not a *throughput* tool.

---

## 4. Model Selection Strategy

### 4.1 The ranking (open-weight workforce, OpenCode Go catalog, June 2026)

Ranked by *fitness for this system* — long-horizon agentic coding, tool reliability, and cost-per-useful-output — not by raw leaderboard score.

| Rank | Model | Best role here | Strengths | Weaknesses | Why it's in the system |
|---|---|---|---|---|---|
| **1** | **GLM-5.1** (Zhipu) | **Primary Implementer** | Best all-around long-horizon agentic engineering; sustained multi-step tool use; stays on-task across a full feature. | Can over-engineer; slightly slower per step; occasionally gold-plates beyond spec. | It is the most reliable "give it a good spec and walk away" worker in the catalog. Default code producer. |
| **2** | **Qwen3.7 Plus / Max** (Alibaba) | **Researcher** + secondary Implementer | Best efficiency per active parameter; 1M context; very reliable tool calls; fast. | Slightly less rigorous on deep multi-hop bugs than DeepSeek/Kimi. | 1M context makes it the doc/codebase-spike engine; cheap enough to be the everyday second implementer. |
| **3** | **Kimi K2.6 (Thinking)** (Moonshot) | **Autonomous-Run engine + co-primary Verifier/QA** | Tops the 2026 open-weight **coding (78.6)** and **agentic-coding (58.3)** leaderboards — the highest agentic-coding score in the workforce; the strongest long-horizon autonomous runner; ruthless adversarial QA. | Thinking tokens get expensive; occasionally overconfident — needs tight stop conditions. | First-class workhorse, used two ways: (a) the **Autonomous Worker** for big, well-bounded jobs (migrations, test backfills, the Phase-3 loop); (b) rotates with DeepSeek as the different-family **Verifier** (P8). Never both on the same task. |
| **4** | **DeepSeek V4 Pro** | **Co-primary Verifier/QA + algorithm-heavy tasks** | Leads LiveCodeBench & 1M-context tasks; ruthless at edge cases and *breaking* code. | Verbose; spends a lot of thinking tokens; can be slow under load. | Different family from both GLM and Kimi (satisfies P8); the sharpest bug-repro/grader. Rotates with Kimi K2.6 on QA so no model ever grades its own family's output. |
| **5** | **MiniMax M3** | **Multimodal / huge-context specialist** | First open-weight to combine frontier coding + 1M context + native multimodality; tops open-weight SWE-Bench Pro (59.0). | Newest, least battle-tested; behavior less predictable across versions. | The only catalog model that reads screenshots/UI mocks — use it for frontend-from-design and for tasks needing both vision and code. |
| **6** | **MiMo-V2.5-Pro (Xiaomi) / MiniMax M2.7** | **Scribe — mechanical (docs/boilerplate)** | Cheap, fast, perfectly adequate for mechanical generation. | Weaker reasoning; do not trust with architecture, synthesis, or tricky logic. | Does the high-volume low-stakes *typing* (docstrings, changelogs, template fill) so you never waste a stronger model on it. The one synthesis report — the **weekly rollup** — tiers up to **Qwen3.7 Plus** + Opus sign-off; judgment reports (bug/research/ADR/arch) are authored by their owning role, not here. |

### 4.2 The premium tier (the Lead)

| Model | Role | Strengths | Weaknesses | Use cases |
|---|---|---|---|---|
| **Claude Opus 4.8** (Claude Pro) | **Lead / Architect / Review-Gate / Debugger-of-last-resort / Integrator** | Best available judgment on ambiguous, high-blast-radius decisions; strongest at holding a whole system in mind and at catching the subtle, expensive mistake; excellent code review and root-cause reasoning. | Scarce (Pro: ~45 msg / 5h + weekly cap); higher latency; the one resource you can actually run out of. | Sprint planning, contract/schema/interface design, dependency adoption calls, the review *gate* on high-risk diffs, bugs the workers got stuck on, integration decisions. See §12 for rationing. |

### 4.3 Model-to-role default map (pin this)

```
DECISION / DESIGN / REVIEW-GATE ........ Claude Opus 4.8        (Lead)
IMPLEMENT (default) ..................... GLM-5.1               (Implementer)
IMPLEMENT (agentic / long bounded) ..... Kimi K2.6 Thinking    (Autonomous Worker)
IMPLEMENT (parallel / cheap) ........... Qwen3.7 Plus          (Implementer-2)
TEST + ADVERSARIAL QA (rotate, P8) ..... Kimi K2.6 ↔ DeepSeek V4 Pro (Verifier) ← never the author's family
LONG AUTONOMOUS / BIG MIGRATION ........ Kimi K2.6 Thinking    (Autonomous Worker)
RESEARCH / DOC-SPIKE / 1M CONTEXT ...... Qwen3.7 Max           (Researcher)
FRONTEND-FROM-DESIGN / MULTIMODAL ...... MiniMax M3            (Worker)
DOCS / CHANGELOG / TEMPLATE FILL ........ MiMo-V2.5-Pro        (Scribe — mechanical)
WEEKLY-SUMMARY SYNTHESIS ............... Qwen3.7 Plus         (Scribe — synthesis; Opus signs off)
SECRET / OFFLINE FALLBACK .............. local Qwen3-Coder-Next (Resilience)
```

### 4.4 Selection rules (the non-obvious ones)

- **Pin model versions per role in `AGENTS.md`.** "Latest" is not a version. When a role's model bumps (e.g., GLM-5.1 → 5.2), treat it as a *change* — run the regression suite, note it in an ADR. Silent model swaps are a documented failure mode (§14).
- **Match model to the task's *difficulty class*, not its prestige.** A CRUD endpoint goes to the cheapest model that passes its tests (often Qwen3.7 Plus or even MiMo), not to GLM-5.1. Save the strong workers for genuinely hard implementation.
- **Two models, never one, on anything that ships.** Implementer + different-family Verifier is the floor (P8). The cost is trivial; the defect-catch rate is high.
- **Kimi K2.6 is first-class but family-bound (P8).** It is your autonomous-run engine *and* a co-primary Verifier — but never both on the same task. The rule `dispatch.sh` enforces: the Verifier's family ≠ the author's family. So Kimi authors → DeepSeek grades; GLM/Qwen authors → Kimi *or* DeepSeek grades. One model, two hats, never on the same diff.
- **Reach for 1M context deliberately, not by default (P4).** Use Qwen3.7 Max / DeepSeek's long context for *research over a large surface* (read these 30 files and produce a memo), then hand the *memo* — not the 30 files — to the implementer.

---

## 5. Agent Design

### 5.1 First, a correction to the premise (challenging a weak assumption)

The brief asks for six permanent agents (Architect, Backend, Frontend, QA, Research, DevOps). **In a solo, scarce-Opus system, six always-on agents is the wrong mental model and will hurt you.** "Backend Engineer" and "Frontend Engineer" are not different *agents* — they are the *same open-weight worker pool* pointed at different parts of the codebase with different specs. Treating them as separate standing daemons multiplies coordination overhead (P3) for zero gain.

So the roles below are defined as **hats (modes of operation)**, not as concurrently-running processes. At any moment, *zero or one* instance of each hat is active, instantiated on demand by handing the right prompt + model + task spec to OpenCode. The Lead is one brain wearing the Architect/Reviewer/Debugger/Integrator hats in sequence. This is the literal expression of "prefer intelligence over agent count" (P2). Where the brief says "Backend Engineer," read "Implementer hat, pointed at the backend."

### 5.2 Role: Lead (Architect / Reviewer / Debugger / Integrator) — Claude Opus 4.8

| Facet | Definition |
|---|---|
| **Responsibilities** | Decompose intent into a sprint of self-contained task specs with acceptance criteria. Own all cross-module interfaces, schemas, and ADRs. Run the review *gate* on high-risk diffs. Break bugs workers are stuck on. Make integration & dependency-adoption decisions. |
| **Authority limits** | May NOT write production feature code in bulk (that's the Implementer's job — Opus time is too scarce to spend typing CRUD). May NOT merge without the human's standing policy being satisfied. May NOT spend more than its per-cycle Opus budget (§12.4) — when budget is low, it defers low-risk reviews to auto-approve. Cannot make product/business/irreversible-spend decisions — those escalate to the human. |
| **Required inputs** | Compressed repo view: `/architecture` (ADRs + contracts), the last cycle's report ledger, the human's priorities, and (for the gate) the specific diff + its QA report. |
| **Expected outputs** | (a) `sprint-plan.md`; (b) N task specs in `/tasks/active/`; (c) new/updated contracts & ADRs in `/architecture/`; (d) review verdicts in `/reviews/`; (e) escalation notes to the human. |
| **Success metrics** | % of its task specs that pass QA *first try* (spec quality proxy, target >70%); zero high-severity defects reaching trunk; planning fits inside Opus budget; architecture coherence holds (no contradicting ADRs). |
| **Failure conditions** | Specs so vague workers thrash (SpecGap not closed). Reviewing low-risk diffs and exhausting budget before the risky ones. Letting a contract change slip through as a "small" worker edit. Writing code instead of specs. |

### 5.3 Role: Implementer & Autonomous Worker (a.k.a. Backend/Frontend Engineer) — GLM-5.1 · Kimi K2.6 · Qwen3.7

| Facet | Definition |
|---|---|
| **Responsibilities** | Take exactly one task spec, implement it on its own branch until acceptance criteria pass, produce a task-completion report. |
| **Authority limits** | May only touch the file set named in the spec. May NOT create or change a cross-module interface/contract — if the task seems to require it, STOP and emit an escalation (the spec was under-specified → back to Lead). May NOT add a new third-party dependency without it being pre-approved in the spec. May NOT merge. |
| **Required inputs** | One self-contained task spec + the specific contracts it implements + repo conventions from `AGENTS.md`. Nothing else. |
| **Expected outputs** | A branch `task/<id>-slug` with commits; passing local gates; a completion report (§10.1); a list of any spec ambiguities encountered. |
| **Success metrics** | First-pass QA acceptance rate; diff stays within declared file set; zero scope creep; merged-and-stays-merged (P9). |
| **Failure conditions** | Editing files outside scope; inventing an interface; gold-plating beyond spec; "passing" tests by weakening them; hallucinating a library API. |

**Autonomous-Worker variant — Kimi K2.6 Thinking.** For large, *well-bounded* jobs (a framework migration, a test backfill, a mechanical refactor spanning many files), instantiate the Implementer hat on **Kimi K2.6 Thinking** — the catalog's strongest long-horizon autonomous runner (highest 2026 agentic-coding score). The same authority limits apply, with two tightened for unsupervised operation: (a) it appends a progress note to the task's Working Notes every N steps so the run stays interruptible and auditable; (b) its stop conditions are stricter — any contract ambiguity halts it immediately, because a long autonomous run amplifies a wrong assumption into a large diff. Its output is still graded by a **different-family** Verifier (DeepSeek V4 Pro, never Kimi — P8).

### 5.4 Role: Verifier / QA — Kimi K2.6 ↔ DeepSeek V4 Pro (co-primary, rotated; always a different family from the author, P8)

| Facet | Definition |
|---|---|
| **Responsibilities** | Write/extend tests to the acceptance criteria, run them, attempt to *break* the implementation (adversarial cases, edge conditions), reproduce reported bugs, and emit a QA verdict that the risk-router and Opus gate consume. |
| **Authority limits** | May NOT modify the implementation to make tests pass (that's the Implementer's job — separation of powers). May NOT weaken acceptance criteria. May NOT approve for merge (only the gate/Lead approves) — it produces evidence, not verdicts on merge. |
| **Required inputs** | The branch diff, the task spec's acceptance criteria, the relevant contracts. |
| **Expected outputs** | A test suite delta, a pass/fail matrix, a list of discovered defects with repro steps, a risk rating (low/med/high) that drives the router. |
| **Success metrics** | Defects caught *before* the Opus gate / before trunk; low escaped-defect rate (bugs found post-merge that QA should have caught); test additions actually exercise the new code (coverage of the diff, not global coverage). |
| **Failure conditions** | Rubber-stamping the implementer's own model's mistakes (mitigated by family diversity); writing tests that assert current buggy behavior; missing the obvious edge case. |

**Rotation rule (who grades what).** Kimi K2.6 and DeepSeek V4 Pro are *co-primary* verifiers; the dispatcher picks whichever is **not** the author's family. GLM-/Qwen-authored diffs → graded by Kimi **or** DeepSeek; Kimi-authored diffs → graded by DeepSeek. This preserves P8 while letting Kimi serve as both a builder (on some tasks) and a grader (on others) across the sprint — maximizing use of the catalog's top agentic coder without ever letting it certify its own output.

### 5.5 Role: Researcher — Qwen3.7 Max / DeepSeek V4 Pro

| Facet | Definition |
|---|---|
| **Responsibilities** | Answer bounded technical questions for the Lead: evaluate libraries, read large doc sets / large parts of the codebase, prototype throwaway spikes, produce a **decision memo** (options, trade-offs, recommendation, evidence). |
| **Authority limits** | Produces *recommendations*, never *decisions* — the Lead decides (research informs leverage points, it doesn't own them). Spikes are throwaway and live on a `spike/` branch that never merges. |
| **Required inputs** | A research question with explicit decision criteria and a deadline/token budget. |
| **Expected outputs** | A research-summary report (§10.4): options table, recommendation, risks, and the *minimum* context the Lead needs to decide — not a 30-file dump (P4). |
| **Success metrics** | Lead can make the decision from the memo alone; recommendation holds up; no rework from missed constraints. |
| **Failure conditions** | Returning raw data instead of a decision-ready memo; analysis paralysis; recommending the shiny option without weighing migration/maintenance cost. |

### 5.6 Role: Scribe — MiMo-V2.5-Pro (mechanical) · Qwen3.7 Plus (weekly synthesis)

| Facet | Definition |
|---|---|
| **Responsibilities** | Mechanical writing: docstrings, changelogs, README updates, filling report templates from git data, drafting ADRs from the Lead's bullet points. |
| **Authority limits** | No judgment calls. Never authors architecture or decisions — only transcribes/formats them. Its output is always reviewed by whoever owns the underlying decision. |
| **Required inputs** | The diff / the Lead's decision bullets / the report template + data. |
| **Expected outputs** | Filled templates, docstrings, changelog entries. |
| **Success metrics** | Accuracy to source; zero invented facts; saves the stronger models from doing clerical work. |
| **Failure conditions** | Inventing rationale that wasn't in the source; drifting from template; being trusted with anything requiring judgment. |

**Stakes-tiering (important — the Scribe never bounds Opus's decision quality).** The Scribe is a *typist*, tiered by report stakes so that no weak model is ever the sole author of anything Opus depends on: (a) **mechanical** output — docstrings, changelogs, README, filling a task-completion template from git data — runs on **MiMo-V2.5-Pro**; (b) the **weekly summary**, the one report that is a genuine rollup Opus reads to plan, is drafted by **Qwen3.7 Plus** and **signed off by Opus** in the weekly review (§8.5); (c) the **judgment-bearing reports** — bug-investigation, research-summary, ADRs, architecture-review — are *authored by the role that owns the judgment* (the debugging model, the Researcher, and Opus, respectively); the Scribe only formats them. Net effect: the strongest model is already in the loop for every report that matters — as author or sign-off — and is never spent typing the mechanical ones.

### 5.7 Role: DevOps — deterministic scripts + open-weight model (designed once by Lead)

| Facet | Definition |
|---|---|
| **Responsibilities** | CI/CD pipeline, pre-commit hooks, test runners, secret scanning, release tagging, the dispatch/queue runner, the report generators. **Most of this is code, not a model (P10).** |
| **Authority limits** | The *pipeline design* is a high-leverage decision → Lead/Opus designs it once and writes the ADR. Day-to-day, DevOps is scripts that run deterministically; an open model only touches it to write a new script or debug CI, under a spec. |
| **Required inputs** | The pipeline ADR; the failing CI log when debugging. |
| **Expected outputs** | Green CI; reproducible builds; one-command rollback; the automation that §13 progressively expands. |
| **Success metrics** | CI flakiness rate ~0; mean-time-to-rollback < 2 min; % of toil automated (trends up over months). |
| **Failure conditions** | Flaky tests that mask defects; non-reproducible builds; secrets reaching logs; a pipeline only the original model version understands. |

### 5.8 Separation of powers (the org chart in one rule)

> **The model that writes code cannot be the model that grades it, and neither can be the model that approves the merge.**

Implementer writes → Verifier (different family) grades → Lead/gate approves → DevOps scripts merge. This three-way separation is the entire governance model. It is cheap (all but the Lead are $10-tier) and it is what keeps a fully-automated future (§13.3) from quietly shipping garbage.

---

## 6. Context Engineering System

Context is the product you are really managing. Four memory tiers, each with a precise scope, location, lifetime, and *who writes it*. The golden rule (P4): **a consumer loads the smallest tier that suffices.** An implementer loads task memory + the one or two contracts it needs — never the whole project memory, never the report ledger.

### 6.1 The four memory tiers

```
┌─────────────────────────────────────────────────────────────────────────┐
│ TIER            SCOPE            LIFETIME      WRITER        LOADED BY     │
├─────────────────────────────────────────────────────────────────────────┤
│ AGENT MEMORY    a role's how-to  stable/months Human+Lead    every run of │
│ (role prompt)   identity,        (versioned)                 that role    │
│                 heuristics,                                                │
│                 model pin                                                  │
│                                                                           │
│ PROJECT MEMORY  the system's     evolves w/    Lead (Opus)   Lead always; │
│ (architecture)  truth: ADRs,     architecture                workers load  │
│                 contracts,                                    only the     │
│                 invariants,                                   slice they   │
│                 glossary                                      touch        │
│                                                                           │
│ TASK MEMORY     one unit of work transient     Lead writes,  the one      │
│ (task spec)     spec, criteria,  (1 sprint)    worker        worker doing  │
│                 working notes                  appends notes  that task    │
│                                                                           │
│ REPORT MEMORY   what happened    permanent,    Scribe/       Lead at plan  │
│ (ledger)        outcomes,        append-only   workers       time; weekly  │
│                 metrics, defects                             review        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Agent memory — *who the role is*

Stored as `/agents/<role>.md` (+ a shared `AGENTS.md` at repo root that OpenCode reads automatically, and `CLAUDE.md` that Opus reads). Contains, per role: the model pin (exact version), the role's responsibilities & authority limits (copied from §5), coding conventions it must follow, hard-won heuristics ("in this repo, never call the DB from a handler — go through the repository layer"), and its output contract. This is *stable* — you edit it deliberately, version it in git, and treat changes as policy changes. It is loaded on **every** invocation of that role so behavior is consistent across months and session resets.

### 6.3 Project memory — *what is true about the system*

Stored under `/architecture` and surfaced to the Lead via `CLAUDE.md`. Three sub-stores:

- **ADRs** (`/architecture/adr/NNNN-title.md`) — every non-trivial decision: context, options, decision, consequences, status. This is the single most valuable artifact for month-3-coherence. When Opus plans, it reads the ADR index to avoid re-litigating or contradicting past decisions (P5).
- **Contracts** (`/architecture/contracts/*`) — the interfaces, schemas, API specs, and event formats that modules agree on. Machine-checkable where possible (OpenAPI, JSON Schema, type stubs). Workers consume these; only the Lead changes them.
- **Invariants & glossary** (`/architecture/invariants.md`, `glossary.md`) — system-wide rules that must always hold ("all money is integer cents," "all timestamps are UTC ISO-8601") and the canonical vocabulary so models don't invent synonyms.

### 6.4 Task memory — *one unit of work*

Stored as `/tasks/active/<id>-slug.md`, the self-contained spec (schema in §6.6). It includes a **Working Notes** section the worker appends to as it goes (decisions made, ambiguities hit, dead ends). When the task completes, the whole file moves to `/tasks/completed/` and its outcome is summarized into the report ledger. Task memory is *transient context* — it exists to make the handoff to a stateless worker lossless (P6), then it's archived.

### 6.5 Report memory — *what happened*

Stored under `/reports/**`, **append-only** (never edit a past report; correct with a new entry). This is the system's long-term episodic memory and audit trail. It feeds two things: the Lead's next planning call (so planning is informed by last cycle's reality, closing the loop in §3.2), and the weekly performance review (§8.5). Because it's structured (§10) and durable, it is also your dataset for *learning* — e.g., noticing that one model family keeps failing a task class.

### 6.6 The task-spec schema (the most important file format in the system)

This is the payload that lets a $10 stateless model produce senior output. Every field exists to close SpecGap (P1) or bound authority (P6).

```markdown
---
id: 014
slug: rate-limit-login
owner_role: implementer
model: glm-5.1
verifier_model: deepseek-v4-pro
branch: task/014-rate-limit-login
blast_radius: low          # low|med|high  (high ⇒ Lead designed the contract)
files_allowed:             # hard authority boundary (P6)
  - src/api/auth/login.ts
  - src/api/auth/__tests__/login.test.ts
depends_on_contracts:
  - architecture/contracts/auth-api.openapi.yaml
deps_preapproved: []       # any new library must be listed here or task STOPS
---

# Goal
One sentence. What must be true when this is done.

# Context (compressed)
3–6 sentences. Only what's needed to do THIS task. Link contracts, don't inline the repo.

# Acceptance criteria  (executable where possible)
- [ ] POST /login returns 429 after 5 failed attempts in 60s from one IP
- [ ] Successful login resets the counter
- [ ] Unit tests in login.test.ts cover: under-limit, at-limit, over-limit, reset
- [ ] `npm test` and `npm run typecheck` pass; coverage of the diff ≥ 90%

# Out of scope  (prevents gold-plating)
- Do NOT add distributed/Redis rate limiting (separate ADR pending).

# Stop conditions  (when to escalate instead of guessing)
- If correct behavior requires changing auth-api contract → STOP, escalate to Lead.
- If a needed dependency isn't in deps_preapproved → STOP, escalate.

# Working notes  (worker appends)
```

---

## 7. Repository Structure

### 7.1 The tree

Two halves: the **operating-system scaffolding** (the directories the brief asked for, which run the AI org) and the **actual product** (`/src`, etc.). Keeping them in one repo means git is the single coordination bus (P3) and Opus can read system-state and code together.

```
repo-root/
├── AGENTS.md                  # OpenCode reads this: conventions, model pins, guardrails
├── CLAUDE.md                  # Opus reads this: architecture pointers, planning protocol
├── OPERATING_MANUAL.md        # this document
│
├── agents/                    # AGENT MEMORY — role definitions (who each role is)
│   ├── lead.md                #   Opus: planning + review + debug protocol
│   ├── implementer.md         #   GLM-5.1 conventions, authority limits, output contract
│   ├── verifier.md            #   DeepSeek/Kimi QA protocol (adversarial checklist)
│   ├── researcher.md          #   Qwen3.7 memo format + decision-criteria discipline
│   ├── scribe.md              #   MiMo templating rules
│   └── devops.md              #   pipeline ownership + script conventions
│
├── tasks/                     # TASK MEMORY — the work queue
│   ├── backlog/               #   specs not yet scheduled
│   ├── active/                #   specs being executed (1 per branch)
│   └── completed/             #   archived specs (audit trail)
│
├── reports/                   # REPORT MEMORY — append-only ledger
│   ├── daily/   YYYY-MM-DD.md
│   ├── weekly/  YYYY-Www.md
│   ├── tasks/   <id>-completion.md
│   ├── bugs/    <id>-investigation.md
│   └── metrics/ ledger.csv     # machine-readable telemetry — gitignored, local (see §7.2)
│
├── architecture/              # PROJECT MEMORY — the system's truth (Lead-owned)
│   ├── README.md              #   the architecture map / module index (Opus entrypoint)
│   ├── adr/      NNNN-*.md     #   Architecture Decision Records
│   ├── contracts/             #   interfaces/schemas (OpenAPI, JSON Schema, type stubs)
│   ├── invariants.md          #   system-wide rules that must always hold
│   └── glossary.md            #   canonical vocabulary
│
├── docs/                      # human- and user-facing documentation (Scribe-maintained)
│   ├── setup.md  usage.md  api.md  runbooks/
│
├── prompts/                   # PROMPT LIBRARY — versioned, reusable (§11)
│   ├── task-execution.md   code-review.md   bug-investigation.md
│   ├── research.md   architecture-analysis.md   doc-generation.md
│
├── reviews/                   # REVIEW PIPELINE state
│   ├── queue/                 #   diffs awaiting the gate (risk-router output)
│   ├── verdicts/   <id>.md    #   Lead/gate decisions + QA reports
│   └── checklist.md           #   the standing review checklist (§9.4)
│
├── knowledge/                 # durable cross-cutting know-how (not decisions)
│   ├── patterns/              #   reusable solutions discovered in this repo
│   ├── postmortems/           #   what broke + lesson (feeds failure-mode vigilance §14)
│   └── external/              #   distilled research keepers (library gotchas, etc.)
│
├── scripts/                   # DETERMINISM layer (P10): dispatch, gates, report-gen
│   ├── dispatch.sh   gate.sh   new-task.sh   rollback.sh   ledger-append.sh
│
├── .github/workflows/  (or .gitea/, etc.)  # CI: lint, type, test, coverage, secret-scan
│
└── src/  tests/  …            # THE ACTUAL PRODUCT
```

### 7.2 Purpose of every top-level folder

- **`/agents`** — *Agent memory.* Stable role identities loaded on every invocation; the "job descriptions" that make stateless workers behave consistently for months (§6.2).
- **`/tasks`** — *Task memory + the queue.* The unit-of-work specs flow `backlog → active → completed`. The dispatcher reads `active/`; the audit trail accumulates in `completed/` (§6.4).
- **`/reports`** — *Report memory.* The committed, durable memory is the daily/weekly/task/bug reports — the Scribe writes them deliberately and they are version-controlled and append-only. The live `metrics/ledger.csv` is the exception: it is **local operational telemetry** that scripts append to continuously, so it is *gitignored* (to avoid cross-branch churn) and its durable summary is rolled into the committed weekly report. Everything here feeds planning and the weekly performance review (§6.5, §10).
- **`/architecture`** — *Project memory.* The Lead-owned source of truth: ADRs, contracts, invariants, glossary. The thing that preserves coherence (P5). Opus's planning entrypoint.
- **`/docs`** — Human/user-facing documentation, kept current by the Scribe. Distinct from `/architecture` (decisions/contracts) — `/docs` is "how to use it," `/architecture` is "why it's built this way."
- **`/prompts`** — Versioned prompt library (§11). Prompts are *code*; they live in git, get reviewed, and improve over time.
- **`/reviews`** — Review-pipeline working state: the queue the risk-router fills, the verdicts the gate emits, and the standing checklist. Your "PR review" substrate without a second human.
- **`/knowledge`** — Durable, cross-cutting know-how that isn't a *decision* (those are ADRs) and isn't a *task*: reusable patterns, postmortems, distilled external research. The system's hard-won wisdom.
- **`/scripts`** — The determinism layer (P10). Everything mechanical lives here so models never do clerical/dispatch work and the system is auditable.
- **`/src`, `/tests`** — The product itself. Everything above exists to produce and protect what's in here.

### 7.3 Why one repo, not many

A solo operator with a multi-repo, multi-agent setup spends their scarce attention on cross-repo coordination — the exact overhead P3 forbids. One repo means: one `git log` is the full history of *both* the product and the decisions that shaped it; Opus can correlate a regression with the ADR that caused it; rollback is one command in one place. Split to multiple repos only when a component has a genuinely independent release cadence and consumer — and write the ADR justifying it.

---

## 8. Branching Strategy & Operating Cycles

### 8.1 Branching model: trunk-based with short-lived task branches

```
main (trunk)  ──●─────●─────●─────────────●─────●─────●──▶   always releasable
                 \           \           /       \     /
   task/014-...   ●──●──●──(rebase)──●──/(gate)    \   /
   task/015-...               ●──●──●──────────────●─/(gate)
                              ^                     ^
                         1 spec = 1 branch     merge only after
                         worker owns it        QA + gate pass
```

- **One task spec → one branch → one merge.** Branch name `task/<id>-slug`. Lifetime measured in hours, not days — small specs keep merges trivial and rollbacks surgical (P11).
- **Integration policy: rebase, then `--no-ff` merge.** The worker rebases its branch onto current trunk (linear, readable feature history); the gate then integrates it with a single **`--no-ff`** merge, so every task lands as exactly one *merge commit*. That merge commit is precisely what makes rollback one command — `git revert -m 1` (§9.5) reverts it and removes exactly one feature, cleanly. Pure fast-forward is deliberately **avoided**: it leaves no merge commit to revert, which would break the rollback guarantee (P11). `scripts/gate.sh` implements exactly this (rebase → `merge --no-ff` → tag).
- **`spike/<topic>`** branches for research throwaways — never merged, deleted after the memo lands.
- **Trunk is always releasable.** Nothing merges unless CI is green and the gate approved.

### 8.2 Branch ownership

| Branch | Owner | May write | May merge |
|---|---|---|---|
| `main` (trunk) | The Lead (gate) + DevOps scripts | nobody directly — only via approved merges | only `scripts/gate.sh` after gate verdict |
| `task/<id>-*` | the assigned Implementer (one worker) | only files in `files_allowed` | never self-merges |
| `spike/<topic>` | the Researcher | throwaway code | never (deleted after memo) |
| `fix/<id>-*` | the Lead (for stuck-bug breaks) | the failing area | via gate, like any task |

The rule that prevents the brief's #2 failure mode ("multiple agents editing the same files"): **a file may be in the `files_allowed` of at most one *active* branch at a time.** `scripts/dispatch.sh` enforces this — it refuses to dispatch a task whose `files_allowed` intersects any active branch's. This makes parallel work *structurally* conflict-free instead of hoping models cooperate (P3).

### 8.3 Conflict resolution

Because file ownership is partitioned, *content* conflicts are rare; the conflicts you do get are **semantic** (two branches both rely on an interface that changed). Protocol:

1. **Mechanical conflicts** (same file touched despite partitioning, e.g., a shared lockfile): the worker `git rebase`s its branch onto current trunk before requesting the gate — rebase the *branch onto trunk* (never merge trunk *into* the branch) to keep the feature history linear. Final integration into trunk is still the single `--no-ff` merge from §8.1, which is what keeps rollback one command.
2. **Semantic conflicts** (contract drift): these are high-leverage by definition (a contract moved) → **escalate to the Lead**. The Lead adjudicates by updating the contract + ADR, then re-issues affected specs. Workers never resolve a semantic conflict themselves — they'd guess, and a guess about an interface is exactly the expensive mistake the system exists to prevent.
3. **Tie-break rule:** trunk always wins; the branch rebases onto it. Never rewrite trunk to accommodate a branch.

### 8.4 Daily Operating Cycle

The day is built around the **Opus budget**: Pro allows ≈45 Opus messages per rolling 5-hour window plus a weekly ceiling. The cycle below spends only **~16–26 messages across the whole day** (morning planning + evening gate), comfortably inside a single window and leaving headroom for emergent debugging. Opus is spent only at the two leverage points — **morning planning** and **evening review gate** — while the cheap workforce runs essentially unbounded (Go is flat-rate) in between. Times are a template; shift them to your chronotype, keep the *shape*.

```
 TIME      PHASE            WHO            OPUS COST     WHAT HAPPENS
 ─────────────────────────────────────────────────────────────────────────────
 09:00     PLAN             Opus (Lead)    ~6–10 msgs    read compressed repo view +
 (30–45m)  "the keystone"                  (the single   yesterday's ledger → rank risks
                                            highest-      → emit 3–6 task specs w/ accept-
                                            leverage      ance criteria + any contract/ADR
                                            spend of      updates. ONE good planning pass
                                            the day)      sets up the whole day.
 ─────────────────────────────────────────────────────────────────────────────
 09:45     DISPATCH         scripts        0             dispatch.sh creates branches,
                            (DevOps)                      checks file-set disjointness,
                                                          hands each spec to a worker.
 ─────────────────────────────────────────────────────────────────────────────
 10:00–    EXECUTE          Implementers   0             workers implement to spec on
 13:00     (parallel,       (GLM-5.1,                    their branches; OpenCode Go,
           cheap, high      Qwen3.7)                     ~unbounded. Human does product
           volume)                                       work / answers worker escalations.
 ─────────────────────────────────────────────────────────────────────────────
 11:00     VERIFY           Verifier       0             as each branch finishes, a
 (rolling) (different       (DeepSeek/                   DIFFERENT-family model writes/runs
           family, P8)      Kimi)                        tests + adversarial review → QA
                                                         report + risk rating → reviews/queue
 ─────────────────────────────────────────────────────────────────────────────
 13:00     MIDDAY           Human +        0–2 msgs      glance at the queue + any worker
 CHECK     "unblock"        maybe Opus     (only if a    escalations. If a worker hit a
 (15m)                                     stop-cond     stop condition (contract gap), Opus
                                           fired)        patches the spec/contract. Otherwise
                                                         Opus spends NOTHING here.
 ─────────────────────────────────────────────────────────────────────────────
 13:15–    EXECUTE 2        Implementers   0             second batch / continued work;
 16:30                      + Verifier                   verification continues rolling.
 ─────────────────────────────────────────────────────────────────────────────
 16:30     REVIEW GATE      Opus (Lead)    ~8–14 msgs    BATCH review of the queue. Risk-
 (45–60m)  "the filter"     via risk                     router already split it: low-risk
                            router                       diffs (passing CI + clean QA) get
                                                         auto-approved; Opus spends its
                                                         attention ONLY on threshold-crossing
                                                         diffs. Emits verdicts → merges.
 ─────────────────────────────────────────────────────────────────────────────
 17:30     CLOSE            Scribe         0             scribe writes daily report from git
 (10m)                     (MiMo) +                      + ledger; metrics appended to
                           scripts                       ledger.csv; tomorrow's backlog
                                                         surfaced. Human reviews 1-page summary.
 ─────────────────────────────────────────────────────────────────────────────
 TOTAL OPUS/DAY: ~16–26 messages  → inside the Pro window, ~15 msgs reserve for emergent debugging.
```

The discipline this enforces: **Opus touches the day exactly twice on purpose** (plan, gate) and once on demand (a stuck bug). Everything else is $10-tier or free scripting. If you find Opus creeping into the 10:00–16:30 execution block for ordinary coding, that's budget leaking toward low-leverage work — stop and re-spec instead.

### 8.5 Weekly Operating Cycle

One day a week (suggest Friday, or your sprint boundary) runs a different shape: zoom out from tasks to the *system*. This is where coherence is maintained and debt is paid down — the work that prevents month-3 architectural collapse.

| Block | Activity | Driver | Opus role | Output |
|---|---|---|---|---|
| **1. Sprint review & planning** | What merged-and-stayed-merged vs. what got reverted? Set next week's themes & priorities. | Human + Lead | Reads the week's ledger; proposes the next sprint's leverage points & a rough task slate. | Weekly summary **drafted by Qwen3.7 Plus, signed off by the Lead** → `reports/weekly/YYYY-Www.md`; seeded `tasks/backlog/`. |
| **2. Architecture review** | Audit ADRs vs. reality. Did any worker quietly violate a contract or invariant? Any ADR now stale? | Lead (Opus) | The keystone weekly Opus spend: reconcile the codebase against `/architecture`; write/retire ADRs. | Updated ADRs/contracts; a "drift report." |
| **3. Technical-debt review** | Inventory smells, TODOs, flaky tests, duplication; rank by (risk × spread). | Researcher inventories (cheap, 1M ctx) → Lead prioritizes | Opus only *prioritizes* the cheap inventory — it doesn't read everything itself (P4). | Ranked debt list → top 1–2 items become next-week tasks. |
| **4. Documentation review** | Are `/docs` and docstrings current with the week's merges? | Scribe drafts → Lead spot-checks | Minimal: spot-check accuracy of high-stakes docs only. | Updated `/docs`. |
| **5. Performance review (the meta-loop)** | Read `ledger.csv`: cost/task, first-pass QA rate, escaped defects, Opus-budget burn, per-model failure-by-task-class. Tune routing. | Human + Lead | Opus reads the *metrics*, not the raw work; recommends routing/model-pin changes. | Tuned `AGENTS.md` model pins + routing thresholds; a short retro. |

The performance review (block 5) is what makes the system *improve* rather than merely *run*. Concretely you are looking for signals like "MiMo failed 3/4 of its scribe tasks that involved tables — promote those to MiniMax M3" or "Opus budget hit zero on Wednesday because review threshold was too low — raise it." Tuning those two knobs (model-per-task-class and the escalation threshold) weekly is the single highest-ROI maintenance activity in the whole system.

---

## 9. Review Pipeline, Merge Approval & Rollback

### 9.1 The pipeline (cheap → expensive, stop as early as possible)

This is the physical implementation of P7 (verification asymmetry) and the "decision-value per dollar" thesis. A diff passes through escalating filters; it should be *resolved as cheaply as possible* and only reach Opus if cheaper filters can't certify it.

```
 worker branch ready
        │
        ▼
 ┌──────────────────┐  fail   ┌────────────────────────────┐
 │ 1. CI GATE       │────────▶│ back to Implementer (auto)  │
 │ lint, typecheck, │         │ with the failing log        │
 │ tests, coverage  │         └────────────────────────────┘
 │ of diff, secret  │
 │ scan  (scripts)  │  pass
 └────────┬─────────┘
          ▼
 ┌──────────────────┐  defects ┌───────────────────────────┐
 │ 2. QA (Verifier, │─────────▶│ back to Implementer with   │
 │ different family)│          │ repro steps (auto loop,    │
 │ adversarial +    │          │ max N rounds, then escalate)│
 │ risk rating      │          └───────────────────────────┘
 └────────┬─────────┘  clean + risk rating
          ▼
 ┌──────────────────────────────┐
 │ 3. RISK ROUTER  (scripts)    │
 │ crosses ANY threshold?       │
 │  • touches a contract/schema │     NO ──▶ AUTO-APPROVE ──┐
 │  • blast_radius: high        │            (CI+QA suffice)│
 │  • > X files / Y lines       │                           │
 │  • security-sensitive path   │     YES                   │
 │  • new dependency            │      │                    │
 └──────────────┬───────────────┘      ▼                    │
                                ┌───────────────┐           │
                                │ 4. OPUS GATE  │           │
                                │ (scarce) full │           │
                                │ review of the │           │
                                │ risky diff    │           │
                                └──────┬────────┘           │
                                 approve│ / request-changes  │
                                        ▼                    ▼
                                 ┌──────────────────────────────┐
                                 │ 5. MERGE (scripts/gate.sh)   │
                                 │ rebase → no-ff merge → tag   │
                                 │ → append ledger              │
                                 └──────────────────────────────┘
```

### 9.2 Merge approval (who may say "ship it")

- **Auto-approve** (no Opus): diff passed CI + clean QA from a different-family verifier + crossed **zero** risk thresholds. The *majority* of diffs land here. This is the entire point — routine, well-specified, test-verified work does not consume scarce judgment.
- **Opus gate**: any threshold crossed (contract/schema/security/new-dep/large diff/high blast radius). Opus issues `approve` or `request-changes` with specific, actionable items.
- **Human gate**: a small set of classes always require *your* sign-off regardless of model verdicts — production data migrations, anything touching auth/payments/secrets, public API changes, and irreversible spend. Encode these in `reviews/checklist.md` as "HUMAN-REQUIRED."

### 9.3 The review process (what the gate actually checks)

The Verifier checks *correctness against the spec*. The Opus gate checks the things tests can't: **does this fit the architecture, and is it the right shape?** Specifically — contract/invariant adherence (P5), whether the abstraction is right or will need ripping out, security/blast-radius, and whether the diff did *only* what the spec asked (no silent scope creep). Opus is reviewing for *leverage and coherence*, not for typos — those were caught at stage 1.

### 9.4 The standing review checklist (`reviews/checklist.md`)

```
AUTOMATED (stage 1–2, every diff, no human/Opus):
  [ ] lint + format clean
  [ ] typecheck passes
  [ ] all tests green; diff coverage ≥ 90%
  [ ] no secrets / keys in diff (gitleaks or equiv)
  [ ] diff touches only files in the spec's files_allowed
  [ ] no new dependency unless in deps_preapproved

OPUS GATE (stage 4, only if risk-routed):
  [ ] honors the relevant contract(s) & invariants; no contract changed implicitly
  [ ] abstraction is right-sized (won't need to be ripped out next sprint)
  [ ] no scope creep beyond the spec's Goal / respects "Out of scope"
  [ ] error handling + failure modes for THIS change are sane
  [ ] security: input validation, authz, no injection surface introduced
  [ ] reversible: can be reverted cleanly; no data-shape lock-in without an ADR

HUMAN-REQUIRED (always, regardless of model verdicts):
  [ ] production data migration
  [ ] auth / payments / secrets / PII path
  [ ] public API or contract breaking change
  [ ] irreversible spend or external-facing release
```

### 9.5 Rollback process (P11 — one command, always available)

Because every task lands as a small, gate-approved, **`--no-ff`** merge (exactly one merge commit) with a tag, rollback is mechanical and fast:

```bash
# scripts/rollback.sh <merge-tag>
git revert --no-edit -m 1 <merge-commit>     # invert the merge as a new commit
git tag rollback/<id>-$(date +%s)            # mark it for the ledger
scripts/ledger-append.sh rollback <id> "<reason>"   # record WHY (feeds weekly review)
# CI re-runs on trunk; if green, you're back to a known-good state in < 2 minutes.
```

Three rules make rollback reliable: (1) **revert, don't reset** — never rewrite trunk history; a revert is itself revertable. (2) **One merge = one logical change** — small task branches mean a rollback removes exactly one feature, not a tangle. (3) **Always record the reason in the ledger** — a rollback is data; it tells the weekly review which task class or model is producing fragile work. If you ever can't roll back in one command, that's a Sev-1 process defect, not a code bug — fix the process.

---

## 10. Reporting System

Reports are not bureaucracy — they are the system's **memory and its training signal** (§6.5). Two design rules: every report has a **machine-readable header** (so `ledger.csv` and the weekly review can aggregate without re-reading prose) and is **append-only**. Mechanical reports (task-completion, docstrings, changelogs) are filled by the Scribe on **MiMo** from git data and the workers' notes; the **weekly summary** is drafted by **Qwen3.7 Plus** and signed off by Opus (§8.5); and the judgment-bearing reports (bug, research, ADR, architecture-review) are *authored by their owning role* — the Scribe only formats them. A stronger model is never spent on mechanical report *typing*, but every report Opus plans on is authored or signed-off by a model that holds the relevant judgment.

### 10.1 Task-completion report (`reports/tasks/<id>-completion.md`)

```markdown
---
type: task-completion
id: 014
slug: rate-limit-login
model: glm-5.1
verifier: deepseek-v4-pro
branch: task/014-rate-limit-login
result: merged            # merged | reverted | abandoned
opus_gate: auto-approved  # auto-approved | gated-approved | gated-changes(N rounds)
first_pass_qa: true       # did QA pass on the worker's first submission?
qa_rounds: 1
diff: {files: 2, +lines: 84, -lines: 6}
cost_tokens: {impl: 41000, qa: 12000}
duration_min: 38
date: 2026-06-05
---

## What was built
One paragraph, factual, from the diff.

## Acceptance criteria — final state
- [x] 429 after 5 fails / 60s
- [x] counter reset on success
- [x] tests cover under/at/over/reset
- [x] typecheck + coverage ≥ 90%

## Deviations from spec
None. (Or: what changed and why — links to escalation/ADR.)

## Defects found in QA (and fixed)
- edge: counter didn't reset on password-reset flow → fixed in commit abc123.

## Follow-ups created
- task/019: add Redis-backed limiter (ADR-0021 pending).
```

### 10.2 Bug-investigation report (`reports/bugs/<id>-investigation.md`)

```markdown
---
type: bug-investigation
id: B-031
severity: high            # sev1|high|med|low
status: fixed             # open | root-caused | fixed | wont-fix
broke_in: task/009        # the merge that introduced it (from git bisect)
detected_by: prod-log     # prod | qa | user | monitor
escalated_to_opus: true   # did cheap debugging fail and need the Lead?
date: 2026-06-05
---

## Symptom
Observable behavior + how to reproduce (exact steps / failing test).

## Root cause
The actual mechanism, not the symptom. (Bisect result, the faulty assumption.)

## Why it escaped review
The gap in QA/gate that let it through. (THIS feeds checklist improvements.)

## Fix
What changed; link to fix/<id> branch + merge tag.

## Prevention
- regression test added: <path>
- checklist/invariant updated? <link or "no">
- postmortem if sev1: knowledge/postmortems/<id>.md
```

### 10.3 Architecture-review report (`reports/weekly/` section, or standalone for big reviews)

```markdown
---
type: architecture-review
period: 2026-W23
adrs_added: [0019, 0020]
adrs_retired: [0011]
drift_found: yes
date: 2026-06-05
---

## Contract/invariant adherence
Per contract: held / violated (where, by which merge).

## Drift report
Places where code and /architecture disagree, ranked by risk.
- e.g., src/billing bypasses the repository layer (violates invariant I-3) — risk: high.

## Decisions
- ADR-0019: adopt event-outbox pattern for billing (supersedes ADR-0011).

## Remediation tasks seeded
- task/041: route billing writes through repo layer (closes drift #1).
```

### 10.4 Research-summary report (`reports/` or `knowledge/external/`)

```markdown
---
type: research-summary
question: "Queue: Redis Streams vs. Postgres-based (pgmq) for our scale?"
researcher: qwen3.7-max
decision_owner: lead
recommendation: pgmq
confidence: med
date: 2026-06-05
---

## Decision criteria (given up front)
throughput needed, ops burden (solo!), cost, exactly-once semantics.

## Options
| Option | Throughput | Ops burden | Cost | Exactly-once | Notes |
|---|---|---|---|---|---|
| Redis Streams | high | +1 service | $ | manual | another thing to run |
| pgmq (Postgres) | sufficient | none (already run PG) | $0 | yes (txn) | fits solo ops |

## Recommendation + rationale
pgmq: removes a service for a solo operator; throughput headroom is 8x current peak.

## Risks / when to revisit
revisit if sustained throughput > 2k msg/s (then Redis Streams).

## Minimum context for the Lead to decide
(the table above + these 3 sentences — NOT the 14 pages I read)
```

### 10.5 Weekly-summary report (`reports/weekly/YYYY-Www.md`)

```markdown
---
type: weekly-summary
period: 2026-W23
merged: 17
reverted: 1
escaped_defects: 0
first_pass_qa_rate: 0.76
opus_msgs_spent: 118        # vs. budget
cost_usd: 30                # flat this month
date: 2026-06-05
---

## Shipped (merged & stayed merged)
- rate-limit on login, billing outbox, …

## Reverted / abandoned (and the lesson)
- task/012 reverted: MiMo mis-generated a migration → migrations now HUMAN-REQUIRED.

## Metrics vs. last week
| metric | this | last | Δ |
|---|---|---|---|
| first-pass QA rate | 0.76 | 0.71 | ↑ |
| escaped defects | 0 | 2 | ↓ |
| Opus msgs/merged-task | 6.9 | 8.4 | ↓ (good) |

## Routing/model tuning decisions
- promote table-heavy scribe tasks MiMo → MiniMax M3 (3 failures last week).
- raise risk-router line threshold 150 → 220 (Opus gate was over-triggering).

## Next week's leverage points
1. … 2. … 3. …
```

---

## 11. Prompt Library

Prompts are **versioned code** (`/prompts`, §7). Each has the same backbone: a role anchor, the *minimum* context, an explicit **output contract**, and **stop conditions** (when to escalate rather than guess — this is what makes cheap models safe). Variables in `{{double_braces}}`. These six are the load-bearing ones.

### 11.1 Task execution (Implementer) — `prompts/task-execution.md`

```
ROLE: You are the Implementer ({{model}}). You implement ONE task to spec. You do
not design interfaces; you consume them.

INPUTS:
- Task spec: {{task_spec}}        (authoritative; if it conflicts with anything, it wins)
- Contracts you implement: {{contracts}}
- Repo conventions: see AGENTS.md (already loaded)

DO:
1. Implement the Goal so every Acceptance Criterion passes.
2. Touch ONLY files in `files_allowed`. 
3. Commit in small logical steps with clear messages.
4. Append decisions/ambiguities to the spec's Working Notes as you go.

DO NOT:
- create or modify any cross-module interface/contract,
- add a dependency not in `deps_preapproved`,
- exceed the spec ("Out of scope" is binding); no gold-plating,
- weaken or delete acceptance tests to make them pass.

STOP CONDITIONS (emit `ESCALATE:` + reason, then halt — do NOT guess):
- the task can't be done without changing a contract,
- the spec is ambiguous on a behavior an acceptance criterion depends on,
- a required dependency isn't pre-approved.

OUTPUT CONTRACT:
- a working branch with passing local gates,
- a filled task-completion report (template 10.1),
- if you escalated: a precise statement of the missing decision.
```

### 11.2 Code review (Verifier + Opus gate) — `prompts/code-review.md`

```
ROLE: You are the Verifier ({{model}}, a DIFFERENT model family than the author).
Your job is to BREAK this code, not to praise it.

INPUTS: diff {{diff}}, spec {{task_spec}}, contracts {{contracts}}.

REVIEW IN THIS ORDER (cheapest-to-catch first):
1. Correctness vs. each acceptance criterion — write a failing test for any gap.
2. Adversarial inputs: empty, huge, malformed, concurrent, boundary, unicode, negative.
3. Contract/invariant adherence (cite the contract line).
4. Scope: did the diff do ONLY what the spec asked? Flag any creep.
5. Security: injection, authz, secret handling, unvalidated input.
6. Failure modes: what happens when each external call fails?

OUTPUT CONTRACT (this exact shape — the risk-router parses it):
  RISK: low|med|high
  BLOCKING: [ {file:line, issue, repro, suggested_fix}, ... ]   # empty ⇒ may auto-approve
  NON_BLOCKING: [ ... ]
  TESTS_ADDED: [paths]
  VERDICT: pass | fail
Do NOT modify the implementation. Produce evidence; the gate decides.

# OPUS-GATE ADDENDUM (only when risk-routed to the Lead):
Beyond the above, judge LEVERAGE: is the abstraction right-sized, does it fit the
architecture (ADRs), will it need ripping out next sprint, is it reversible?
Output: APPROVE | REQUEST-CHANGES + the specific, minimal changes required.
```

### 11.3 Bug investigation — `prompts/bug-investigation.md`

```
ROLE: You are debugging ({{model}}). Find the ROOT CAUSE before proposing any fix.
A fix without a root cause is rejected.

INPUTS: symptom {{symptom}}, repro {{repro}}, suspect area {{area}}, recent merges {{log}}.

METHOD (do not skip to a fix):
1. Reproduce deterministically (write the failing test FIRST).
2. Localize: git bisect across recent merges if regression; binary-search the code path.
3. Form ONE hypothesis; state the mechanism; predict an observation that would confirm it.
4. Test the prediction. If wrong, discard and reform — do not patch symptoms.
5. Only once the mechanism is proven: propose the minimal fix + a regression test.

STOP / ESCALATE TO LEAD (Opus) IF:
- root cause crosses a module/contract boundary,
- two failed hypotheses without convergence (you may be missing architecture context),
- the fix would require a contract or schema change.

OUTPUT CONTRACT: bug-investigation report (template 10.2): symptom, ROOT CAUSE
(with proof), why it escaped review, fix, prevention (regression test + checklist update).
```

### 11.4 Research — `prompts/research.md`

```
ROLE: You are the Researcher ({{model}}). You produce DECISIONS-READY memos, not data dumps.

QUESTION: {{question}}
DECISION CRITERIA (rank by these, nothing else): {{criteria}}
CONSTRAINTS: solo operator (ops burden matters), budget {{budget}}, deadline {{deadline}}.

DO:
- enumerate 2–4 real options,
- score each against the criteria in a table,
- give ONE recommendation with rationale tied to the criteria,
- state what would make you change the recommendation (the revisit trigger).

DO NOT:
- return raw notes / unfiltered search results,
- recommend the newest/shiniest without weighing migration + maintenance cost,
- exceed the context the Lead needs to decide (P4: compress).

OUTPUT CONTRACT: research-summary report (template 10.4). The final section MUST be
"Minimum context for the Lead to decide" — 3–6 sentences + the options table. That, not
your full reading, is what gets handed up.
```

### 11.5 Architecture analysis (Lead / Opus) — `prompts/architecture-analysis.md`

```
ROLE: You are the Lead/Architect (Claude Opus). You own system coherence. You are SCARCE —
spend your reasoning on leverage, not on restating code.

INPUTS (compressed — you do NOT read the whole repo):
- architecture/README.md (module map), relevant ADRs {{adrs}}, contracts {{contracts}},
- last cycle's ledger {{ledger}}, the specific question/change {{request}}.

PRODUCE:
1. Restate the decision and its BLAST RADIUS + IRREVERSIBILITY (why it's yours to make).
2. Options with explicit trade-offs against our invariants and current architecture.
3. Decision + an ADR (template) — context, decision, consequences, what it supersedes.
4. If it implies interface change: the updated CONTRACT (machine-checkable form).
5. The task specs needed to realize it (hand to workers), each with acceptance criteria.

GUARDRAILS:
- do not re-litigate settled ADRs unless new evidence is in the ledger,
- prefer the reversible option unless the irreversible one is decisively better,
- minimize the number of workers/branches the decision requires (P2/P3),
- if this is really a product/business call → escalate to the human, don't decide.
```

### 11.6 Documentation generation (Scribe) — `prompts/doc-generation.md`

```
ROLE: You are the Scribe ({{model}}). You transcribe and format. You invent NOTHING.

INPUTS: diff/decision {{source}}, target doc {{target}}, template {{template}}.

DO:
- update {{target}} to match {{source}} exactly,
- fill the template; keep the machine-readable header accurate,
- write docstrings that state behavior, params, returns, and failure cases from the code.

DO NOT:
- invent rationale, benchmarks, or behavior not present in the source,
- make architectural or naming decisions (flag them for the Lead instead),
- drift from the template structure.

OUTPUT CONTRACT: the updated doc/report file only. If the source is ambiguous or seems to
contradict an invariant, emit `FLAG:` + the specific concern instead of guessing.
```

### 11.7 Prompt-library discipline

Treat these like any other code: they live in git, changes go through review, and when you discover a recurring failure (a model keeps gold-plating), you fix it *in the prompt* and note it in the changelog — never by repeatedly correcting the model in chat. A prompt fix is a permanent, compounding improvement; a chat correction evaporates when the session ends. The prompt library is where the system's operational learning accumulates, alongside `/knowledge`.

---

## 12. Cost Optimization

### 12.1 Reframe: the scarce resource is Opus *attention*, not dollars

Your dollar cost is fixed at ~$30/mo (Pro + Go) and barely moves — OpenCode Go is flat-rate, so worker volume is *already* optimized (it's effectively free at the margin). The thing you actually ration is **Opus messages** (the Pro cap). So "cost optimization" here means **maximizing decision-value per Opus message**, plus a secondary goal of not wasting worker *time* (latency) on the wrong model. Optimize the scarce input, ignore the abundant one.

### 12.2 The routing tables (pin these to the wall)

**Always Opus (high leverage — these earn back their cost many times over):**

| Task class | Why Opus |
|---|---|
| Sprint planning / task decomposition | Sets up *all* downstream work; a bad plan wastes a day of cheap labor. |
| Interface / schema / API contract design | Highest blast radius; everything builds on it (P5). |
| Architecture decisions & ADRs | Irreversible-ish; defines coherence. |
| Dependency adoption (new lib/framework) | Long-lived, hard to undo, security surface. |
| The review *gate* on risk-routed diffs | Catches the expensive mistake tests can't. |
| Bugs workers got stuck on (2+ failed hypotheses) | Needs whole-system reasoning. |
| Integration decisions across modules | Cross-cutting; semantic-conflict adjudication. |
| Security boundary design | Mistakes here are catastrophic + irreversible. |

**Never Opus (low leverage — spending Opus here is pure waste):**

| Task class | Send to |
|---|---|
| Boilerplate, scaffolding, CRUD with a clear spec | GLM-5.1 / Qwen3.7 |
| Test writing to given acceptance criteria | DeepSeek / Kimi (Verifier) |
| Formatting, lint fixes, mechanical refactors | scripts / MiMo |
| Docstrings, changelogs, README updates | MiMo (Scribe) |
| Log grepping, reproducing a *known* bug | Qwen3.7 / DeepSeek |
| Filling report templates (mechanical) | MiMo (Scribe); weekly rollup → Qwen3.7 Plus + Opus sign-off |
| Reading large doc sets to answer a bounded question | Qwen3.7 Max (1M ctx) |

**Open-weight by default (the broad middle):** anything that is *specified and verifiable* — i.e., SpecGap ≈ 0 and a test can prove it correct. If you can write the acceptance criteria, a worker can satisfy them; Opus's only job there was writing those criteria.

### 12.3 The decision rule in one line

> If the task is **specified and test-verifiable**, a worker does it. If doing it *requires making a decision that constrains future work or is expensive to reverse*, Opus does it. Everything else is a spec-quality problem: close the SpecGap with a *small* Opus spend, then let workers run.

### 12.4 The Opus Budget Ledger (the control system)

Track Opus spend like a burn-down. `ledger.csv` gets one row per Opus message with `{date, phase, task_id, purpose, outcome}`. Each weekly review computes **Opus-messages-per-merged-task** — the system's core efficiency metric. Targets and responses:

```
 Opus msgs / merged task     interpretation                 action
 ───────────────────────────────────────────────────────────────────────────────
   < 4                       healthy; specs are good         keep going
   4 – 8                     normal range                    monitor
   8 – 12                    Opus creeping into low-leverage  raise risk threshold;
                             review or weak specs             improve spec quality
   > 12                      budget will bind; you're using   AUDIT: are you sending
                             Opus as a worker                 specified work to Opus?
   hitting the Pro cap       review gate is the bottleneck    THEN (only then) upgrade
                             OR threshold too low             to Max 5x ($100)
```

The upgrade-to-Max trigger is **data, not vibes**: only when the ledger shows you consistently hitting the cap on *gate reviews of genuinely high-risk diffs* (not on debugging that should've been a worker task) do you pay 5x. Most solo operators never need to — they need better specs and a higher risk threshold, which is free.

### 12.5 Concrete cost tactics (in order of impact)

1. **Compress context into Opus (P4).** Opus reads `/architecture` + ledger, never the raw tree. This is the biggest single lever on Opus-message efficiency — a focused planning prompt does in 6 messages what a "here's the whole repo" prompt does in 20.
2. **Batch the review gate.** Review the day's queue in one session, not diff-by-diff. Context is already warm; you amortize the architectural framing across all diffs.
3. **Raise the risk threshold until escaped defects appear, then back off one notch.** The router should send Opus the *fewest* diffs that keeps escaped-defects at zero. This is an explicit tuning loop in the weekly review.
4. **Match worker to difficulty class.** Don't send a CRUD endpoint to GLM-5.1 when Qwen3.7 Plus or MiMo passes its tests faster. Saves wall-clock, which is *your* time.
5. **Cache decisions as ADRs.** A decision made once and recorded never costs an Opus message again. Re-deriving a settled decision is the most common silent waste.
6. **Kill mechanical report-typing with scripts + MiMo.** Never let Opus *format* a report; the lone synthesis report (the weekly rollup) goes to Qwen3.7 Plus with an Opus sign-off, not to Opus's pen.
7. **Use a different-family Verifier so most diffs auto-approve.** Every diff that clears CI + QA without Opus is a saved message. P8 is a cost optimization as much as a quality one.

---

## 13. Automation Roadmap

The progression is **manual → semi-automated → autonomous orchestration**, and you should *not* skip stages — each phase teaches you the failure modes you must script around in the next. The human and Opus stay at the leverage points throughout; what gets automated is the *deterministic connective tissue* (P10).

### 13.1 Phase 1 — Manual operation (Weeks 1–4)

You are the orchestrator. You run OpenCode by hand, copy specs into it, eyeball the queue, invoke Opus in the Claude app, merge with git.

- **Tools:** OpenCode CLI (Go subscription), Claude Pro (web/desktop), git, a handful of shell aliases. No custom automation yet.
- **Architecture:** the directory structure (§7), the task-spec schema (§6.6), the prompt library (§11), the report templates (§10) — all *used by hand*. `scripts/` has only `new-task.sh` and `rollback.sh`.
- **Risks:** tedium-driven shortcutting (you skip the QA step "just this once" — exactly how defects escape); inconsistent spec quality; you become the bottleneck and throughput is capped by your typing.
- **Expected gains:** you learn the real shape of the work — which task classes need Opus, where specs are ambiguous, what the risk thresholds should be. **This calibration is the actual deliverable of Phase 1.** Don't automate before you have it; you'd just automate your mistakes. Throughput: ~1.5–2x a solo dev with no system.

**Exit criteria → Phase 2:** you've run ≥3 weeks, your ledger has real numbers, and you're confident in the routing thresholds and the task-spec schema.

### 13.2 Phase 2 — Semi-automated operation (Months 2–4)

Scripts handle dispatch, gates, and reporting. Opus and you handle judgment. This is where most solo operators should *stay* for a long time — it captures ~80% of the value at ~20% of the autonomy risk.

- **Tools:** `scripts/dispatch.sh` (creates branches, enforces file-set disjointness, hands specs to OpenCode in non-interactive mode), `scripts/gate.sh` (runs CI + invokes the Verifier model + risk-router; auto-approves or queues for Opus), `scripts/ledger-append.sh`, the Scribe wired to generate reports on merge. Opus invoked via the **Claude API** (small *optional* metered spend, **on top of** the $30 base) *only* for planning and gated reviews — or keep invoking Opus by hand in the Pro app to stay inside the flat $30 stack. CI in GitHub Actions / Gitea Actions. A nightly cron drafts the next day's backlog.
- **Architecture:** a thin **controller script** runs the loop `read active specs → dispatch disjoint set → workers execute → gate.sh verifies → risk-router → {auto-merge | queue for Opus}`. The human approves the Opus-gated items and the HUMAN-REQUIRED classes. The report ledger is now written automatically.
- **Risks:** automation outpacing trust (a scripted auto-merge ships a subtle defect because the threshold was too loose); silent model drift (OpenCode updates a model, behavior shifts, no one notices — *pin versions and run a weekly regression*); the controller hiding problems you'd have caught by hand. Mitigation: keep every auto-approve **revertable and logged**; alert on any metric regression.
- **Expected gains:** you stop being the dispatcher and the typist; your time concentrates on Opus-gated reviews, product decisions, and tuning. Throughput: ~3–5x. Defect rate *drops* vs. Phase 1 because the gates are now consistent (no human skipping steps).

**Exit criteria → Phase 3:** ≥2 months of Phase 2 with escaped-defects ≈ 0, a stable controller, and routing thresholds you trust enough to let run unattended for hours.

### 13.3 Phase 3 — Autonomous orchestration (Month 5+, optional)

The controller runs the full loop unattended within tight guardrails; you supervise by exception. **This is a power tool, not a destination — many excellent operators deliberately never go past Phase 2.**

- **Tools:** a persistent **orchestrator** (a small long-running service, or scheduled tasks) that plans (calls Opus API at sprint boundaries), dispatches, verifies, gates, merges, and reports on its own. A policy file defines the autonomy envelope: which risk classes it may auto-merge vs. must escalate. Observability/alerting (it pages you on threshold breaches, budget exhaustion, or a metric regression). Opus is on the API, budgeted. The orchestrator's default unattended execution engine is **Kimi K2.6 Thinking** (best long-horizon autonomy), and every run it produces is graded by a different-family Verifier (**DeepSeek V4 Pro**) before the gate — so separation of powers (§5.8) holds even with no human watching.
- **Architecture:** event-driven loop — `plan (scheduled) → enqueue → for each task: dispatch→execute→verify→risk-route→{auto-merge | human/Opus queue} → report`. Crucially, the **separation of powers (§5.8) is preserved in code**: the implementer model, the verifier model, and the gate are distinct, and the HUMAN-REQUIRED classes (§9.4) are hard stops the orchestrator physically cannot bypass. The human reviews a morning digest and an exception queue.
- **Risks:** the big ones. Reward-hacking at scale (workers satisfying acceptance criteria while missing intent, now without a human noticing for hours); compounding architectural drift if the weekly Opus architecture review lapses; budget runaway (an Opus-API loop that retries); cascading bad merges if a threshold is mis-set; over-trust leading to atrophied human oversight. Mitigation: hard budget ceilings with circuit-breakers, mandatory daily human digest review, the architecture review *cannot* be skipped (the orchestrator blocks the next sprint's planning until it's done), and a "two reverts in a day → auto-pause and page the human" rule.
- **Expected gains:** throughput decouples from your hours — the system makes progress overnight and while you do product/business work. Realistic ceiling for a solo operator: ~5–8x, *bounded by your review-and-direction capacity*, not by the orchestrator. Past that, you're no longer a solo dev; you're running an AI org and the constraint is your own judgment bandwidth — which is the right problem to have and the cue to slow down, not speed up.

### 13.4 The roadmap in one table

| | Phase 1: Manual | Phase 2: Semi-auto | Phase 3: Autonomous |
|---|---|---|---|
| **Who dispatches** | you | `dispatch.sh` | orchestrator |
| **Who verifies** | you trigger QA | `gate.sh` + Verifier model | orchestrator |
| **Who merges** | you | you approve, script merges | script (within envelope) |
| **Opus invoked** | by hand (Pro app) | API, plan + gated reviews | API, scheduled + exceptions |
| **Human role** | orchestrator | reviewer + tuner | supervisor by exception |
| **Throughput** | 1.5–2x | 3–5x | 5–8x |
| **Main risk** | tedium → skipped steps | drift / loose thresholds | reward-hacking at scale |
| **Stay here if…** | you're calibrating | you want max value/risk ratio | you can't, want overnight progress |

---

## 14. Failure Modes (Top 25)

Ranked roughly by expected damage × likelihood for *this* system. Format: **warning signs → root causes → mitigation.** The ones marked ★ are the system-killers — wire explicit detection for those.

| # | Failure mode | Warning signs | Root causes | Mitigation |
|---|---|---|---|---|
| 1 ★ | **Architectural drift / coherence decay** | New code contradicts ADRs; modules duplicate concepts; "why is this here?" | Weekly architecture review skipped; workers inventing interfaces; Opus only doing tasks not coherence | Mandatory weekly arch review (§8.5 block 2); contracts owned by Lead (P5); orchestrator blocks planning until review done |
| 2 ★ | **Spec drift (SpecGap not closed)** | Workers thrash; high QA-round counts; lots of `ESCALATE` | Vague specs; Opus rushing planning; acceptance criteria not executable | Enforce the spec schema (§6.6); track first-pass-QA rate; if <60%, fix specs before adding tasks |
| 3 ★ | **Silent model drift on version bump** | Behavior changes with no code change; regression appears overnight | OpenCode updated a model; "latest" pin | Pin exact versions in `AGENTS.md`; weekly regression suite; treat a bump as a change (ADR) |
| 4 ★ | **Reward hacking / test gaming** | Tests pass but behavior wrong; coverage high, quality low | Worker weakened tests or asserted buggy behavior; verifier same family | Separation of powers (§5.8); different-family Verifier (P8); Opus gate spot-checks test *quality* not just pass/fail |
| 5 ★ | **Opus budget exhaustion mid-sprint** | Pro cap hit by noon; can't review the risky diff | Opus used as a worker; review threshold too low; no budget tracking | Opus Budget Ledger (§12.4); raise risk threshold; reserve 15 msgs/day; never send specified work to Opus |
| 6 | **Multiple workers editing same files** | Merge conflicts; lost edits | File ownership not partitioned | `dispatch.sh` rejects intersecting `files_allowed` (§8.2); one file → one active branch |
| 7 | **Context rot (1M window stuffed)** | Model loses the thread; ignores earlier instructions; inconsistent | Dumping whole repo into context | Compress (P4); workers load only their slice; never use 1M as a substitute for curation |
| 8 | **Escaped defects (QA too shallow)** | Bugs found in prod that QA should've caught | Non-adversarial QA; missing edge cases; coverage of wrong code | Adversarial review prompt (§11.2); diff-coverage gate; each escaped defect updates the checklist (§10.2) |
| 9 | **Over-escalation to Opus (cost blowup)** | Opus-msgs/merged-task > 12; cap hit on trivia | Risk threshold too low; reviewing everything | Raise threshold; trust CI+QA auto-approve; measure and tune weekly |
| 10 | **Under-escalation (architecture rots)** | High-blast-radius diffs auto-merging; #1 follows | Risk threshold too high; router misses contract touches | Router must flag *any* contract/schema/security/dep touch regardless of size; audit auto-approvals weekly |
| 11 | **Dependency hallucination** | Import of a nonexistent package/API; build breaks late | Model invented a plausible library/method | `deps_preapproved` allowlist; CI resolves deps; Researcher verifies APIs before adoption |
| 12 | **Branch sprawl** | Dozens of stale `task/*` branches; unclear state | Tasks not closed; abandoned work | One spec→one short-lived branch; auto-delete merged/abandoned; cap active branches |
| 13 | **Review-queue backlog** | Diffs pile up waiting for the gate; throughput stalls | Opus is the bottleneck; batch review skipped | Batch reviews (§12.5); raise auto-approve share; if persistent, upgrade to Max (§12.4) |
| 14 ★ | **Secret leakage (prompt/log/commit)** | Keys in logs, in a worker's context, or committed | No secret scanning; secrets in specs; model echoes env | `gitleaks` in CI (blocking); never put secrets in specs; local model for secret-sensitive code (§3.4) |
| 15 | **Flaky tests mask defects** | Intermittent CI failures ignored; "just re-run" | Nondeterministic tests; time/concurrency deps | Quarantine flaky tests; flakiness rate in weekly review; fix or delete — never ignore |
| 16 | **Stale ADRs / docs** | Docs describe a system that no longer exists | Doc review skipped; Scribe not wired to merges | Weekly doc review (§8.5); Scribe updates on merge; ADR status field (active/superseded) |
| 17 | **Over-engineering / gold-plating** | Diffs larger than the spec; speculative abstraction | Implementer exceeding scope; no "Out of scope" | Binding "Out of scope" in spec (§6.6); gate flags scope creep (§11.2); prefer smallest change |
| 18 | **Non-reproducible builds** | "Works on my machine"; CI ≠ local | Unpinned deps/toolchain; env drift | Lockfiles; pinned toolchain; containerized CI; reproducibility is a gate |
| 19 | **Human-in-the-loop atrophy** | You rubber-stamp digests; stop reading diffs | Over-trust in Phase 3 automation | HUMAN-REQUIRED hard stops (§9.4); mandatory digest review; periodic manual deep-dives |
| 20 | **Semantic merge conflicts** | Two branches assume different contract versions | Contract changed mid-flight | Contracts are Lead-owned; changes re-issue affected specs (§8.3); trunk wins, rebase |
| 21 | **Report sprawl / noise** | Tons of reports nobody reads (brief's own warning) | Over-reporting; reports as prose not data | Machine-readable headers (§10); reports must feed a decision; Scribe writes, scripts aggregate |
| 22 | **Wrong-model-for-class waste** | Slow throughput; cost (time) high for simple tasks | Sending easy work to heavy models | Difficulty-class routing (§4.4); weekly per-model failure-by-class tuning |
| 23 | **Cascading bad merge** | One bad merge breaks trunk; subsequent work builds on it | Auto-merge threshold too loose; no post-merge smoke | Post-merge smoke test; "2 reverts/day → auto-pause" (§13.3); small revertable merges (P11) |
| 24 | **Knowledge loss on session reset** | Re-deriving settled decisions; repeated mistakes | Relying on chat memory not artifacts | Everything in files (P3): ADRs, `/knowledge`, postmortems; nothing lives only in a session |
| 25 | **Single-provider dependency** | OpenCode/Claude outage halts everything | No fallback path | Local model fallback (§3.4); BYO-key route in OpenCode; the system runs (degraded) offline (P11) |

---

## 15. Final Recommendation

### 15.1 The exact stack I would deploy

If my objective were to build a highly productive solo AI-assisted software organization over the next three years, this is precisely what I would run on day one — no more, no less:

```
 SUBSCRIPTIONS ($30/mo)
   • Claude Pro ($20)            → Opus 4.8 as the single LEAD brain
   • OpenCode Go ($10)           → the open-weight workforce

 ROLES → MODELS (pinned in AGENTS.md)
   • Lead/Architect/Gate/Debug   → Claude Opus 4.8     (scarce; leverage points only)
   • Implementer (primary)       → GLM-5.1
   • Autonomous Worker / agentic → Kimi K2.6 Thinking  (big bou