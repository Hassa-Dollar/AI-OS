---
id: OS-P1
slug: python-speclib
owner_role: autonomous
model: opencode-go/kimi-k2.7-code          # OS task (no component profile) → explicit pins, P8 pairing
verifier_model: opencode-go/deepseek-v4-pro
branch: task/OS-P1-python-speclib
blast_radius: high         # rewrites the parsing core every script depends on
files_allowed:
  - scripts/os/
  - scripts/_lib.sh
  - scripts/test/
  - scripts/doctor.sh
  - docs/INSTALL.md
depends_on_contracts:
  - architecture/contracts/profile.schema.md
deps_preapproved: []       # Python 3 STDLIB ONLY (ADR-0023) — needing pip is a STOP condition
---

# Goal
The OS parsing/resolution core lives in a Python 3 stdlib-only package `scripts/os/`, with `_lib.sh`'s
parsing functions delegating to it — behavior byte-identical, `bats scripts/test` fully green.

# Context (compressed)
ADR-0023 ports the bug-dense "brain" bash to Python (order: this speclib first). ADR-0022 defines the
resolution semantics (owner_role via profile.json; verifier + verifier_secondary; override + reason;
catalog from architecture/catalog.json). The bats suite is the black-box harness: it tests CLI behavior,
not implementation, so it must pass unmodified except where a test asserts bash internals.

# Acceptance criteria  (executable)
- [ ] `scripts/os` (executable) exposes subcommands: `spec get|list <file> <key>`, `roles resolve <spec>`,
      `roles overrides <spec>`, `catalog assert <slug>`, `catalog family <slug>`, `verdict <file> <FIELD>`
      — same outputs/exit codes as today's `fm_scalar`/`fm_list`/`resolve_roles`/`override_of_spec`/
      `assert_in_catalog`/`family_of`/`verdict_field`.
- [ ] `_lib.sh`'s versions of those functions become one-line delegations to `scripts/os` (log/die stay bash).
- [ ] Python unit tests (stdlib `unittest`, `scripts/test/python/`) cover: quoted YAML list items (BUG-02),
      inline comments, verdict last-match-wins (BUG-09), owner_role default, verifier_secondary fallback,
      override precedence, off-catalog fail-closed.
- [ ] `bats scripts/test` green; `bash scripts/dispatch.sh <fixture> --dry-run` output identical pre/post.
- [ ] `scripts/doctor.sh` probes `python3 --version` ≥ 3.10; `docs/INSTALL.md` lists the prerequisite.

# Out of scope  (binding)
- No changes to gate.sh/dispatch.sh beyond what delegation requires (they port in OS-P3/P4).
- No pip dependencies, no pyproject.toml, no type-checker CI step.

# Stop conditions
- A bats test can only pass by changing its assertion → STOP, escalate (behavior contract question).
- Any capability seems to need a pip package → STOP, escalate.

# Working notes  (worker appends)
