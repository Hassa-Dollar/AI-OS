"""Tests for the budget governor: the four caps before every attempt, and the attempt's clock."""
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from aios import cli, config, git, harness, run
from tests.helpers import git_repo
from tests.test_harness import fake_harness

PROJECT = """schema = 1
name = "demo"
forge = "local"
[[components]]
name = "app"
path = "./"
profile = "python"
checks = ["python3 -m unittest"]
"""

SPEC = """+++
id = "T-1"
title = "Fix the parser"
files_allowed = ["parser.py"]
+++
# Goal
Fix it.
## Acceptance criteria
- `python3 -m unittest` passes
"""


def decision(action="dispatch"):
    from aios import router
    return router.Decision(action, "AUTO", "T1", "bugfix", "z-ai/glm-5.3-flash", "z-ai",
                           "deepseek/deepseek-v4-pro-0813", "deepseek", "clef-flash", 0.9, ["test"], {})


class FakeGw:
    """A gateway whose key reports the usage and limit given."""

    def __init__(self, usage_daily=0.0, usage_monthly=0.0, limit_remaining=None):
        self.info = {"usage_daily": usage_daily, "usage_monthly": usage_monthly, "limit_remaining": limit_remaining}

    def key_info(self):
        return dict(self.info)


def spec(budget_usd=None):
    """The task's spec: only the fields `budget_left` reads."""
    return SimpleNamespace(id="T-1", budget_usd=budget_usd)


def proj(**budget):
    """A project with the given [budget] numbers."""
    return config.Project(root=Path("."), name="demo", components=(), **budget)


class TaskSpent(unittest.TestCase):
    def test_the_attempts_add_up(self):
        runs = [{"attempt": {"usd": 0.1}}, {"attempt": {"usd": 0.2}}]
        self.assertEqual(run.task_spent(runs, None), 0.3)

    def test_the_record_verdict_counts_too(self):
        record = {"attempts": [{"verdict": {"usd": 0.05}}]}
        self.assertEqual(run.task_spent([{"attempt": {"usd": 0.1}}], record), 0.15)

    def test_nothing_spent_yet(self):
        self.assertEqual(run.task_spent([], None), 0.0)


class BudgetLeft(unittest.TestCase):
    def test_task_cap_is_the_smallest(self):
        left = run.budget_left(FakeGw(), proj(per_task_usd=1.0, per_day_usd=5.0), spec(1.0),
                               config.Machine(per_month_usd=20.0), [], None)
        self.assertEqual(left, 1.0)

    def test_day_cap_is_the_smallest(self):
        left = run.budget_left(FakeGw(), proj(per_task_usd=1.0, per_day_usd=0.5), spec(1.0),
                               config.Machine(per_month_usd=20.0), [], None)
        self.assertEqual(left, 0.5)

    def test_month_cap_is_the_smallest(self):
        left = run.budget_left(FakeGw(), proj(per_task_usd=1.0, per_day_usd=5.0), spec(1.0),
                               config.Machine(per_month_usd=0.4), [], None)
        self.assertEqual(left, 0.4)

    def test_key_limit_is_the_smallest(self):
        left = run.budget_left(FakeGw(limit_remaining=0.3), proj(per_task_usd=1.0, per_day_usd=5.0), spec(1.0),
                               config.Machine(per_month_usd=20.0), [], None)
        self.assertEqual(left, 0.3)

    def test_month_is_skipped_without_a_monthly_budget(self):
        left = run.budget_left(FakeGw(usage_monthly=100.0), proj(per_task_usd=1.0, per_day_usd=5.0), spec(1.0),
                               config.Machine(), [], None)
        self.assertEqual(left, 1.0)  # the task cap wins; the month's usage is never read

    def test_a_null_key_limit_is_ignored(self):
        left = run.budget_left(FakeGw(), proj(per_task_usd=1.0, per_day_usd=5.0), spec(1.0),
                               config.Machine(per_month_usd=20.0), [], None)
        self.assertEqual(left, 1.0)

    def test_the_month_cap_refuses(self):
        with self.assertRaisesRegex(run.BudgetError, r"T-1: the month's budget is spent \(\$19\.98 of \$20\.00\)"):
            run.budget_left(FakeGw(usage_monthly=19.98), proj(per_task_usd=1.0, per_day_usd=5.0), spec(1.0),
                            config.Machine(per_month_usd=20.0), [], None)

    def test_the_day_cap_refuses(self):
        with self.assertRaisesRegex(run.BudgetError, r"T-1: the day's budget is spent \(\$4\.98 of \$5\.00\)"):
            run.budget_left(FakeGw(usage_daily=4.98), proj(per_task_usd=1.0, per_day_usd=5.0), spec(1.0),
                            config.Machine(), [], None)

    def test_the_task_cap_refuses(self):
        runs = [{"attempt": {"usd": 0.98}}]
        with self.assertRaisesRegex(run.BudgetError, r"T-1: the task's budget is spent \(\$0\.98 of \$1\.00\)"):
            run.budget_left(FakeGw(), proj(per_task_usd=1.0, per_day_usd=5.0), spec(1.0), config.Machine(), runs, None)

    def test_the_key_limit_refuses(self):
        with self.assertRaisesRegex(run.BudgetError, r"T-1: the key limit is spent \(\$0\.01 left\)"):
            run.budget_left(FakeGw(limit_remaining=0.01), proj(per_task_usd=1.0, per_day_usd=5.0), spec(1.0),
                            config.Machine(), [], None)


class Dispatch(unittest.TestCase):
    def setUp(self):
        state = Path(subprocess.check_output(["mktemp", "-d"], text=True).strip())
        env = mock.patch.dict(os.environ, {f"XDG_{k}_HOME": str(state / k) for k in ("CONFIG", "CACHE", "STATE", "DATA")})
        env.start()
        self.addCleanup(env.stop)  # identical temp repos share a root commit, so each test needs its own state dirs
        self.root = git_repo({"parser.py": "x = 1\n", ".aios/project.toml": PROJECT, "AGENTS.md": "Be careful.\n"})
        self.spec = self.root / ".aios" / "tasks" / "T-1.md"
        self.spec.parent.mkdir(parents=True, exist_ok=True)
        self.spec.write_text(SPEC)
        self.p = config.paths()
        self.p.config.mkdir(parents=True, exist_ok=True)
        self.p.credentials.write_text("sk-or-v1-test")
        os.chmod(self.p.credentials, 0o600)
        fake_harness(self.p)
        self.out = io.StringIO()
        self.wt = self.p.data / "worktrees" / run.project_id(config.load_project(self.root)) / "T-1"

    def dispatch(self, gw=None):
        with mock.patch.object(run, "route", return_value=decision()):
            return run.dispatch(self.spec, gw=gw or FakeGw(), out=lambda s: self.out.write(s + "\n"))

    def test_dispatch_passes_the_budget_left_to_the_harness(self):
        self.assertEqual(self.dispatch(), 0, self.out.getvalue())
        cfg = json.loads(next(self.p.state.glob("demo-*/runs/T-1/*/cfg.yaml")).read_text())
        self.assertEqual(cfg["agent"]["cost_limit"], 1.0)  # per_task_usd: the smallest of the four caps
        self.assertIn("budget: $1.0000 for this attempt", self.out.getvalue())

    def test_a_refusal_creates_no_worktree_branch_or_harness_call(self):
        config.save_machine(self.p, config.Machine(per_month_usd=20.0))
        with mock.patch.object(run.harness, "run") as h:
            with self.assertRaisesRegex(run.BudgetError, "the month's budget is spent"):
                self.dispatch(FakeGw(usage_monthly=19.98))
        h.assert_not_called()
        self.assertFalse(self.wt.exists())
        self.assertEqual(git.git(["branch", "--list", "aios/T-1"], self.root).strip(), "")


class Secs(unittest.TestCase):
    def test_secs_uses_the_monotonic_clock(self):
        p = config.paths({"HOME": tempfile.mkdtemp()})
        fake_harness(p)
        ws, run_dir = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "run"
        with mock.patch.object(harness.time, "monotonic", side_effect=[100.0, 130.0]) as mono, \
             mock.patch.object(harness.time, "time", side_effect=[1000.0, 5000.0]) as wall:
            a = harness.run(p, ws, "m/x", "t", key="k", run_dir=run_dir, privacy={}, cost_limit=1.0)
        self.assertEqual(a.secs, 30)  # 4000 would mean the wall clock was read
        self.assertEqual(mono.call_count, 2)
        self.assertEqual(wall.call_count, 0)


class Cli(unittest.TestCase):
    def test_a_budget_error_is_reported_as_exit_2(self):
        spec = Path(tempfile.mkdtemp()) / "t.md"
        spec.write_text(SPEC)
        err = io.StringIO()
        with mock.patch.object(cli.run, "dispatch", side_effect=run.BudgetError("T-1: the month's budget is spent")):
            with contextlib.redirect_stderr(err):
                self.assertEqual(cli.main(["dispatch", str(spec)]), 2)
        self.assertIn("aios: T-1: the month's budget is spent", err.getvalue())


if __name__ == "__main__":
    unittest.main()
