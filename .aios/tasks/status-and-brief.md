+++
id = "status-and-brief"
title = "aios status and aios brief: task state derived from git"
files_allowed = ["aios/status.py", "aios/cli.py", "tests/test_status.py"]
contracts = ["architecture/contracts/record.schema.md"]
depends_on = ["approve-and-land"]
blast_radius = "medium"
kind = "feature"
budget_usd = 0.75
+++

## Goal
The operator's cockpit:
- **`aios status`** shows one line per task.
- **`aios brief`** gives the start-of-session summary, and replaces v1's SESSION-HANDOFF file.

Both derive every task's state from git and the local worktrees alone (ADR-0030 rule 3). They never write anything.

## Context
- **Standard library only** (AGENTS.md); ASCII source; fail loud; match the existing style.
- Existing pieces:
  - `config.find_root`, `config.load_project`, `config.paths`;
  - `spec.parse_spec(text, source)`, which raises `SpecError`;
  - `run.base_ref(proj, root)` and `run.worktree_path(paths, proj, task_id)`;
  - `records.read(wt, id)` and `records.load_runs(runs_dir)`.

  Attempts live under `<state>/<project_id>/runs/<id>/<timestamp>/`. A timestamp dir **without** `attempt.json` is a
  worker still running, or one that crashed.
  - `gateway.Gateway(key, privacy=...).key_info()` returns `usage_daily` and `limit_remaining`.
- **A record:** `gate`, `flags`, `approval`, `usd_total`, `summary`, and `attempts[-1]["verdict"]`
  (`verdict`, `risk`, `blocking`).
- **ADR-0030 rule 3:**
  - a spec without a record is ready;
  - a live `aios/<id>` worktree is in flight;
  - a record on the default branch is done;
  - a record removed by a revert is rolled back.

## Required changes
1. **New `aios/status.py`:**
   ```python
   STATES = ("needs-you", "in-flight", "ready", "blocked", "done", "rolled-back", "invalid")

   @dataclass(frozen=True)
   class Task:
       id: str
       title: str
       state: str
       detail: str

   def tasks(root: Path, *, refresh: bool = True, out=print) -> list[Task]: ...
   def status(root: Path, *, out=print) -> int: ...
   def brief(root: Path, *, gw=None, out=print) -> int: ...
   ```
   - **`tasks(root)`:**
     1. If the project has a remote and `refresh` is true, run `git fetch --quiet <remote>` with a 60 s timeout. A
        failure prints `(offline: using cached <base>)` once and goes on.
     2. Read every `.aios/tasks/*.md` on `base = run.base_ref(...)` with `git ls-tree --name-only <base> .aios/tasks/`
        and `git show <base>:<path>`. Never read the working tree. A spec that fails to parse becomes state
        `invalid`, with the error as its detail.
     3. Classify each spec, in this order:
        - **`done`:** `<base>:.aios/records/<id>.json` exists. Detail:
          `gate <gate> | verdict <verdict> | $<usd_total .4f>`, plus ` | approved by <by>` when approved.
        - **`rolled-back`:** no record on base, but `git log -1 --format=%h <base> -- .aios/records/<id>.json` finds
          a commit, because the record once existed. Detail: `record removed in <hash>`.
        - **The worktree exists:**
          - The latest run dir has no `attempt.json`: `in-flight`, `worker running (or crashed) since <dir name>`.
          - No record in the worktree: `in-flight`, `attempt <n>: <exit>; next: aios gate`.
          - A record whose verdict is `pass`:
            - approved, or gate `AUTO`: `needs-you`, `ready to land: aios land`;
            - otherwise: `needs-you`, `gate <gate>: needs aios approve`. For `HUMAN`, say it needs the operator.
          - A record whose verdict is `fail`: `needs-you`, `verdict fail: <first blocking item, at most 100 chars>`.
          - A record whose verdict is `needs_decision`: `needs-you`, `the verifier needs a decision`.
        - **Otherwise,** by `depends_on`:
          - every dependency is `done`: `ready`;
          - else `blocked`, detail `waiting on <ids>`.
     4. Return the tasks sorted by `STATES` order, then by id.
   - **`status(root)`:** print one line per task, `<id padded to 6>  <state padded to 11>  <title>  | <detail>`.
     Return 0.
   - **`brief(root, gw=None)`:**
     1. A first line with the counts per state, for the states present.
     2. Then sections, each printed only when non-empty:
        - `Needs you:` (`needs-you` and `invalid` tasks);
        - `In flight:`;
        - `Ready next:`;
        - `Recently landed:` (the 5 newest records on base, by `git log --diff-filter=A` order on `.aios/records/`).
     3. A last line:
        `spend: today $<usage_daily .2f> of $<per_day_usd .2f> | this month $<usage_monthly .2f> of $<per_month_usd .2f> | key $<limit_remaining .2f> left`.
        - The monthly budget comes from `config.load_machine(paths).per_month_usd`. When it is not set, print
          `of (not set: run aios doctor --fix)` in its place.
        - When `limit_remaining` is null, print `key: no limit` instead.
        - `gw` defaults to a real Gateway when the key exists.
        - Any error while reading spend prints `spend: unavailable (<reason>)` instead. It never fails the command.

     Return 0.
2. **`aios/cli.py`:** add `aios status` and `aios brief`, both run from inside the project (`config.find_root(Path.cwd())`).
   Outside a project, report a `ConfigError` (exit 2).

## Acceptance criteria
- `tests/test_status.py` (unittest, temp repos only, never the network) uses a local repo, with no remote, holding
  specs on `main`. It covers every state:
  - `ready`, and `blocked` by a dependency that is not done;
  - `in-flight`, both while running (a run dir without `attempt.json`) and after an attempt;
  - every `needs-you` variant: pass with AUTO, pass needing approval, HUMAN, fail and needs_decision;
  - `done`, from a record committed on `main`;
  - `rolled-back`, from a record added and then removed on `main`;
  - `invalid`, from a spec that does not parse.

  It also checks:
  - `status` never writes: `git status --porcelain` and every HEAD are unchanged;
  - `brief`'s sections and its spend line, with a fake gateway, and `spend: unavailable` when `key_info` raises;
  - the CLI wiring.
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/status.py` has at most 150 non-blank, non-comment lines.

## Out of scope
`tail`, `report`, `stop` and `resume` (later the status work tasks); any change to other modules.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.

## Amendments
- 2026-10-23, Lead, before dispatch: the spend line includes the monthly budget (monthly-budget-setup and
  budget-governor have landed).
