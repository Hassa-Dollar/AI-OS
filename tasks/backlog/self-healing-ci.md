# Backlog: self-healing CI — auto-remediate guard failures, then escalate

> Status: **backlog (capture only)** — design + an ADR when picked up. Raised by the operator after Step 4.
> Do NOT implement without a numbered spec + an ADR (new capability + a security boundary: autonomous writes).

## Idea
Today a guard/CI failure (e.g. `verify-coherence` dead-link, stale inventory, shellcheck, a failing test) is
**flagged and auto-logged to the memory DB** (via `die()` -> `_capture`, ADR-0016), but the **fix** is manual:
the operator pastes the failure to the Lead. Upgrade: on a failure, the system tries to fix itself before
involving a human —

1. **Tier 1 — deterministic auto-fix (no AI).** Mechanical failures have a known remedy: stale AUTO-INVENTORY
   -> run `handoff.sh`; a format nit -> run the formatter. Apply, re-run the guard, open a PR.
2. **Tier 2 — dispatch an open-weight worker.** Judgment fixes (a dead link: which target was meant? update
   or remove?) get a bounded task spec auto-generated from the failure and dispatched via `dispatch.sh` to a
   cheap model, on its own branch, inside the existing guardrails: `files_allowed` scoped to the offending
   files, `gitleaks`, the gate, and P8 (verifier family != author family).
3. **Tier 3 — escalate to the Lead.** If the worker's fix fails the gate, or intent is ambiguous,
   escalate with the failure + the worker's attempt — exactly the AGENTS section-8 escalation path.

## Why it fits (mostly reuses what exists)
- The **failure signal** already exists (the guards) and is **already logged** (ADR-0016 autonomous capture).
- The **executor + guardrails** already exist (`dispatch.sh`, `gate.sh`, P8, `gitleaks`, `files_allowed`).
- It is a proven pattern (auto-fix bots: Dependabot / Renovate auto-merge, lint-fix bots) — not novel infra.

## Open questions (resolve in the spec / ADR)
- Trigger surface: local (`ci-local` offers to remediate) vs. CI (a workflow opens an auto-fix PR on red).
- Tiering policy: which failures are Tier-1 safe (whitelist), which are Tier-2 (judgment), which are
  never-auto (anything touching auth / secrets / CI workflows -> human only).
- Loop + cost guard: max auto-fix attempts before forced escalation; hard cap on worker spend.
- Audit: every auto-fix recorded in the ledger + DB with provenance (who/what fixed it).

## Acceptance (sketch — for when scheduled)
- A seeded dead-link (or stale inventory) triggers an auto-fix that lands a green PR with no human input.
- A fix the worker cannot resolve escalates to the Lead with full context, and never merges unverified.
- Security-sensitive failures are never auto-fixed; they always escalate.
