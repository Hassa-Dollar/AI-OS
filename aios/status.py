"""`aios status` and `aios brief`: the operator's cockpit, worked out from git and the worktrees alone.

ADR-0030 rules 2, 3 and 5: a task's state is computed when read, from the base ref and this machine's own state
directories, and neither command ever writes anything.

Sections:
  1. Facts     the project and its base ref -> the specs, records, landings and attempts aios can see
  2. Classify  one spec and what aios can see -> its Task: a state and the detail that says what to do
  3. Commands  the tasks -> one line per task (`aios status`) and the session summary (`aios brief`)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import config, gateway, git, records, run
from . import spec as specs

STATES = ("needs-you", "in-flight", "ready", "blocked", "done", "rolled-back", "invalid")
SECTIONS = (("Needs you:", ("needs-you", "invalid")), ("In flight:", ("in-flight",)), ("Ready next:", ("ready",)))
TASKS, RECORDS = ".aios/tasks/", ".aios/records"


@dataclass(frozen=True)
class Task:
    """One task's state and the detail that says what to do next."""
    id: str
    title: str
    state: str
    detail: str


@dataclass(frozen=True)
class Facts:
    """What one project looks like to a read-only command: its project, base ref and this machine's paths."""
    proj: config.Project
    base: str
    paths: config.Paths


# --- 1. Facts ---------------------------------------------------------------------------
# From: the project, its base ref and this machine's state directories
# To:   the specs, records, landings and attempts the classifier reads; nothing here writes
def _record(f: Facts, path: str) -> dict | None:
    """A JSON file's contents on the base ref, or None when it is not there."""
    try:
        return json.loads(git.git(["show", f"{f.base}:{path}"], f.proj.root))
    except git.GitError:
        return None


def _specs(f: Facts) -> tuple[list, list]:
    """Every spec on the base ref: the parsed ones, and (path, error) for the ones that do not parse."""
    ok, bad = [], []
    for path in git.git(["ls-tree", "--name-only", f.base, TASKS], f.proj.root).splitlines():
        try:                    # only *.md files are specs; a .gitkeep is not one and is simply ignored
            if path.endswith(".md"):
                ok.append(specs.parse_spec(git.git(["show", f"{f.base}:{path}"], f.proj.root), path))
        except specs.SpecError as e:
            bad.append((path, e))
    return ok, bad


def _landed(f: Facts) -> list[tuple[str, str, dict]]:
    """The newest records added on base, as (task id, commit, record), newest first; a brief takes five."""
    out, commit = [], ""
    log = git.git(["log", "--first-parent", "--diff-filter=A", "--name-only", "--format=%x09%H",
                   f.base, "--", RECORDS], f.proj.root)
    for line in log.splitlines():
        if line.startswith("\t"):
            commit = line[1:]
        elif line.startswith(RECORDS + "/") and line.endswith(".json"):
            record = _record(f, line)
            if record is not None:      # a record a later revert removed is not a landing any more
                out.append((Path(line).stem, commit, record))
    return out[:5]


# --- 2. Classify ------------------------------------------------------------------------
# From: one spec and what aios can see of it
# To:   the task's Task: a state, and the detail that says what to do next
def _detail(record: dict, landed: bool) -> str:
    """A record's detail: what a landed task did and cost, or what a gated task asks of the operator."""
    attempts = record.get("attempts") or []
    verdict = (attempts[-1].get("verdict") or {}) if attempts else {}
    gate = record.get("gate")
    if landed:
        approval = record.get("approval") or {}
        detail = (f"gate {gate} | verdict {verdict.get('verdict') or 'none'} | "
                  f"${float(record.get('usd_total') or 0.0):.4f}")
        return f"{detail} | approved by {approval['by']}" if approval.get("by") else detail
    kind = verdict.get("verdict")
    if kind == "pass":
        if record.get("approval") or gate == "AUTO":
            return "ready to land: aios land"
        return f"gate {gate}: " + ("the operator must approve" if gate == "HUMAN" else "needs aios approve")
    if kind != "fail":
        return "the verifier needs a decision" if kind == "needs_decision" else "no verdict yet; next: aios gate"
    # a failing review: the first thing it blocks on, cut to 100 characters so a status line stays short
    return f"verdict fail: {(verdict.get('blocking') or ['no reason given'])[0][:100]}"


def _task(s, f: Facts, record: dict | None, on_base: dict) -> Task:
    """One spec's Task: its record and worktree decide first, then its dependencies (ADR-0030 rule 3)."""
    if record is not None:
        return Task(s.id, s.title, "done", _detail(record, landed=True))
    removed = git.git(["log", "-1", "--format=%h", f.base, "--", f"{RECORDS}/{s.id}.json"], f.proj.root).strip()
    if removed:
        return Task(s.id, s.title, "rolled-back", f"record removed in {removed}")
    wt = run.worktree_path(f.paths, f.proj, s.id)
    if not wt.exists():
        waiting = [d for d in s.depends_on if on_base.get(d) is None]
        if waiting:
            return Task(s.id, s.title, "blocked", "waiting on " + ", ".join(waiting))
        return Task(s.id, s.title, "ready", "next: aios dispatch")
    runs_dir = f.paths.state / run.project_id(f.proj) / "runs" / s.id
    dirs = sorted(p for p in runs_dir.iterdir() if p.is_dir()) if runs_dir.is_dir() else []
    # the newest run dir without an attempt.json is a worker still running, or one that crashed
    running = None if not dirs or (dirs[-1] / "attempt.json").is_file() else dirs[-1].name
    if running:
        return Task(s.id, s.title, "in-flight", f"worker running (or crashed) since {running}")
    record = records.read(wt, s.id)
    if record is None:
        attempts = records.load_runs(runs_dir)
        exit_code = attempts[-1]["attempt"].get("exit", "none") if attempts else "none"
        return Task(s.id, s.title, "in-flight", f"attempt {len(attempts)}: {exit_code}; next: aios gate")
    return Task(s.id, s.title, "needs-you", _detail(record, landed=False))


# --- 3. Commands ------------------------------------------------------------------------
# From: a project root (and, for brief, an optional gateway)
# To:   one line per task, or the session summary and the spend, on stdout
def tasks(root: Path, *, refresh: bool = True, out=print) -> list[Task]:
    """Every spec on the base ref as a Task, sorted by state then id; git and the worktrees decide."""
    proj = config.load_project(root)
    f = Facts(proj, run.base_ref(proj, root), config.paths())
    if refresh and git.remote_url(root, proj.remote):   # offline only costs us the newest refs
        try:
            git.git(["fetch", "--quiet", proj.remote], root, timeout=60)
        except git.GitError:
            out(f"(offline: using cached {f.base})")
    ok, bad = _specs(f)
    on_base = {s.id: _record(f, f"{RECORDS}/{s.id}.json") for s in ok}
    found = [_task(s, f, on_base[s.id], on_base) for s in ok]
    return sorted(found + [Task(Path(p).stem, Path(p).name, "invalid", str(e)) for p, e in bad],
                  key=lambda t: (STATES.index(t.state), t.id))


def status(root: Path, *, out=print) -> int:
    """`aios status`: one line per task, then 0; it never writes anything."""
    for t in tasks(root, out=out):
        out(f"{t.id:<6}  {t.state:<11}  {t.title}  | {t.detail}")
    return 0


def _spend(f: Facts, gw) -> str:
    """The spend line, or `spend: unavailable (why)`: a failure here never fails the brief."""
    try:
        info = (gw or gateway.Gateway(config.load_key(f.paths), privacy=gateway.privacy_of(f.proj))).key_info()
        month = config.load_machine(f.paths).per_month_usd
        budget = f"${month:.2f}" if month is not None else "(not set: run aios doctor --fix)"
        key = "key: no limit" if info.get("limit_remaining") is None else f"key ${info['limit_remaining']:.2f} left"
        return (f"spend: today ${info['usage_daily']:.2f} of ${f.proj.per_day_usd:.2f} | "
                f"this month ${info['usage_monthly']:.2f} of {budget} | {key}")
    except Exception as e:  # spend is a courtesy: offline, no key or a bad answer must not fail the brief
        return f"spend: unavailable ({e})"


def brief(root: Path, *, gw=None, out=print) -> int:
    """`aios brief`: the start-of-session summary that replaces v1's SESSION-HANDOFF file; returns 0."""
    proj = config.load_project(root)
    f = Facts(proj, run.base_ref(proj, root), config.paths())
    found = tasks(root, out=out)
    n = {state: sum(1 for t in found if t.state == state) for state in STATES}
    head = f"{len(found)} task" + ("" if len(found) == 1 else "s")
    out(", ".join([head] + [f"{n[state]} {state}" for state in STATES if n[state]]))
    sections = [(heading, [f"  {t.id:<6}  {t.title}  | {t.detail}" for t in found if t.state in states])
                for heading, states in SECTIONS]
    sections.append(("Recently landed:",
                     [f"  {i:<6}  {c[:12]}  | {_detail(r, landed=True)}" for i, c, r in _landed(f)]))
    for heading, group in sections:
        if group:
            out(heading)
            out("\n".join(group))
    out(_spend(f, gw))
    return 0
