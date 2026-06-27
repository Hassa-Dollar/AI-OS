# Backlog: move the Lead (Opus) to the API — programmatic, budgeted, 24/7-capable

> Status: backlog (capture only) — AFTER SaaS 1 is proven. Raised by the operator. Will need an ADR.
> Do NOT implement before SaaS 1 ships and the ledger has real Opus-spend-per-task data.

## Idea
Today the Lead (Opus) runs only as a human-invoked Cowork/Pro session — message-capped, and (by design) the
system cannot summon it. Move Opus to the Anthropic API so the determinism layer can invoke the Lead
programmatically (auto-gate risk-flagged diffs, auto-plan sprints) — the missing piece for true 24/7.

## Why it's attractive
- **Precise spend control:** token-metered, per-call budgets, hard $ caps, context-size caps — fine-grained
  vs Pro's flat cap. Caveat (be honest): "more control" is NOT "cheaper by default" — API Opus is costly per
  token and has NO flat ceiling; a loose loop can run high. The control is a throttle you must SET, not free
  savings. The flat ~$30 Pro ceiling is exactly what you give up.
- **Closes the autonomy gap:** the risk-router / scheduler can call the Lead directly instead of waiting for a
  human session → workers + auto-merge + auto-Lead-gate = continuous operation.
- **Portable by design:** the Lead's "brain" already lives in files (CLAUDE.md + prompts/), so it drops in as
  the API system prompt — no logic trapped in a Cowork session.

## Prerequisites (build BEFORE automating an API Lead)
- **An Opus budget governor** in the determinism layer: max $/day + max calls/window + context-size cap +
  fallback to a cheaper model for non-leverage work. The API has no flat cap — this guard is the safety.
- **Keep the human on the section-5 hard stops:** even an API Lead routes auth/payments/secrets/PII/public-API
  to a human; the API automates the routine gate, never the hard stops.
- **Data-driven trigger (CLAUDE.md section 7):** switch only once the ledger proves Lead-msgs/task is low and
  the gate (not stray debugging) is the bottleneck — then project the API $ from real per-task spend first.

## Sequencing
Prove SaaS 1 on Pro/Cowork (flat-rate — you literally cannot overspend while calibrating) -> read the ledger
-> project API cost -> build the budget governor -> port the Lead to API -> enable auto-invocation. Same 24/7
epic as the scheduled-digest + self-healing-CI backlog.
