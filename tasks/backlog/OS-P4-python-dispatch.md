---
id: OS-P4
slug: python-dispatch
owner_role: autonomous
model: opencode-go/kimi-k2.7-code          # OS task (no component profile) → explicit pins, P8 pairing
verifier_model: opencode-go/deepseek-v4-pro
branch: task/OS-P4-python-dispatch
blast_radius: high
files_allowed:
  - scripts/os/
  - scripts/dispatch.sh
  - scripts/new-task.sh
  - scripts/test/
depends_on_contracts: []
deps_preapproved: []       # Python 3 STDLIB ONLY (ADR-0023) — pip is a STOP condition
---

# Goal
`dispatch.sh` (and `new-task.sh`) become 2-line shims over `scripts/os dispatch` / `scripts/os new-task`
with identical validation order, messages, and worker invocation.

# Context (compressed)
Depends on OS-P1..P3. Port 1:1: spec resolution, secret scan (incl. the BUG-26 env-var-reference
allowlist), roles v2 + override_reason guard (ADR-0022), catalog + P8 checks, file-set disjointness
(worktree + live task branches), branch creation, ledger event, ADR-0019 identity env, and the
opencode worker invocation (message BEFORE -f attachments — BUG-03/10; stream AND capture — BUG-23-class).
Subprocess = list-argv only.

# Acceptance criteria  (executable)
- [ ] `bash scripts/dispatch.sh <fixture> --dry-run` output/exit parity with pre-port for: valid spec,
      off-catalog, P8 clash, multi-component files_allowed, secret-in-spec, env-var reference,
      owner_role resolution, pin-without-reason (capture in the completion report).
- [ ] Python unittest for the secret-scan filter and the disjointness check (fixture specs → verdicts).
- [ ] `bats scripts/test` fully green.

# Out of scope  (binding)
- No behavior changes at all — this is a pure port.

# Stop conditions
- Parity requires reproducing a behavior that looks like a BUG → document, STOP for Lead ruling.
- Any capability seems to need a pip package → STOP, escalate.

# Working notes  (worker appends)
