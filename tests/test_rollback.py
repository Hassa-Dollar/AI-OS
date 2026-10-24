"""Tests for `aios rollback`: the revert travels through the forge and takes the record with it."""
import contextlib
import io
import shutil
import unittest
from pathlib import Path
from unittest import mock

from aios import cli, config, git, land, run
from tests.test_land import Env, FakeForge


class Landed(Env):
    """A temp project with a local forge where T-1 has already landed on main."""

    def __init__(self):
        super().__init__()
        self.dispatch()
        self.gate()
        self.commit_spec()
        assert self.land() == 0

    @property
    def rwt(self):
        """The worktree a rollback works in: the task's id plus -revert (ADR-0030)."""
        return run.worktree_path(self.p, config.load_project(self.root), "T-1-revert")

    def branch_gone(self):
        """Whether the revert branch and the revert worktree are both gone."""
        return not self.rwt.exists() and not git.git(["branch", "--list", "aios/T-1-revert"], self.root).strip()


class Rollback(unittest.TestCase):
    def setUp(self):
        self.env = Landed()
        self.addCleanup(self.env.cleanup)

    def test_a_rollback_removes_the_code_and_the_record(self):
        self.assertEqual(land.rollback(self.env.spec, out=lambda s: None), 0)
        head = git.git(["rev-parse", "HEAD"], self.env.root).strip()
        self.assertEqual(len(git.git(["rev-list", "--parents", "-1", head], self.env.root).split()), 3)  # a merge
        tree = git.git(["ls-tree", "-r", "--name-only", head], self.env.root).split()
        self.assertNotIn("fixed.txt", tree)  # the task's own change is gone
        self.assertNotIn(".aios/records/T-1.json", tree)  # so the task reads as rolled back (ADR-0030 rule 3)
        self.assertIn("parser.py", tree)
        self.assertEqual((self.env.root / "parser.py").read_text(), "x = 1\n")
        self.assertFalse((self.env.root / "fixed.txt").exists())
        self.assertTrue(self.env.branch_gone())

    def test_a_task_that_never_landed_cannot_be_rolled_back(self):
        env = Env()
        self.addCleanup(env.cleanup)
        env.dispatch()
        env.gate()
        with self.assertRaisesRegex(config.ConfigError, "T-1: no landed record on main"):
            land.rollback(env.spec, out=lambda s: None)
        self.assertTrue(env.wt.exists())

    def test_a_conflicting_later_change_refuses_the_rollback(self):
        # main moved on and rewrote the file the task added, so the revert cannot apply cleanly
        (self.env.root / "fixed.txt").write_text("changed after the land\n")
        git.git(["commit", "-qam", "later change"], self.env.root)
        head = git.git(["rev-parse", "HEAD"], self.env.root).strip()
        merge = git.git(["log", "--first-parent", "--diff-filter=A", "--format=%H", "-1", "main",
                         "--", ".aios/records/T-1.json"], self.env.root).strip()
        with self.assertRaisesRegex(config.ConfigError,
                                    rf"revert it by hand: git revert -m 1 {merge[:12]}"):
            land.rollback(self.env.spec, out=lambda s: None)
        self.assertEqual(git.git(["rev-parse", "HEAD"], self.env.root).strip(), head)  # main is unchanged
        self.assertEqual((self.env.root / "fixed.txt").read_text(), "changed after the land\n")
        self.assertTrue(self.env.branch_gone())

    def test_a_second_rollback_refuses_and_leaves_nothing_behind(self):
        self.assertEqual(land.rollback(self.env.spec, out=lambda s: None), 0)
        with self.assertRaisesRegex(config.ConfigError, "T-1: already rolled back on main; nothing to revert"):
            land.rollback(self.env.spec, out=lambda s: None)
        self.assertTrue(self.env.branch_gone())

    def test_the_injected_forge_gets_the_revert_branch_title_and_body(self):
        f = FakeForge()
        self.assertEqual(land.rollback(self.env.spec, forge=f, out=lambda s: None), 0)
        merge = git.git(["log", "--first-parent", "--diff-filter=A", "--format=%H", "-1", "main",
                         "--", ".aios/records/T-1.json"], self.env.root).strip()
        branch, title, body = f.calls[0]
        self.assertEqual(branch, "aios/T-1-revert")
        self.assertEqual(title, "Revert T-1: Fix the parser")
        self.assertIn(f"Rolls back T-1 (merge {merge[:12]}).", body)
        self.assertIn("The revert removes .aios/records/T-1.json, so the task reads as rolled back "
                      "(ADR-0030 rule 3).", body)
        self.assertTrue(self.env.branch_gone())

    def test_an_existing_revert_worktree_refuses_the_rollback(self):
        self.env.rwt.mkdir(parents=True)
        with self.assertRaisesRegex(config.ConfigError, "a revert worktree for T-1 is already there"):
            land.rollback(self.env.spec, out=lambda s: None)
        shutil.rmtree(self.env.rwt)
        self.assertEqual(land.rollback(self.env.spec, out=lambda s: None), 0)

    def test_the_cli_rolls_a_task_back(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["rollback", str(self.env.spec)])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("T-1: rolled back by ", out.getvalue())
        self.assertFalse((self.env.root / "fixed.txt").exists())
        self.assertTrue(self.env.branch_gone())

    def test_the_cli_rollback_is_wired_to_land_rollback(self):
        f = str(self.env.spec)
        with mock.patch.object(land, "rollback", return_value=0) as rb:
            code = cli.main(["rollback", f])
        self.assertEqual(code, 0)
        rb.assert_called_once_with(Path(f))


if __name__ == "__main__":
    unittest.main()
