+++
id = "budget-governor"
title = "Budget governor: month, day and task caps before every attempt; attempt time ignores host sleep"
files_allowed = ["aios/run.py", "aios/harness.py", "aios/cli.py", "tests/test_budget.py", "tests/test_dispatch.py", "tests/test_gate_run.py", "tests/test_land.py"]
depends_on = ["monthly-budget-setup"]
blast_radius = "high"
kind = "feature"
budget_usd = 0.75
+++

## Goal
No worker attempt starts unless the month, the day, the task and the key all have money left. Each attempt's cost
limit is whatever is left (ADR-0034 section 5: money caps, not token caps).

Also make attempt timing ignore host sleep. A laptop that slept overnight recorded `secs: 44103` for a 30-minute
attempt. The timeout itself behaved correctly, because `subprocess` uses the monotonic clock.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`, including its comment rule.
- **Caps:**
  - month: `config.load_machine(p).per_month_usd` (the monthly-budget-setup task);
  - day: `proj.per_day_usd`;
  - task: the spec's `budget_usd`, or else `proj.per_task_usd`.
- **`gateway.Gateway(key, privacy=...).key_info()`** returns OpenRouter's `/key` data. It costs nothing. The fields used
  here are `usage_monthly`, `usage_daily` and `limit_remaining` (null for a key with no limit).
- **Money already spent on a task:**
  - its attempts: `records.load_runs(runs_dir)` gives `[{"decision": ..., "attempt": {"usd": ...}}, ...]`;
  - the reviewer's cost, when the worktree already has a committed record: `record["attempts"][-1]["verdict"]["usd"]`.
- **Existing tests** run `run.dispatch` through one helper per file: `Dispatch.dispatch` in `tests/test_dispatch.py`
  and `Env.dispatch` in `tests/test_gate_run.py`. Tests must never use the network.

## Required changes
1. **`aios/run.py`:**
   ```python
   class BudgetError(RuntimeError): ...
   MIN_ATTEMPT_USD = 0.05

   def task_spent(runs: list[dict], record: dict | None) -> float: ...
   def budget_left(gw, proj, s, machine, runs: list[dict], record: dict | None) -> float: ...
   ```
   - **`task_spent`** is the sum of every attempt's `usd`, plus the record's last verdict `usd` when there is one,
     rounded to 6 decimals.
   - **`budget_left`** makes one `key_info()` call. It returns the smallest of:
     - the task's remaining cap;
     - the day's remaining cap (`per_day_usd - usage_daily`);
     - the month's remaining cap (`per_month_usd - usage_monthly`), when `per_month_usd` is set;
     - `limit_remaining`, when it is not null.

     It raises `BudgetError` when that smallest value is below `MIN_ATTEMPT_USD`. The message names the cap that ran
     out and shows the numbers, for example `<id>: the month's budget is spent ($19.98 of $20.00)`. Otherwise it
     returns the value rounded to 4 decimals.
   - **`dispatch(..., gw=None)`** gets a new keyword argument.
     - After the dry-run return, and **before** the worktree is created:
       - `gw = gw or gateway.Gateway(config.load_key(p), privacy=gateway.privacy_of(proj))`;
       - compute `left = budget_left(...)`;
       - print `  budget: $<left .4f> for this attempt`.
     - Pass `cost_limit=left` to `harness.run`.
     - When the budget refuses, no worktree and no branch are created.
2. **`aios/harness.py`:** measure `secs` with `time.monotonic()` everywhere `harness.run` computes it.
3. **`aios/cli.py`:** report `run.BudgetError` like the other errors (exit 2, `aios: ...`).
4. **Existing test helpers:** in `tests/test_dispatch.py`, `tests/test_gate_run.py` and `tests/test_land.py`, the one
   dispatch helper of each file passes `gw=` a fake whose `key_info()` returns
   `{"usage_daily": 0.0, "usage_monthly": 0.0, "limit_remaining": None}`. Change nothing else in those files.

## Acceptance criteria
- `tests/test_budget.py` (unittest, temp dirs only, never the network) covers:
  - `task_spent`, with and without a record verdict;
  - `budget_left`: each of the four limits being the smallest one, the month being skipped when no monthly budget
    is set, a null `limit_remaining` being ignored, and `BudgetError` naming the exhausted cap;
  - `dispatch` passing `cost_limit` equal to `budget_left` to the harness;
  - `dispatch` with the month spent: `BudgetError`, no worktree, no `aios/<id>` branch, and no harness call;
  - `harness.run` measuring `secs` with `time.monotonic` and not `time.time` (patch both clocks with values that
    diverge);
  - `aios dispatch` printing `aios: ...` and exiting 2 on a `BudgetError`.
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/run.py` has at most 140 non-blank, non-comment lines.

## Out of scope
Fix rounds, choosing reviewers, the gate, and any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.

## Amendments
- 2026-10-23, Lead, before dispatch: `tests/test_land.py` also dispatches tasks, through its `Env.dispatch` helper.
  It is granted, and its helper gets the same fake gateway.
