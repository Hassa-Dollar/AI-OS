# ADR-0009: Machine-enforce the fixed model catalog (+ harden the verdict parser)

- **Status:** Accepted
- **Date:** 2026-06-18
- **Deciders:** Lead (Opus) + human operator

## Context
ADR-0005 fixed the workforce to **seven** hosted models and ADR-0007 bumped GLM. But "the catalog is
fixed" was **doctrine only** — nothing in the determinism layer checked that a pinned `model:` /
`verifier_model:` (or a profile's role binding) was actually one of the seven.

Manual model testing (the validation pass over all seven) confirmed the `opencode-go` gateway **also**
serves the superseded predecessors we bumped away from — `glm-5.1`, `kimi-k2.6`, `mimo-v2.5`,
`minimax-m2.7`, `qwen3.6-plus` — plus extras like `deepseek-v4-flash`. So a stale pin or a typo
(`glm-5.1` instead of `glm-5.2`) would **run silently against the wrong model**: no error, only the
ledger might later reveal it. That is exactly the "silent model drift" failure mode (manual §13), and it
contradicts the project's first priority — guardrails that stop the wrong thing from happening quietly.

The same test pass surfaced a second, smaller gap: `gate.sh` read the verifier's `RISK:`/`VERDICT:`
with `grep … | head -1`, unanchored. It works for compliant output (the review prompt front-loads
`RISK:` and emits one `VERDICT:`, and DeepSeek complied), but a verbose verifier that writes
"risk:"/"verdict:" in prose could misparse. The failure is fail-closed (defaults to `fail`), so it can
only *reject good work*, never merge bad — but it is still avoidable.

## Decision
1. **One source of truth + a guard in `scripts/_lib.sh`:** a `CATALOG` array (the seven exact slugs) and
   `assert_in_catalog <slug> [role]` that `die`s (what / cause / try) on anything else.
2. **Enforce at creation and at execution:**
   - `new-task.sh` and `profile.sh apply` — validate `model` / `verifier_model` and **every** model slug a
     profile binds (roles + `unbound`) when the spec / binding is created.
   - `dispatch.sh` and `gate.sh` — validate again right before a worker / the verifier actually runs.
3. **A version bump stays a tracked CHANGE:** editing `CATALOG` happens in the *same commit* as the
   bump's ADR + regression run (Failure Mode #3; cf. ADR-0005/0007). The guard does not replace that
   discipline — it makes a skipped step fail loudly instead of silently.
4. **Harden the verdict parser** (`gate.sh`): anchor `RISK:`/`VERDICT:` to line start (markdown prefixes
   allowed) and take the **last** match — the conclusion wins.

## Consequences
- The fixed catalog (ADR-0005) is now **executable**, not aspirational: an off-catalog, superseded, or
  typo'd slug fails at the earliest touch point with an actionable message.
- Coverage spans the whole lifecycle: spec creation, profile binding, dispatch, and the gate.
- The gate's verdict reading is robust to a chatty verifier while remaining fail-closed.
- Adding or replacing a model is now a deliberate edit next to an ADR — friction that is *wanted*.

## Alternatives considered
- **Leave it as doctrine** — rejected; silent wrong-model runs are the precise guardrail gap the project
  prioritizes closing.
- **Validate against `opencode models` at runtime** — rejected; adds a network dependency, and the gateway
  lists the superseded slugs as "valid" anyway. The point is *our* allowlist, not the gateway's.
- **Only guard at dispatch** — rejected; profiles and hand-written specs introduce off-catalog slugs
  earlier, so creation-time checks catch them sooner, and `gate.sh` is the last line before the verifier runs.
