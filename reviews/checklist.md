# Standing Review Checklist  (manual §9.4)

Applied at the gate. Most diffs clear CI + a clean cross-family QA pass and auto-merge. The Lead
sees ONLY diffs the risk router flagged. The HUMAN-REQUIRED items below are hard stops the gate
must never auto-approve.

## Every diff (the Verifier checks; gate.sh enforces the mechanical ones)
- [ ] Meets the spec's acceptance criteria — observably, not just asserted.
- [ ] No file outside the spec's `files_allowed` was touched.
- [ ] `files_allowed` (and the diff) stay within ONE component; no cross-component import (ADR-0002).
- [ ] No contract/schema/interface changed implicitly.
- [ ] No new dependency that isn't in `deps_preapproved`.
- [ ] Tests added/updated; diff coverage ≥ 90%; lint + typecheck pass; secret-scan clean.
- [ ] No acceptance test weakened, skipped, or deleted to make the suite pass.
- [ ] Stays within "Out of scope" — no gold-plating.

## Lead gate (risk-routed diffs only — prompts/code-review.md Opus-gate addendum)
- [ ] Honors the relevant contracts & invariants; abstraction is right-sized.
- [ ] Security + failure modes for THIS change are sane.
- [ ] Reversible; no data-shape lock-in without an ADR.

## HUMAN-REQUIRED — hard stops (gate may NEVER auto-approve; escalate to the human)
- [ ] Auth / authorization changes.
- [ ] Payments / money movement.
- [ ] Secrets / credential handling.
- [ ] PII handling or storage.
- [ ] Production data migration.
- [ ] Public API or any contract-breaking change.
