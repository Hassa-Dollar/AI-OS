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
