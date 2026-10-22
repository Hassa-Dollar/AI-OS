+++
id = "D4b"
title = "aios fix: fix rounds on the escalation ladder"
files_allowed = ["aios/run.py", "aios/cli.py", "tests/test_fix.py"]
depends_on = ["D4a"]
blast_radius = "high"
kind = "feature"
budget_usd = 0.75
+++

## Goal
After a gate verdict of `fail`, or a Lead review, run the next worker attempt on the same worktree. The attempt's
prompt has the review appended, and the model is chosen by the escalation ladder (ADR-0031 rule 5, steps 1-3).

This replaces the Lead's manual fix-round script.

## Context
- **Standard library only** (AGENTS.md); ASCII source; fail loud; match the existing style. Reuse `dispatch()`'s
  pieces; do not duplicate them.
- **ADR-0031 ladder:**
  1. `needs_decision` goes to the Lead immediately.
  2. Fix round 1: the same model, with the review appended.
  3. Fix round 2: the next model in the same tier.

  Limits: 3 implement attempts in all. An `infra` attempt (exit `"infra"`) is not the model's fault: it is retried
  once and never counts.
- **Existing pieces:**
  - **`aios/run.py`:**
    - `worktree_path`, `project_id`, `worker_prompt(spec_text, root)`;
    - `_NOT_CACHES` and the commit trailers used by `dispatch()`;
    - `budget_left(gw, proj, s, runs, record)` and `BudgetError` (D4a).
  - **`records.load_runs(runs_dir)`** returns `[{"decision": ..., "attempt": {...}}, ...]`, oldest first.
    `records.read(wt, id)` returns the committed record. Its last verdict is
    `record["attempts"][-1]["verdict"]`, with `verdict`, `risk`, `blocking` and `summary`.
  - **`catalog.load_roster()`** and `catalog.latest(config.paths())` (the cached live catalog; `None` means not
    synced yet).
    - `catalog.eligible(roster, live, role="implement", tier=..., exclude_families=(...,), deny_vendors=..., max_tier=...)`
      returns roster entries cheapest first, with `.id` and `.family`.
  - **`harness.run(...)`** returns an `Attempt` with `exit`, `model`, `steps`, `usd`, `secs`, `summary`, `harness`.

## Required changes
1. **`aios/run.py`:** add
   `def fix(spec_path: Path, *, review: Path | None = None, model: str | None = None, gw=None, out=print) -> int`.
   1. **Load.** Load the spec and the project. The worktree must exist; otherwise raise
      `ConfigError("... dispatch it first")`. `runs = records.load_runs(...)` must not be empty, and
      `decision = runs[0]["decision"]`. Routing is decided once; a fix round never re-routes.
   2. **Review text.**
      - **With `review`** (the Lead's review file): the text is `"## Lead review\n\n" + file text`, labelled
        `Lead review`.
      - **Otherwise:** the committed record must exist, else `ConfigError("... run 'aios gate' first")`. Then, by
        its last verdict:
        - `pass` raises `ConfigError("<id>: the verdict passed; nothing to fix")`.
        - `needs_decision` raises `ValueError("<id>: the verifier needs a decision; that goes to the Lead (ADR-0031). Re-run with --review FILE")`.
        - `fail` gives the text `"## Verifier review: fail (<risk>)\n\n" + one "- <item>" line per blocking item + "\n\n" + summary`,
          labelled `verifier: fail`.
   3. **Ladder.** Let `n` be the number of runs whose attempt exit is not `"infra"`.
      - `n >= 3` raises
        `ConfigError("<id>: 3 implement attempts used (ADR-0031); the Lead decides: re-spec it or hand it to a human")`.
      - **With `model`** (the Lead's override): it must be in the roster with the `implement` role and a family other
        than `decision["verifier_family"]` (P8); otherwise raise `ValueError`.
      - **`n == 1`:** use `decision["author"]`.
      - **`n == 2`:** use the first `catalog.eligible(..., role="implement", tier=decision["tier"], exclude_families=(decision["verifier_family"],), deny_vendors=proj.deny_vendors, max_tier=proj.max_tier)`
        entry not yet used as an author in `runs`.
        - If there is none, raise `ConfigError("<id>: no other <tier> model is eligible; the Lead decides (ADR-0031 step 4)")`.
   4. **Budget.** `left = budget_left(gw, proj, s, runs, record)`, where `record` is the committed record or `None`,
      and `gw` defaults the same way as in `dispatch()`.
   5. **Run.**
      - Call `harness.run(...)` on the worktree with the chosen model and the text
        `worker_prompt(spec_text, root) + "\n\n" + review_text`, using `cost_limit=left`, the project's privacy and a
        new timestamped run dir.
      - Write `attempt.json` there as `{"decision": decision, "attempt": attempt.record()}`.
      - If the exit is `"infra"`, run **one** more attempt the same way, in a new run dir.
   6. **Commit**, exactly as `dispatch()` does: stage with the cache excludes when the exit is `submitted` or
      `limits`, and commit only if something is staged. The message is:
      `<id>: fix round <n> (<label>)\n\nImplemented-By: <model> via <harness>\nRouted: gate <g>, tier <t>, router <r>`.
   7. **Report.** Print
      `<id>: fix round <n> | <model> | <label>`, then
      `  attempt: <exit> | <steps> steps | $<usd .4f> | <secs>s`.
      Return `0` if the exit is `submitted`, otherwise `4`.
2. **`aios/cli.py`:** add `aios fix <spec> [--review FILE] [--model ID]`.

## Acceptance criteria
- `tests/test_fix.py` (unittest, temp dirs only, never the network) builds a dispatched task as
  `tests/test_gate_run.py` does, with the fake harness and a fake gateway for `key_info`. It covers:
  - **A verifier `fail` record:**
    - round 1 uses the same model;
    - the prompt the harness received contains the blocking items and the summary;
    - a commit `<id>: fix round 1 (verifier: fail)` appears;
    - returns 0.
  - **The next round** (`n == 2`) picks the next eligible model in the same tier, never the verifier's family.
    Use a roster and catalog fixture.
  - **The cap:** after 3 counted attempts, raises.
  - **Infra:** `infra` attempts are not counted; one `infra` attempt is retried exactly once.
  - **Refusals:** `pass` raises `ConfigError`; `needs_decision` without `--review` raises `ValueError`.
  - **`--review` text** reaches the prompt, labelled `Lead review`.
  - **`--model`:** a model of the verifier's family is refused.
  - **Budget:** a `BudgetError` from `budget_left` means no attempt runs.
  - **CLI:** `aios fix` parses `--review` and `--model`.
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/run.py` has at most 200 non-blank, non-comment lines.

## Out of scope
Ladder steps 4-6 (tier climbing, frontier models, human hand-off): they stay Lead decisions. Also any change to the
gate or the harness.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
