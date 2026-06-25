# ADR-0018: Coherence enforced by CI fitness functions

- **Status:** Accepted
- **Date:** 2026-06-25
- **Deciders:** Lead (Opus) + human operator

## Context
Docs that *describe* the repo drift from the repo. The architecture map's component/profile inventory and
the session handoff are the worst offenders: every structural change (add/remove a component or profile)
silently invalidates them, and we kept hand-fixing — the dead-reference sweep in analysis Fix 6 was a manual
`grep`. Manual coherence does not scale and is exactly the class of toil the OS should automate.

The proven fix is **generate from a source of truth + verify in CI**: Kubernetes `make generate` +
`hack/verify-*`, Go `go generate` + `git diff --exit-code`, protobuf/OpenAPI/Terraform. Evolutionary
architecture calls the CI half a **fitness function** (Ford/Parsons): a check that fails the build on
architectural drift. We already have the *generate* half — `gen_inventory` discovers `components/*` and
`profiles/*` and writes the `AUTO-INVENTORY` block, made deterministic (timestamp-free) in Step 2.5. This
ADR adds the *verify* half.

## Decision
We will enforce coherence with CI fitness functions. The first (Step 4.1, this ADR) is
`scripts/verify-coherence.sh`; graph-integrity (4.2) and dead-link (4.3) scans extend the same decision.

- **One generator, two callers.** `gen_inventory` (+ a `block_inclusive` reader) live in `_lib.sh`, shared
  by `handoff.sh` (the *writer*) and `verify-coherence.sh` (the *checker*) — they cannot disagree.
- **Block compare, not whole-file diff.** `verify-coherence.sh` compares the `AUTO-INVENTORY` block *as it
  is in each doc* against a fresh `gen_inventory`, and fails on any difference. It is git-independent and
  mutates nothing.
- **Only deterministic blocks are checked.** `AUTO-STATE` / `AUTO-SHIPPED` carry a timestamp + live git/PR
  state and cannot be reproduced in CI; they are out of scope by design. (This is *why* the inventory was
  made timestamp-free in Step 2.5 — the prerequisite for this gate.)
- **Two enforcement points.** Merge-blocking in `os-ci` (the `os` job); pre-push in `scripts/ci-local.sh`.
  Pinned by `scripts/test/coherence.bats` (clean→pass · hand-edit→fail · change-without-regen→fail ·
  prose-edit→still-pass).
- **Remediation is one command:** a failure tells the operator to run `bash scripts/handoff.sh` and commit.

## Consequences
- Generated docs can no longer silently rot: a hand-edit of a generated block, or a structural change made
  without regenerating, fails CI with a fix-it message. Fix 6's manual grep becomes an automatic gate.
- New rule (CI-enforced): adding/removing a component or profile requires running `handoff.sh`.
- `gen_inventory`'s output is now OS API surface (two callers + a test): changing it is a deliberate change
  — update the generator, regenerate the docs, and the bats pins move with it.
- Scope today is the inventory block; 4.2/4.3 land referential-integrity + dead-link checks under this ADR.

## Alternatives considered
- **Regenerate-in-place + whole-file `git diff --exit-code`** (the literal k8s pattern). Our generated docs
  are *mixed* (hand-written prose + one generated block) and `ci-local.sh` runs against a *dirty* tree, so a
  whole-file diff false-fails on legitimate prose edits (it would have on Fix 6). Block compare avoids it.
- **A pre-commit hook only.** Local, bypassable, not authoritative. CI is the gate; `ci-local.sh` mirrors it.
- **Keep it manual (status quo).** Already cost repeated hand-fixes; doesn't scale. Rejected.
