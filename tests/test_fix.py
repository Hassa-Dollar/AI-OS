"""Tests for `aios fix`: the fix-round ladder, the appended review, and the CLI command (ADR-0031 rule 5)."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aios import catalog, cli, config, gate, git, harness, records, router, run
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

PASS = {"verdict": "pass", "risk": "low", "blocking": [], "summary": "all clear"}
FAIL = {"verdict": "fail", "risk": "medium", "blocking": ["unhandled case"], "summary": "the parser is wrong"}
NEED = {"verdict": "needs_decision", "risk": "low", "blocking": [], "summary": "which schema, v1 or v2?"}
PASS_CHECKS = [("python3 -m unittest", 0, "Ran 1 test")]


def decision():
    """The routing decision a dispatch recorded: a junior implementer and a cross-family reviewer."""
    return router.Decision("dispatch", "AUTO", "junior", "bugfix", "acme/econ", "acme",
                           "deepseek/deepseek-v4-pro-0813", "deepseek", "clef-flash", 0.9, ["cheapest"], {})


def model(mid, *, score, pin, pout):
    """One scored catalog entry in the shape `catalog.sync` caches (a fake live catalog, not a roster)."""
    return {"id": mid, "usable": True, "context_length": 200_000,
            "supported_parameters": ["tools", "structured_outputs"],
            "pricing": {"prompt": pin, "completion": pout},
            "benchmarks": {"artificial_analysis": {"intelligence_index": score}}}


# The reviewer's own family is the cheapest implementer of all, so every ladder step has to skip it.
# Prices rise with the list, so `catalog.candidates` ranks them: deepseek-cheap, acme/econ and bolt/standard
# are junior (score >= 40), echo/mid and the two seniors are mid (>= 45).
LIVE = [model("deepseek/deepseek-cheap", score=42.0, pin="0.0000001", pout="0.0000002"),
        model("acme/econ", score=41.0, pin="0.0000002", pout="0.0000004"),
        model("bolt/standard", score=44.0, pin="0.0000003", pout="0.0000006"),
        model("echo/mid", score=46.0, pin="0.0000004", pout="0.0000008"),
        model("cortex/front", score=60.0, pin="0.0000005", pout="0.000001"),
        model("dune/senior", score=55.0, pin="0.0000006", pout="0.0000012")]


class FakeGw:
    """A gateway whose key has no usage and no limit."""

    def __init__(self, daily=0.0):
        self.daily = daily

    def key_info(self):
        return {"usage_daily": self.daily, "usage_monthly": 0.0, "limit_remaining": None}


class FakeGate:
    """A gateway whose chat() returns canned verdicts."""

    def __init__(self, verdicts):
        self.verdicts = list(verdicts)

    def chat(self, model, messages, schema=None, max_tokens=None):
        return {"json": dict(self.verdicts.pop(0) if self.verdicts else PASS), "usd": 0.0123}


# A stand-in for mini-swe-agent that changes the worktree every run, and takes its exit status from a plan
# file next to itself: one line per attempt, consumed in order, "Submitted" once the plan is empty.
FAKE_MINI = """#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
cfg = json.load(open(argv[argv.index("-c", argv.index("-c") + 1) + 1]))
out = argv[argv.index("-o") + 1]
ws = cfg["environment"]["cwd"]
json.dump({"model": cfg["model"]["model_name"], "template": cfg["agent"]["instance_template"],
           "cost_limit": cfg["agent"]["cost_limit"]},
          open(os.path.join(os.path.dirname(out), "seen.json"), "w"))
plan = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plan")
lines = [ln.strip() for ln in open(plan).read().splitlines() if ln.strip()] if os.path.exists(plan) else []
status, rest = (lines[0], lines[1:]) if lines else ("Submitted", [])
open(plan, "w").write("\\n".join(rest))
open(os.path.join(ws, "fixed.txt"), "a").write("round\\n")
json.dump({"info": {"exit_status": status, "submission": "", "model_stats": {"instance_cost": 0.0123, "api_calls": 7}},
           "messages": [{"role": "user", "content": "task"}, {"role": "assistant", "content": "I fixed it."}]},
          open(out, "w"))
"""


class Env:
    """A temp project, a spec, a dispatched task and its record: everything `aios fix` reads."""

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
        mini = harness.home(self.p) / "bin" / "mini"
        mini.write_text(FAKE_MINI)
        mini.chmod(0o755)
        self.p.cache.mkdir(parents=True, exist_ok=True)
        catalog.cache_file(self.p).write_text(json.dumps(LIVE))
        self.out = io.StringIO()
        self.wt = None
        self.rounds = 0

    def cleanup(self):
        self._env.stop()

    def dispatch(self):
        with mock.patch.object(run, "route", return_value=decision()):
            rc = run.dispatch(self.spec, gw=FakeGw(), out=lambda s: self.out.write(s + "\n"))
        if rc != 0:
            raise AssertionError(f"dispatch failed ({rc}):\n{self.out.getvalue()}")
        self.wt = self.p.data / "worktrees" / run.project_id(config.load_project(self.root)) / "T-1"
        return self.wt

    def gate(self, verdicts):
        with mock.patch.object(gate, "run_checks", return_value=list(PASS_CHECKS)):
            return gate.run_gate(self.spec, gw=FakeGate(verdicts), out=lambda s: self.out.write(s + "\n"))

    def fix(self, spec=None, **kw):
        """One `aios fix` call; `rounds` counts the attempts it ran, even when it raises."""
        before = len(self.runs())
        try:
            return run.fix(spec or self.spec, gw=FakeGw(), out=lambda s: self.out.write(s + "\n"), **kw)
        finally:
            self.rounds = len(self.runs()) - before

    def plan(self, *statuses):
        """The fake harness's exit statuses for the next attempts, consumed one per attempt."""
        f = harness.home(self.p) / "bin" / "plan"
        f.write_text("".join(s + "\n" for s in statuses))
        return f

    def runs(self):
        """The task's attempts, oldest first, as the ladder and the record read them."""
        return records.load_runs(self.runs_dir)

    def seen(self, n=-1):
        """The model, the prompt and the cost limit of the nth attempt (the last by default)."""
        dirs = sorted(d for d in self.runs_dir.iterdir() if d.is_dir())
        return json.loads((dirs[n] / "seen.json").read_text())

    @property
    def runs_dir(self):
        return self.p.state / run.project_id(config.load_project(self.root)) / "runs" / "T-1"

    def head(self):
        return git.git(["log", "-1", "--format=%B"], self.wt).strip()

    def last_line(self):
        return self.out.getvalue().splitlines()[-1]


class Fix(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.addCleanup(self.env.cleanup)

    def test_round_1_reruns_the_same_model_with_the_review_appended(self):
        self.env.dispatch()
        self.env.gate([FAIL, FAIL])
        self.assertEqual(self.env.fix(), 0)
        seen = self.env.seen()
        self.assertEqual(seen["model"], "acme/econ")
        self.assertIn("## Review: fail (medium)", seen["template"])
        self.assertIn("- unhandled case", seen["template"])
        self.assertIn("the parser is wrong", seen["template"])
        self.assertIn("Be careful.", seen["template"])  # the worker prompt is still there, review after it
        self.assertIn("T-1: fix round 1 (review: fail)", self.env.head())
        self.assertIn("Implemented-By: acme/econ via mini-swe-agent 2.4.6", self.env.head())
        self.assertIn("Routed: gate AUTO, level junior, router clef-flash", self.env.head())
        self.assertIn("T-1: fix round 1 | acme/econ | review: fail", self.env.out.getvalue())
        self.assertIn("  attempt: submitted | 7 steps | $0.0123 | ", self.env.last_line())

    def test_round_2_takes_the_next_cheapest_unused_model_at_the_level(self):
        self.env.dispatch()
        self.env.gate([FAIL, FAIL])
        self.env.fix()
        self.assertEqual(self.env.fix(), 0)
        self.assertEqual(self.env.seen()["model"], "bolt/standard")
        self.assertEqual(self.env.rounds, 1)
        self.assertFalse(any(r["attempt"]["model"].startswith("deepseek/") for r in self.env.runs()))
        self.assertIn("T-1: fix round 2 (review: fail)", self.env.head())

    def test_round_3_moves_one_level_up(self):
        self.env.dispatch()
        self.env.gate([FAIL, FAIL])
        self.env.fix()
        self.env.fix()
        self.assertEqual(self.env.fix(), 0)
        self.assertEqual(self.env.seen()["model"], "echo/mid")  # bolt/standard is junior, not mid
        self.assertIn("T-1: fix round 3 (review: fail)", self.env.head())

    def test_four_attempts_are_refused(self):
        self.env.dispatch()
        self.env.gate([FAIL, FAIL])
        self.env.fix()
        self.env.fix()
        self.env.fix()
        before = git.git(["rev-parse", "HEAD"], self.env.wt).strip()
        with self.assertRaisesRegex(config.ConfigError, "T-1: 4 attempts used; the operator and the Lead"):
            self.env.fix()
        self.assertEqual(self.env.rounds, 0)
        self.assertEqual(git.git(["rev-parse", "HEAD"], self.env.wt).strip(), before)

    def test_infra_is_retried_once_and_never_counts(self):
        self.env.dispatch()
        self.env.gate([FAIL, FAIL])
        self.env.plan("RateLimit")
        self.assertEqual(self.env.fix(), 0)
        self.assertEqual([(r["attempt"]["model"], r["attempt"]["exit"]) for r in self.env.runs()],
                         [("acme/econ", "submitted"), ("acme/econ", "infra"), ("acme/econ", "submitted")])
        self.assertIn("T-1: fix round 1 (review: fail)", self.env.head())
        self.env.fix()
        self.assertEqual(self.env.seen()["model"], "bolt/standard")  # round 2, not a third try of the same model

    def test_a_passed_review_has_nothing_to_fix(self):
        self.env.dispatch()
        self.env.gate([PASS])
        with self.assertRaisesRegex(config.ConfigError, "T-1: the review passed; nothing to fix"):
            self.env.fix()
        self.assertEqual(self.env.rounds, 0)

    def test_a_needs_decision_verdict_goes_to_the_lead(self):
        self.env.dispatch()
        self.env.gate([NEED])
        with self.assertRaisesRegex(ValueError, "T-1: the reviewer needs a decision; that goes to the Lead"):
            self.env.fix()
        self.assertEqual(self.env.rounds, 0)

    def test_a_lead_review_reaches_the_prompt(self):
        self.env.dispatch()
        self.env.gate([NEED])
        review = self.env.root / "lead-review.md"
        review.write_text("Keep schema v1; the reviewer's question is answered there.\n")
        self.assertEqual(self.env.fix(review=review), 0)
        seen = self.env.seen()
        self.assertIn("## Lead review\n\nKeep schema v1", seen["template"])
        self.assertIn("T-1: fix round 1 (Lead review)", self.env.head())
        self.assertIn("T-1: fix round 1 | acme/econ | Lead review", self.env.out.getvalue())

    def test_a_model_of_the_reviewer_s_family_is_refused(self):
        self.env.dispatch()
        self.env.gate([FAIL, FAIL])
        with self.assertRaisesRegex(ValueError, "deepseek/deepseek-cheap is not an implementer candidate"):
            self.env.fix(model="deepseek/deepseek-cheap")
        self.assertEqual(self.env.rounds, 0)

    def test_a_model_override_is_honoured_at_any_level(self):
        self.env.dispatch()
        self.env.gate([FAIL, FAIL])
        self.assertEqual(self.env.fix(model="cortex/front"), 0)
        self.assertEqual(self.env.seen()["model"], "cortex/front")
        self.assertIn("Implemented-By: cortex/front via mini-swe-agent 2.4.6", self.env.head())

    def test_the_day_s_cap_stops_a_fix_before_any_attempt(self):
        self.env.dispatch()
        self.env.gate([FAIL, FAIL])
        with mock.patch.object(FakeGw, "key_info", return_value={"usage_daily": 99.0, "usage_monthly": 0.0,
                                                                 "limit_remaining": None}):
            with self.assertRaisesRegex(run.BudgetError, "the day's budget is spent"):
                self.env.fix()
        self.assertEqual(self.env.rounds, 0)

    def test_requires_a_dispatched_task(self):
        stray = Path(tempfile.mkdtemp()) / "t.md"
        stray.write_text(SPEC)
        with self.assertRaisesRegex(config.ConfigError, "not inside a project"):
            run.fix(stray, out=lambda s: None)

    def test_requires_a_worktree(self):
        self.env.dispatch()
        git.git(["worktree", "remove", "--force", str(self.env.wt)], self.env.root)
        with self.assertRaisesRegex(config.ConfigError, "dispatch it first"):
            self.env.fix()

    def test_no_attempts_recorded_says_dispatch_it_first(self):
        self.env.dispatch()
        for d in self.env.runs_dir.iterdir():
            shutil.rmtree(d)
        with self.assertRaisesRegex(config.ConfigError, "T-1: no attempts recorded; dispatch it first"):
            self.env.fix()
        self.assertEqual(self.env.rounds, 0)

    def test_no_record_says_run_the_gate_first_unless_the_lead_reviews(self):
        self.env.dispatch()
        with self.assertRaisesRegex(config.ConfigError, "T-1: no record committed yet; run 'aios gate' first"):
            self.env.fix()
        self.assertEqual(self.env.rounds, 0)
        review = self.env.root / "lead-review.md"
        review.write_text("## The Lead\n\nShip the schema change as designed.\n")
        self.assertEqual(self.env.fix(review=review), 0)
        self.assertIn("Ship the schema change as designed", self.env.seen()["template"])
        self.assertIn("T-1: fix round 1 (Lead review)", self.env.head())

    def test_cli_parses_review_and_model(self):
        self.env.dispatch()
        review = self.env.root / "lead-review.md"
        review.write_text("Ship it.\n")
        with mock.patch.object(run, "fix", return_value=0) as fix:
            err, out = io.StringIO(), io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["fix", str(self.env.spec), "--review", str(review),
                                           "--model", "cortex/front"]), 0)
        self.assertEqual(fix.call_args.args, (self.env.spec,))
        self.assertEqual(fix.call_args.kwargs.get("review"), review)
        self.assertEqual(fix.call_args.kwargs.get("model"), "cortex/front")

    def test_cli_sends_review_and_model_to_fix(self):
        review = Path(tempfile.mkdtemp()) / "lead.md"
        review.write_text("Ship it as designed.\n")
        with mock.patch.object(run, "fix", return_value=0) as fix:
            err, out = io.StringIO(), io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["fix", "spec.md", "--review", str(review),
                                           "--model", "cortex/front"]), 0)
        self.assertEqual(fix.call_args.args, (Path("spec.md"),))
        self.assertEqual(fix.call_args.kwargs.get("review"), review)
        self.assertEqual(fix.call_args.kwargs.get("model"), "cortex/front")

    def test_cli_reports_a_refused_override_as_exit_2(self):
        self.env.dispatch()
        self.env.gate([FAIL, FAIL])
        err, out = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["fix", str(self.env.spec), "--model", "deepseek/deepseek-cheap"]), 2)
        self.assertIn("not an implementer candidate", err.getvalue())


if __name__ == "__main__":
    unittest.main()
