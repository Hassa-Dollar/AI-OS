+++
id = "fix-rounds"
title = "aios fix: fix rounds that climb from the same model to the next candidate, then one level up"
files_allowed = ["aios/run.py", "aios/cli.py", "tests/test_fix.py"]
depends_on = ["budget-governor", "router-roles"]
blast_radius = "high"
kind = "feature"
budget_usd = 1.0
+++

## Goal
After a failing review (or a Lead review), run the next worker attempt on the same worktree. The review is appended
to the worker's instructions. The model is chosen by the fix-round ladder. This replaces the Lead's manual
fix-round script.

## The ladder
Read ADR-0031 rule 5 and ADR-0034 sections 2-4. Each step applies only after the one before it.

| Attempt | Who does it |
|---|---|
| dispatch | the routed implementer |
| fix round 1 | the **same model** |
| fix round 2 | the **next cheapest implementer at the same level** not used yet |
| fix round 3 | the **cheapest implementer one level up** (junior to mid, mid to senior; senior stays senior) not used yet |
| after 4 attempts | stop: the operator and the Lead decide |

- Frontier models are ordinary candidates (ADR-0034), so climbing a level needs no switch. The budget governor's caps
  still apply to every attempt.
- An `infra` attempt (exit `"infra"`) is not the model's fault. It is retried once, and never counts.
- A `needs_decision` verdict goes to the Lead. `aios fix` refuses it unless `--review` gives the Lead's decision.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`: the comment rule, and never compress code
  to fit a line cap.
- **`aios/run.py`:** `worktree_path`, `project_id`, `worker_prompt(spec_text, root)`, `_NOT_CACHES`, `route` (do not
  call it here: routing is decided once), `budget_left(gw, proj, s, machine, runs, record)` and `BudgetError`
  (budget-governor). `dispatch` shows how an attempt is run, saved and committed. Reuse its pieces; do not duplicate
  them.
- **`records.load_runs(runs_dir)`** gives `[{"decision": ..., "attempt": {...}}, ...]`, oldest first.
  `records.read(wt, id)` gives the committed record. Its last verdict is `record["attempts"][-1]["verdict"]`, with
  `verdict`, `risk`, `blocking` and `summary`.
- **`decision`** (the first run's) has `level`, `author`, `author_family`, `verifier`, `verifier_family` and `roles`.
- **`catalog.latest(p)`**, **`catalog.load_policy(project=...)`** and
  **`catalog.candidates(live, role="implementer", level=..., policy=..., exclude_families=(...,))`** return
  candidates cheapest first (`.id`, `.family`). `catalog.LEVELS = ("junior", "mid", "senior")`.
- **`harness.run(...)`** returns an `Attempt` with `exit`, `model`, `steps`, `usd`, `secs`, `summary` and `harness`.

## Required changes
1. **`aios/run.py`:** add
   `def fix(spec_path: Path, *, review: Path | None = None, model: str | None = None, gw=None, out=print) -> int`.
   1. **Load.** Load the spec and the project.
      - The worktree must exist, otherwise raise `ConfigError("... dispatch it first")`.
      - `runs` must not be empty. Set `decision = runs[0]["decision"]`.
   2. **Review text.**
      - **With `review`:** the text is `"## Lead review\n\n" + file text`, labelled `Lead review`.
      - **Otherwise** the committed record must exist, else raise `ConfigError("... run 'aios gate' first")`. Then,
        by its last verdict:
        - `pass` raises `ConfigError("<id>: the review passed; nothing to fix")`.
        - `needs_decision` raises `ValueError("<id>: the reviewer needs a decision; that goes to the Lead. Re-run with --review FILE")`.
        - `fail` gives `"## Review: fail (<risk>)\n\n" + one "- <item>" line per blocking item + "\n\n" + summary`,
          labelled `review: fail`.
   3. **Ladder.** Let `n` be the number of runs whose attempt exit is not `"infra"`.
      - `n >= 4` raises `ConfigError("<id>: 4 attempts used; the operator and the Lead decide what happens next")`.
      - **With `model`** (a Lead override): it must be an implementer candidate in the live catalog at any level
        (`level=None`), and not of the reviewer's family. Otherwise raise `ValueError`.
      - **Without a model:**
        - `n == 1`: `decision["author"]`;
        - `n == 2`: the first implementer candidate at `decision["level"]`, excluding the reviewer's family, that no
          run has used;
        - `n == 3`: the same, one level up.
        - If there is none, raise `ConfigError("<id>: no unused implementer at <level>; the Lead decides")`.
   4. **Budget.** `left = budget_left(gw, proj, s, config.load_machine(paths), runs, record)`. `gw` defaults as in
      `dispatch`.
   5. **Run.**
      - Call `harness.run(...)` on the worktree with the chosen model and
        `worker_prompt(spec_text, root) + "\n\n" + review_text`, using `cost_limit=left`, the project's privacy and a
        new timestamped run dir.
      - Write `attempt.json` with the **same decision**: routing is decided once.
      - If the exit is `"infra"`, run **one** more attempt the same way.
   6. **Commit.** Stage and commit exactly as `dispatch` does, with the message
      `<id>: fix round <n> (<label>)\n\nImplemented-By: <model> via <harness>\nRouted: gate <g>, level <l>, router <r>`.
   7. **Report.** Print `<id>: fix round <n> | <model> | <label>` and then `  attempt: <exit> | <steps> steps | $<usd .4f> | <secs>s`.
      Return `0` if the exit is `submitted`, otherwise `4`.
2. **`aios/cli.py`:** add `aios fix <spec> [--review FILE] [--model ID]`.

## Acceptance criteria
- `tests/test_fix.py` (unittest, temp dirs only, never the network) builds a dispatched task as
  `tests/test_gate_run.py` does. It uses the fake harness, a fake gateway for `key_info`, and a scored fake live
  catalog with several implementer candidates at two levels.
- It covers:
  - **fail record, round 1:** the same model; the prompt holds the blocking items and the summary; the commit
    `<id>: fix round 1 (review: fail)`; returns 0;
  - **round 2:** the next cheapest unused model at the same level, never from the reviewer's family;
  - **round 3:** the cheapest unused model one level up;
  - **4 attempts:** refused;
  - **`infra`:** not counted, and retried exactly once;
  - **`pass`:** raises `ConfigError`;
  - **`needs_decision` without `--review`:** raises `ValueError`;
  - **`--review`:** the text reaches the prompt, labelled `Lead review`;
  - **`--model`:** a model from the reviewer's family is refused;
  - **budget:** a `BudgetError` means no attempt runs;
  - **CLI:** `aios fix` parses `--review` and `--model`.
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/run.py` has at most 210 non-blank, non-comment lines.

## Out of scope
The gate, the router, the harness, and any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
