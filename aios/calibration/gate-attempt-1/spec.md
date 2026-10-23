+++
id = "D1c"
title = "aios gate: verifier verdict, record, and the gate command"
files_allowed = ["aios/gate.py", "aios/run.py", "aios/cli.py", "tests/test_gate_run.py"]
contracts = ["architecture/contracts/record.schema.md"]
depends_on = ["D1a", "D1b"]
blast_radius = "high"
kind = "feature"
budget_usd = 1.0
+++

## Goal
Complete the gate. `aios gate <spec>` runs, on a dispatched task's worktree:
1. the deterministic checks (D1b);
2. a cross-family verifier, which returns a JSON verdict bound to the diff's patch-id;
3. flags and tier;
4. the task record (D1a), written and committed on the task branch.

Merging stays manual; that is D2.

## Context
- **Standard library only** (AGENTS.md); ASCII source; fail loud; match the existing style.
- Use these existing pieces. Read them first; do not rewrite them.
  - **`aios/gate.py`** (D1b): `changes`, `out_of_scope`, `added_dependencies`, `flags`, `tier`, `run_checks`.
  - **`aios/records.py`** (D1a): `load_runs(runs_dir)`, `build(...)`, `write(worktree, record)`.
  - **`aios/gateway.py`**:
    - `Gateway(key, privacy=...)`;
    - `.chat(model, messages, schema=..., max_tokens=...)` returns `{"json": ..., "usd": ..., ...}`;
    - `privacy_of(project)`.
  - **`aios/run.py`**: `dispatch()` already computes the worktree path, the base ref and the component; attempts
    live under `<state>/<project_id>/runs/<task id>/`.
  - **`aios/prompts/verifier.md`**: a `string.Template` with `$spec`, `$checks` and `$diff`. It was written by the
    Lead and must not be edited.

## Required changes
1. **`aios/run.py`**: extract three helpers from `dispatch()` and make `dispatch()` use them. Its behaviour must not
   change; the existing dispatch tests must still pass.
   ```python
   def base_ref(proj, root: Path) -> str: ...          # "<remote>/<default>" if the remote exists, else "<default>"
   def worktree_path(paths, proj, task_id: str) -> Path: ...
   def component_of(proj, spec):                        # the component owning files_allowed (longest path); raises ConfigError if none
   ```
2. **`aios/gate.py`**: add the following.
   ```python
   VERDICT_SCHEMA = {"type": "object", "additionalProperties": False,
                     "required": ["verdict", "risk", "blocking", "summary"],
                     "properties": {"verdict": {"type": "string", "enum": ["pass", "fail", "needs_decision"]},
                                    "risk": {"type": "string", "enum": ["low", "medium", "high"]},
                                    "blocking": {"type": "array", "items": {"type": "string"}},
                                    "summary": {"type": "string"}}}
   def patch_id(wt: Path, base: str) -> str: ...
   def verify(gw, model: str, spec_text: str, diff_text: str, checks: list[tuple[str, int, str]]) -> dict: ...
   def run_gate(spec_path: Path, *, gw=None, out=print) -> int: ...
   ```
   - **`patch_id`**: the first field of `git patch-id --stable` run on the output of `git diff base...HEAD`, or `""`
     for an empty diff.
     - Run `patch-id` through `subprocess.run(["git", "patch-id", "--stable"], input=..., cwd=wt, ...)`, with a timeout.
   - **`verify`**:
     - Renders `verifier.md` with `string.Template(...).substitute(spec=..., checks=..., diff=...)`.
     - `checks` is rendered as one block per check: `$ <command>` / `exit <code>` / the output tail.
     - Calls `gw.chat(model, [{"role": "user", "content": prompt}], schema=VERDICT_SCHEMA, max_tokens=4000)`.
     - Returns `result["json"]` plus `{"usd": result["usd"], "verifier": model}`.
   - **`run_gate(spec_path)`**:
     1. Load the spec and the project (`config.find_root` from the spec's directory). The task's worktree must exist,
        otherwise raise `ConfigError("... dispatch it first")`.
     2. `runs = records.load_runs(<state>/<project_id>/runs/<id>)` must not be empty. `decision = runs[0]["decision"]`.
     3. Compute: `base = run.base_ref(...)`, `ch = changes(wt, base)`, `oos = out_of_scope(spec, id, ch.files)`,
        `deps = added_dependencies(wt, base, ch.files)`, `results = run_checks(paths, wt, run.component_of(...))`.
     4. Call the verifier **only if** there is nothing out of scope **and** every check exited 0.
        - It is called with `decision["verifier"]`, the spec file text, and the diff text.
        - The diff text is `git diff base...HEAD -- . ':(exclude)**/package-lock.json'`, truncated to 60,000
          characters, with `\n[diff truncated]` appended when cut.
        - `gw` defaults to `gateway.Gateway(config.load_key(paths), privacy=gateway.privacy_of(project))`.

        Otherwise, the verdict is:
        ```
        {"verdict": "fail", "risk": "high", "blocking": [one line per out-of-scope file and per failed check],
         "summary": "gate failed before verification", "usd": 0.0, "verifier": None}
        ```
     5. Add `patch_id` and `commit` (`git rev-parse HEAD` in the worktree) to the verdict.
     6. Compute flags:
        - `fl = flags(spec, ch.files, ch.authored_lines, deps, sensitive_paths=project.sensitive_paths, verifier_risk=verdict["risk"])`;
        - if there is anything out of scope, also add `("out-of-scope", "LEAD")`;
        - `final = tier(decision["gate"], fl)`.
     7. Build the record with `records.build(spec.id, runs, ...)`, passing:
        - `spec_blob` = `git hash-object <spec file>` run in the project root;
        - `tool_version = f"aios {aios.__version__}"`;
        - the verdict, the flag names, `gate=final`;
        - `summary` = the verdict's summary.

        Then `records.write(wt, record)`, and in the worktree run `git add .aios/records/<id>.json` and
        `git commit -m "<id>: record (verdict <verdict>, gate <final>)"`.
     8. Print one line, `<id>: verdict <verdict> (<risk>) | gate <final> | flags <names or none> | $<usd>`, then one
        line per blocking item. Return `0` if the verdict is `"pass"`, otherwise `1`.
3. **`aios/cli.py`**: add `aios gate <spec>`, which calls `gate.run_gate` and returns its code.
   `ValueError` from the gate must be reported like the other errors (exit 2), not as a traceback.

## Acceptance criteria
- `tests/test_gate_run.py` (unittest) builds a real dispatched task as `tests/test_dispatch.py` does: a temp repo,
  `run.dispatch` with a mocked `route` and the fake harness from `tests/test_harness.py`. Then:
  - with `gate.run_checks` patched to return passing results, and a **fake gateway** whose `chat()` returns a canned
    verdict, `run_gate` returns 0. The committed record has `gate`, `flags`, the verdict with `patch_id` and `commit`,
    and `usd_total` including the verifier's usd;
  - a failing check, or an out-of-scope file, skips the verifier (the fake `chat` is never called), returns 1, and
    still writes and commits the record;
  - a verifier answering `risk: "high"` makes the gate at least `LEAD`;
  - `run_gate` without a worktree raises `ConfigError`;
  - `patch_id` is stable across a rebase that doesn't change content, and `""` for an empty diff.
- The existing tests, including `tests/test_dispatch.py`, still pass: `python3 -m unittest discover -s tests -t .`.
- `aios/gate.py` has at most 210 non-blank, non-comment lines.

## Out of scope
Merging or pushing branches (D2), fix rounds and the escalation ladder (D4), and editing `aios/prompts/verifier.md`.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
