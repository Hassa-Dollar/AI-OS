+++
id = "D4a"
title = "Budget governor: task and day caps before every attempt; attempt time ignores host sleep"
files_allowed = ["aios/run.py", "aios/harness.py", "aios/cli.py", "tests/test_budget.py", "tests/test_dispatch.py", "tests/test_gate_run.py"]
depends_on = ["D1c"]
blast_radius = "high"
kind = "feature"
budget_usd = 0.5
+++

## Goal
Enforce the money caps that `project.toml` already declares (ADR-0031 rule 5). No attempt starts unless the task's
budget and the day's budget both have room. Each attempt's harness cost limit is whatever is left.

Also make attempt timing ignore host sleep. A WSL2 host that was suspended overnight recorded `secs: 44103` for a
30-minute attempt. The timeout itself behaved, because `subprocess` uses the monotonic clock.

## Context
- **Standard library only** (AGENTS.md); ASCII source; fail loud; match the existing style.
- **Caps:**
  - `proj.per_task_usd` and `proj.per_day_usd` (`config.Project`);
  - a spec's `budget_usd`, which overrides `per_task_usd` when set.
- **`gateway.Gateway(key, privacy=...).key_info()`** returns OpenRouter's `/key` data. It costs nothing. The fields
  used here:
  - `usage_daily`: dollars spent today on this key, across all projects;
  - `limit_remaining`: the credit left, or `None` for a key without a limit.
- **Spend already made on a task:**
  - its attempts: `records.load_runs(runs_dir)` returns `[{"decision": ..., "attempt": {"usd": ..., ...}}, ...]`;
  - the verifier's cost in the committed record, when one exists in the worktree: `record["attempts"][-1]["verdict"]["usd"]`.
- **Existing tests run `run.dispatch` through one helper per file:**
  - `Dispatch.dispatch` in `tests/test_dispatch.py`;
  - `Env.dispatch` in `tests/test_gate_run.py`.

  Tests must never use the network.

## Required changes
1. **`aios/run.py`:**
   ```python
   class BudgetError(RuntimeError): ...
   MIN_ATTEMPT_USD = 0.05

   def task_spent(runs: list[dict], record: dict | None) -> float: ...
   def budget_left(gw, proj, s, runs: list[dict], record: dict | None) -> float: ...
   ```
   - **`task_spent`** returns the sum of every run's `attempt["usd"]`, plus the record's last verdict `usd` when the
     record has one, rounded to 6 decimals.
   - **`budget_left`** computes three limits:
     - `task_left = (s.budget_usd or proj.per_task_usd) - task_spent(runs, record)`;
     - `day_left = proj.per_day_usd - usage_daily`, from one `gw.key_info()` call;
     - the credit, `limit_remaining`, when it is not `None`.

     If the smallest of them is below `MIN_ATTEMPT_USD`, it raises:
     `BudgetError(f"{s.id}: no budget left: task ${spent:.4f} of ${cap:.2f}, today ${usage_daily:.4f} of ${per_day:.2f}, credit {credit}")`.
     Otherwise it returns that smallest limit, rounded to 4 decimals.
   - **`dispatch(..., gw=None)`** gets a new keyword argument.
     - After the dry-run return, and **before** the worktree is created:
       - `gw = gw or gateway.Gateway(config.load_key(p), privacy=gateway.privacy_of(proj))`;
       - `left = budget_left(gw, proj, s, [], None)`;
       - print `  budget: $<left .4f> for this attempt`.
     - Pass `cost_limit=left` to `harness.run`; it currently gets `s.budget_usd or proj.per_task_usd`.
     - A refused budget creates no worktree and no branch.
2. **`aios/harness.py`:** measure `secs` with `time.monotonic()`, in both places where `harness.run` computes it.
3. **`aios/cli.py`:** report `run.BudgetError` like the other errors (exit 2).
4. **Existing test helpers:** in `tests/test_dispatch.py` and `tests/test_gate_run.py`, the one dispatch helper of
   each file passes `gw=` a fake whose `key_info()` returns `{"usage_daily": 0.0, "limit_remaining": None}`. Change
   nothing else in those files.

## Acceptance criteria
- `tests/test_budget.py` (unittest, temp dirs only, never the network) covers:
  - `task_spent`, with and without a record verdict;
  - `budget_left`:
    - the task, the day or the credit each being the binding limit;
    - `limit_remaining: None` being ignored;
    - `BudgetError` below `MIN_ATTEMPT_USD`, with the numbers in its message;
  - `dispatch`:
    - passes `cost_limit` equal to `budget_left`'s result to the harness;
    - with the day spent, raises `BudgetError`, leaves no worktree and no `aios/<id>` branch, and never calls the harness;
  - `harness.run`'s `secs` follows `time.monotonic` and not `time.time`. Patch both clocks with diverging values.
  - `aios dispatch` prints `aios: ...` and exits 2 on a `BudgetError`.
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/run.py` has at most 140 non-blank, non-comment lines.

## Out of scope
Fix rounds and the ladder (D4b), the gate, any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
