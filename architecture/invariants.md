# System Invariants

Rules that must ALWAYS hold across the whole codebase. Workers may never weaken these
(AGENTS.md §3); changing one is a high-leverage decision → the Lead writes an ADR first.
This file is append-mostly: add invariants as the system earns them; never silently drop one.

## Active invariants

1. Timestamps are UTC, ISO-8601 (or integer epoch-ms). Never format, store, or compare in local time.
2. Money and quantities are integer minor-units (e.g. cents); never floats.
3. Route handlers stay thin: no direct DB, filesystem, or network I/O inside a handler. A handler
   parses input, calls a service/repository, and shapes the response — nothing more.
4. `tsconfig` strict mode is never relaxed; no `any` and no non-null `!` without a `// reason:` comment.

> Starter set for a TypeScript/Node service. Refine as the product earns real rules — but the
> Lead must ADR any change, and workers may only tighten, never weaken, these.

## Format
`<N>. <imperative rule>.  — rationale; ADR: <id if one governs it>`
