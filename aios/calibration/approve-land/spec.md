+++
id = "approve-and-land"
title = "aios approve and aios land"
files_allowed = ["aios/land.py", "aios/gate.py", "aios/cli.py", "tests/test_land.py"]
contracts = ["architecture/contracts/record.schema.md"]
depends_on = ["forge-merge"]
blast_radius = "high"
kind = "feature"
budget_usd = 1.0
+++

## Goal
Close the loop after the gate:
- record an approval on the task branch;
- land the branch through the project's forge (forge-merge) when its record allows it, then remove the worktree.

Rollback is rollback-command. Do not add it.

## Context
- **Standard library only** (AGENTS.md); ASCII source; fail loud; match the existing style.
- Existing pieces. Read them first; do not rewrite them.
  - **`aios/gate.py`:** `patch_id(wt, base)`, `verifier_diff(wt, base, limit)`, `run_gate(spec_path, *, gw, out)`, `TIERS`.
  - **`aios/records.py`:** `read(repo, task_id)` and `write(worktree, record)`.
  - **`aios/forge.py`** (forge-merge): `for_project(proj)` returns a forge whose `land(branch, title, body)` returns the merge
    sha. It raises `ForgeError`.
  - **`aios/run.py`:** `base_ref(proj, root)`, `worktree_path(paths, proj, task_id)`.
  - **Loading:** `config.find_root(dir)` (returns `None` outside a project), `config.load_project(root)`,
    `config.paths()`, and `spec.load_spec(path)`. A spec's `.branch` is `aios/<id>`.
- **Record contract:**
  - the verdict lives on the **last** attempt: `record["attempts"][-1]["verdict"]`;
  - an approval is `record["approval"] = {"by": "operator" | "lead", "note": "<text>"}`.
- **Gate tiers** (ADR-0026, doctrine):
  - `AUTO` lands without an approval;
  - `OPERATOR` and `LEAD` need an approval;
  - `HUMAN` needs the **operator's** approval. The Lead is a model and can never approve HUMAN-REQUIRED work.

## Required changes
1. **`aios/gate.py`: the task's own record is not part of the change being judged.** Add a keyword
   `task_id: str | None = None` to `patch_id` and to `verifier_diff`. When it is given, their diff also excludes
   `.aios/records/<task_id>.json` (pathspec `:(exclude).aios/records/<task_id>.json`). `run_gate` passes `s.id` to
   both.
   - Without this, re-running the gate after a record commit binds the new verdict to a diff that contains the old
     record. It also shows the old verdict to the verifier.
2. **New `aios/land.py`:**
   ```python
   def approve(spec_path: Path, *, by: str, note: str, out=print) -> int: ...
   def land(spec_path: Path, *, forge=None, out=print) -> int: ...
   ```
   - **Common loading:**
     - spec and project, through `find_root` on the spec's directory (`None` raises `ConfigError`);
     - `wt = run.worktree_path(...)`, which must exist, else `ConfigError("... dispatch it first")`;
     - `record = records.read(wt, s.id)`, which must exist, else `ConfigError("... run 'aios gate' first")`;
     - the record's `gate` must be one of `gate.TIERS`, else `ValueError` (fail closed).
   - **`approve`:**
     1. The verdict must be `"pass"`. Otherwise raise `ValueError("<id>: the verdict is <v>; only a passing verdict can be approved")`.
     2. `by` must be `"operator"` or `"lead"`, and `note.strip()` must not be empty. Otherwise raise `ValueError`.
     3. If the record's gate is `HUMAN` and `by != "operator"`, raise `ValueError("<id>: the HUMAN gate needs the operator's approval")`.
     4. Set `record["approval"] = {"by": by, "note": note.strip()}`, then call `records.write(wt, record)`.
     5. In the worktree, run `git add .aios/records/<id>.json` and `git commit -m "<id>: approve (<by>)"`.
     6. Print `<id>: approved by <by> | gate <gate>` and return `0`.
   - **`land`:**
     1. `git status --porcelain` in the worktree, ignoring build caches (the `run._NOT_CACHES` pathspecs), must be
        empty. Otherwise raise `ConfigError("<wt> has uncommitted changes")`. The gate's own checks leave caches
        such as `__pycache__` behind in repos without ignore rules (lesson 15).
     2. The verdict must be `"pass"`. Otherwise raise `ValueError`.
     3. **Patch binding:** `gate.patch_id(wt, base, task_id=s.id)` must equal the verdict's `patch_id`. Otherwise
        raise `ValueError("<id>: the branch changed since the gate; run 'aios gate' again")`.
     4. **Approval:**
        - if the gate is not `AUTO` and there is no approval, raise `ValueError("<id>: gate <g> needs 'aios approve' first")`;
        - if the gate is `HUMAN`, the approval must be by `"operator"`.
     5. **Land:**
        - `forge = forge or forge_mod.for_project(proj)`;
        - call `forge.land(s.branch, f"{s.id}: {s.title}", body)` with this body:
          ```
          <record summary>

          Gate: <gate> | flags: <comma-separated, or none> | verdict: <verdict> (<risk>) by <verifier>
          Approval: <by>: <note>                    (this line only when approved)
          Cost: $<usd_total formatted .4f> | record: .aios/records/<id>.json
          ```
     6. **Cleanup:** the worktree may still hold build caches, because the gate's checks write them.
        - Re-run step 1's check (`git status --porcelain`, ignoring build caches).
        - If it is clean, run `git worktree remove --force <wt>` (only caches can remain), then `git branch -D <branch>`,
          both in the project root.
        - If it is not clean, raise `ConfigError("<id>: landed <sha[:12]>, but <wt> has uncommitted changes; remove it by hand")`.
          Never force-remove anything else.
     7. Print `<id>: landed <sha[:12]> | gate <gate> | $<usd_total .4f>` and return `0`.
3. **`aios/gate.py`:** set `VERIFIER_MAX_TOKENS = 32000` (amendment, below).
4. **`aios/cli.py`:**
   - add `aios approve <spec> --by {operator,lead} --note TEXT` and `aios land <spec>`;
   - report `forge.ForgeError` like the other errors (exit 2).

## Acceptance criteria
- `tests/test_land.py` (unittest, temp dirs and repos only) uses a **local-forge** project.
  - **Setup:** build a dispatched task the way `tests/test_gate_run.py` does (temp repo, worktree, a change commit,
    an `attempt.json`). Then produce the record with `gate.run_gate`, with `run_checks` patched to pass and a fake
    gateway returning a passing verdict.
  - **Cases:**
    - **AUTO:** `land` returns 0.
      - The main checkout's HEAD is a merge commit containing the change and `.aios/records/<id>.json`.
      - The worktree directory and the `aios/<id>` branch are gone.
    - **LEAD** (router gate `LEAD` in the decision):
      - `land` without an approval raises;
      - `approve(by="lead")` commits `<id>: approve (lead)` with the approval in the record;
      - `land` then returns 0.
    - **HUMAN:**
      - `approve(by="lead")` raises;
      - `approve(by="operator")` works, and `land` lands.
    - **A failing verdict:** `approve` and `land` both raise.
    - **A code commit after the gate:**
      - `land` raises "changed since the gate";
      - re-running `run_gate` (which now excludes the old record) and then `land` succeeds.
    - **Uncommitted changes in the worktree:** `land` raises.
    - **An injected fake forge** receives `(branch, title, body)`. The body holds the summary, the gate line and
      the cost line.
    - **CLI:** `aios approve` parses `--by` and `--note`, and a `ForgeError` from `aios land` exits 2.
  - **Gate:** a test proves `patch_id(..., task_id=...)` and `verifier_diff(..., task_id=...)` ignore the task's record.
- The existing tests still pass: `python3 -m unittest discover -s tests -t .`.
- `aios/land.py` has at most 110 non-blank, non-comment lines, and `aios/gate.py` at most 215.

## Out of scope
`aios rollback` (rollback-command), any change to `aios/forge.py`, fix rounds and the ladder (the budget-and-fix-rounds work).

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.

## Amendments
- 2026-10-22, Lead review of attempt 1: `land`'s cleanliness check ignores build caches (step 1). Without that, every
  land in a repo without ignore rules would fail on the gate's own `__pycache__`. The worker found this.
- 2026-10-22, Lead, after gating attempt 1:
  - Cleanup (step 6) re-checks cleanliness, then force-removes only when nothing but caches remain. Otherwise it
    fails loud. The verifier rightly objected to an unconditional `--force` fallback.
  - `gate.VERIFIER_MAX_TOKENS = 32000`. Measured on this task's own 32 KB verifier prompt, `deepseek-v4-pro` needed
    17,607 reasoning tokens (411 s, $0.033). With 16,000 it ran out on every provider tried (Alibaba, Baidu,
    AtlasCloud).
