---
id: OS-P2
slug: python-ledger-db-metrics
owner_role: autonomous
model: opencode-go/kimi-k2.7-code          # OS task (no component profile) → explicit pins, P8 pairing
verifier_model: opencode-go/deepseek-v4-pro
branch: task/OS-P2-python-ledger-db-metrics
blast_radius: med
files_allowed:
  - scripts/os/
  - scripts/db.sh
  - scripts/ledger-append.sh
  - scripts/handoff.sh
  - scripts/test/
  - docs/handoff/SESSION-HANDOFF.md
depends_on_contracts: []
deps_preapproved: []       # Python 3 STDLIB ONLY (ADR-0023): csv, sqlite3 — pip is a STOP condition
---

# Goal
Ledger writes go through Python `csv` (no more malformed rows), db.sh's sqlite plumbing moves to the
stdlib `sqlite3` module behind the same CLI, and the handoff gains an auto-generated AUTO-METRICS block
(ADR-0024) computed from the ledger.

# Context (compressed)
Depends on OS-P1 (the `scripts/os` package exists). ledger.csv already contains a malformed row (an
embedded newline from an unquoted `pr=Warning:` value) — `csv` fixes the class. db.sh keeps its exact
CLI (remember/recall/export/sync + ADR-0019 confinement env), db.bats stays green. AUTO-METRICS shows:
last-7-day product:OS land ratio, first_pass_qa, dispatch count, and Opus msgs/merged-task if derivable
— deterministic given the ledger, following the AUTO-INVENTORY block pattern in handoff.sh.

# Acceptance criteria  (executable)
- [ ] `scripts/os ledger append <event> <task> <note>` writes RFC-4180 CSV; existing malformed rows are
      tolerated on read; `ledger-append.sh` delegates to it.
- [ ] `scripts/db.sh` CLI is unchanged; internals call `scripts/os db …` (sqlite3 stdlib); db.bats green.
- [ ] `scripts/handoff.sh` injects AUTO-METRICS:BEGIN/END into SESSION-HANDOFF §3; verify-coherence
      treats it like AUTO-INVENTORY (deterministic given the ledger file).
- [ ] Python unittest coverage for the metrics computation (fixture ledger → known numbers).
- [ ] `bats scripts/test` fully green.

# Out of scope  (binding)
- No schema change to ledger.csv columns; no rewrite of gate/dispatch callers (OS-P3/P4).

# Stop conditions
- Metrics ambiguity (what counts as a "product" land) → propose in Working Notes, STOP for Lead sign-off.
- Any capability seems to need a pip package → STOP, escalate.

# Working notes  (worker appends)
