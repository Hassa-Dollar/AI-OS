"""Tests for `aios gate`: the verifier, the record, and the CLI command."""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aios import cli, config, gate, gateway, git, records, run
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
files_allowed = ["parser.py", "fixed.txt"]
+++
# Goal
Fix it.
## Acceptance criteria
- `python3 -m unittest` passes
"""

CANNED = {"verdict": "pass", "risk": "low", "blocking": [], "summary": "all clear"}


def decision(action="dispatch"):
    from aios import router
    return router.Decision(action, "AUTO", "T1", "bugfix", "z-ai/glm-5.3-flash", "z-ai",
                           "deepseek/deepseek-v4-pro-0813", "deepseek", "clef-flash", 0.9, ["test"], {})


class FakeGate:
    """A gateway whose chat() returns canned verdicts."""

    def __init__(self, verdicts=None):
        self.calls = []
        self.verdicts = list(verdicts or [CANNED])

    def chat(self, model, messages, schema=None, max_tokens=None):
        self.calls.append({"model": model, "schema": schema, "max_tokens": max_tokens})
        return {"json": dict(self.verdicts.pop(0) if self.verdicts else CANNED), "usd": 0.0123}


class FakeGw:
    """A gateway whose key has no usage and no limit."""

    def key_info(self):
        return {"usage_daily": 0.0, "usage_monthly": 0.0, "limit_remaining": None}


class Env:
    """A temp project, a spec, and a dispatched task in its worktree."""

    def __init__(self):
        state = Path(tempfile.mkdtemp())
        self._env = mock.patch.dict(os.environ,
                                    {f"XDG_{k}_HOME": str(state / k) for k in ("CONFIG", "CACHE", "STATE", "DATA")})
        self._env.start()
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
        self.wt = None

    def cleanup(self):
        self._env.stop()

    def dispatch(self, d=None):
        with mock.patch.object(run, "route", return_value=d or decision()):
            rc = run.dispatch(self.spec, gw=FakeGw(), out=lambda s: self.out.write(s + "\n"))
        if rc != 0:
            raise AssertionError(f"dispatch failed ({rc}):\n{self.out.getvalue()}")
        self.wt = self.p.data / "worktrees" / run.project_id(config.load_project(self.root)) / "T-1"
        return self.wt

    def gate(self, gw=None, **kw):
        return gate.run_gate(self.spec, gw=gw, out=lambda s: self.out.write(s + "\n"), **kw)

    def record(self):
        return records.read(self.wt, "T-1")

    def last_line(self):
        return self.out.getvalue().splitlines()[-1]


@contextlib.contextmanager
def fixture():
    env = Env()
    try:
        yield env
    finally:
        env.cleanup()


@contextlib.contextmanager
def stub_checks(results):
    """Replace gate.run_checks with canned results: [(command, exit, tail), ...]."""
    with mock.patch.object(gate, "run_checks", return_value=list(results)) as m:
        yield m


PASS_CHECKS = [("python3 -m unittest", 0, "Ran 1 test")]


class Gate(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.addCleanup(self.env.cleanup)

    def test_component_of_prefers_the_longest_matching_prefix(self):
        proj = config.Project(root=self.env.root, name="demo", components=(
            config.Component("app", "", "python"), config.Component("api", "api/", "node")))
        s = gate.spec.Spec(id="T-1", title="x", files_allowed=("./", "api/"))
        self.assertEqual(run.component_of(proj, s).path, "api/")
        self.assertEqual(run.component_of(proj, gate.spec.Spec(id="T-1", title="x", files_allowed=("./",))).path, "")

    def test_component_of_raises_when_no_component_covers_the_grant(self):
        proj = config.Project(root=self.env.root, name="demo", components=(config.Component("api", "api/", "node"),))
        s = gate.spec.Spec(id="T-2", title="x", files_allowed=("parser.py",))
        with self.assertRaisesRegex(config.ConfigError, "T-2: files_allowed reaches outside every"):
            run.component_of(proj, s)

    def test_pass_records_and_commits(self):
        self.env.dispatch()
        task_commit = git.git(["rev-parse", "HEAD"], self.env.wt).strip()
        gw = FakeGate()
        with stub_checks(PASS_CHECKS):
            self.assertEqual(self.env.gate(gw), 0)
        self.assertEqual(len(gw.calls), 1)
        self.assertEqual(gw.calls[0]["schema"], gate.VERDICT_SCHEMA)
        self.assertEqual(gw.calls[0]["max_tokens"], gate.VERIFIER_MAX_TOKENS)
        self.assertEqual(gw.calls[0]["model"], "deepseek/deepseek-v4-pro-0813")
        rec = self.env.record()
        self.assertEqual(rec["gate"], "AUTO")
        self.assertEqual(rec["flags"], [])
        v = rec["attempts"][-1]["verdict"]
        self.assertEqual(v["verdict"], "pass")
        self.assertEqual(v["verifier"], "deepseek/deepseek-v4-pro-0813")
        self.assertTrue(v["patch_id"])
        self.assertEqual(v["commit"], task_commit)
        self.assertEqual(rec["usd_total"], 0.0246)
        self.assertEqual(git.git(["log", "-1", "--format=%s"], self.env.wt).strip(),
                         "T-1: record (verdict pass, gate AUTO)")
        self.assertFalse(git.git(["status", "--porcelain", "--untracked-files=no"], self.env.wt).strip())
        self.assertTrue((self.env.wt / ".aios" / "records" / "T-1.json").is_file())
        self.assertEqual(self.env.last_line(), "T-1: verdict pass (low) | gate AUTO | flags none | $0.0246")

    def test_failing_check_skips_verifier(self):
        self.env.dispatch()
        gw = FakeGate()
        with stub_checks([("python3 -m unittest", 1, "failed")]):
            self.assertEqual(self.env.gate(gw), 1)
        self.assertEqual(gw.calls, [])
        v = self.env.record()["attempts"][-1]["verdict"]
        self.assertEqual(v["verdict"], "fail")
        self.assertIsNone(v["verifier"])
        self.assertEqual(v["usd"], 0.0)
        self.assertEqual(v["blocking"], ["check failed (exit 1): python3 -m unittest"])
        self.assertEqual(git.git(["log", "-1", "--format=%s"], self.env.wt).strip(),
                         "T-1: record (verdict fail, gate LEAD)")
        self.assertEqual(self.env.last_line(), "  - check failed (exit 1): python3 -m unittest")

    def test_out_of_scope_skips_verifier(self):
        self.env.dispatch()
        (self.env.wt / "outside.py").write_text("x = 2\n")
        git.git(["add", "--all", "--", ".", *run._NOT_CACHES], self.env.wt)
        git.git(["commit", "-qm", "outside"], self.env.wt)
        gw = FakeGate()
        with stub_checks(PASS_CHECKS):
            self.assertEqual(self.env.gate(gw), 1)
        self.assertEqual(gw.calls, [])
        rec = self.env.record()
        self.assertIn("out-of-scope", rec["flags"])
        self.assertEqual(rec["gate"], "LEAD")
        self.assertIn("out of scope: outside.py", self.env.out.getvalue())

    def test_verifier_risk_high_is_leaded(self):
        self.env.dispatch()
        with stub_checks(PASS_CHECKS):
            self.assertEqual(self.env.gate(FakeGate([{**CANNED, "risk": "high"}])), 0)
        rec = self.env.record()
        self.assertIn("verifier-risk-high", rec["flags"])
        self.assertEqual(rec["gate"], "LEAD")
        self.assertIn("gate LEAD", self.env.out.getvalue())

    def test_verifier_fail_or_needs_decision(self):
        self.env.dispatch()
        failing = {**CANNED, "verdict": "fail", "risk": "medium", "blocking": ["unhandled case"]}
        with stub_checks(PASS_CHECKS):
            self.assertEqual(self.env.gate(FakeGate([failing, dict(failing)])), 1)
            v = self.env.record()["attempts"][-1]["verdict"]
            self.assertEqual([r["verdict"] for r in v["reviews"]], ["fail", "fail"])
            self.assertEqual(v["confirmed_by"], "deepseek/deepseek-v4-pro-0813")
            self.assertEqual(self.env.gate(FakeGate([{**CANNED, "verdict": "needs_decision"}])), 1)

    def test_a_first_fail_needs_a_confirming_second_review(self):
        self.env.dispatch()
        gw = FakeGate([{**CANNED, "verdict": "fail", "risk": "medium", "blocking": ["unhandled case"]},
                       {**CANNED, "summary": "fine on a second look"}])
        with stub_checks(PASS_CHECKS):
            self.assertEqual(self.env.gate(gw), 0)
        self.assertEqual([c["model"] for c in gw.calls],
                         ["deepseek/deepseek-v4-pro-0813", "deepseek/deepseek-v4-pro-0813"])
        rec = self.env.record()
        v = rec["attempts"][-1]["verdict"]
        self.assertEqual(v["verdict"], "pass")
        self.assertEqual([r["verdict"] for r in v["reviews"]], ["fail", "pass"])
        self.assertIn("A first review failed this change", v["summary"])
        self.assertNotIn("confirmed_by", v)

    def test_no_worktree_raises(self):
        with self.assertRaisesRegex(config.ConfigError, "dispatch it first"):
            gate.run_gate(self.env.spec, out=lambda s: None)

    def test_patch_id_is_content_based_and_stable(self):
        self.env.dispatch()
        git.git(["checkout", "-q", "-b", "empty", "main"], self.env.wt)
        self.assertEqual(gate.patch_id(self.env.wt, "main"), "")
        git.git(["checkout", "-q", "aios/T-1"], self.env.wt)
        (self.env.wt / "new.py").write_text("y = 2\n")
        git.git(["add", "new.py"], self.env.wt)
        git.git(["commit", "-qm", "new"], self.env.wt)
        pid = gate.patch_id(self.env.wt, "main")
        (self.env.root / "other.txt").write_text("base\n")
        git.git(["add", "other.txt"], self.env.root)
        git.git(["commit", "-qm", "base"], self.env.root)
        git.git(["rebase", "main"], self.env.wt)
        self.assertEqual(gate.patch_id(self.env.wt, "main"), pid)
        (self.env.wt / "new.py").write_text("y = 3\n")
        git.git(["add", "new.py"], self.env.wt)
        git.git(["commit", "-qm", "different"], self.env.wt)
        self.assertNotEqual(gate.patch_id(self.env.wt, "main"), pid)

    def test_verifier_diff_excludes_lockfiles_and_truncates(self):
        self.env.dispatch()
        (self.env.wt / "package-lock.json").write_text("{}\n")
        (self.env.wt / "web").mkdir()
        (self.env.wt / "web" / "yarn.lock").write_text("# yarn\n")
        (self.env.wt / "parser.py").write_text("x = 2\n")
        git.git(["add", "."], self.env.wt)
        git.git(["commit", "-qm", "locks"], self.env.wt)
        text = gate.verifier_diff(self.env.wt, "main")
        self.assertIn("parser.py", text)
        self.assertNotIn("package-lock.json", text)
        self.assertNotIn("yarn.lock", text)
        (self.env.wt / "big.txt").write_text("x" * 100_000)
        git.git(["add", "big.txt"], self.env.wt)
        git.git(["commit", "-qm", "big"], self.env.wt)
        self.assertTrue(gate.verifier_diff(self.env.wt, "main").endswith("[diff truncated]"))

    def test_cli_gate_builds_the_privacy_aware_gateway(self):
        self.env.dispatch()
        proj = config.load_project(self.env.root)
        out = io.StringIO()
        with mock.patch.object(gateway, "Gateway", return_value=FakeGate()) as gw_cls:
            with stub_checks(PASS_CHECKS), contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["gate", str(self.env.spec)]), 0)
        self.assertEqual(gw_cls.call_args.kwargs.get("privacy"), gateway.privacy_of(proj))

    def test_cli_gate_reports_value_error_as_exit_2(self):
        self.env.dispatch()
        with mock.patch.object(gate, "run_gate", side_effect=ValueError("no verifier")):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(cli.main(["gate", str(self.env.spec)]), 2)
        self.assertIn("aios: no verifier", err.getvalue())


if __name__ == "__main__":
    unittest.main()
