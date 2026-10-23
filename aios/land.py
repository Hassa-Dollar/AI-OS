"""`aios approve`, `aios land` and `aios rollback`: the verdict, the merge, and taking a merge back (ADR-0026).

An approval lives on the task's own branch, as a commit to its record. Landing binds the merge to the exact diff
the verifier judged (the record's patch id), then hands the branch to the project's forge and cleans up.

Only the operator may override a failing review, and the record keeps both the verdict and the override.

Sections:
  1. landing context  a spec path -> the spec, project, worktree and record, or an error
  2. verdict rules    a task id and a record -> the verdict it stands on, and whether it may merge
  3. approve          a spec, the approver and a note -> the approval written and committed to the branch
  4. PR body          the record and its verdict -> the body for the forge's PR or merge message
  5. land             a spec path -> the branch merged through the forge, then cleaned up
  6. rollback         a spec path -> the task's merge reverted through the forge, then cleaned up
"""
from __future__ import annotations

from pathlib import Path

from . import config, forge as forge_mod, gate, git, records, run, spec

JUNK = tuple(run._NOT_CACHES)  # build caches a worker left behind are never uncommitted work (lesson #3)


# --- 1. landing context ----------------------------------------------------------------
# From: a spec path
# To:   the spec, its project, the worktree and the record, or ConfigError / ValueError
def _context(spec_path: Path):
    """The spec, project, worktree and record a landing decision needs; every absence fails loud."""
    s = spec.load_spec(spec_path)
    root = config.find_root(spec_path.resolve().parent)
    if root is None:
        raise config.ConfigError(f"{spec_path}: not inside a project with .aios/project.toml (run 'aios init')")
    proj, paths = config.load_project(root), config.paths()
    wt = run.worktree_path(paths, proj, s.id)
    if not wt.exists():
        raise config.ConfigError(f"{wt}: no worktree for {s.id}; dispatch it first")
    record = records.read(wt, s.id)
    if record is None:
        raise config.ConfigError(f"{wt}: no record for {s.id}; run 'aios gate' first")
    if record.get("gate") not in gate.TIERS:
        raise ValueError(f"{s.id}: record gate {record.get('gate')!r} is not one of {', '.join(gate.TIERS)}")
    return s, proj, root, wt, record


# --- 2. verdict rules ------------------------------------------------------------------
# From: a task id and its record
# To:   the last attempt's verdict, and checks that refuse what must not merge
def _verdict(task_id: str, record: dict) -> dict:
    """The verdict the record stands on: the last attempt's (the record contract)."""
    attempts = record.get("attempts") or []
    if not attempts or "verdict" not in attempts[-1]:
        raise ValueError(f"{task_id}: the record has no verdict; run 'aios gate' first")
    return attempts[-1]["verdict"]


def _check_verdict(task_id: str, verdict: dict) -> None:
    """Only a passing verdict may be approved or landed; anything else is refused."""
    if verdict.get("verdict") != "pass":
        raise ValueError(f"{task_id}: the verdict is {verdict.get('verdict')}; "
                         "only a passing verdict can be approved")


def _check_override(task_id: str, verdict: dict, by: str, override: str) -> None:
    """An override is the operator's alone, on a verdict that really failed, and only with a reason."""
    if by != "operator":
        raise ValueError(f"{task_id}: only the operator can override a review")
    if verdict.get("verdict") not in ("fail", "needs_decision"):
        raise ValueError(f"{task_id}: the verdict is {verdict.get('verdict')}; nothing to override")
    if not override.strip():
        raise ValueError(f"{task_id}: --override must not be empty")


def _overridden(approval: dict) -> bool:
    """Whether an approval's override is the operator's, so a non-passing verdict may still merge."""
    return bool(approval.get("override")) and approval.get("by") == "operator"


# --- 3. approve ------------------------------------------------------------------------
# From: a spec path, --by, --note and an optional --override
# To:   the approval in the record, committed to the task branch, and a status line
def approve(spec_path: Path, *, by: str, note: str, override: str | None = None, out=print) -> int:
    """`aios approve <spec>`: commit the operator's or the Lead's approval onto the task branch."""
    s, _proj, _root, wt, record = _context(spec_path)
    verdict = _verdict(s.id, record)
    if by not in ("operator", "lead") or not note.strip():
        raise ValueError(f"{s.id}: --by must be 'operator' or 'lead' and --note must not be empty")
    if override is None:
        _check_verdict(s.id, verdict)
    else:
        # The Lead never overrules a review; the operator may, and the record then needs at least the Lead's gate.
        _check_override(s.id, verdict, by, override)
        record["gate"] = gate.tier(record["gate"], [("operator-override", "LEAD")])
    if record["gate"] == "HUMAN" and by != "operator":
        raise ValueError(f"{s.id}: the HUMAN gate needs the operator's approval")
    approval = {"by": by, "note": note.strip()}
    if override is not None:
        approval["override"] = override.strip()
    record["approval"] = approval
    records.write(wt, record)
    git.git(["add", "--", f".aios/records/{s.id}.json"], wt)
    who = f"{by}, override" if override is not None else by
    if git.git(["diff", "--cached", "--name-only"], wt).strip():
        git.git(["commit", "--quiet", "-m", f"{s.id}: approve ({who})"], wt)
    if override is not None:
        out(f"{s.id}: review overridden by the operator | gate {record['gate']}")
    else:
        out(f"{s.id}: approved by {by} | gate {record['gate']}")
    return 0


# --- 4. PR body ------------------------------------------------------------------------
# From: the task's record and its verdict
# To:   the body for the forge's PR or merge message
def _body(record: dict, verdict: dict) -> str:
    """The PR body: what changed and what the gate said, never a transcript."""
    lines = [record.get("summary") or "", "",
             f"Gate: {record['gate']} | flags: {', '.join(record.get('flags') or ()) or 'none'} | "
             f"verdict: {verdict['verdict']} ({verdict['risk']}) by {verdict.get('verifier')}",
             f"Cost: ${record.get('usd_total') or 0.0:.4f} | record: .aios/records/{record['task']}.json"]
    if a := record.get("approval"):
        lines.insert(3, f"Approval: {a['by']}: {a['note']}")
        if a.get("override"):
            lines.insert(4, f"Override: {a['override']}")
    return "\n".join(lines)


# --- 5. land ---------------------------------------------------------------------------
# From: a spec path, and the project's forge
# To:   the branch merged into the default branch, the worktree and branch removed, and a status line
def land(spec_path: Path, *, forge=None, out=print) -> int:
    """`aios land <spec>`: merge the gated branch through the forge, then remove the worktree and the branch."""
    s, proj, root, wt, record = _context(spec_path)
    if git.git(["status", "--porcelain", "--", ".", *JUNK], wt).strip():
        raise config.ConfigError(f"{wt} has uncommitted changes")
    verdict = _verdict(s.id, record)
    if verdict.get("verdict") != "pass" and not _overridden(record.get("approval") or {}):
        _check_verdict(s.id, verdict)
    if gate.patch_id(wt, run.base_ref(proj, root), task_id=s.id) != verdict.get("patch_id"):
        raise ValueError(f"{s.id}: the branch changed since the gate; run 'aios gate' again")
    g, approval = record["gate"], record.get("approval")
    if g != "AUTO" and not approval:
        raise ValueError(f"{s.id}: gate {g} needs 'aios approve' first")
    if g == "HUMAN" and approval.get("by") != "operator":
        raise ValueError(f"{s.id}: the HUMAN gate needs the operator's approval")
    f = forge or forge_mod.for_project(proj)
    sha = f.land(s.branch, f"{s.id}: {s.title}", _body(record, verdict))
    # The forge may leave work behind (the gate's checks write build caches too): only caches may remain, and we
    # never force-remove anything else (lesson #3). Otherwise the operator cleans it up by hand.
    if git.git(["status", "--porcelain", "--", ".", *JUNK], wt).strip():
        raise config.ConfigError(f"{s.id}: landed {sha[:12]}, but {wt} has uncommitted changes; remove it by hand")
    git.git(["worktree", "remove", "--force", str(wt)], root)
    git.git(["branch", "-D", s.branch], root)
    out(f"{s.id}: landed {sha[:12]} | gate {g} | ${record.get('usd_total') or 0.0:.4f}")
    return 0


# --- 6. rollback ------------------------------------------------------------------------
# From: a spec path, the project's forge, and the merge that landed the task on the base ref
# To:   a revert branch merged back through the forge, the revert worktree and branch gone, and a status line
def rollback(spec_path: Path, *, forge=None, out=print) -> int:
    """`aios rollback <spec>`: revert the merge that landed the task, so its code and its record both go."""
    s, proj, paths, root = run._project(spec_path)  # no worktree and no record: the task is already on the base
    if git.remote_url(root, proj.remote):
        git.git(["fetch", "--quiet", proj.remote], root, timeout=300)
    base = run.base_ref(proj, root)
    merge = git.git(["log", "--first-parent", "--diff-filter=A", "--format=%H", "-1", base,
                     "--", f".aios/records/{s.id}.json"], root).strip()
    if not merge:
        raise config.ConfigError(f"{s.id}: no landed record on {base}")
    branch = f"aios/{s.id}-revert"
    rwt = run.worktree_path(paths, proj, f"{s.id}-revert")
    if rwt.exists():
        raise config.ConfigError(f"{rwt}: a revert worktree for {s.id} is already there; remove it by hand")
    git.git(["worktree", "add", "--quiet", "-b", branch, str(rwt), base], root, timeout=300)
    try:
        git.git(["revert", "-m", "1", "--no-edit", merge], rwt)
    except git.GitError:
        try:
            git.git(["revert", "--abort"], rwt)
        except git.GitError:
            pass  # the revert failed before it wrote any conflict, so there is nothing to abort
        # The worktree is aios's own and holds nothing but the failed revert, so force cannot lose real work.
        git.git(["worktree", "remove", "--force", str(rwt)], root)
        git.git(["branch", "-D", branch], root)
        raise config.ConfigError(f"{s.id}: the revert conflicts with later changes; revert it by hand") from None
    f = forge or forge_mod.for_project(proj)
    body = (f"Rolls back {s.id} (merge {merge[:12]}). The revert removes .aios/records/{s.id}.json, "
            f"so the task reads as rolled back (ADR-0030 rule 3).")
    sha = f.land(branch, f"Revert {s.id}: {s.title}", body)
    git.git(["worktree", "remove", str(rwt)], root)
    git.git(["branch", "-D", branch], root)
    out(f"{s.id}: rolled back by {sha[:12]}")
    return 0
