# ADR-0004: Repo ergonomics — clarity, identity, operator-facing errors

- **Status:** Accepted
- **Date:** 2026-06-13
- **Deciders:** Lead (Opus) + human operator

## Context
As a forkable scaffold, a newcomer must orient fast. Today: the root `README.md` reads as "how to
install the scaffold," not "what this repo is"; three doc-ish trees (`docs/`, `architecture/`,
`knowledge/`) overlap by name; an example task is duplicated across `tasks/backlog/` and
`tasks/completed/`; and script failures print a single coloured `[ai-os]` line with no cause or
remedy, forcing the operator to copy-paste it into a model to act on it.

## Decision
- **Root `README.md` = identity + quickstart** for someone who just cloned/forked: what AI-Dev-OS is,
  the OS-vs-`components/` split, and the first commands. Scaffold-install / bootstrap detail moves to
  `docs/INSTALL.md`.
- **Purpose headers:** each of `docs/`, `architecture/`, `knowledge/` gets a one-line "this is X, not Y":
  `architecture/` = decisions / contracts / invariants (the *why* / truth, Lead-owned); `docs/` = how to
  use a component (human-facing); `knowledge/` = cross-cutting patterns / postmortems / distilled
  research (wisdom, **not** decisions).
- **Cleanup (moderate):** de-duplicate the example task — the backlog copy becomes
  `tasks/backlog/EXAMPLE-task.md` (can't be confused with the real completed `000`), and the old
  `tasks/backlog/000-EXAMPLE-…` is removed. `knowledge/`'s clearly-named subdirs are kept; the directory
  gains a purpose-header README instead of being pruned.
- **Operator-facing error convention (#4):** `_lib.sh` gains a structured `die`/`warn` that prints three
  lines — *what failed* / *likely cause* / *try this* (a concrete command where possible). Every call
  site supplies a remedy. Colour stays: cyan info, yellow warn, red error.

## Consequences
- A forker understands the repo from the README in one screen; the three trees stop overlapping by name.
- Failures become self-explanatory and actionable without escalating to a model.

## Alternatives considered
- **Rename `knowledge/` / `architecture/`:** more churn (script + cross-link references) for marginal
  gain; purpose headers achieve the clarity at lower blast radius (matches the *moderate* appetite).
  Deferred.
