# AI-Dev-OS

A solo **AI development operating system**. One scarce premium model — **Claude Opus 4.8, "the Lead"** —
produces specs, contracts, and reviews; cheap **open-weight models** (via the OpenCode Go gateway) do the
implement / verify / research / document work. Coordination is **git + files on disk**, not a live agent
bus. Target cost ≈ $30/mo. Full rationale: [`OPERATING_MANUAL.md`](./OPERATING_MANUAL.md).

> **Forkable by design.** Clone it, point it at *your* model gateway + GitHub, and build. The repo is
> public on purpose (`CLAUDE.md` §8); cloners run the pipeline against their own auth — never the author's.

## How the repo is laid out
- **The OS** (this scaffold): [`CLAUDE.md`](./CLAUDE.md) (Lead protocol) · [`AGENTS.md`](./AGENTS.md)
  (workforce rules + model catalog) · `agents/` `prompts/` `scripts/` `architecture/` `reviews/`
  `reports/` `tasks/` `knowledge/` `docs/`.
- **`profiles/<family>/<variant>/`** — reusable **specialization templates** (conventions, invariants, CI,
  product skeleton, and the role→model bindings) for one stack/domain. See ADR-0003 +
  `architecture/contracts/profile.schema.md`.
- **`components/<name>/`** — the actual product(s) you build, each **self-contained and extractable**
  (liftable out to host/publish on its own). See ADR-0002 +
  `architecture/contracts/os-component-boundary.md`.

## Quickstart
1. **Install + prerequisites:** [`docs/INSTALL.md`](./docs/INSTALL.md) (OpenCode Go, Claude Pro, `gh`,
   optional `gitleaks`).
2. **Bootstrap with a profile** for your first component:
   ```bash
   bash bootstrap.sh --profile web-app/ts-node-service
   ```
3. **Plan → spec → ship.** The Lead writes a spec in `tasks/active/<id>-<slug>.md`, then:
   ```bash
   scripts/dispatch.sh <id>     # a worker implements on a branch
   scripts/ship.sh <id>         # gate (CI + cross-family QA + risk router) → PR/auto-merge → land
   ```
4. **Resume any session cold:** read [`docs/handoff/SESSION-HANDOFF.md`](./docs/handoff/SESSION-HANDOFF.md).

## The one rule
`Leverage = BlastRadius × Irreversibility × SpecGap` — high-leverage work (contracts, schemas, security,
ADRs, the review gate, hard bugs) stays with the Lead; everything specified + test-verifiable goes to the
workforce. The verifier is **always a different model family** than the author (P8). Coherence is owned in
`architecture/` and on disk, never in a model's memory.
