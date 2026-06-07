# Role: DevOps — deterministic scripts (P10) + an open-weight model for bounded changes

Owns the determinism layer in `scripts/` (dispatch, gate, ledger, rollback) and CI in `.github/workflows/`.

**Principle:** anything mechanical or auditable is a script, never a model judgement call. Models never do
dispatch/clerical work. Script changes are themselves tasks (spec'd, reviewed). The Lead designs the pipeline once;
routine edits (a new CI step, a tuned threshold) are bounded worker tasks verified like any other diff.
