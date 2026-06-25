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

## Stack invariants (profile-provided)
Stack-specific rules (e.g. "money is integer cents", "handlers stay thin") live in the **active profile**
and are applied per-component to `components/<name>/conventions.md` (ADR-0013). They hold for every
component governed by that profile; the Lead must ADR any change.

## Format
`<N>. <imperative rule>.  — rationale; ADR: <id if one governs it>`
