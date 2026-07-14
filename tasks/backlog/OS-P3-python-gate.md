---
id: OS-P3
slug: python-gate
owner_role: autonomous
model: opencode-go/kimi-k2.7-code          # OS task (no component profile) → explicit pins, P8 pairing
verifier_model: opencode-go/deepseek-v4-pro
branch: task/OS-P3-python-gate
blast_radius: high         # the review pipeline itself
files_allowed:
  - scripts/os/
  - scripts/gate.sh
  - scripts/test/
depends_on_contracts: []
deps_preapproved: []       # Python 3 STDLIB ONLY (ADR-0023) — pip is a STOP condition
---

# Goal
`gate.sh` becomes a 2-line shim over `scripts/os gate <id> [--dry-run]` with identical behavior:
rebase → CI steps → boundary audit → deps guard → dangerous-API scan → cross-family QA → risk router
→ PR/queue decision.

# Context (compressed)
Depends on OS-P1/P2 (speclib + ledger in Python). Port gate.sh's logic 1:1 — same env config
(LINT_CMD…, MAX_FILES/MAX_LINES, SECURITY_REGEX, GATE_MERGE), same messages where tests assert them,
same ledger events, same DRY_RUN synth verdict. Subprocess calls (git/gh/opencode) use list-argv —
never shell strings (the BUG-03/10 class). Upgrade sanctioned by the plan: the security-path heuristic
may also grep the reviewable diff CONTENT (not just paths) for the same regex; keep it labeled
[advisory] (architecture/invariants.md).

# Acceptance criteria  (executable)
- [ ] `bash scripts/gate.sh <fixture> --dry-run` output/exit parity with pre-port (capture both in the
      completion report).
- [ ] The verifier read-only check, verdict reuse rule (BUG-09), lockfile exclusions (BUG-23), and
      resilient push (retry + verbatim stderr) behave identically; risk flags unchanged + `model-override`.
- [ ] Python unittest for the risk router and boundary audit (fixture diffs → expected flags/escapes).
- [ ] `bats scripts/test` fully green.

# Out of scope  (binding)
- No new risk flags beyond diff-content security grep; no dispatch.sh changes (OS-P4).

# Stop conditions
- Parity requires reproducing a behavior that looks like a BUG → document, STOP for Lead ruling.
- Any capability seems to need a pip package → STOP, escalate.

# Working notes  (worker appends)
