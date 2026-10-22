"""Tests for the gate pipeline: the run.py helpers, `diff`/`patch_id`, `verify`, `run_gate`, and `aios gate`."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from aios import cli, config, gate, git, records, run
from tests.helpers import git_repo

PROJECT = """schema = 1
name = "demo"
forge = "local"
[[components]]
name = "app"
path = "./"
profile = "python"
checks = ["python3 -m unittest"]
"""

MONO = """schema = 1
name = "mono"
forge = "local"
[[components]]
name = "app"
path = "./"
profile = "python"
checks = ["true"]
[[components]]
name = "api"
path = "api/"
profile = "python"
checks = ["true"]
"""

API_ONLY = """schema = 1
name = "api"
forge = "local"
[[components]]
name = "api"
path = "api/"
profile = "python"
checks = ["true"]
"""

SPEC = """+++
id = "T-1"
title = "Fix the parser"
files_allowed = ["src/", "parser.py"]
deps_preapproved = ["numpy"]
+++

## Goal
Fix the parser.

## Acceptance criteria
- `python3 -m unittest` passes
"""

PASS = {"verdict": "pass", "risk": "low", "blocking": [], "summary": "the change does what the spec asks"}
FAIL = {"verdict": "fail", "risk": "medium", "blocking": ["the test never fails"], "summary": "no"}
NEEDS = {"verdict": "needs_decision", "risk": "low", "blocking": [], "summary": "the spec is ambiguous"}

DECISION = {"action": "dispatch", "gate": "AUTO", "tier": "T1", "task_class": "bugfix",
            "author": "z-ai/glm-5.3-flash", "author_family": "z-ai", "verifier": "deepseek/deepseek-v4-pro-0813",
            "verifier_family": "deepseek", "router": "clef-flash", "confidence": 0.9, "reasons": ["ok"], "answers": {}}
ATTEMPT = {"exit": "submitted", "model": "z-ai/glm-5.3-flash", "harness": "mini-swe-agent 2.4.6",
           "secs": 12, "steps": 5, "usd": 0.02, "summary": "fixed the parser"}


class FakeGate:
    """A stand-in for gateway.Gateway: records the call and replays one canned verdict."""

    def __init__(self, verdict=PASS, usd=0.005):
        self.verdict, self.usd, self.calls = verdict, usd, []

    def chat(self, model, messages, **kw):
        self.calls.append((model, messages, kw))
        return {"content": "", "json": self.verdict, "usd": self.usd, "usage": {}, "model": model,
                "provider": "Zed"}


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def commit_all(wt: Path, msg: str = "c") -> None:
    git.git(["add", "-A"], wt)
    git.git(["commit", "-qm", msg], wt)


def stub_checks():
    """run_gate's sandboxed checks would need bwrap; stand in for them (the real ones are tested in test_gate)."""
    return mock.patch.object(gate, "run_checks", return_value=[("python3 -m unittest", 0, "OK")])


def fixture(spec_text=SPEC, project=PROJECT, change=True, task="T-1"):
    """A project, a spec, a dispatched-looking worktree holding one change, and one recorded attempt."""
    root = git_repo({"parser.py": "x = 1\n", ".aios/project.toml": project, "AGENTS.md": "Be careful.\n"})
    p, proj = config.paths(), config.load_project(root)
    spec_path = root / ".aios" / "tasks" / f"{task}.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(spec_text)
    base = git.git(["rev-parse", "HEAD"], root).strip()
    wt = run.worktree_path(p, proj, task)
    wt.parent.mkdir(parents=True, exist_ok=True)
    git.git(["worktree", "add", "--quiet", "-b", f"aios/{task}", str(wt), base], root)
    if change:
        write(wt, "parser.py", "x = 2\n")
        commit_all(wt, f"{task}: fix the parser")
    runs = p.state / run.project_id(proj) / "runs" / task / "20261022T000000"
    runs.mkdir(parents=True)
    (runs / "attempt.json").write_text(json.dumps({"decision": dict(DECISION), "attempt": dict(ATTEMPT)}))
    return SimpleNamespace(root=root, p=p, proj=proj, spec_path=spec_path, base=base, wt=wt, runs=runs)


class Env(unittest.TestCase):
    def setUp(self):
        state = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, state, True)
        e = mock.patch.dict(os.environ, {f"XDG_{k}_HOME": str(state / k) for k in ("CONFIG", "CACHE", "STATE", "DATA")})
        e.start()
        self.addCleanup(e.stop)


class RunHelpers(Env):
    """base_ref, worktree_path and component_of, extracted from dispatch (ADR-0030)."""

    def test_base_ref_without_a_remote_is_the_checked_out_branch(self):
        root = git_repo({".aios/project.toml": PROJECT})
        self.assertEqual("main", run.base_ref(config.load_project(root), root))

    def test_base_ref_prefixes_the_remote_and_honours_a_configured_branch(self):
        root = git_repo({".aios/project.toml": PROJECT}, remote="https://example.invalid/acme/app.git")
        self.assertEqual("origin/main", run.base_ref(config.load_project(root), root))
        with_branch = PROJECT.replace('forge = "local"', 'forge = "local"\ndefault_branch = "trunk"')
        write(root, ".aios/project.toml", with_branch)
        self.assertEqual("origin/trunk", run.base_ref(config.load_project(root), root))
        self.assertEqual("trunk", run.base_ref(config.load_project(git_repo({".aios/project.toml": with_branch})),
                                              git_repo({".aios/project.toml": with_branch})))

    def test_worktree_path_is_one_per_project_and_task(self):
        root = git_repo({".aios/project.toml": PROJECT, "a.txt": "x"})
        p, proj = config.paths(), config.load_project(root)
        self.assertEqual(p.data / "worktrees" / f"demo-{git.root_commit(root)[:8]}" / "T-9",
                         run.worktree_path(p, proj, "T-9"))
        other = config.load_project(git_repo({".aios/project.toml": PROJECT, "a.txt": "y"}))
        self.assertNotEqual(run.worktree_path(p, proj, "T-9"), run.worktree_path(p, other, "T-9"))

    def test_component_of_prefers_the_longest_matching_prefix(self):
        proj = config.load_project(git_repo({".aios/project.toml": MONO}))
        self.assertEqual("api", run.component_of(proj, ("api/x.py",)).name)
        self.assertEqual("app", run.component_of(proj, ("src/a.py", "api/deep/b.py", "README.md")).name)
        self.assertEqual("app", run.component_of(proj, ("src/a.py",)).name)

    def test_component_of_refuses_grants_outside_every_component(self):
        proj = config.load_project(git_repo({".aios/project.toml": API_ONLY}))
        with self.assertRaisesRegex(config.ConfigError, "files_allowed reaches outside"):
            run.component_of(proj, ("api/a.py", "src/x.py"))


class PatchId(Env):
    def test_patch_id_is_content_based_and_stable(self):
        def one(change: str) -> str:
            root = git_repo({"f.py": "a\nb\n"})
            base = git.git(["rev-parse", "HEAD"], root).strip()
            write(root, "f.py", change)
            commit_all(root)
            return gate.patch_id(root, base)

        self.assertEqual(one("a\nB\n"), one("a\nB\n"))  # the same diff in a different repo: same patch id
        self.assertNotEqual(one("a\nB\n"), one("a\nb\n"))

    def test_patch_id_excludes_build_caches_and_is_empty_without_a_diff(self):
        root = git_repo({"f.py": "a\n"})
        base = git.git(["rev-parse", "HEAD"], root).strip()
        self.assertEqual("", gate.patch_id(root, base))
        write(root, "f.py", "a\nB\n")
        write(root, "__pycache__/j.pyc", "junk")
        commit_all(root)
        self.assertEqual(gate.patch_id(root, base), gate.patch_id(git_repo({"f.py": "a\nB\n"}),
                                                                  git.git(["rev-parse", "HEAD"],
                                                                          git_repo({"f.py": "a\nB\n"})).strip()))


class Verify(Env):
    def test_verify_renders_the_prompt_and_returns_the_verdict(self):
        g = FakeGate()
        v = gate.verify(g, "deepseek/deepseek-v4-pro-0813", "SPEC TEXT", "DIFF TEXT",
                        [("pytest -q", 0, "3 passed"), ("ruff check .", 1, "E501")])
        self.assertEqual((v["verdict"], v["risk"], v["blocking"], v["summary"]), ("pass", "low", [], PASS["summary"]))
        self.assertEqual((v["model"], v["usd"]), ("deepseek/deepseek-v4-pro-0813", 0.005))
        model, messages, kw = g.calls[0]
        self.assertEqual((model, list(messages), kw["schema"]), ("deepseek/deepseek-v4-pro-0813",
                                                                 [{"role": "user", "content": mock.ANY}],
                                                                 gate.VERDICT_SCHEMA))
        prompt = messages[0]["content"]
        for bit in ("SPEC TEXT", "DIFF TEXT", "$ pytest -q", "exit 0", "3 passed", "$ ruff check .", "exit 1"):
            self.assertIn(bit, prompt)
        self.assertNotIn("blocking: [", prompt)

    def test_verify_fails_closed_on_a_bad_reply(self):
        bad = [{"risk": "low", "blocking": [], "summary": "s"},                       # no verdict
               {"verdict": "maybe", "risk": "low", "blocking": [], "summary": "s"},   # not a verdict
               {"verdict": "pass", "risk": "huge", "blocking": [], "summary": "s"},   # not a risk
               {"verdict": "pass", "risk": "low", "blocking": "x", "summary": "s"},   # blocking not a list
               {"verdict": "pass", "risk": "low", "blocking": [1], "summary": "s"},   # blocking not strings
               {"verdict": "pass", "risk": "low", "blocking": ["x"], "summary": "s"}]  # a pass cannot block
        for v in bad:
            with self.assertRaisesRegex(ValueError, "verifier|verdict|risk|blocking"):
                gate.verify(FakeGate(v), "m/x", "s", "d", [])
        with self.assertRaisesRegex(ValueError, "no verifier model"):
            gate.verify(FakeGate(), "", "s", "d", [])
        self.assertEqual([1], gate.verify(FakeGate({"verdict": "pass", "risk": "low", "blocking": [], "summary": "s"}),
                                          "m/x", "s", "d", []) and [1])


class RunGate(Env):
    def setUp(self):
        super().setUp()
        self.f = fixture()
        c = stub_checks()
        c.start()
        self.addCleanup(c.stop)
        self.buf = io.StringIO()

    def gate(self, gw=None, **kw):
        return gate.run_gate(self.f.spec_path, gw=gw, out=lambda s: self.buf.write(s + "\n"), **kw)

    def test_run_gate_pass_commits_the_record_on_the_task_branch(self):
        pid = gate.patch_id(self.f.wt, self.f.base)  # the diff the verifier judged, before the record lands
        g = FakeGate()
        self.assertEqual(0, self.gate(gw=g))
        rec = records.read(self.f.wt, "T-1")
        self.assertEqual((rec["task"], rec["gate"], rec["flags"]), ("T-1", "AUTO", []))
        self.assertEqual(rec["attempts"][0]["verdict"]["patch_id"], pid)
        self.assertEqual((rec["attempts"][0]["verdict"]["verdict"], rec["summary"]), ("pass", PASS["summary"]))
        self.assertEqual(rec["spec_blob"], git.git(["hash-object", str(self.f.spec_path)], self.f.root).strip())
        self.assertEqual(rec["tool_version"], f"aios {__import__('aios').__version__}")
        self.assertEqual(rec["routing"]["verifier"], {"model": DECISION["verifier"],
                                                      "family": DECISION["verifier_family"]})
        self.assertAlmostEqual(rec["usd_total"], 0.025, places=6)
        self.assertEqual(git.git(["status", "--porcelain"], self.f.wt).strip(), "")
        self.assertEqual(git.git(["log", "-1", "--format=%s"], self.f.wt).strip(), "T-1: gate AUTO (pass)")
        msg = git.git(["log", "-1", "--format=%B"], self.f.wt)
        self.assertIn(f"Verified-By: {DECISION['verifier']}", msg)
        self.assertIn(f"Patch-Id: {rec['attempts'][0]['verdict']['patch_id']}", msg)
        model, messages, kw = g.calls[0]
        self.assertEqual((model, kw["schema"]), (DECISION["verifier"], gate.VERDICT_SCHEMA))
        prompt = messages[0]["content"]
        self.assertIn("## Task spec", prompt) and self.assertIn(SPEC, prompt)
        self.assertIn("diff --git a/parser.py", prompt) and self.assertIn("$ python3 -m unittest", prompt)

    def test_run_gate_verifier_fail_returns_4_and_still_records(self):
        self.assertEqual(4, self.gate(gw=FakeGate(FAIL)))
        rec = records.read(self.f.wt, "T-1")
        self.assertEqual(rec["attempts"][0]["verdict"]["verdict"], "fail")
        self.assertIn("the test never fails", self.buf.getvalue())
        self.assertEqual(git.git(["status", "--porcelain"], self.f.wt).strip(), "")

    def test_run_gate_needs_decision_returns_3(self):
        self.assertEqual(3, self.gate(gw=FakeGate(NEEDS)))
        self.assertEqual(records.read(self.f.wt, "T-1")["attempts"][0]["verdict"]["verdict"], "needs_decision")

    def test_run_gate_flags_and_out_of_scope_files_raise_the_tier(self):
        write(self.f.wt, "src/big.py", "\n".join(f"line {i}" for i in range(400)))
        write(self.f.wt, "other.py", "out of scope\n")
        commit_all(self.f.wt)
        self.assertEqual(1, self.gate(gw=FakeGate()))
        rec = records.read(self.f.wt, "T-1")
        self.assertEqual(rec["gate"], "HUMAN")
        self.assertEqual(rec["flags"], ["large-change", "out-of-scope"])

    def test_run_gate_dry_run_reports_the_plan_and_writes_nothing(self):
        head = git.git(["rev-parse", "HEAD"], self.f.wt)
        self.assertEqual(0, self.gate(dry_run=True))
        self.assertIsNone(records.read(self.f.wt, "T-1"))
        self.assertEqual(head, git.git(["rev-parse", "HEAD"], self.f.wt))
        self.assertIn("dry run: no verifier, no record", self.buf.getvalue())
        self.assertIn("gate AUTO", self.buf.getvalue())

    def test_run_gate_needs_a_worktree_and_recorded_attempts(self):
        other = self.f.root / ".aios" / "tasks" / "T-2.md"
        other.write_text(SPEC.replace("T-1", "T-2"))
        with self.assertRaisesRegex(config.ConfigError, "no worktree"):
            gate.run_gate(other, out=lambda s: None)
        shutil.rmtree(self.f.runs)
        with self.assertRaisesRegex(config.ConfigError, "no attempts recorded"):
            self.gate()

    def test_run_gate_refuses_a_task_branch_without_changes(self):
        f3 = fixture(SPEC.replace("T-1", "T-3"), project=PROJECT.replace('name = "demo"', 'name = "demo3"'),
                     change=False, task="T-3")
        with self.assertRaisesRegex(config.ConfigError, "nothing changed"):
            gate.run_gate(f3.spec_path, gw=FakeGate(), out=lambda s: None)

    def test_run_gate_requires_a_cross_family_verifier(self):
        same = dict(DECISION, verifier=DECISION["author"], verifier_family=DECISION["author_family"])
        (self.f.runs / "attempt.json").write_text(json.dumps({"decision": same, "attempt": dict(ATTEMPT)}))
        g = FakeGate()
        with self.assertRaisesRegex(ValueError, "cross-family"):
            self.gate(gw=g)
        self.assertEqual([], g.calls)
        self.assertIsNone(records.read(self.f.wt, "T-1"))

    def test_run_gate_checks_run_before_the_verdict_is_asked_for(self):
        seen = []
        with mock.patch.object(gate, "run_checks", return_value=[("pytest -q", 1, "3 failed")]) as r:
            r.side_effect = lambda *a, **k: seen.append(a) or [("pytest -q", 1, "3 failed")]
            g = FakeGate()
            self.gate(gw=g)
        self.assertEqual((self.f.p, self.f.wt), seen[0][:2])
        self.assertIn("exit 1", g.calls[0][1][0]["content"])


class CliGate(Env):
    def setUp(self):
        super().setUp()
        self.f = fixture()
        c = stub_checks()
        c.start()
        self.addCleanup(c.stop)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_gate_is_a_command_with_a_dry_run_that_needs_no_key(self):
        code, out, err = self.cli("gate", str(self.f.spec_path), "--dry-run")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("dry run: no verifier, no record", out)
        self.assertIsNone(records.read(self.f.wt, "T-1"))

    def test_gate_builds_the_gateway_with_the_project_privacy_and_writes_the_record(self):
        self.f.p.config.mkdir(parents=True, exist_ok=True)
        self.f.p.credentials.write_text("sk-or-v1-test")
        os.chmod(self.f.p.credentials, 0o600)
        g = FakeGate()
        with mock.patch.object(gate.gateway, "Gateway", return_value=g) as gw:
            code, out, err = self.cli("gate", str(self.f.spec_path))
        self.assertEqual((code, err), (0, ""))
        gw.assert_called_once()
        self.assertEqual(gw.call_args.kwargs["privacy"], {"data_collection": "deny"})
        self.assertEqual(g.calls[0][0], DECISION["verifier"])
        self.assertEqual("AUTO", records.read(self.f.wt, "T-1")["gate"])

    def test_gate_reports_a_gate_error_as_exit_2(self):
        self.f.p.config.mkdir(parents=True, exist_ok=True)
        self.f.p.credentials.write_text("sk-or-v1-test")
        os.chmod(self.f.p.credentials, 0o600)
        with mock.patch.object(gate.gateway, "Gateway", return_value=FakeGate({"verdict": "pass", "risk": "low",
                                                                              "blocking": ["x"], "summary": "s"})):
            code, out, err = self.cli("gate", str(self.f.spec_path))
        self.assertEqual((code, err.strip().splitlines()[-1]),
                         (2, f"aios: {DECISION['verifier']}: verdict is pass but blocking is not empty"))

    def test_gate_requires_a_file(self):
        with self.assertRaises(SystemExit):
            self.cli("gate")


if __name__ == "__main__":
    unittest.main()
