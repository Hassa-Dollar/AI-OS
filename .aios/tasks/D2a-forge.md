+++
id = "D2a"
title = "aios/forge.py: merge a task branch on a local or GitHub forge"
files_allowed = ["aios/forge.py", "tests/test_forge.py"]
depends_on = ["D1c"]
blast_radius = "high"
kind = "feature"
budget_usd = 0.75
+++

## Goal
Add the forge layer (ADR-0030 rule 9). Given a branch that holds a gated task, merge it into the project's default
branch, either on a `local` forge or on `github`. The `aios land`, `approve` and `rollback` commands come later (D2b).
Do not add them.

## Context
- **Standard library only** (AGENTS.md); ASCII source; fail loud; match the style of `aios/git.py` and `aios/run.py`.
- Existing pieces:
  - `aios.git.git(args, cwd, timeout=...)` runs git and returns stdout. It raises `GitError` carrying git's stderr.
  - `aios.git.default_branch(repo, remote)`.
  - `config.Project` has `root`, `forge` (`"github"` or `"local"`), `remote` and `default_branch` (which may be `None`).
    - The default branch is `proj.default_branch or git.default_branch(proj.root, proj.remote)`.
- **GitHub goes through the `gh` CLI, version 2.46.** In that version:
  - `gh pr checks` has no `--json`, so read checks with `gh pr view <n> --json statusCheckRollup,mergeStateStatus`;
  - there is no `gh pr update-branch`, so use the REST endpoint through `gh api` (below).
- **Never put a PR or commit body on the command line** (lesson: no large text in argv). It goes through stdin or a
  temp file outside the repo.

## Interface (exact)
```python
class ForgeError(RuntimeError): ...

def run_gh(args: list[str], cwd: Path, input: str | None = None) -> str: ...

class Local:
    def __init__(self, proj): ...
    def land(self, branch: str, title: str, body: str) -> str: ...

class GitHub:
    POLL_S, GRACE_S, TIMEOUT_S = 15, 90, 3600
    def __init__(self, proj, *, gh=run_gh, sleep=time.sleep, clock=time.monotonic): ...
    def land(self, branch: str, title: str, body: str) -> str: ...

def for_project(proj, **kw) -> Local | GitHub: ...
```

## Behaviour
1. **`run_gh(args, cwd, input)`**
   - Runs `["gh", *args]` with `cwd`, `input`, `capture_output=True`, `text=True` and `timeout=120`.
   - Returns stdout.
   - A non-zero exit raises `ForgeError(f"gh {args[0]} {args[1]} failed: <stderr or stdout, stripped>")`.
   - A timeout raises `ForgeError` too.
2. **`Local.land(branch, title, body)`** merges in the operator's main checkout. This is ADR-0030's one documented
   exception to "never write to the main checkout", and it is allowed only into a clean tree.
   - **Checks first, and change nothing if they fail:**
     - `proj.root` must have the default branch checked out (`git rev-parse --abbrev-ref HEAD`);
     - `git status --porcelain` must be empty (untracked files count).

     If either fails, raise `ForgeError` saying which. Never stash and never switch branches.
   - **Merge:** `git merge --no-ff --file <tmp> <branch>`, where `<tmp>` is a temp file outside the repo holding
     `title + "\n\n" + body`.
   - **Conflict:** if the merge fails, run `git merge --abort` and raise `ForgeError("<branch>: merge conflict ...")`.
     The tree is clean again afterwards.
   - **Returns** the merge commit's sha (`git rev-parse HEAD`).
3. **`GitHub.land(branch, title, body)`**. All `gh` calls go through `self.gh(args, proj.root, input=...)`.
   1. **Push:** `git push --quiet <remote> <branch>:<branch>` from `proj.root`.
   2. **PR:**
      - If `gh pr view <branch> --json number,state,url` succeeds with `state == "OPEN"`, reuse that PR.
      - Otherwise (it raises `ForgeError`, or the state is not OPEN), run
        `gh pr create --base <default> --head <branch> --title <title> --body-file -` with `input=body`, then read
        the number and url with the same `gh pr view` call.
   3. **Wait for checks.** Poll `gh pr view <n> --json statusCheckRollup,mergeStateStatus`, calling
      `self.sleep(POLL_S)` between polls. Classify each rollup entry:

      | Entry | Pending when | Passed when | Otherwise |
      |---|---|---|---|
      | has `status` (a CheckRun) | `status != "COMPLETED"` | `conclusion` is `SUCCESS`, `NEUTRAL` or `SKIPPED` | failed |
      | has `state` (a StatusContext) | `state` is `PENDING` or `EXPECTED` | `state == "SUCCESS"` | failed |

      Then act on the classification:
      - **Any entry failed:** raise `ForgeError("checks failed: <names>  <pr url>")`. Use `name`, or `context` for
        a StatusContext. Do not merge.
      - **No entries at all after `GRACE_S`** (measured with `self.clock()` from the push): this is BUG-14 (GitHub
        sometimes spawns no run). Re-trigger **once** with `gh pr close <n>` then `gh pr reopen <n>`, and restart
        the grace period. If there are still no entries after the second grace period, raise
        `ForgeError("no checks reported ...")`.
      - **Every entry passed** (at least one entry): go to step 4.
      - **More than `TIMEOUT_S` since the push:** raise `ForgeError("checks still pending after ...")`.
   4. **Merge state:**
      - **`BEHIND`** (branch protection wants the branch up to date):
        - run `gh api -X PUT repos/{owner}/{repo}/pulls/<n>/update-branch` **once**, then go back to step 3;
        - `update-branch` is asynchronous (it answers 202), so treat it as a new push: restart the grace period and
          the timeout from the update;
        - a `BEHIND` seen again is waited out (sleep `POLL_S`, poll again). Only a `BEHIND` still reported more than
          `GRACE_S` after the update raises `ForgeError`.
      - **`DIRTY`** (conflicts): raise `ForgeError`.
      - **Otherwise:** `gh pr merge <n> --merge`.
   5. **Result:** read the merge commit sha with `gh pr view <n> --json mergeCommit` (`mergeCommit.oid`).
   6. **Cleanup:** delete the remote branch with `git push --quiet <remote> --delete <branch>`. If that fails because
      the ref is already gone (the message contains `remote ref does not exist`), ignore it. Any other failure raises.
   7. Return the sha.
4. **`for_project(proj, **kw)`** returns `Local(proj)` for `forge = "local"`, and `GitHub(proj, **kw)` for
   `"github"`. Anything else raises `ForgeError`.

## Acceptance criteria
- `tests/test_forge.py` (unittest, temp dirs and repos only, never the network) covers each behaviour.
  - **`Local`:**
    - a clean main checkout gets a two-parent merge commit whose message is the title and body, and the sha is returned;
    - a dirty tree (an untracked file is enough) or the wrong branch raises, and HEAD is unchanged;
    - a conflict raises, and `git status --porcelain` is empty afterwards.
  - **`GitHub`:** use a **fake `gh`** callable that records its calls and replays scripted JSON, a fake `sleep` that
    advances a fake `clock`, and a local **bare repo as the remote**, so the real `git push` works.
    - **Happy path:**
      - the bare repo receives the branch;
      - `pr create` gets the body through `input` and never in `args`;
      - checks go from pending to success;
      - `pr merge` is called, the merge oid is returned, and the remote branch is deleted.
    - An existing open PR is reused: no `pr create`.
    - A failed check raises, naming the check, and `pr merge` is never called.
    - BUG-14:
      - no checks, then close and reopen exactly once, then success: the PR merges;
      - no checks twice: raises.
    - `BEHIND` once: `update-branch` is called, then the PR merges. One stale `BEHIND` poll after the update, then
      `CLEAN`: the PR merges with no BUG-14 poke. `BEHIND` for more than `GRACE_S` after the update: raises.
      `DIRTY`: raises.
    - The overall timeout raises.
  - `for_project` picks the class from `proj.forge`.
- `python3 -m unittest discover -s tests -t .` passes from the repo root.
- `aios/forge.py` has at most 155 non-blank, non-comment lines, and imports only the standard library and `aios` modules.

## Out of scope
The `aios land`, `approve` and `rollback` commands and record checks (D2b); worktree removal; any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.

## Amendments
- 2026-10-22, Lead review of attempt 1: `update-branch` is asynchronous, so a stale `BEHIND` after the update is
  waited out (step 4); the line cap is 155.
