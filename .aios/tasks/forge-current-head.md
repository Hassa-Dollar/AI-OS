+++
id = "forge-current-head"
title = "forge: read check results only for the commit that was pushed, not a stale earlier one"
files_allowed = ["aios/forge.py", "tests/test_forge.py"]
depends_on = ["forge-merge"]
blast_radius = "high"
kind = "bugfix"
budget_usd = 0.5
+++

## Goal
Fix a bug found live while landing reviewer-calibration (lesson 21). The task's pull request was already open, and
its previous commit had a failed CI run. aios pushed a fixed commit, and `GitHub.land`'s first poll still saw the
**old** commit's failed run: GitHub moves a pull request's head a few seconds after a push. The forge then raised
"checks failed" while the new commit's run was only starting, and that run passed.

The same race can happen after `update-branch`: GitHub creates a new head commit asynchronously.

## Context
- **Standard library only**; ASCII source; fail loud. Follow `AGENTS.md`: the comment rule, and never compress code
  to fit a line cap.
- **`aios/forge.py`, `GitHub.land`:**
  - It pushes `<branch>`, opens or reuses the PR, then polls
    `self._view(n, "statusCheckRollup,mergeStateStatus")` until the checks pass or fail.
  - `BEHIND` calls `update-branch` once.
  - `gh pr view <n> --json headRefOid` gives the PR's current head commit sha.
- **The tests** use a fake `gh` that replays scripted JSON per poll, a fake clock, and a local bare remote.

## Required changes
1. **Record the pushed commit.** Right after the push, set `pushed = git rev-parse <branch>` (in the project root).
2. **Read the head on every poll.** Add `headRefOid` to the poll's fields. Read the rollup only when the head is
   current:
   - before any `update-branch`: when `headRefOid == pushed`;
   - after `update-branch`: when `headRefOid` differs from the head seen just before the update. GitHub made a new
     merge commit, whose sha we cannot know in advance.

   While the head is not current, sleep `POLL_S` and poll again. This waiting counts toward `TIMEOUT_S`, but **not**
   toward the BUG-14 grace period (that period is for "the current head has no checks at all").
3. **Remove the stale-`BEHIND` wait.** The head check above covers that race more precisely, so drop the
   `updated_at` / `GRACE_S` wait for a stale `BEHIND` that was added earlier. A `BEHIND` reported for a head that is
   already current after the update raises `ForgeError`, as before.
4. **Keep everything else**, including the merge, the cleanup tolerance and the error messages.

## Acceptance criteria
- `tests/test_forge.py` adds:
  - **A reused PR:** the first poll reports the old head with a FAILED check. The next polls report the pushed head,
    first pending, then passed. The PR merges, and no ForgeError is raised.
  - **After `update-branch`:** one poll still shows the old head as `BEHIND`. Then a new head appears, pending, then
    passed. The PR merges, with `update-branch` called once.
  - **A head that never becomes current:** raises after `TIMEOUT_S`.
  - The existing forge tests still pass, adjusted only where they script `headRefOid`.
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/forge.py` has at most 170 non-blank, non-comment lines.

## Out of scope
Any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
