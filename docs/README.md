# docs/ — human-facing documentation

**This directory = how to *use* and *operate* the system** (install, session handoff, runbooks) — the
*how*. It is distinct from its two neighbours:

- `architecture/` = the system's **decisions and truth** (ADRs, contracts, invariants, glossary) — the *why*.
- `knowledge/` = cross-cutting **wisdom** (reusable patterns, postmortems, distilled research) — not decisions.

Per-component, product-specific usage lives in that component's own `components/<name>/README.md` (so the
component stays extractable). `docs/` holds OS-level material only.

Contents: `INSTALL.md` (stand up the scaffold) · `handoff/SESSION-HANDOFF.md` (resume a session cold) ·
`runbooks/` (operational procedures).
