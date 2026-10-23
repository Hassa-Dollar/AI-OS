+++
id = "test-temp-cleanup"
title = "tests: no leaked temp dirs, no stdout noise"
files_allowed = ["tests/__init__.py", "tests/test_gate_run.py"]
blast_radius = "low"
kind = "tests"
budget_usd = 0.25
+++

## Goal
The test suite leaks every temp dir it creates. After a few days of runs, the developer machine's `/tmp` held about
600 `aios-repo-*` and 2,100 `tmp*` directories (2.3 GB). One test also prints a gate summary line to stdout.

Fix both at the root, in one place, without touching each test.

## Context
- `tests/__init__.py` already creates one throwaway directory per test run (`_SANDBOX`) and points `HOME` and the
  `XDG_*` variables into it (lesson 10). Everything else still uses the system temp dir, and nothing removes anything:
  - `tempfile.mkdtemp` in `tests/helpers.git_repo` and in many test files;
  - `mktemp -d` run as a subprocess in `tests/test_gate_run.py`.
- `unittest discover -s tests -t .` imports `tests/__init__.py` before any test module.

## Required changes
1. **`tests/__init__.py`:**
   - Create `<_SANDBOX>/tmp`, then point both `tempfile.tempdir` and `os.environ["TMPDIR"]` at it, so that every temp
     dir a test (or a subprocess it starts) makes lives under `_SANDBOX`.
   - Register `atexit` removal of `_SANDBOX` with `shutil.rmtree(_SANDBOX, ignore_errors=True)`.
   - Keep the existing HOME/XDG behaviour, and update the module docstring.
2. **`tests/test_gate_run.py`:**
   - Replace the `subprocess.check_output(["mktemp", "-d"], ...)` call with `tempfile.mkdtemp()`.
   - Make `test_cli_gate_builds_the_privacy_aware_gateway` capture stdout with `contextlib.redirect_stdout`, so that
     nothing is printed.

## Acceptance criteria
- `python3 -m unittest discover -s tests -t .` passes and prints no `T-1: verdict ...` line.
- After a full run, no new `aios-repo-*` or `tmp*` directory is left in the system temp dir. To check, count them
  before and after a run with `TMPDIR` unset.

## Out of scope
Any file outside `tests/__init__.py` and `tests/test_gate_run.py`, and deleting the leftovers of earlier runs.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
