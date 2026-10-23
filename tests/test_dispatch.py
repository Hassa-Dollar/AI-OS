import io
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from aios import config, git, router, run
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
    return router.Decision(action, "AUTO", "T1", "bugfix", "z-ai/glm-5.3-flash", "z-ai",
                           "deepseek/deepseek-v4-pro-0813", "deepseek", "clef-flash", 0.9, ["test"], {})


class FakeGw:
    """A gateway whose key has no usage and no limit."""

    def key_info(self):
        return {"usage_daily": 0.0, "usage_monthly": 0.0, "limit_remaining": None}


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

    def dispatch(self, d=None, **kw):
        with mock.patch.object(run, "route", return_value=d or decision()):
            return run.dispatch(self.spec, gw=FakeGw(), out=lambda s: self.out.write(s + "\n"), **kw)

    def head_and_status(self):
        return git.git(["rev-parse", "HEAD"], self.root), git.git(["status", "--porcelain"], self.root)

    def test_runs_in_a_worktree_and_commits_there_only(self):
        before = self.head_and_status()
        self.assertEqual(self.dispatch(), 0, self.out.getvalue())
        self.assertEqual(self.head_and_status(), before)  # the operator's checkout is untouched
        wt = self.p.data / "worktrees" / run.project_id(config.load_project(self.root)) / "T-1"
        self.assertEqual(git.git(["rev-parse", "--abbrev-ref", "HEAD"], wt).strip(), "aios/T-1")
        msg = git.git(["log", "-1", "--format=%B"], wt)
        self.assertIn("Implemented-By: z-ai/glm-5.3-flash via mini-swe-agent 2.4.6", msg)
        self.assertEqual((wt / "fixed.txt").read_text(), "done\n")
        committed = git.git(["show", "--name-only", "--format=", "HEAD"], wt).split()
        self.assertEqual(committed, ["fixed.txt"])  # build caches are never committed (lesson #3)
        attempts = list(self.p.state.glob("demo-*/runs/T-1/*/attempt.json"))
        self.assertEqual(len(attempts), 1)
        self.assertIn("Be careful.", (attempts[0].parent / "cfg.yaml").read_text())  # target AGENTS.md reached the worker
        with self.assertRaisesRegex(config.ConfigError, "in flight"):
            self.dispatch()

    def test_dry_run_and_refusal_touch_nothing(self):
        self.assertEqual(self.dispatch(dry_run=True), 0)
        self.assertFalse((self.p.data / "worktrees").exists())
        self.assertEqual(self.dispatch(decision("refuse")), 3)
        self.assertFalse((self.p.data / "worktrees").exists())

    def test_escalation_is_not_committed(self):
        (self.p.data / "harness" / "bin" / "fake_final").write_text("ESCALATE: needs a contract change")
        self.assertEqual(self.dispatch(), 4)
        self.assertIn("ESCALATE: needs a contract change", self.out.getvalue())
        wt = next((self.p.data / "worktrees").glob("*/T-1"))
        self.assertEqual(git.git(["log", "-1", "--format=%s"], wt).strip(), "init")

    def test_requires_a_project(self):
        stray = Path(subprocess.check_output(["mktemp", "-d"], text=True).strip()) / "t.md"
        stray.write_text(SPEC)
        with self.assertRaisesRegex(config.ConfigError, "aios init"):
            run.dispatch(stray, out=lambda s: None)


if __name__ == "__main__":
    unittest.main()
