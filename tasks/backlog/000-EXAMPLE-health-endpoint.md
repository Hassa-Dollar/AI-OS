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
