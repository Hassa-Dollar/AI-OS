---
id: "000"
slug: example-health-endpoint
owner_role: implementer                       # resolved to a model via the component's profile (ADR-0022)
branch: task/000-example-health-endpoint
blast_radius: low
files_allowed:                                # all under ONE component (os-component-boundary contract)
  - components/<name>/src/routes/health.ts
  - components/<name>/src/routes/health.test.ts
  - reports/tasks/000-completion.md           # required output (AGENTS.md §6) — keep this line
depends_on_contracts: []
deps_preapproved: []
# model_override: + override_reason:  — audited exception only (ADR-0022); the gate risk-flags it.
# OS/chore task (no component)? no profile exists — set model: + verifier_model: explicitly (P8!).
---

# Goal
**(EXAMPLE — copy this file to start a real task; do not dispatch it as-is.)**
Expose `GET /health` returning `{ "status": "ok", "uptime_s": <int> }` with HTTP 200.

# Context (compressed)
Illustrates the task-spec schema (manual §6.6) and the boundary rule: `files_allowed` lives wholly within
one `components/<name>/`. Handlers stay thin; no framework. Link contracts here — don't inline the repo.

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
