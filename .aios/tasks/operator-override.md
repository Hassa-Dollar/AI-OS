+++
id = "operator-override"
title = "aios approve --override: only the operator can overrule a failing review"
files_allowed = ["aios/land.py", "aios/cli.py", "tests/test_land.py"]
contracts = ["architecture/contracts/record.schema.md"]
blast_radius = "high"
kind = "feature"
budget_usd = 0.5
+++

## Goal
Reviewers are sometimes wrong. When the Lead has shown with evidence that a failing review is wrong, the **operator**
(the human) may overrule it. The Lead never can (operator decision, 2026-10-22). The override is recorded next to the
failing verdict, so the record stays honest.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`, including its comment rule.
- **`aios/land.py`** has `approve(spec_path, *, by, note, out=print)` and `land(spec_path, *, forge=None, out=print)`.
  - Today `approve` refuses any verdict other than `pass`.
  - Today `land` requires a `pass` verdict, a matching patch-id, and an approval when the gate is not `AUTO`
    (by the operator for `HUMAN`).
- **Record contract:** `approval = {"by": "operator" | "lead", "note": "...", "override": "<why>"}`. The `override`
  key is optional and new.

## Required changes
1. **`approve(spec_path, *, by, note, override: str | None = None, out=print)`:**
   - Without `override`: unchanged.
   - With `override`:
     - it is accepted only when `by == "operator"`, otherwise `ValueError("<id>: only the operator can override a review")`;
     - and only when the verdict is `fail` or `needs_decision`, otherwise
       `ValueError("<id>: the verdict is pass; nothing to override")`;
     - `override.strip()` must not be empty;
     - the record's gate becomes at least `LEAD` (use `gate.tier`);
     - then `approval = {"by": "operator", "note": note.strip(), "override": override.strip()}`;
     - commit `<id>: approve (operator, override)`;
     - print `<id>: review overridden by the operator | gate <gate>`.
2. **`land`:**
   - A verdict other than `pass` is accepted only when `approval.override` is set and `approval.by == "operator"`.
   - Every other rule stays, including the patch binding and cleanup.
   - The pull request body gets the line `Override: <override>` under the approval line.
3. **`aios/cli.py`:** `aios approve <spec> --by ... --note ... [--override TEXT]`.

## Acceptance criteria
- `tests/test_land.py` gets new tests, using the existing fixtures, for:
  - an operator override of a `fail` verdict, which is recorded and then lands;
  - a Lead override, which is refused;
  - an override of a `pass` verdict, which is refused;
  - an empty override, which is refused;
  - landing a `fail` verdict without an override, which is still refused;
  - the gate being raised to LEAD;
  - the override line in the pull request body;
  - the CLI flag.
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/land.py` has at most 110 non-blank, non-comment lines.

## Out of scope
Any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
