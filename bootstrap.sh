#!/usr/bin/env bash
# bootstrap.sh — create the AI-Dev-OS directory skeleton + seed files the scaffold omits.
#
# The project-scaffold ships AGENTS.md, CLAUDE.md, prompts/ and scripts/ — but NOT the
# directory tree those scripts and CLAUDE.md's compressed-context protocol assume exists
# (architecture/, agents/, reviews/checklist.md, tasks/backlog, knowledge/, ...). This
# script writes that skeleton (manual §7.1) plus starter content.
#
# Safe to re-run: it never overwrites a file that already exists (idempotent).
# Run it once at the ROOT of the repo where you copied the scaffold:
#     bash bootstrap.sh
set -euo pipefail

# --- args ------------------------------------------------------------------
PROFILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:?--profile needs <family/variant>}"; shift 2 ;;
    *) echo "[bootstrap][warn] ignoring unknown arg: $1"; shift ;;
  esac
done

# --- locate repo root (git if available, else cwd) -------------------------
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then ROOT="$PWD"; echo "[bootstrap][warn] not a git repo yet; using $ROOT"; fi
cd "$ROOT"

c_made=0; c_skip=0
made() { printf '  \033[32m+ %s\033[0m\n' "$1"; c_made=$((c_made+1)); }
skip() { printf '  \033[90m· %s (exists, kept)\033[0m\n' "$1"; c_skip=$((c_skip+1)); }

# wf <path>  — write stdin to <path> only if it does not already exist.
wf() {
  local p="$1"
  if [[ -e "$p" ]]; then cat >/dev/null; skip "$p"; return 0; fi
  mkdir -p "$(dirname "$p")"; cat > "$p"; made "$p"
}
# keep <dir...> — ensure dir exists and has a .gitkeep so git tracks it when empty.
keep() { local d; for d in "$@"; do mkdir -p "$d"; if [[ -z "$(ls -A "$d" 2>/dev/null)" ]]; then : > "$d/.gitkeep"; made "$d/.gitkeep"; else skip "$d/ (non-empty)"; fi; done; }

echo "[bootstrap] seeding AI-Dev-OS skeleton in: $ROOT"

# ===========================================================================
# architecture/  — PROJECT MEMORY (Lead-owned source of truth). CLAUDE.md reads this first.
# ===========================================================================
wf architecture/README.md <<'SEED'
# Architecture Map — the Lead's entrypoint

> CLAUDE.md step 1 loads THIS file first. Keep it a compressed map, not the code.
> Target: a Lead (Opus) should orient from this page + the ADR index + the touched
> contracts in well under ~8K tokens. If you ever feel you must read the whole tree,
> this map is stale — fix the map, don't read everything (CLAUDE.md §1, manual P4).

## System in one paragraph
<What this product is and the single responsibility of each top-level module. 4–6 sentences.>

## Module map
| Module (path) | Responsibility | Key contracts it owns/consumes | Owner role |
|---|---|---|---|
| `src/...` | <what> | `architecture/contracts/<name>.yaml` | implementer |

## Entry points
- Runtime entrypoint(s): <e.g. src/server.ts → bootstraps HTTP server>
- Build/run: <commands; or point to docs/setup.md>

## Invariants & decisions (do not contradict)
- Invariants: see [`invariants.md`](./invariants.md) — always hold; changing one needs an ADR.
- Decisions: see the ADR index in [`adr/`](./adr/) — start at `0001`.
- Contracts: see [`contracts/`](./contracts/) — load ONLY the ones a task touches.

## How to keep this current
The weekly architecture review (CLAUDE.md §6) reconciles this map against the code.
A merged task that adds/moves a module must update the table above in the same diff.
SEED

wf architecture/invariants.md <<'SEED'
# System Invariants

Rules that must ALWAYS hold across the whole codebase. Workers may never weaken these
(AGENTS.md §3); changing one is a high-leverage decision → the Lead writes an ADR first.
This file is append-mostly: add invariants as the system earns them; never silently drop one.

## Active invariants
> The three below are EXAMPLES copied from AGENTS.md §4. Replace with YOUR system's real
> rules, or delete them. An empty-but-honest list beats a wrong one.

1. (example) Money is integer minor-units (cents); never floats.
2. (example) All timestamps are UTC, ISO-8601.
3. (example) HTTP handlers never touch the DB directly — always go through the repository layer.

## Format
`<N>. <imperative rule>.  — rationale; ADR: <id if one governs it>`
SEED

wf architecture/glossary.md <<'SEED'
# Glossary — canonical vocabulary

One name per concept, used identically in code, specs, contracts and reports. If two words
mean the same thing, pick one here and treat the other as a defect.

| Term | Definition | Notes / synonyms to avoid |
|---|---|---|
| <Term> | <one-line definition> | use "<term>", not "<synonym>" |
SEED

wf architecture/adr/0000-template.md <<'SEED'
# ADR-0000: <short decision title>

- **Status:** Proposed | Accepted | Superseded by ADR-NNNN | Deprecated
- **Date:** YYYY-MM-DD
- **Deciders:** Lead (Opus) [+ human if HUMAN-REQUIRED class]

## Context
<The forces at play: the problem, constraints, and what makes this hard/irreversible.>

## Decision
<The choice, stated as "We will ...". Be specific enough that a worker cannot misread it.>

## Consequences
<What becomes easier, what becomes harder, and what new invariants/contracts this creates.>

## Alternatives considered
<Option B and why it lost. One or two lines each.>
SEED

wf architecture/adr/0001-adopt-ai-dev-os.md <<'SEED'
# ADR-0001: Adopt the Solo AI-Dev-OS operating model

- **Status:** Accepted
- **Date:** 2026-06-07
- **Deciders:** Lead (Opus) + human operator

## Context
A single operator is building software with AI. Premium model capacity (Claude Opus, via
Claude Pro) is scarce and rate-limited; open-weight coding models (via OpenCode Go) are
effectively unbounded at flat rate. We need an operating model that spends the scarce
resource only at leverage points and routes volume to the workforce.

## Decision
We adopt the AI-Dev-OS as described in `OPERATING_MANUAL.md`:
- **Routing:** `Leverage = BlastRadius × Irreversibility × SpecGap`. High-leverage work
  (contracts, schemas, security, ADRs, the review gate, hard bugs) stays with the Lead;
  everything specified + test-verifiable goes to the workforce (`AGENTS.md`).
- **Separation of powers (P8):** the model that writes a diff never grades it; the verifier
  is always a different model family. Enforced by `scripts/dispatch.sh` and `scripts/gate.sh`.
- **Spec-first:** the unit of work is a self-contained task spec (manual §6.6); a worker
  handed one spec needs nothing else.
- **Determinism layer:** dispatch, gate, ledger and rollback are scripts (`scripts/`), not
  model judgement. One task = one `--no-ff` merge = one-command rollback.
- **Model pins:** the exact model→role map lives in `AGENTS.md §1`. A version bump is a
  CHANGE → regression run + a new ADR.

## Consequences
- Coherence is owned in one place (`architecture/`) and on disk, not in any model's memory.
- Cost is bounded by Opus *attention*, tracked in `reports/metrics/ledger.csv`.
- The team progresses through the automation phases (manual §13) deliberately; we do not
  skip Phase 1 calibration.

## Alternatives considered
- One premium model does everything: blows the rate limit, no volume.
- Many cheap agents, no Lead: architectural drift and reward-hacking with no owner of coherence.
SEED

wf architecture/contracts/README.md <<'SEED'
# Contracts

Machine-checkable interfaces between modules: OpenAPI specs, JSON Schema, protobuf, or typed
stubs. A contract is the boundary a worker implements *against* but may never change on its own.

## Rules
- Designing or changing a contract is HIGH leverage → the **Lead** owns it; record the change
  in an ADR (`architecture/adr/`). A worker who needs a contract change must STOP and escalate
  (AGENTS.md §3).
- A task spec lists the contracts it touches under `depends_on_contracts:`. The risk router
  (`scripts/gate.sh`) flags any diff that edits files here and routes it to the Opus gate.
- One file per contract; name it for the boundary, e.g. `payments-api.yaml`, `user.schema.json`.
SEED

# ===========================================================================
# agents/  — AGENT MEMORY (who each role is; loaded per invocation). Manual §6.2, §5.
# ===========================================================================
wf agents/lead.md <<'SEED'
# Role: Lead — Claude Opus 4.8  (Architect / Reviewer / Debugger / Integrator)

Full protocol: `CLAUDE.md`. This card is the one-screen identity.

**You own:** system coherence. Your product is **specs and contracts**, not bulk code.
**You are scarce:** ~45 Opus msgs / 5h (Pro). Target <8 Opus msgs per merged task; keep ~15/day in reserve.
**You touch the day twice on purpose:** morning PLAN (emit 3–6 task specs + any ADR/contract),
evening GATE (batch-review only risk-routed diffs). Once on demand: a stuck bug (≥2 failed worker hypotheses).
**You never:** type CRUD, re-review auto-approved diffs, or read the whole repo (load the compressed map).
**You escalate to the HUMAN:** product/scope, irreversible spend/release, auth/payments/secrets/PII/prod-migration, public API breaks.
SEED

wf agents/implementer.md <<'SEED'
# Role: Implementer / Autonomous Worker — GLM-5.1 (default) · Kimi K2.7-Code (big agentic) · Qwen3.7 Plus (parallel)

Standing rules: `AGENTS.md`. Prompt: `prompts/task-execution.md`.

**You do:** implement ONE task spec to its acceptance criteria, on its branch, editing only `files_allowed`.
**You may not:** change any contract/interface/schema, add an un-pre-approved dependency, exceed "Out of scope",
weaken/delete tests, or touch `main`. Any of these → emit `ESCALATE: <reason>` and STOP — do not guess.
**Done means:** branch passes local gates (lint, typecheck, tests, diff-coverage ≥90%, secret-scan) +
a completion report in `reports/tasks/<id>-completion.md`. "Done" = merged AND stays merged (P9).
**Autonomous Worker (Kimi):** append to the spec's Working Notes every N steps; if two steps make no
measurable progress → STOP and escalate.
SEED

wf agents/verifier.md <<'SEED'
# Role: Verifier / QA — Kimi K2.7-Code ↔ DeepSeek V4 Pro (rotated; ALWAYS a different family than the author, P8)

Prompt: `prompts/code-review.md`. Invoked by `scripts/gate.sh` on the task branch.

**You do:** adversarially test someone else's diff — run/extend tests, hunt edge cases, check the spec's
acceptance criteria are truly met (not just claimed), and look for reward-hacking (criteria satisfied, intent missed).
**You output (machine-readable, first lines):**
```
RISK: low|med|high
VERDICT: pass|fail
BLOCKING: [ ... ]
```
**Hard rule:** you never grade a diff authored by your own model family. `dispatch.sh`/`gate.sh` refuse violations.
SEED

wf agents/researcher.md <<'SEED'
# Role: Researcher — Qwen3.7 Max (1M context) · DeepSeek V4 Pro

Prompt: `prompts/research.md`. Output lives in `knowledge/external/` or a research report (§10.4).

**You do:** read large surfaces (docs, RFCs, big codebases) and return a DECISION MEMO, not a dump:
the decision criteria given up front, the options, a recommendation + rationale, and risks/when-to-revisit.
**Discipline:** answer the bounded question; give the Lead the *minimum* context needed to decide. No code changes.
SEED

wf agents/scribe.md <<'SEED'
# Role: Scribe — MiMo-V2.5-Pro (mechanical) · Qwen3.7 Plus (weekly synthesis)

Prompt: `prompts/doc-generation.md`.

**You do:** mechanical, template-shaped writing — docstrings, changelogs, completion reports from git+ledger,
keeping `docs/` current with merges. Qwen3.7 Plus drafts the weekly summary; the **Lead signs it off**.
**You may not:** invent architecture or decisions (those are the Lead's ADRs) — only record what is true.
SEED

wf agents/devops.md <<'SEED'
# Role: DevOps — deterministic scripts (P10) + an open-weight model for bounded changes

Owns the determinism layer in `scripts/` (dispatch, gate, ledger, rollback) and CI in `.github/workflows/`.

**Principle:** anything mechanical or auditable is a script, never a model judgement call. Models never do
dispatch/clerical work. Script changes are themselves tasks (spec'd, reviewed). The Lead designs the pipeline once;
routine edits (a new CI step, a tuned threshold) are bounded worker tasks verified like any other diff.
SEED

# ===========================================================================
# reviews/  — REVIEW PIPELINE (queue/, verdicts/ are gitignored working state; checklist is committed)
# ===========================================================================
wf reviews/checklist.md <<'SEED'
# Standing Review Checklist  (manual §9.4)

Applied at the gate. Most diffs clear CI + a clean cross-family QA pass and auto-merge. The Lead
sees ONLY diffs the risk router flagged. The HUMAN-REQUIRED items below are hard stops the gate
must never auto-approve.

## Every diff (the Verifier checks; gate.sh enforces the mechanical ones)
- [ ] Meets the spec's acceptance criteria — observably, not just asserted.
- [ ] No file outside the spec's `files_allowed` was touched.
- [ ] No contract/schema/interface changed implicitly.
- [ ] No new dependency that isn't in `deps_preapproved`.
- [ ] Tests added/updated; diff coverage ≥ 90%; lint + typecheck pass; secret-scan clean.
- [ ] No acceptance test weakened, skipped, or deleted to make the suite pass.
- [ ] Stays within "Out of scope" — no gold-plating.

## Lead gate (risk-routed diffs only — prompts/code-review.md Opus-gate addendum)
- [ ] Honors the relevant contracts & invariants; abstraction is right-sized.
- [ ] Security + failure modes for THIS change are sane.
- [ ] Reversible; no data-shape lock-in without an ADR.

## HUMAN-REQUIRED — hard stops (gate may NEVER auto-approve; escalate to the human)
- [ ] Auth / authorization changes.
- [ ] Payments / money movement.
- [ ] Secrets / credential handling.
- [ ] PII handling or storage.
- [ ] Production data migration.
- [ ] Public API or any contract-breaking change.
SEED

# ===========================================================================
# tasks/ reports/ reviews/ knowledge/ docs/  — tracked dirs (.gitkeep where empty)
# ===========================================================================
keep tasks/backlog tasks/active tasks/completed
keep reports/daily reports/weekly reports/tasks reports/bugs reports/metrics
keep reviews/queue reviews/verdicts
keep knowledge/patterns knowledge/postmortems knowledge/external
keep docs/runbooks

# A complete, INERT example spec (in backlog, so dispatch won't pick it up). Copy it to learn the schema.
# Named EXAMPLE-task (not 000-…) so it can't be confused with a real completed task 000 (ADR-0004).
wf tasks/backlog/EXAMPLE-task.md <<'SEED'
---
id: "000"
slug: example-health-endpoint
owner_role: implementer
model: opencode/glm-5.1
verifier_model: opencode/deepseek-v4-pro   # different family than author (P8)
branch: task/000-example-health-endpoint
blast_radius: low
files_allowed:
  - src/routes/health.ts
  - src/routes/health.test.ts
depends_on_contracts: []
deps_preapproved: []
---

# Goal
Expose `GET /health` returning `{ "status": "ok", "uptime_s": <int> }` with HTTP 200.

# Context (compressed)
New service has no liveness endpoint. Router is in `src/routes/`; handlers go through the
existing app factory. Do not add a framework or middleware. See architecture/README.md.

# Acceptance criteria  (executable where possible)
- [ ] `GET /health` returns 200 and a JSON body with `status: "ok"`.
- [ ] `uptime_s` is a non-negative integer (process uptime in seconds).
- [ ] tests cover: 200 path, body shape, uptime type.
- [ ] typecheck + lint pass; diff coverage ≥ 90%.

# Out of scope  (binding — prevents gold-plating)
- No `/readiness`, metrics, or DB checks. No new dependencies.

# Stop conditions  (escalate instead of guessing)
- If a liveness contract should exist → STOP, escalate to Lead.
- If a needed dependency isn't in deps_preapproved → STOP, escalate.

# Working notes  (worker appends)
SEED

wf docs/setup.md <<'SEED'
# Setup

How to install, configure, and run THIS product (human-facing). Kept current by the Scribe.
Distinct from `architecture/` (which is *why* it's built this way).

- Prerequisites: <runtime, package manager, services>
- Install: <commands>
- Configure: <env vars, config files>
- Run (dev): <command>   ·   Run (prod): <command>
SEED

wf docs/usage.md <<'SEED'
# Usage

How to use the product once running (human-facing): primary workflows, CLI/API examples.
The Scribe updates this when a merge changes user-visible behavior.
SEED

# ===========================================================================
# CI + sourced env for the gate
# ===========================================================================
wf scripts/ci-env.sh <<'SEED'
#!/usr/bin/env bash
# ci-env.sh — the CI commands gate.sh reads from the environment.
# NOT secret (no tokens here) → committed on purpose. `source scripts/ci-env.sh` before gate.sh,
# or add `source scripts/ci-env.sh` to your shell profile / .envrc. Match these to YOUR stack.
export LINT_CMD="${LINT_CMD:-}"            # e.g. "npm run lint"
export TYPECHECK_CMD="${TYPECHECK_CMD:-}"  # e.g. "npm run typecheck"
export TEST_CMD="${TEST_CMD:-}"            # e.g. "npm test"
export COVERAGE_CMD="${COVERAGE_CMD:-}"    # e.g. "npm run coverage -- --min 90"
export SECRET_SCAN_CMD="${SECRET_SCAN_CMD:-}"  # blank → gate.sh auto-uses gitleaks if installed
# Risk-router thresholds (gate.sh defaults shown; tune weekly from the ledger):
export MAX_FILES="${MAX_FILES:-10}"
export MAX_LINES="${MAX_LINES:-300}"
SEED

wf .github/workflows/ci.yml <<'SEED'
# CI — the same gates scripts/gate.sh runs locally, enforced on the server too.
# Fill the run: steps with YOUR stack's commands (keep them identical to scripts/ci-env.sh).
name: ci
on:
  push:
    branches: [ main ]
  pull_request:
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      # - uses: actions/setup-node@v4   # or setup-python, etc. — match your runtime
      #   with: { node-version: '22' }
      # - run: npm ci
      - name: lint        # ${LINT_CMD}
        run: 'echo "TODO: lint cmd"'
      - name: typecheck   # ${TYPECHECK_CMD}
        run: 'echo "TODO: typecheck cmd"'
      - name: test        # ${TEST_CMD}
        run: 'echo "TODO: test cmd"'
      - name: secret-scan
        uses: gitleaks/gitleaks-action@v2
SEED

# --- make the scaffold scripts executable ----------------------------------
if compgen -G "scripts/*.sh" >/dev/null; then chmod +x scripts/*.sh && echo "  chmod +x scripts/*.sh"; fi

# --- apply a profile if requested ------------------------------------------
if [[ -n "$PROFILE" ]]; then
  if [[ -f scripts/profile.sh ]]; then
    echo "[bootstrap] applying profile: $PROFILE"
    bash scripts/profile.sh apply "$PROFILE" || echo "[bootstrap][warn] profile apply failed — run it manually: scripts/profile.sh apply $PROFILE"
  else
    echo "[bootstrap][warn] scripts/profile.sh missing — skipped --profile $PROFILE"
  fi
fi

echo
echo "[bootstrap] done — created $c_made file(s), kept $c_skip existing."
echo "[bootstrap] next:"
echo "  1) git add -A && git commit -m 'chore: bootstrap AI-Dev-OS skeleton'"
echo "  2) confirm/choose a profile: scripts/profile.sh apply <family/variant>  (see docs/INSTALL.md)"
