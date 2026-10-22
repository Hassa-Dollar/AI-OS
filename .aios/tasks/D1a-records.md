+++
id = "D1a"
title = "aios/records.py: build, write and read per-task records"
files_allowed = ["aios/records.py", "tests/test_records.py"]
contracts = ["architecture/contracts/record.schema.md"]
blast_radius = "medium"
kind = "feature"
budget_usd = 0.5
+++

## Goal
Add the module that turns a task's routing decision, worker attempts and verdict into the committed record
`.aios/records/<id>.json` (contract: `architecture/contracts/record.schema.md`), and reads records back.

## Context
- **Standard library only** (AGENTS.md); Python ≥ 3.11. Match the style of the existing `aios/` modules: short
  module docstring, `from __future__ import annotations`, type hints.
- `aios/run.py` (do **not** modify it) already stores every worker attempt on the local machine as
  `<runs_dir>/<timestamp>/attempt.json`, with timestamps like `20261022T001500`. Each file contains
  `{"decision": {...}, "attempt": {...}}`.
  - `decision` keys: `action`, `gate`, `tier`, `task_class`, `author`, `author_family`, `verifier`,
    `verifier_family`, `router`, `confidence`, `reasons`, `answers`.
  - `attempt` keys: `exit`, `model`, `steps`, `usd`, `secs`, `summary`, `harness`.
- Records are committed to public or private repos. They must **never** contain absolute paths or the local username.

## Interface (exact)
```python
RECORD_SCHEMA = 1

def load_runs(runs_dir: Path) -> list[dict]: ...
def build(task_id: str, runs: list[dict], *, spec_blob: str, tool_version: str, roster_version: str = "",
          verdict: dict | None = None, flags: list[str] | tuple[str, ...] = (), gate: str = "AUTO",
          approval: dict | None = None, summary: str = "", lessons: list[str] | tuple[str, ...] = ()) -> dict: ...
def write(worktree: Path, record: dict) -> Path: ...
def read(repo: Path, task_id: str) -> dict | None: ...
```

## Behaviour
1. **`load_runs(runs_dir)`**
   - Returns the parsed `attempt.json` of every direct subdirectory of `runs_dir` that has one, ordered by
     subdirectory name (oldest first).
   - Subdirectories without an `attempt.json` are skipped.
   - A missing `runs_dir` returns `[]`.
2. **`build(...)`** returns a dict with exactly these keys:
   - `record_schema`: `RECORD_SCHEMA`.
   - `task`, `spec_blob`, `tool_version`: passed through.
   - `routing`: taken from the **first** run's decision. Routing is decided once (ADR-0031), and later runs never change it.
     ```
     {router, answers, tier, author: {model, family}, verifier: {model, family},
      gate: <decision gate>, reasons, policy_version: 1, roster_version}
     ```
     If `runs` is empty, `routing` is `None`.
   - `attempts`: one entry per run, in order.
     - Fields: `n` (1-based), `model`, `harness`, `secs`, `steps`, `usd`, `exit`.
     - The **last** entry also gets `verdict` when `verdict` is given.
   - `flags` (as a list), `gate` (the final gate argument, not the router's), `approval`, `summary`, `lessons` (as a list).
   - `usd_total`: the sum of every attempt's `usd`, plus `verdict["usd"]` if the verdict has one, rounded to 6 decimals.
3. **`write(worktree, record)`**
   - Writes `<worktree>/.aios/records/<record["task"]>.json`, creating the directory if needed, and returns the path.
   - Format: `json.dumps(record, indent=1, sort_keys=True) + "\n"`.
   - **Redaction:** before writing, every string anywhere in the record (nested dicts and lists included) has:
     - every substring matching `(?<![\w.])/(home|Users|root|tmp|mnt|var)/[^\s"'\]\)]*` replaced with `<path>`;
     - the current username (`getpass.getuser()`, only if at least 3 characters long) replaced with `<user>`.

     The caller's dict must not be mutated.
4. **`read(repo, task_id)`** returns the parsed `.aios/records/<task_id>.json`, or `None` if it doesn't exist.

## Acceptance criteria
- `tests/test_records.py` (unittest, temp dirs only) covers every numbered behaviour above, including:
  - `load_runs`: order, skipped subdirectories, missing directory;
  - `build`: routing taken from the first run, verdict only on the last attempt, `usd_total` including the verdict's
    usd, empty `runs`;
  - `write`: redaction of a home path, a `/tmp/...` path and the username; no mutation of the input dict;
  - `read`: round-trip, and `None` when the record is absent.
- `python3 -m unittest discover -s tests -t .` passes from the repo root.
- `aios/records.py` has at most 110 non-blank, non-comment lines and imports only the standard library.

## Out of scope
Any other module, CLI wiring, and git commits of records (the gate does those in D1c).

## Stop conditions
If the contract and this spec disagree in a way that blocks you, stop and reply `ESCALATE: <reason>`.
