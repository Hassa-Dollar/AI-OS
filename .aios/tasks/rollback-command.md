+++
id = "rollback-command"
title = "aios rollback: revert a landed task through the forge"
files_allowed = ["aios/land.py", "aios/cli.py", "tests/test_rollback.py"]
depends_on = ["approve-and-land"]
blast_radius = "high"
kind = "feature"
budget_usd = 0.5
+++

## Goal
Roll a landed task back. The revert travels through the project's forge like any other change, and it removes the
task's record together with its code. Per ADR-0030 rule 3, git then shows the task as "rolled back", which is how P9
("stays merged") is measured.

## Context
- **Standard library only** (AGENTS.md); ASCII source; fail loud; match the existing style.
- Existing pieces. Read them first; do not rewrite them.
  - **`aios/land.py`** (approve-and-land): its loading helpers.
  - **`aios/forge.py`:** `for_project(proj).land(branch, title, body)` returns the merge sha. Both forges land with a
    **merge commit**: `--no-ff` locally, `gh pr merge --merge` on GitHub.
  - **`aios/run.py`:** `base_ref`, `worktree_path`.
  - **`aios.git`:** `git(...)` and `remote_url(repo, remote)`.
- **Verified git behaviour** (the Lead checked these):
  - `git log --first-parent --diff-filter=A --format=%H -1 <base> -- .aios/records/<id>.json` prints the merge commit
    that landed the task;
  - `git revert -m 1 --no-edit <merge>` removes both the task's code and its record.

## Required changes
1. **`aios/land.py`:** add `def rollback(spec_path: Path, *, forge=None, out=print) -> int`.
   1. Load the spec and the project. No worktree is needed.
      - If the project has a remote (`git.remote_url(root, proj.remote)`), first run `git fetch --quiet <remote>`
        in the root.
      - `base = run.base_ref(proj, root)`.
   2. Find the land merge with the `git log` command above. If there is none, raise
      `ConfigError("<id>: no landed record on <base>")`.
   3. Create the revert worktree:
      - `rwt = run.worktree_path(paths, proj, f"{s.id}-revert")` on the branch `aios/<id>-revert`. An existing
        `rwt` raises `ConfigError`.
      - In the root, run `git worktree add --quiet -b aios/<id>-revert <rwt> <base>`.
      - In `rwt`, run `git revert -m 1 --no-edit <merge>`.
      - If the revert fails:
        - run `git revert --abort` in `rwt`;
        - remove the worktree and the branch;
        - raise `ConfigError("<id>: the revert conflicts with later changes; revert it by hand")`.
   4. Land it: `forge = forge or forge_mod.for_project(proj)`, then
      `sha = forge.land("aios/<id>-revert", f"Revert {s.id}: {s.title}", body)`. The body is:
      `Rolls back <id> (merge <merge[:12]>). The revert removes .aios/records/<id>.json, so the task reads as rolled back (ADR-0030 rule 3).`
   5. Cleanup: `git worktree remove <rwt>` and `git branch -D aios/<id>-revert`, both run in the root.
   6. Print `<id>: rolled back by <sha[:12]>` and return `0`.
2. **`aios/cli.py`:** add `aios rollback <spec>`.

## Acceptance criteria
- `tests/test_rollback.py` (unittest, temp dirs and repos only) uses a local-forge project.
  - Set it up by landing a task through `land.land`, as `tests/test_land.py` does.
  - **Cases:**
    - **Normal rollback:** `rollback` returns 0.
      - The main checkout's HEAD is a merge whose tree no longer has the task's change or
        `.aios/records/<id>.json`.
      - The revert worktree and branch are gone.
    - **A task that never landed:** `rollback` raises `ConfigError`.
    - **A conflicting later change on main:** `rollback` raises `ConfigError`.
      - Main is unchanged.
      - No revert worktree or branch is left behind.
    - **An injected fake forge** receives the `aios/<id>-revert` branch, the `Revert <id>: ...` title and the body.
    - **CLI:** `aios rollback` is wired to `land.rollback`.
- The existing tests still pass: `python3 -m unittest discover -s tests -t .`.
- `aios/land.py` has at most 150 non-blank, non-comment lines.

## Out of scope
Any change to `aios/forge.py` or `aios/gate.py`; rolling back several tasks at once; ladder logic (the budget-and-fix-rounds work).

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.

## Amendments
- 2026-10-23, Lead review:
  - **A second rollback is refused in plain words.** After a rollback the record is gone from the base, but the
    `git log` search above still finds the old land merge. Reverting it again fails with "nothing to commit", and the
    operator would wrongly read "the revert conflicts with later changes". So, once the merge is found and before the
    revert worktree is created, check that the record is still on the base:
    `git ls-tree --name-only <base> -- .aios/records/<id>.json` prints nothing when it is gone. In that case raise
    `ConfigError("<id>: already rolled back on <base>; nothing to revert")`.
  - **The conflict message gives the hand command.** It becomes
    `"<id>: the revert conflicts with later changes; revert it by hand: git revert -m 1 <merge[:12]>"`.
  - **Tests:**
    - a second rollback after a successful one raises that `ConfigError`, and no revert worktree or branch is left
      behind;
    - the conflict test checks the `git revert -m 1 <merge[:12]>` hint.
  - `aios/land.py` may have at most 158 non-blank, non-comment lines. Lesson 20: readable over compressed.
