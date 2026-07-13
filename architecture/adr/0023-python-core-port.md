# ADR-0023: Port the OS "brain" scripts to Python 3 (stdlib-only); bash keeps the "limbs"

- **Status:** Accepted
- **Date:** 2026-07-13
- **Deciders:** Lead + human operator

## Context
The determinism layer is ~2,000 lines of bash. The bug registry clusters in its parsing/quoting logic:
BUG-02/03/09/10/17/23/26/27/30 all live in `_lib.sh` / `gate.sh` / `dispatch.sh` / `db.sh` — hand-rolled
YAML/JSON/verdict parsers (awk/sed), argv quoting, CSV assembled by string concat. The thin wrappers
(`ship.sh`, `run.sh`, `pr.sh`, `approve.sh`, `rollback.sh`, `change.sh`, `ci-*.sh`, `bootstrap.sh`)
have produced ZERO registry bugs — they are short git/gh command sequences, which is what bash is for.

## Decision
1. **Language: Python 3 (≥3.10), stdlib-only.** No pip dependencies, ever, at the OS layer
   (supply-chain discipline, ADR-0014). The stdlib covers each observed bug class one-for-one:
   `subprocess` list-argv (quoting), `json`/`re` (parsers), `csv` (ledger), `sqlite3` (db.sh).
2. **Shape:** a `scripts/os/` package invoked as `scripts/os <cmd>`; every ported `.sh` entrypoint
   becomes a 2-line shim so all documented commands and the bats suite keep working unchanged.
3. **The bats suite is the acceptance harness:** it tests CLI behavior, not implementation — every
   port task's hard AC is `bats scripts/test` green plus dry-run output parity.
4. **Port order (worker-dispatched tasks OS-P1..P5, product tasks always first):** speclib/parsers →
   ledger+db → gate → dispatch → coherence+handoff generators.
5. **Bash keeps the limbs permanently:** the zero-bug thin wrappers listed above stay bash.
6. **No new logic in bash from now on:** new OS behavior lands in `scripts/os/`; a bash file may only
   gain a delegating call.

## Consequences
- The dominant bug class (bash-genre parsing/quoting) is retired module-by-module with a regression
  harness already in place; each port is a crisp, delegable worker task (pipeline reps, ADR-0024).
- New prerequisite: python3 ≥3.10 (ships with WSL/Ubuntu/macOS) — added to doctor.sh + INSTALL.md in OS-P1.
- Two languages coexist during the port; the shim rule + port order bound that window.

## Alternatives considered
- **Go (single binary):** type-safe, but every fork needs a Go toolchain, every OS edit a rebuild, and
  a public repo can't commit binaries — pays for distribution this repo-local tooling doesn't need. Rejected.
- **Go + Python mix:** two toolchains and `_lib.sh` semantics duplicated across languages — recreates
  the two-sources-of-truth disease ADR-0022 just removed. Rejected.
- **TypeScript/Node (runner-up):** Node 22 is already required and the workforce is strong in TS, but a
  root `package.json` muddies the OS-vs-product CI split (ADR-0006) and npm gravity invites the exact
  supply-chain surface ADR-0014 avoids; TS execution on Node 22 LTS still needs a build/strip step. Revisit
  only if the OS ever needs to share code with product components (it is deliberately product-agnostic).
- **Stay bash + harden:** accepts the recurring bug tax on a codebase that is still evolving. Rejected.
