+++
id = "reviewer-confirm"
title = "Review: a fail counts only when a second review confirms it; the reviewer's token budget comes from money"
files_allowed = ["aios/review.py", "aios/gate.py", "tests/test_review.py", "tests/test_gate_run.py"]
contracts = ["architecture/contracts/record.schema.md"]
depends_on = ["router-roles", "reviewer-calibration"]
blast_radius = "high"
kind = "feature"
budget_usd = 1.0
+++

## Goal
ADR-0034 section 6 (read it) and section 5. Two changes to how the gate asks for a review:
1. **A `fail` counts only when a second, independent review confirms it.** Reviewers sometimes fail good code on
   speculation. It happened four times on 2026-10-22, while no reviewer ever passed buggy code in calibration. So:
   - a first `fail` triggers one more review;
   - the second review comes from the cheapest **calibrated** reviewer of yet another family when one exists,
     otherwise from the same model;
   - the change fails only if both reviews say `fail`;
   - both reviews are kept in the record.
2. **No fixed token cap.** Each review call's `max_tokens` is what the task's remaining money can pay for at that
   model's output price, up to the model's own maximum.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`: the comment rule, and never compress code
  to fit a line cap.
- **`aios/gate.py`:**
  - `verify(gw, model, spec_text, diff_text, checks)` makes one review call and returns
    `{verdict, risk, blocking, summary, verifier, usd}`. It passes `max_tokens=VERIFIER_MAX_TOKENS` (32000).
  - `run_gate` calls `verify` once when nothing is out of scope and every check passed.
  - It knows `d = runs[0]["decision"]` (with `author_family` and `verifier_family`), the spec, the project and
    `paths`.
- **Existing pieces:**
  - `catalog.latest(p)` returns the live catalog (model dicts with `pricing.completion`, USD per token, and
    `top_provider.max_completion_tokens`);
  - `catalog.load_policy()`;
  - `catalog.candidates(live, role="reviewer", level=None, policy=..., exclude_families=...)`, cheapest first
    (`level=None` means no score minimum);
  - `calibrate.passed(p, model)`.
- **The task's budget:** the spec's `budget_usd`, or else `proj.per_task_usd`. What is already spent is the sum of the
  attempts' `usd` in `runs`.
- **Record contract:** the verdict may carry `reviews` (one entry per review call) and `confirmed_by`.

## Required changes
1. **`aios/gate.py`:** `verify(..., max_tokens: int | None = VERIFIER_MAX_TOKENS)`. Pass the value through to
   `gw.chat`. Nothing else in `verify` changes.
2. **New `aios/review.py`:**
   ```python
   MIN_TOKENS = 4096

   def max_tokens_for(model: str, live: list[dict], usd_left: float) -> int: ...
   def pick_confirmer(p, live: list[dict], policy, *, first: str, exclude_families: tuple[str, ...]) -> str: ...
   def review(gw, model: str, spec_text: str, diff_text: str, checks, *, confirmer: str,
              max_tokens) -> dict: ...
   ```
   - **`max_tokens_for`:**
     - For a model in `live`, compute `int(usd_left / price_per_output_token)`, capped at the model's
       `max_completion_tokens` when known, and never below `MIN_TOKENS`.
     - For a model not in `live`, or with a zero price, return `gate.VERIFIER_MAX_TOKENS`.
   - **`pick_confirmer`:** the first candidate from
     `catalog.candidates(live, role="reviewer", level=None, policy=policy, exclude_families=exclude_families)` for
     which `calibrate.passed(p, id)` holds and which is not `first`. When there is none, it returns `first`.
   - **`review`:**
     1. Call `v1 = gate.verify(gw, model, ..., max_tokens=max_tokens(model))`.
     2. If `v1["verdict"]` is not `"fail"`, return v1 plus `"reviews": [v1 without its own reviews key]`.
     3. Otherwise call `v2 = gate.verify(gw, confirmer, ..., max_tokens=max_tokens(confirmer))`.
     4. **Both fail:** the result is `verdict` `"fail"`, with:
        - `risk`: the higher of the two;
        - `blocking`: v1's items, then v2's items that v1 lacks;
        - `summary`: v1's summary;
        - `verifier`: `model`, and `confirmed_by`: `confirmer`;
        - `usd`: the sum of both;
        - `reviews: [v1, v2]`.
     5. **v2 does not fail:** the result is v2's `verdict`, `risk`, `blocking` and `verifier`, with:
        - `usd`: the sum of both;
        - `reviews: [v1, v2]`;
        - `summary`: v2's summary plus `" (A first review failed this change; a second review did not confirm it.)"`.
3. **`aios/gate.py`, in `run_gate`:** replace the single `verify` call with `review.review(...)`.
   - `usd_left` is the task budget minus what the attempts spent, and at least 0.
   - `max_tokens` is `lambda m: review.max_tokens_for(m, live, usd_left)`, with `live = catalog.latest(paths) or []`.
   - The confirmer comes from `review.pick_confirmer(paths, live, catalog.load_policy(), first=d["verifier"], exclude_families=(d["author_family"], d["verifier_family"]))`.
   - Everything else in `run_gate` is unchanged: the canned fail when checks fail or a file is out of scope, the
     patch binding, the flags and the record.
4. **`tests/test_gate_run.py`:** adjust only the tests whose fake gateway now sees a second call after a `fail`.

## Acceptance criteria
- `tests/test_review.py` (unittest, never the network, fakes for the gateway, catalog and calibration) covers:
  - `max_tokens_for`: money-bound, capped by the model's maximum, the floor, and an unknown model;
  - `pick_confirmer`: another calibrated family; falling back to `first`; skipping an uncalibrated model;
  - `review`:
    - a pass makes one call;
    - fail and fail gives a confirmed fail with merged blocking items and both reviews;
    - fail and pass gives a pass with the note;
    - fail and `needs_decision` gives `needs_decision`;
    - each call's `max_tokens` is right;
    - `usd` is the sum of both calls.
- `tests/test_gate_run.py` gets one end-to-end case: a fake gateway that fails and then passes gives a passing
  record with two `reviews`.
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/review.py` has at most 90 and `aios/gate.py` at most 225 non-blank, non-comment lines.

## Out of scope
Choosing the first reviewer (the router does that), the calibration command, and any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
