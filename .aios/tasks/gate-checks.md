+++
id = "gate-checks"
title = "aios/gate.py: deterministic gate checks (changes, scope, dependencies, checks, flags, tier)"
files_allowed = ["aios/gate.py", "tests/test_gate.py"]
contracts = ["architecture/contracts/spec.schema.md"]
blast_radius = "high"
kind = "feature"
budget_usd = 0.75
+++

## Goal
Add the deterministic half of the gate: the functions that decide whether a task branch may merge, and with
what review, before any model looks at it. The verifier and the `aios gate` command come later (gate-command). Do not
add them.

## Context
- **Standard library only** (AGENTS.md); Python ≥ 3.11. Match the existing modules: module docstring,
  `from __future__ import annotations`, built-in generics, fail loud (never swallow exceptions).
- Use the existing helpers:
  - `aios.git.git(args, cwd, timeout=...)` runs a git command and returns its stdout.
  - `aios.spec.path_allowed(spec, path)` checks a path against the spec's file grants.
  - `aios.harness.sandbox(paths, network=False)` returns `(bwrap_args, env)`.
  - `aios.run.CACHES` lists build-cache directories.
- Review tiers, from least to most review: `AUTO` < `OPERATOR` < `LEAD` < `HUMAN` (ADR-0026, ADR-0031).

## Interface (exact)
```python
TIERS = ("AUTO", "OPERATOR", "LEAD", "HUMAN")
LOCKFILES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "uv.lock", "Cargo.lock")
MAX_FILES, MAX_LINES = 12, 350

@dataclass(frozen=True)
class Changes:
    files: tuple[str, ...]
    authored_lines: int

def changes(wt: Path, base: str) -> Changes: ...
def out_of_scope(spec, task_id: str, files: tuple[str, ...]) -> list[str]: ...
def added_dependencies(wt: Path, base: str, files: tuple[str, ...]) -> list[str]: ...
def flags(spec, files: tuple[str, ...], authored_lines: int, deps_added: list[str], *,
          sensitive_paths: tuple[str, ...] = (), verifier_risk: str | None = None) -> list[tuple[str, str]]: ...
def tier(router_gate: str, flag_list: list[tuple[str, str]]) -> str: ...
def run_checks(paths, wt: Path, component, *, runner=subprocess.run) -> list[tuple[str, int, str]]: ...
```

## Behaviour
1. **`changes(wt, base)`**
   - `files`: the sorted paths changed between the merge base of `base` and `HEAD` (`git diff --name-only base...HEAD`).
     A path is dropped if any of its directory segments is one of the `aios.run.CACHES` names, or if it ends in `.pyc`.
   - `authored_lines`: the sum of added plus removed lines from `git diff --numstat base...HEAD`, counting only the
     files kept above, and excluding any file whose basename is in `LOCKFILES` (lesson #3).
   - Binary files (numstat shows `-`) count 0.
2. **`out_of_scope(spec, task_id, files)`** returns, in order, the files the spec does not grant.
   - `.aios/records/<task_id>.json` (the task's own record) is always allowed.
3. **`added_dependencies(wt, base, files)`** returns the sorted names newly added in this diff, across changed manifests:
   - **`package.json`** (any directory): keys of `dependencies`, `devDependencies`, `peerDependencies` and
     `optionalDependencies` that are present at `HEAD` but not at `base`.
   - **`pyproject.toml`**: the name part of each requirement string in `[project].dependencies` and every list in
     `[project].optional-dependencies` (the name is everything before the first character of `<>=!~;[ `).
   - **`requirements*.txt`**: the same name rule, one requirement per non-comment, non-blank line.

   Details:
   - The base version is read with `git show <base>:<path>`. A manifest that doesn't exist at `base` counts as empty.
   - Names are compared case-insensitively and returned lower-cased.
4. **`flags(...)`** returns `(name, tier)` pairs, in this order, each at most once:
   - `("dependency-change", "LEAD")` if any added dependency is not in `spec.deps_preapproved` (compared case-insensitively);
   - `("touches-contract", "LEAD")` if a file is under `architecture/contracts/` or equals one of `spec.contracts`;
   - `("sensitive-path", "LEAD")` if a file equals, or is under, one of `sensitive_paths`
     (an entry ending in `/` is a directory);
   - `("large-change", "OPERATOR")` if there are more than `MAX_FILES` files or more than `MAX_LINES` authored lines;
   - `("verifier-risk-high", "LEAD")` if `verifier_risk == "high"`.
5. **`tier(router_gate, flag_list)`** returns the highest tier among `router_gate` and all flag tiers, ordered by `TIERS`.
6. **`run_checks(paths, wt, component, runner=...)`** runs each of `component.checks`, in order, inside the worker
   sandbox (no network). For each check, it calls:
   ```
   runner(["bwrap", *args, "--bind", str(wt), str(wt), "--chdir", str(wt / component.path), "bash", "-c", check],
          env=env, capture_output=True, text=True, timeout=1800)
   ```
   with `args, env = harness.sandbox(paths, network=False)`.
   - It returns `(check, returncode, last 2000 characters of stdout+stderr)` for each.
   - It does **not** stop at the first failure.
   - A component whose `checks` is `None` raises `ValueError`, because the gate fails closed (ADR-0030).

## Acceptance criteria
- `tests/test_gate.py` (unittest) covers every numbered behaviour, using throwaway git repos built in temp dirs:
  - `changes`: cache and `.pyc` exclusion, a lockfile not counted in `authored_lines`, a binary file counted as 0;
  - `out_of_scope`: directory grants, and the task's own record being allowed;
  - `added_dependencies`: all three manifest kinds, a manifest new in the diff, case-insensitivity, a removed
    dependency not counted;
  - every flag, including pre-approved dependencies producing no flag;
  - `tier` ordering;
  - `run_checks` with a **fake runner**: argument shape, continuing past a failure, `checks=None` raising.
- `python3 -m unittest discover -s tests -t .` passes from the repo root.
- `aios/gate.py` has at most 150 non-blank, non-comment lines and imports only the standard library and `aios` modules.

## Out of scope
The verifier call, writing records, the `aios gate` CLI command, and changes to any other file.

## Stop conditions
If the interface or behaviour above is contradictory or impossible as written, stop and reply `ESCALATE: <reason>`.
