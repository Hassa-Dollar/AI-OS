"""Tests for `aios approve` and `aios land`: the approval, the patch binding, and the merge."""
import contextlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aios import cli, config, forge, gate, git, land, records, run
from tests.helpers import git_repo
from tests.test_harness import fake_harness

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

SPEC = """+++
id = "T-1"
title = "Fix the parser"
files_allowed = ["parser.py", "fixed.txt"]
+++
# Goal
Fix it.
## Acceptance criteria
- `python3 -m unittest` passes
"""

CANNED = {"verdict": "pass", "risk": "low", "blocking": [], "summary": "all clear"}
PASS_CHECKS = [("python3 -m unittest", 0, "Ran 1 test")]
FAIL_CHECKS = [("python3 -m unittest", 1, "1 test failed")]


def decision(gate_tier="AUTO"):
    from aios import router
    return router.Decision("dispatch", gate_tier, "T1", "bugfix", "z-ai/glm-5.3-flash", "z-ai",
                           "deepseek/deepseek-v4-pro-0813", "deepseek", "clef-flash", 0.9, ["test"], {})


class FakeGate:
    """A gateway whose chat() returns a passing verdict."""

    def chat(self, model, messages, schema=None, max_tokens=None):
        return {"json": dict(CANNED), "usd": 0.0123}


class FakeForge:
    """A forge that records (branch, title, body) instead of merging anything."""

    def __init__(self, sha="a" * 40):
        self.sha, self.calls = sha, []

    def land(self, branch, title, body):
        self.calls.append((branch, title, body))
        return self.sha


class Env:
    """A temp project with a local forge, and a dispatched task in its worktree."""

    def __init__(self, gate_tier="AUTO"):
        self._tmp = tempfile.mkdtemp(prefix="aios-land-")
        for d in ("config", "cache", "state", "data", "repo"):
            (Path(self._tmp) / d).mkdir()
        self._env = mock.patch.dict(os.environ, {f"XDG_{k}_HOME": f"{self._tmp}/{k.lower()}"
                                                 for k in ("CONFIG", "CACHE", "STATE", "DATA")})
        self._env.start()
        self.root = git_repo({"parser.py": "x = 1\n", ".aios/project.toml": PROJECT, "AGENTS.md": "Be careful.\n"},
                             remote=None)
        shutil.move(str(self.root), str(Path(self._tmp) / "repo" / "proj"))
        self.root = Path(self._tmp) / "repo" / "proj"
        self.spec = self.root / ".aios" / "tasks" / "T-1.md"
        self.spec.parent.mkdir(parents=True, exist_ok=True)
        self.spec.write_text(SPEC)
        self.p = config.paths()
        self.p.config.mkdir(parents=True, exist_ok=True)
        self.p.credentials.write_text("sk-or-v1-test")
        os.chmod(self.p.credentials, 0o600)
        fake_harness(self.p)
        self.gate_tier = gate_tier
        self.wt = None

    def cleanup(self):
        self._env.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def dispatch(self):
        with mock.patch.object(run, "route", return_value=decision(self.gate_tier)):
            assert run.dispatch(self.spec, out=lambda s: None) == 0
        self.wt = run.worktree_path(self.p, config.load_project(self.root), "T-1")

    def gate(self, checks=PASS_CHECKS):
        with mock.patch.object(gate, "run_checks", return_value=list(checks)):
            return gate.run_gate(self.spec, gw=FakeGate(), out=lambda s: None)

    def approve(self, by="operator", note="hil pass, rev b"):
        return land.approve(self.spec, by=by, note=note, out=lambda s: None)

    def land(self, forge=None):
        return land.land(self.spec, forge=forge, out=lambda s: None)

    def commit_spec(self):
        """The spec is the operator's file: commit it so the main checkout is clean enough to merge into."""
        git.git(["add", ".aios/tasks/T-1.md"], self.root)
        git.git(["commit", "-qm", "spec"], self.root)

    def record(self):
        return records.read(self.wt, "T-1")


class Land(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.addCleanup(self.env.cleanup)
        self.env.dispatch()

    def test_auto_lands_without_an_approval(self):
        self.env.gate()
        self.assertIsNone(self.env.record()["approval"])
        self.assertEqual(self.env.land(FakeForge()), 0)

    def test_auto_lands_and_cleans_up(self):
        self.env.gate()
        self.env.commit_spec()
        self.assertEqual(self.env.land(), 0)
        head = git.git(["rev-parse", "HEAD"], self.env.root).strip()
        self.assertEqual(len(git.git(["rev-list", "--parents", "-1", "HEAD"], self.env.root).split()), 3)  # a merge
        self.assertEqual(git.git(["log", "-1", "--format=%s"], self.env.root).strip(), "T-1: Fix the parser")
        merged = git.git(["diff", "--name-only", f"{head}^..{head}"], self.env.root).split()
        self.assertIn("fixed.txt", merged)
        self.assertIn(".aios/records/T-1.json", merged)
        self.assertFalse(self.env.wt.exists())
        self.assertEqual(git.git(["branch", "--list", "aios/T-1"], self.env.root).strip(), "")

    def test_uncommitted_changes_in_the_worktree(self):
        self.env.gate()
        (self.env.wt / "parser.py").write_text("x = 4\n")
        with self.assertRaisesRegex(config.ConfigError, "has uncommitted changes"):
            self.env.land(FakeForge())
        (self.env.wt / "parser.py").write_text("x = 1\n")
        (self.env.wt / "stray.txt").write_text("junk\n")
        with self.assertRaisesRegex(config.ConfigError, "has uncommitted changes"):
            self.env.land(FakeForge())

    def test_a_code_commit_after_the_gate_needs_a_new_gate(self):
        self.env.gate()
        (self.env.wt / "parser.py").write_text("x = 3\n")
        git.git(["add", "parser.py"], self.env.wt)
        git.git(["commit", "-qm", "more"], self.env.wt)
        with self.assertRaisesRegex(ValueError, "T-1: the branch changed since the gate; run 'aios gate' again"):
            self.env.land(FakeForge())
        self.env.gate()
        self.env.commit_spec()
        self.assertEqual(self.env.land(FakeForge()), 0)

    def test_the_injected_forge_gets_the_branch_title_and_body(self):
        self.env.gate()
        f = FakeForge()
        self.assertEqual(self.env.land(f), 0)
        branch, title, body = f.calls[0]
        self.assertEqual((branch, title), ("aios/T-1", "T-1: Fix the parser"))
        self.assertIn("all clear", body)
        self.assertIn("Gate: AUTO | flags: none | verdict: pass (low) by deepseek/deepseek-v4-pro-0813", body)
        self.assertIn("Cost: $0.0246 | record: .aios/records/T-1.json", body)
        self.assertNotIn("Approval:", body)

    def test_the_approval_line_shows_up_once_approved(self):
        self.env.gate()
        self.env.approve()
        f = FakeForge()
        self.assertEqual(self.env.land(f), 0)
        self.assertIn("Approval: operator: hil pass, rev b", f.calls[0][2])

    def test_a_forge_that_leaves_real_work_behind_fails_loud(self):
        """The merge may succeed, but only build caches may be left behind: never force anything else away."""
        self.env.gate()
        self.env.commit_spec()
        wt = self.env.wt

        class Messy(FakeForge):
            def land(self, branch, title, body):
                (wt / "leftover.txt").write_text("not a cache\n")
                return super().land(branch, title, body)

        f = Messy()
        with self.assertRaisesRegex(config.ConfigError,
                                    "T-1: landed aaaaaaaaaaaa, but .* has uncommitted changes"):
            self.env.land(f)
        self.assertTrue(wt.exists())  # aios never deletes work it did not judge

    def test_a_worktree_holding_only_build_caches_is_removed(self):
        """The gate's checks write caches; they are not uncommitted work (lesson #3)."""
        self.env.gate()
        self.assertTrue((self.env.wt / "__pycache__").is_dir())  # the gate's own checks leave one behind
        (self.env.wt / "__pycache__" / "parser.cpython-311.pyc").write_bytes(b"")
        (self.env.wt / ".coverage").write_text("")
        self.env.commit_spec()
        self.assertEqual(self.env.land(), 0)
        self.assertFalse(self.env.wt.exists())

    def test_no_worktree_fails_loud(self):
        env = Env()
        self.addCleanup(env.cleanup)
        with self.assertRaisesRegex(config.ConfigError, "dispatch it first"):
            env.land(FakeForge())

    def test_no_record_fails_loud(self):
        env = Env()
        self.addCleanup(env.cleanup)
        env.dispatch()
        with self.assertRaisesRegex(config.ConfigError, "run 'aios gate' first"):
            env.land(FakeForge())


class Approval(unittest.TestCase):
    def setUp(self):
        self.env = Env(gate_tier="LEAD")
        self.addCleanup(self.env.cleanup)
        self.env.dispatch()

    def test_lead_gate_needs_an_approval_then_lands(self):
        self.env.gate()
        with self.assertRaisesRegex(ValueError, "T-1: gate LEAD needs 'aios approve' first"):
            self.env.land(FakeForge())
        self.assertEqual(self.env.approve(by="lead", note="ok"), 0)
        self.assertEqual(git.git(["log", "-1", "--format=%s"], self.env.wt).strip(), "T-1: approve (lead)")
        self.assertEqual(self.env.record()["approval"], {"by": "lead", "note": "ok"})
        self.env.commit_spec()
        self.assertEqual(self.env.land(), 0)

    def test_human_gate_needs_the_operator(self):
        env = Env(gate_tier="HUMAN")
        self.addCleanup(env.cleanup)
        env.dispatch()
        env.gate()
        with self.assertRaisesRegex(ValueError, "T-1: the HUMAN gate needs the operator's approval"):
            env.approve(by="lead")
        self.assertEqual(env.approve(by="operator", note="ok"), 0)
        env.commit_spec()
        self.assertEqual(env.land(), 0)

    def test_a_failing_verdict_cannot_be_approved_or_landed(self):
        self.env.gate(checks=FAIL_CHECKS)
        with self.assertRaisesRegex(ValueError, "T-1: the verdict is fail"):
            self.env.approve(by="operator")
        with self.assertRaisesRegex(ValueError, "T-1: the verdict is fail"):
            self.env.land(FakeForge())

    def test_the_approval_needs_a_by_and_a_note(self):
        self.env.gate()
        with self.assertRaisesRegex(ValueError, "--by must be"):
            self.env.approve(by="model", note="ok")
        with self.assertRaisesRegex(ValueError, "--note must not be empty"):
            self.env.approve(by="operator", note="   ")

    def test_operator_gate_needs_an_approval_and_accepts_either_approver(self):
        env = Env(gate_tier="OPERATOR")
        self.addCleanup(env.cleanup)
        env.dispatch()
        env.gate()
        with self.assertRaisesRegex(ValueError, "gate OPERATOR needs 'aios approve' first"):
            env.land(FakeForge())
        self.assertEqual(env.approve(by="lead"), 0)
        env.commit_spec()
        self.assertEqual(env.land(), 0)

    def test_an_unknown_gate_fails_closed(self):
        self.env.gate()
        record = self.env.record()
        record["gate"] = "MAYBE"
        records.write(self.env.wt, record)
        with self.assertRaisesRegex(ValueError, "MAYBE"):
            self.env.approve(by="operator")
        with self.assertRaisesRegex(ValueError, "MAYBE"):
            self.env.land(FakeForge())


class Cli(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.addCleanup(self.env.cleanup)
        self.env.dispatch()
        self.env.gate()

    def test_cli_approve_parses_by_and_note(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["approve", str(self.env.spec), "--by", "lead", "--note", "ok"]), 0)
        self.assertIn("T-1: approved by lead | gate AUTO", out.getvalue())
        self.assertEqual(records.read(self.env.wt, "T-1")["approval"], {"by": "lead", "note": "ok"})

    def test_cli_land_reports_a_forge_error_as_exit_2(self):
        err = io.StringIO()
        with mock.patch.object(forge, "for_project", side_effect=forge.ForgeError("gh is not installed")):
            with contextlib.redirect_stderr(err):
                self.assertEqual(cli.main(["land", str(self.env.spec)]), 2)
        self.assertIn("aios: gh is not installed", err.getvalue())


class RecordExclusion(unittest.TestCase):
    """The task's own record is not part of the change being judged (D2b)."""

    def setUp(self):
        self.env = Env()
        self.addCleanup(self.env.cleanup)
        self.env.dispatch()
        self.env.gate()

    def test_patch_id_ignores_the_task_record(self):
        pid = gate.patch_id(self.env.wt, "main", task_id="T-1")
        self.assertNotEqual(pid, gate.patch_id(self.env.wt, "main"))
        self.assertEqual(pid, self.env.record()["attempts"][-1]["verdict"]["patch_id"])
        self.env.approve()
        self.assertEqual(gate.patch_id(self.env.wt, "main", task_id="T-1"), pid)
        self.assertNotEqual(gate.patch_id(self.env.wt, "main"), pid)

    def test_verifier_diff_ignores_the_task_record(self):
        diff = gate.verifier_diff(self.env.wt, "main", task_id="T-1")
        self.assertIn("fixed.txt", diff)
        self.assertNotIn(".aios/records/T-1.json", diff)
        self.assertIn(".aios/records/T-1.json", gate.verifier_diff(self.env.wt, "main"))


if __name__ == "__main__":
    unittest.main()
