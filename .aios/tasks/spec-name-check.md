+++
id = "spec-name-check"
title = "aios spec rejects coded task names; CI checks every task's name"
files_allowed = ["aios/spec.py", "aios/cli.py", "tests/test_spec.py", "tests/test_cli.py", ".github/workflows/ci.yml"]
contracts = ["architecture/contracts/spec.schema.md"]
blast_radius = "medium"
kind = "feature"
budget_usd = 0.5
+++

## Goal
The operator reads task names in `.aios/tasks/` and `.aios/records/`. A name must say what the task does: 2 to 6
lowercase words joined by hyphens, such as `approve-and-land`. Codes like `D2b` or `H1` meant nothing to them, so
every existing task was renamed. This task makes aios refuse coded names from now on.

Read the `id` row of `architecture/contracts/spec.schema.md`.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`: the comment rule, and never compress code
  to fit a line cap.
- **`spec.parse_spec` stays as it is.** Many tests build throwaway specs with ids like `T-1`, and runtime parsing
  must keep accepting them. The naming rule is checked by the `aios spec` command, and in CI.
- **`aios/cli.py`, `cmd_spec(args)`:** it validates each file with `spec.load_spec`, prints `ok      <file>  <id>: <title>`
  or `FAIL    <error>`, then reports `OVERLAP` lines for file grants shared between specs. It returns 2 when there is
  any problem.
- **Done tasks share file grants by nature** (two finished tasks both edited `aios/gate.py`), so a check over every
  spec must skip the overlap report.

## Required changes
1. **`aios/spec.py`:**
   ```python
   NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+){1,5}$")

   def name_problem(s: Spec, path: str | None = None) -> str | None: ...
   ```
   It returns None when `s.id` matches `NAME_RE`, is at most 50 characters, and (when `path` is given) equals the
   file's stem. Otherwise it returns one plain sentence naming the problem, for example
   `"'D2b' is not a descriptive name: use 2 to 6 lowercase words joined by hyphens, such as approve-and-land"` or
   `"the file is named x.md but the id is y; name the file <id>.md"`.
2. **`aios/cli.py`:**
   - **`aios spec`** applies `name_problem` to each spec that loads. A problem prints `FAIL    <file>: <sentence>`
     and counts as a problem.
   - **A new flag, `--names`,** keeps the load and name checks and skips the overlap report.
3. **`.github/workflows/ci.yml`:** add a step named `task names`, after the unit tests, that runs
   `python3 bin/aios spec --names .aios/tasks/*.md`. Keep the existing steps unchanged.

## Acceptance criteria
- `tests/test_spec.py` covers `name_problem` with:
  - good names;
  - codes (`D2b`, `H1`);
  - uppercase, a single word, seven words, and more than 50 characters;
  - an id that differs from the file's name.
- `tests/test_cli.py` (or `tests/test_spec.py`) covers:
  - `aios spec` failing on a coded name with the sentence;
  - `--names` skipping the overlap report;
  - the default still reporting overlaps.
- `python3 bin/aios spec --names .aios/tasks/*.md` passes on the current repository: every task already has a
  descriptive name.
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/spec.py` has at most 195 non-blank, non-comment lines.

## Out of scope
Changing `parse_spec`'s id rule, renaming anything, and any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
