# System Invariants

Rules that must ALWAYS hold. Workers may never weaken these (AGENTS.md §3); changing one is a
high-leverage decision → the Lead writes an ADR first. Append-mostly; never silently drop one.

## OS-level invariants (universal — hold across every component and profile)
Owned by the OS spine; not provided by a profile.

1. One-way dependency: a file under `components/<X>/` never references a path outside it; cross-component
   interaction happens only through a contract in `architecture/contracts/`.  — ADR-0002
2. A task's `files_allowed` lies wholly within a single component (plus the implicit completion-report and
   Working-Notes allowances of AGENTS.md §3).  — ADR-0002
3. The determinism layer reads canonical seam files and `profile.json`; no script branches on a profile or
   component name.  — ADR-0003
4. Role→model binding lives ONLY in the component's profile (`profile.json`); a task spec names a role
   (`owner_role`) — any model pin requires `override_reason` and is risk-routed to the Lead. The model
   catalog + families live in `architecture/catalog.json`.  — ADR-0022

## Enforcement honesty — what each guardrail actually is
`[mechanical]` = structurally enforced by a script on deterministic input. `[advisory]` = a heuristic
tripwire calibrated for **sloppy-but-cooperative workers** (the threat model, ADR-0014) — it can be
bypassed by an adversary and must never be described as a security boundary.

- `files_allowed` boundary audit (gate) — **[mechanical]** on the committed diff vs the spec list.
- Runtime-dependency pre-approval (gate) — **[mechanical]** for `package.json` runtime deps.
- P8 cross-family verification — **[mechanical]** via profile lint + `verifier_secondary` (ADR-0022).
- Fixed-catalog guard — **[mechanical]** against `architecture/catalog.json` (ADR-0009).
- Verifier read-only rule (gate) — **[mechanical]**: the worktree must be byte-identical after QA.
- Component isolation grep (`../` imports) — **[advisory]**; real enforcement is the profile ESLint
  boundary rule inside product CI (task OS-G1).
- Security-path risk regex (gate router) — **[advisory]**; it routes to the Lead, it does not block.
- Secret scan (dispatch regex; gitleaks) — **[advisory]** patterns; gitleaks in CI is the stronger layer.

## Stack invariants (profile-provided)
Stack-specific rules (e.g. "money is integer cents", "handlers stay thin") live in the **active profile**
and are applied per-component to `components/<name>/conventions.md` (ADR-0013). They hold for every
component governed by that profile; the Lead must ADR any change.

## Format
`<N>. <imperative rule>.  — rationale; ADR: <id if one governs it>`
