+++
id = "forge-cleanup-fix"
title = "forge: remote-branch cleanup tolerates GitHub's delete-on-merge"
files_allowed = ["aios/forge.py", "tests/test_forge.py"]
depends_on = ["forge-merge"]
blast_radius = "medium"
kind = "bugfix"
budget_usd = 0.25
+++

## Goal
Fix a bug found by the first live run of `forge.GitHub.land` (PR #106).

The PR merged, but `land` then raised. GitHub's `deleteBranchOnMerge` had already deleted the head branch, so the
forge's own `git push --quiet origin --delete aios/forge-merge` was rejected with:
```
 ! [remote rejected] aios/forge-merge (cannot lock ref 'refs/heads/aios/forge-merge': unable to resolve reference 'refs/heads/aios/forge-merge')
```
The cleanup only tolerates `remote ref does not exist`. As a result, a merged PR is reported as a failure.

## Context
- **Standard library only**; ASCII source; fail loud; match the existing style.
- The cleanup lives at the end of `GitHub._merge` in `aios/forge.py`, after the merge commit sha has been read.

## Required changes
1. **`aios/forge.py`:** in the remote-branch cleanup, a `GitError` whose message contains `remote ref does not exist`
   **or** `unable to resolve reference` is ignored. Both mean the branch is already gone. Any other failure still
   raises. Add a one-line comment naming GitHub's delete-on-merge race.
2. **`tests/test_forge.py`:** add a test where the cleanup's `git push ... --delete` raises `git.GitError` carrying
   the rejection text above. `land` must then return the merge sha and not raise.
   - Patch `aios.git.git` so that only the `--delete` push raises; every other git call goes through for real.
   - A local bare remote cannot reproduce this message. It comes from a server-side race, after git's ref listing.

   The existing `test_any_other_cleanup_failure_raises` must still pass.

## Acceptance criteria
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/forge.py` has at most 155 non-blank, non-comment lines.

## Out of scope
Any other change to the forge, and any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
