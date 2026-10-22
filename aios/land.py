"""`aios approve` and `aios land`: record the human's verdict on a gated branch, then merge it (ADR-0026).

An approval lives on the task's own branch, as a commit to its record. Landing binds the merge to the exact diff
the verifier judged (the record's patch id), then hands the branch to the project's forge and cleans up.
"""
from __future__ import annotations

from pathlib import Path

from . import config, forge as forge_mod, gate, git, records, run, spec

JUNK = tuple(run._NOT_CACHES)  # build caches a worker left behind are never uncommitted work (lesson #3)


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


def _verdict(task_id: str, record: dict) -> dict:
    """The verdict the record stands on: the last attempt's (the record contract)."""
    attempts = record.get("attempts") or []
    if not attempts or "verdict" not in attempts[-1]:
        raise ValueError(f"{task_id}: the record has no verdict; run 'aios gate' first")
    return attempts[-1]["verdict"]


def _check_verdict(task_id: str, verdict: dict) -> None:
    if verdict.get("verdict") != "pass":
        raise ValueError(f"{task_id}: the verdict is {verdict.get('verdict')}; "
                         "only a passing verdict can be approved")


def approve(spec_path: Path, *, by: str, note: str, out=print) -> int:
    """`aios approve <spec>`: commit the operator's or the Lead's approval onto the task branch."""
    s, _proj, _root, wt, record = _context(spec_path)
    _check_verdict(s.id, _verdict(s.id, record))
    if by not in ("operator", "lead") or not note.strip():
        raise ValueError(f"{s.id}: --by must be 'operator' or 'lead' and --note must not be empty")
    if record["gate"] == "HUMAN" and by != "operator":
        raise ValueError(f"{s.id}: the HUMAN gate needs the operator's approval")
    record["approval"] = {"by": by, "note": note.strip()}
    records.write(wt, record)
    git.git(["add", "--", f".aios/records/{s.id}.json"], wt)
    if git.git(["diff", "--cached", "--name-only"], wt).strip():
        git.git(["commit", "--quiet", "-m", f"{s.id}: approve ({by})"], wt)
    out(f"{s.id}: approved by {by} | gate {record['gate']}")
    return 0


def _body(record: dict, verdict: dict) -> str:
    """The PR body: what changed and what the gate said, never a transcript."""
    lines = [record.get("summary") or "", "",
             f"Gate: {record['gate']} | flags: {', '.join(record.get('flags') or ()) or 'none'} | "
             f"verdict: {verdict['verdict']} ({verdict['risk']}) by {verdict.get('verifier')}",
             f"Cost: ${record.get('usd_total') or 0.0:.4f} | record: .aios/records/{record['task']}.json"]
    if a := record.get("approval"):
        lines.insert(3, f"Approval: {a['by']}: {a['note']}")
    return "\n".join(lines)


def land(spec_path: Path, *, forge=None, out=print) -> int:
    """`aios land <spec>`: merge the gated branch through the forge, then remove the worktree and the branch."""
    s, proj, root, wt, record = _context(spec_path)
    if git.git(["status", "--porcelain", "--", ".", *JUNK], wt).strip():
        raise config.ConfigError(f"{wt} has uncommitted changes")
    verdict = _verdict(s.id, record)
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
    try:
        git.git(["worktree", "remove", str(wt)], root)
    except git.GitError:
        git.git(["worktree", "remove", "--force", str(wt)], root)  # only build caches are left behind
    git.git(["branch", "-D", s.branch], root)
    out(f"{s.id}: landed {sha[:12]} | gate {g} | ${record.get('usd_total') or 0.0:.4f}")
    return 0
