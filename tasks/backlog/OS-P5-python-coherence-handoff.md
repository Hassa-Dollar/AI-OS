---
id: OS-P5
slug: python-coherence-handoff
owner_role: autonomous
model: opencode-go/kimi-k2.7-code          # OS task (no component profile) → explicit pins, P8 pairing
verifier_model: opencode-go/deepseek-v4-pro
branch: task/OS-P5-python-coherence-handoff
blast_radius: med
files_allowed:
  - scripts/os/
  - scripts/verify-coherence.sh
  - scripts/handoff.sh
  - scripts/test/
depends_on_contracts: []
deps_preapproved: []       # Python 3 STDLIB ONLY (ADR-0023) — pip is a STOP condition
---

# Goal
The nine coherence checks and the handoff/inventory generators run in `scripts/os coherence` /
`scripts/os handoff`; the `.sh` entrypoints are 2-line shims; profile.json is finally parsed as REAL
JSON (the line-based `json_get`/`json_roles` constraint disappears).

# Context (compressed)
Depends on OS-P1/P2. Last port module (ADR-0023): after this, bash holds only the zero-bug thin
wrappers (ship/run/pr/approve/rollback/change/ci-*/bootstrap — they stay bash permanently). Generated
blocks (AUTO-INVENTORY, AUTO-METRICS) must stay byte-identical to today's output — verify-coherence
compares them, so the generator and checker port together.

# Acceptance criteria  (executable)
- [ ] All nine checks reproduce byte-identical problem messages on the coherence.bats fixtures; the
      suite is green.
- [ ] profile.json parsing uses `json` (a minified/multi-line-value profile now works); a unittest
      proves the previously-unparseable shape resolves.
- [ ] `gen_inventory` parity: same block, byte-for-byte, on the real repo.
- [ ] `bats scripts/test` fully green; remaining `.sh` files pass `bash -n`.

# Out of scope  (binding)
- No new checks; no doc rewording beyond regenerated blocks.

# Stop conditions
- A fixture asserts bash-internal behavior that can't survive the port → STOP, escalate with the diff.
- Any capability seems to need a pip package → STOP, escalate.

# Working notes  (worker appends)
