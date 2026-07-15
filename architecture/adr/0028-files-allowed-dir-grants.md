# ADR-0028: files_allowed directory grants (trailing slash)

- **Status:** Accepted
- **Date:** 2026-07-15
- **Deciders:** Lead (worker OS-V1 escalation — the missing decision it halted on)

## Context
Spec `files_allowed` entries were matched EXACTLY (`grep -qxF`) by the gate boundary audit and the
dispatch disjointness check. A task that must CREATE files under a directory (the `scripts/os/`
Python package, ADR-0023; its tests under `scripts/test/`) cannot enumerate them up front — the
OS-V1 worker correctly emitted `ESCALATE` instead of changing guardrail semantics itself.

## Decision
A `files_allowed` entry ending in `/` is a **directory grant** covering the subtree. Everything else
stays exact. Implemented as `_lib.sh path_allowed` (audit) + `filesets_clash` (P2/P3 disjointness —
file-under-dir and dir-under-dir collide), unit-tested in lib.bats; gate.sh + dispatch.sh consume
them. The boundary contract documents the semantics.

## Consequences
- Package-shaped tasks are grantable without enumerating files; the audit stays mechanical.
- Grants are coarser — the Lead must keep dir grants narrow (`scripts/os/`, never `scripts/`).
- Disjointness got STRICTER for overlapping grants: a dir grant now clashes with any file inside it.

## Alternatives considered
- Exact paths only (enumerate package files in the spec): brittle, re-escalates on every new file,
  fights ADR-0023. Rejected.
- Glob patterns: more power than needed; harder to reason about in bash. Rejected.
