"""Tests for `aios status` and `aios brief`: every task state, worked out from a local repo and this machine."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aios import cli, config, gateway, git, run, status
from tests.helpers import cwd, git_repo

PROJECT = """schema = 1
name = "demo"
forge = "local"
default_branch = "main"
[[components]]
name = "app"
path = "./"
profile = "python"
checks = ["python3 -m unittest"]
"""

RUNNING_DIR = "20261023T101010-000002"


def spec_text(task_id: str, *, deps=()) -> str:
    """A spec body for `task_id`, with its `depends_on` list when it has one."""
    on = "depends_on = [" + ", ".join(f'"{d}"' for d in deps) + "]\n" if deps else ""
    return f"""+++
id = "{task_id}"
title = "Fix the {task_id.replace('-', ' ')}"
files_allowed = ["src/{task_id}.py"]
{on}+++
# Goal
Do it.
## Acceptance criteria
- `python3 -m unittest` passes
"""


def record(task_id: str, *, gate="AUTO", verdict="pass", blocking=(), approval=None, usd=0.0123) -> dict:
    """A plausible record: only the fields `aios status` and `aios brief` read."""
    return {"record_schema": 2, "task": task_id, "gate": gate, "flags": [], "approval": approval,
            "summary": "did it", "usd_total": usd,
            "attempts": [{"n": 1, "exit": "submitted", "usd": usd,
                          "verdict": {"verdict": verdict, "risk": "low", "blocking": list(blocking)}}]}


class FakeGw:
    """A gateway whose key reports the usage and limit given."""

    def __init__(self, **info):
        self.info = {"usage_daily": 1.25, "usage_monthly": 3.5, "limit_remaining": 16.5} | info

    def key_info(self):
        return dict(self.info)


class BurstGw:
    """A gateway whose key record cannot be read at all."""

    def key_info(self):
        raise gateway.GatewayError(500, "upstream exploded")


class StatusTest(unittest.TestCase):
    """A temp project whose specs and records live on main, with no remote and throwaway state dirs."""

    def setUp(self):
        state = Path(tempfile.mkdtemp(prefix="aios-status-"))
        env = mock.patch.dict(os.environ, {f"XDG_{k}_HOME": str(state / k.lower())
                                          for k in ("CONFIG", "CACHE", "STATE", "DATA")})
        env.start()
        self.addCleanup(env.stop)
        self.p = config.paths()
        self.root = git_repo({".aios/project.toml": PROJECT, "README.md": "x\n"})
        (self.root / ".aios" / "records" / ".gitkeep").parent.mkdir(parents=True, exist_ok=True)
        (self.root / ".aios" / "records" / ".gitkeep").touch()
        self.commit("add", "-A")
        self.commit("commit", "-qm", "project")

    def commit(self, *args: str) -> None:
        """Run a git command in the repo, as the operator or a landing would."""
        git.git(list(args), self.root)

    def add_spec(self, task_id: str, **kw) -> None:
        """Write a spec and commit it on main."""
        f = self.root / ".aios" / "tasks" / f"{task_id}.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(spec_text(task_id, **kw))
        self.commit("add", f".aios/tasks/{task_id}.md")
        self.commit("commit", "-qm", f"{task_id}: spec")

    def add_broken_spec(self, task_id: str) -> None:
        """A spec that does not parse: no Goal section."""
        f = self.root / ".aios" / "tasks" / f"{task_id}.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f'+++\nid = "{task_id}"\ntitle = "Broken"\nfiles_allowed = ["src/x.py"]\n+++\nno goal\n')
        self.commit("add", f".aios/tasks/{task_id}.md")
        self.commit("commit", "-qm", f"{task_id}: spec")

    def worktree(self, task_id: str) -> Path:
        """A live worktree for the task, where dispatch would have put it."""
        wt = run.worktree_path(self.p, config.load_project(self.root), task_id)
        self.commit("worktree", "add", "--quiet", "-b", f"aios/{task_id}", str(wt), "main")
        return wt

    def run_dir(self, task_id: str, name: str, attempt: dict | None = None) -> Path:
        """One attempt directory, with an attempt.json when the worker finished one."""
        d = self.p.state / run.project_id(config.load_project(self.root)) / "runs" / task_id / name
        d.mkdir(parents=True, exist_ok=True)
        if attempt is not None:
            (d / "attempt.json").write_text(json.dumps({"decision": {}, "attempt": attempt}))
        return d

    def put_record(self, task_id: str, rec: dict, *, on_main=False) -> None:
        """Write the task's record in its worktree, or commit it on main as a landing does."""
        where = self.root if on_main else self.worktree(task_id)
        path = where / ".aios" / "records" / f"{task_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
        if on_main:
            self.commit("add", f".aios/records/{task_id}.json")
            self.commit("commit", "-qm", f"{task_id}: record")

    def tasks(self, **kw) -> list[status.Task]:
        """The tasks `status.tasks` returns, with what it printed kept in `self.text`."""
        lines: list[str] = []
        ts = status.tasks(self.root, out=lines.append, **kw)
        self.text = "\n".join(lines)
        return ts

    def one(self, ts: list[status.Task], task_id: str) -> status.Task:
        """The one task with this id."""
        return next(t for t in ts if t.id == task_id)


class States(StatusTest):
    def test_ready_and_blocked(self):
        self.add_spec("first-task")
        self.add_spec("second-task", deps=["first-task", "third-task"])
        ts = self.tasks()
        self.assertEqual([(t.id, t.state) for t in ts], [("first-task", "ready"), ("second-task", "blocked")])
        self.assertEqual(self.one(ts, "first-task").detail, "next: aios dispatch")
        self.assertEqual(self.one(ts, "second-task").detail, "waiting on first-task, third-task")

    def test_in_flight_while_the_worker_runs(self):
        self.add_spec("flying-task")
        self.worktree("flying-task")
        self.run_dir("flying-task", "20261023T100000-000001", {"exit": "submitted", "usd": 0.01})
        self.run_dir("flying-task", RUNNING_DIR)
        t = self.one(self.tasks(), "flying-task")
        self.assertEqual(t.state, "in-flight")
        self.assertEqual(t.detail, f"worker running (or crashed) since {RUNNING_DIR}")

    def test_in_flight_after_an_attempt(self):
        self.add_spec("tried-task")
        self.worktree("tried-task")
        self.run_dir("tried-task", "20261023T100000-000001", {"exit": "submitted", "usd": 0.01})
        t = self.one(self.tasks(), "tried-task")
        self.assertEqual((t.state, t.detail), ("in-flight", "attempt 1: submitted; next: aios gate"))

    def test_needs_you_variants(self):
        cases = {"auto-task": ("AUTO", "pass", None, "ready to land: aios land"),
                 "approved-task": ("LEAD", "pass", {"by": "operator", "note": "hil pass"},
                                   "ready to land: aios land"),
                 "operator-task": ("OPERATOR", "pass", None, "gate OPERATOR: needs aios approve"),
                 "human-task": ("HUMAN", "pass", None, "gate HUMAN: the operator must approve"),
                 "decide-task": ("AUTO", "needs_decision", (), "the verifier needs a decision")}
        for task_id, (gate, verdict, approval, detail) in cases.items():
            self.add_spec(task_id)
            self.put_record(task_id, record(task_id, gate=gate, verdict=verdict, approval=approval))
        blocking = "the parser drops the last row of every csv export, and " + "x" * 120
        self.add_spec("fail-task")
        self.put_record("fail-task", record("fail-task", verdict="fail", blocking=[blocking]))
        ts = self.tasks()
        self.assertEqual([t.state for t in ts], ["needs-you"] * len(ts))
        for task_id, (_gate, _verdict, _approval, detail) in cases.items():
            self.assertEqual(self.one(ts, task_id).detail, detail)
        fail = self.one(ts, "fail-task")
        self.assertEqual(fail.detail, f"verdict fail: {blocking[:100]}")
        self.assertLessEqual(len(fail.detail), len("verdict fail: ") + 100)

    def test_done(self):
        self.add_spec("landed-task")
        self.put_record("landed-task", record("landed-task"), on_main=True)
        t = self.one(self.tasks(), "landed-task")
        self.assertEqual((t.state, t.detail), ("done", "gate AUTO | verdict pass | $0.0123"))

    def test_done_with_an_approval(self):
        self.add_spec("ok-task")
        approved = record("ok-task", gate="LEAD", approval={"by": "operator", "note": "hil pass"})
        self.put_record("ok-task", approved, on_main=True)
        t = self.one(self.tasks(), "ok-task")
        self.assertEqual(t.detail, "gate LEAD | verdict pass | $0.0123 | approved by operator")

    def test_rolled_back(self):
        self.add_spec("reverted-task")
        self.put_record("reverted-task", record("reverted-task"), on_main=True)
        self.commit("rm", ".aios/records/reverted-task.json")
        self.commit("commit", "-qm", "reverted-task: rolled back")
        t = self.one(self.tasks(), "reverted-task")
        self.assertEqual(t.state, "rolled-back")
        self.assertRegex(t.detail, r"^record removed in [0-9a-f]{7,}$")

    def test_invalid(self):
        self.add_broken_spec("broken-task")
        t = self.one(self.tasks(), "broken-task")
        self.assertEqual((t.id, t.title, t.state), ("broken-task", "broken-task.md", "invalid"))
        self.assertIn("missing required section 'goal'", t.detail)

    def test_states_are_sorted_by_state_then_id(self):
        self.add_spec("z-done")
        self.put_record("z-done", record("z-done"), on_main=True)
        self.add_spec("a-ready")
        self.add_broken_spec("m-invalid")
        self.add_spec("b-needs-you")
        self.put_record("b-needs-you", record("b-needs-you"))
        self.assertEqual([t.state for t in self.tasks()], ["needs-you", "ready", "done", "invalid"])

    def test_an_offline_fetch_only_notes_the_cached_base(self):
        """A fetch that fails costs one note and nothing else; `refresh=False` does not fetch at all."""
        self.add_spec("ready-task")
        self.commit("update-ref", "refs/remotes/origin/main", "main")
        real, calls = git.git, []

        def offline(args, where, timeout=60):
            calls.append(args)
            if args[:2] == ["fetch", "--quiet"]:
                raise git.GitError("git fetch failed: could not resolve host")
            return real(args, where, timeout=timeout)

        with mock.patch.object(git, "remote_url", return_value="git@example.invalid:x.git"), \
                mock.patch.object(git, "git", offline):
            self.assertEqual(self.one(self.tasks(), "ready-task").state, "ready")
            self.assertIn("(offline: using cached origin/main)", self.text)
            self.tasks(refresh=False)
        self.assertEqual(calls.count(["fetch", "--quiet", "origin"]), 1)

    def test_status_writes_nothing(self):
        self.add_spec("ready-task")
        self.add_spec("flying-task")
        self.worktree("flying-task")
        self.run_dir("flying-task", "20261023T100000-000001", {"exit": "submitted", "usd": 0.01})
        self.add_spec("landed-task")
        self.put_record("landed-task", record("landed-task"), on_main=True)
        refs = "for-each-ref", "--format=%(refname) %(objectname)"
        before, porcelain = self.commit(*refs), self.commit("status", "--porcelain")
        self.assertEqual(status.status(self.root, out=lambda s: None), 0)
        self.assertEqual(status.brief(self.root, gw=FakeGw(), out=lambda s: None), 0)
        self.assertEqual(self.commit(*refs), before)
        self.assertEqual(self.commit("status", "--porcelain"), porcelain)


class Brief(StatusTest):
    def brief(self, gw=None) -> str:
        lines: list[str] = []
        self.assertEqual(status.brief(self.root, gw=gw, out=lines.append), 0)
        return "\n".join(lines)

    def test_counts_sections_and_spend(self):
        config.save_machine(self.p, config.Machine(per_month_usd=20.0))
        self.add_spec("landed-task")
        self.put_record("landed-task", record("landed-task"), on_main=True)
        self.add_spec("gated-task")
        self.put_record("gated-task", record("gated-task", gate="LEAD"))
        self.add_spec("ready-task")
        self.add_spec("flying-task")
        self.worktree("flying-task")
        self.run_dir("flying-task", "20261023T100000-000001", {"exit": "submitted", "usd": 0.01})
        text = self.brief(FakeGw())
        self.assertIn("4 tasks, 1 needs-you, 1 in-flight, 1 ready, 1 done", text)
        self.assertIn("Needs you:\n  gated-task  Fix the gated task  | gate LEAD: needs aios approve", text)
        self.assertIn("In flight:\n  flying-task", text)
        self.assertIn("Ready next:\n  ready-task  Fix the ready task  | next: aios dispatch", text)
        self.assertIn("Recently landed:\n  landed-task", text)
        self.assertIn("spend: today $1.25 of $5.00 | this month $3.50 of $20.00 | key $16.50 left", text)

    def test_recently_landed_is_newest_first_and_capped_at_five(self):
        for n in range(7):
            self.add_spec(f"landed-{n}")
            self.put_record(f"landed-{n}", record(f"landed-{n}"), on_main=True)
        landed = self.brief(FakeGw()).split("Recently landed:\n")[1].split("\nspend:")[0]
        self.assertEqual([row.split()[0] for row in landed.splitlines()],
                         [f"landed-{n}" for n in range(6, 1, -1)])

    def test_the_monthly_budget_and_the_key_limit_may_be_unset(self):
        self.add_spec("ready-task")
        text = self.brief(FakeGw(limit_remaining=None))
        self.assertIn("spend: today $1.25 of $5.00 | this month $3.50 of (not set: run aios doctor --fix) "
                      "| key: no limit", text)

    def test_spend_is_never_fatal(self):
        self.add_spec("ready-task")
        text = self.brief(BurstGw())
        self.assertIn("spend: unavailable (OpenRouter HTTP 500: upstream exploded)", text)
        self.assertIn("1 task, 1 ready", text)

    def test_an_empty_project(self):
        """No specs at all: the brief still reports its counts and its spend line."""
        text = self.brief(FakeGw())
        self.assertIn("0 tasks", text)
        self.assertTrue(text.strip().endswith("spend: today $1.25 of $5.00 | this month $3.50 of "
                                              "(not set: run aios doctor --fix) | key $16.50 left"))


class Cli(StatusTest):
    def run_out(self, *argv) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_status_and_brief_run_inside_the_project(self):
        self.add_spec("ready-task")
        with cwd(self.root):
            code, out, err = self.run_out("status")
        self.assertEqual(code, 0, err)
        self.assertIn("ready-task  ready        Fix the ready task  | next: aios dispatch", out)
        self.assertIn("next: aios dispatch", out)
        with cwd(self.root):
            code, out, err = self.run_out("brief")
        self.assertEqual(code, 0, err)
        self.assertIn("1 task, 1 ready", out)
        self.assertIn("spend: unavailable", out)  # no key is stored in this throwaway state dir

    def test_outside_a_project_fails_loud(self):
        for command in ("status", "brief"):
            with cwd(Path(tempfile.mkdtemp())):
                code, _out, err = self.run_out(command)
            self.assertEqual(code, 2)
            self.assertIn("not inside a project with .aios/project.toml", err)


if __name__ == "__main__":
    unittest.main()
