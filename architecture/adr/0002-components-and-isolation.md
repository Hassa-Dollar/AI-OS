# ADR-0002: Components — extractable deliverables with hard isolation boundaries

- **Status:** Accepted
- **Date:** 2026-06-13
- **Deciders:** Lead (Opus) + human operator

## Context
The repo is a forkable scaffold (ADR-0001, CLAUDE.md §8) but currently mixes the OS with one
product at the repo root. We want (a) each deliverable to be **self-contained and liftable out**
to host/publish on its own, and (b) a single repo to be able to hold several deliverables of
**different stacks** (e.g. firmware + its web dashboard), each coherent independently. The
operator's first-priority requirement is that parallel model workers **never overwrite each
other or leak across boundaries**.

## Decision
- The product moves out of repo root into `components/<name>/`. Each component is **self-contained**:
  its own package manifest / build / test / CI-equivalent / README, and it builds, tests, and runs
  with **no reference to any path outside itself**. Extractability test: `cd components/<name> &&
  <build> && <test>` is green standalone.
- **Dependency direction is one-way:** the OS reaches into components; **no file under
  `components/<X>/` may reference a path outside `components/<X>/`.** Components are mutually
  independent; any cross-component interaction goes through a declared contract in
  `architecture/contracts/`.
- A repo may hold **many** components, each governed by **exactly one** profile (ADR-0003), recorded
  in the component's `.component.yml`.
- **Guardrails (the priority):**
  - A task spec's `files_allowed` must resolve within **exactly one** component (plus the implicit
    completion-report + Working-Notes allowances, AGENTS.md §3). `dispatch.sh` rejects a spec that
    straddles components, in addition to today's cross-task / cross-branch file-disjointness check (P2/P3).
  - A CI guard greps each component for outward path references (`../` escapes) and fails the gate.
  - A **post-merge boundary audit** compares each merged diff against its spec's `files_allowed` and
    appends any escape to the ledger as a `guardrail` event — detection layered on prevention.
- Scripts gain a `COMPONENT` selector (generalizing the planned `PRODUCT_DIR`); build/test/CI run
  inside the selected component.
- **Build scope:** implement the single-component path now (today's service → `components/<name>`).
  Adding a second component (`component.sh new`, multi-component selection) is a later **additive**
  increment, triggered when a real second stack lands — not built speculatively.

## Consequences
- Parallel work is structurally conflict-free across components (different folders ⇒ disjoint files)
  and now also **audited**, directly satisfying the no-mess requirement.
- Each deliverable is publishable on its own; the OS can be stripped away cleanly.
- The relocation is a `git mv` (history preserved); scripts / CI / `architecture/README` / `CLAUDE.md`
  paths update in the same change. Higher blast radius ⇒ **Opus-gated**, single `--no-ff` merge,
  one-command revert.

## Alternatives considered
- **Single `product/` only (no multi-component):** cannot host a polyglot project (firmware + dashboard)
  coherently. Rejected.
- **Global mutable profile instead of per-component:** switching mid-project silently invalidates
  already-gated diffs. Rejected in favour of *selection* (route a task to a component), never *mutation*.
