"""Unit tests for aios.calibrate: the cases, the fingerprint, run, the result cache, and `aios models calibrate`."""
import contextlib
import datetime as dt
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aios import calibrate, cli, config, gate, gateway
from tests.helpers import cwd

PROJECT = """schema = 1
name = "t"
forge = "local"

[[components]]
name = "app"
path = "./"
profile = "generic"
checks = ["true"]

[privacy]
zdr = true
"""


class FakeGW:
    """A gateway whose chat() answers with the canned verdict named by a marker in the prompt (no network)."""

    def __init__(self, plan: dict[str, str], usd: float = 0.0025):
        self.plan, self.usd, self.prompts = plan, usd, []

    def chat(self, model: str, messages: list[dict], *, schema=None, max_tokens=None, reasoning=None) -> dict:
        """The canned reply for the first plan marker found in the prompt; `raise` and `junk` make the call fail."""
        prompt = messages[0]["content"]
        self.prompts.append(prompt)
        want = self.plan.get(next((m for m in self.plan if m in prompt), ""), "pass")
        if want == "raise":
            raise gateway.GatewayError(500, "provider exploded")
        if want == "junk":
            return {"json": None, "usd": self.usd}   # what the gateway yields when the reply is not JSON
        blocking = [] if want == "pass" else [f"defect {want} " + "x" * 120]
        reply = {"verdict": want, "risk": "low", "blocking": blocking, "summary": "it does the thing"}
        return {"json": reply, "usd": self.usd}


def make_case(directory: Path, name: str, expected: str, marker: str) -> None:
    """A case folder under `directory` whose spec text carries `marker`, which the fake gateway answers to."""
    d = directory / name
    d.mkdir(parents=True)
    (d / "spec.md").write_text(f"# {name}\nMARK {marker}\n", encoding="utf-8")
    (d / "change.diff").write_text(f"--- a/f\n+++ b/f\n@@ -1 +1 @@\n-{marker}\n+{marker}\n", encoding="utf-8")
    (d / "case.toml").write_text(f'expected = "{expected}"\nnote = "n"\n\n[[checks]]\ncommand = "true"\n'
                                 'exit = 0\ntail = "ok"\n', encoding="utf-8")


def temp_paths() -> config.Paths:
    """A fresh machine: every XDG directory under its own temp root (never the real ~/.config)."""
    return config.paths({f"XDG_{k}_HOME": str(Path(tempfile.mkdtemp()) / k)
                         for k in ("CONFIG", "CACHE", "STATE", "DATA")})


class Cases(unittest.TestCase):
    def test_the_shipped_cases_load_sorted_with_one_expected_fail(self):
        cs = calibrate.load_cases()
        self.assertEqual([c.id for c in cs], ["approve-land", "forge-cleanup", "gate-attempt-1"])
        self.assertEqual([c.expected for c in cs], ["pass", "pass", "fail"])
        for c in cs:
            self.assertIn("Acceptance criteria", c.spec_text)
            self.assertIn("diff --git", c.diff_text)
            self.assertTrue(all(isinstance(k, tuple) and len(k) == 3 and isinstance(k[1], int) for k in c.checks))
            self.assertEqual([k[0] for k in c.checks], ["python3 -m unittest discover -s tests -t .",
                                                        "python3 -m compileall -q aios"])

    def test_the_fingerprint_covers_the_prompt_and_every_case(self):
        cs = calibrate.load_cases()
        self.assertEqual(calibrate.fingerprint(cs), calibrate.fingerprint(calibrate.load_cases()))
        self.assertNotEqual(calibrate.fingerprint(cs), calibrate.fingerprint(cs[:2]))
        other = [calibrate.Case(c.id, c.expected, c.spec_text, c.diff_text + " ", c.checks) for c in cs]
        self.assertNotEqual(calibrate.fingerprint(cs), calibrate.fingerprint(other))

    def test_a_case_with_a_missing_file_fails_loud(self):
        d = Path(tempfile.mkdtemp())
        make_case(d, "good", "pass", "MARK-1")
        (d / "good" / "change.diff").unlink()
        with self.assertRaisesRegex(ValueError, "good"):
            calibrate.load_cases(d)

    def test_a_case_with_a_bad_expected_fails_loud(self):
        d = Path(tempfile.mkdtemp())
        make_case(d, "bad", "maybe", "MARK-2")
        with self.assertRaisesRegex(ValueError, "bad.*'expected'"):
            calibrate.load_cases(d)
        (d / "bad" / "case.toml").write_text("expected = \"fail\"\n", encoding="utf-8")  # no [[checks]] at all
        self.assertEqual([c.checks for c in calibrate.load_cases(d)], [[]])

    def test_a_case_without_an_expected_or_a_check_fails_loud(self):
        d = Path(tempfile.mkdtemp())
        make_case(d, "bare", "pass", "MARK-4")
        (d / "bare" / "case.toml").write_text('note = "no expected at all"\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "bare.*'expected'"):
            calibrate.load_cases(d)

    def test_a_case_with_a_broken_check_or_toml_fails_loud(self):
        d = Path(tempfile.mkdtemp())
        make_case(d, "noexit", "pass", "MARK-3")
        (d / "noexit" / "case.toml").write_text('expected = "pass"\n[[checks]]\ncommand = "true"\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "noexit"):
            calibrate.load_cases(d)
        (d / "noexit" / "case.toml").write_text("expected =\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "noexit"):
            calibrate.load_cases(d)

    def test_a_missing_case_directory_fails_loud(self):
        with self.assertRaises(OSError):
            calibrate.load_cases(Path(tempfile.mkdtemp()) / "nothing")


class Run(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        make_case(self.dir, "a-ok", "pass", "MARK-OK")
        make_case(self.dir, "b-bug", "fail", "MARK-BUG")
        self.cases = calibrate.load_cases(self.dir)

    def judge(self, plan, **kw):
        """Run the fake gateway over both cases."""
        return calibrate.run(FakeGW(plan), "vendor/model", self.cases, **kw)

    def test_the_production_verifier_call_judges_each_case(self):
        gw = FakeGW({"MARK-OK": "pass", "MARK-BUG": "fail"})
        js = calibrate.run(gw, "vendor/model", self.cases)
        self.assertEqual([(j.case, j.expected, j.got, j.right) for j in js],
                         [("a-ok", "pass", "pass", True), ("b-bug", "fail", "fail", True)])
        self.assertEqual([(j.usd, j.secs) for j in js], [(0.0025, 0), (0.0025, 0)])
        self.assertEqual(js[1].note, "defect fail " + "x" * 120)  # the first blocking item of its fail
        self.assertIn("You are the verifier", gw.prompts[0])          # the prompt production uses
        self.assertIn("MARK-OK", gw.prompts[0])                       # this case's spec and diff
        self.assertIn("$ true", gw.prompts[0])                        # its checks block

    def test_a_wrong_verdict_is_recorded_with_its_first_blocking_item(self):
        js = self.judge({"MARK-OK": "fail", "MARK-BUG": "pass"})
        self.assertEqual([(j.case, j.expected, j.got, j.right) for j in js],
                         [("a-ok", "pass", "fail", False), ("b-bug", "fail", "pass", False)])
        self.assertEqual(js[0].note, "defect fail " + "x" * 120)
        self.assertEqual(js[1].note, "")  # a pass verdict has no blocking item

    def test_repeat_judges_every_case_that_many_times(self):
        gw = FakeGW({"MARK-OK": "pass", "MARK-BUG": "fail"})
        js = calibrate.run(gw, "vendor/model", self.cases, repeat=2)
        self.assertEqual([j.case for j in js], ["a-ok", "a-ok", "b-bug", "b-bug"])
        self.assertEqual(len(gw.prompts), 4)
        self.assertEqual(sum(j.usd for j in js), 0.01)

    def test_an_error_is_wrong_and_the_run_continues(self):
        js = self.judge({"MARK-OK": "raise", "MARK-BUG": "fail"})
        self.assertEqual([(j.case, j.got, j.right, j.usd) for j in js],
                         [("a-ok", "error", False, 0.0), ("b-bug", "fail", True, 0.0025)])
        self.assertIn("provider exploded", js[0].note)

    def test_a_malformed_reply_is_an_error_too(self):
        js = self.judge({"MARK-OK": "junk", "MARK-BUG": "fail"})
        self.assertEqual(js[0].got, "error")
        self.assertIn("no JSON", js[0].note)
        self.assertTrue(js[1].right)

    def test_the_clock_times_each_call(self):
        ticks = iter(range(100, 200))
        js = self.judge({"MARK-OK": "pass", "MARK-BUG": "fail"}, clock=lambda: next(ticks))
        self.assertEqual([j.secs for j in js], [1, 1])

    def test_repeat_below_one_fails_loud(self):
        with self.assertRaisesRegex(ValueError, "repeat"):
            self.judge({}, repeat=0)


class Cache(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        make_case(self.dir, "a-ok", "pass", "MARK-OK")
        make_case(self.dir, "b-bug", "fail", "MARK-BUG")
        self.cases = calibrate.load_cases(self.dir)
        self.p = temp_paths()

    def ok(self, plan=None):
        """Judgments from a run where both cases are judged right (or as `plan` says)."""
        return calibrate.run(FakeGW(plan or {"MARK-OK": "pass", "MARK-BUG": "fail"}), "vendor/model", self.cases)

    def entry(self, model="m"):
        return json.loads((self.p.cache / "calibration.json").read_text(encoding="utf-8"))[model]

    def test_a_clean_pass_is_saved_and_passes(self):
        calibrate.save(self.p, "m", self.ok(), self.cases, today=dt.date(2026, 10, 22))
        self.assertEqual(self.entry(), {"date": "2026-10-22", "fingerprint": calibrate.fingerprint(self.cases),
                                        "right": 2, "total": 2, "usd": 0.005, "secs": 0})
        self.assertTrue(calibrate.passed(self.p, "m", self.cases, today=dt.date(2026, 10, 22)))

    def test_one_wrong_judgment_is_not_a_pass(self):
        calibrate.save(self.p, "m", self.ok({"MARK-OK": "pass", "MARK-BUG": "pass"}), self.cases)
        self.assertEqual((self.entry()["right"], self.entry()["total"]), (1, 2))
        self.assertFalse(calibrate.passed(self.p, "m", self.cases))

    def test_an_old_entry_is_refused(self):
        calibrate.save(self.p, "m", self.ok(), self.cases, today=dt.date(2026, 1, 1))
        self.assertTrue(calibrate.passed(self.p, "m", self.cases, today=dt.date(2026, 1, 31)))  # 30 days: in
        self.assertFalse(calibrate.passed(self.p, "m", self.cases, today=dt.date(2026, 3, 1)))
        self.assertTrue(calibrate.passed(self.p, "m", self.cases, today=dt.date(2026, 3, 1), max_age_days=60))

    def test_a_changed_fingerprint_invalidates_the_result(self):
        calibrate.save(self.p, "m", self.ok(), self.cases)
        self.assertFalse(calibrate.passed(self.p, "m", self.cases[:1]))       # fewer cases
        changed = [calibrate.Case(c.id, c.expected, c.spec_text + "\nmore\n", c.diff_text, c.checks)
                   for c in self.cases]
        self.assertFalse(calibrate.passed(self.p, "m", changed))              # a case changed
        self.assertTrue(calibrate.passed(self.p, "m", calibrate.load_cases(self.dir)))

    def test_a_changed_verifier_prompt_invalidates_the_result(self):
        calibrate.save(self.p, "m", self.ok(), self.cases)
        other = Path(tempfile.mkdtemp()) / "verifier.md"
        other.write_text("You are the verifier, but a different prompt.\n", encoding="utf-8")
        with mock.patch.object(gate, "VERIFIER_PROMPT", other):
            self.assertFalse(calibrate.passed(self.p, "m", self.cases))
        self.assertTrue(calibrate.passed(self.p, "m", self.cases))

    def test_another_models_entry_is_kept(self):
        calibrate.save(self.p, "good", self.ok(), self.cases, today=dt.date(2026, 10, 22))
        calibrate.save(self.p, "bad", self.ok({"MARK-OK": "fail", "MARK-BUG": "pass"}), self.cases,
                       today=dt.date(2026, 10, 22))
        self.assertEqual(sorted(json.loads((self.p.cache / "calibration.json").read_text(encoding="utf-8"))),
                         ["bad", "good"])
        self.assertEqual(self.entry("good")["right"], 2)
        self.assertEqual(self.entry("bad")["right"], 0)
        self.assertTrue(calibrate.passed(self.p, "good", self.cases, today=dt.date(2026, 10, 22)))
        self.assertFalse(calibrate.passed(self.p, "bad", self.cases, today=dt.date(2026, 10, 22)))

    def test_no_entry_and_a_malformed_cache_fail_closed(self):
        self.assertFalse(calibrate.passed(self.p, "m", self.cases))
        self.assertFalse(calibrate.passed(self.p, "m", self.cases, today=dt.date(2026, 1, 1)))
        f = self.p.cache / "calibration.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{ not json", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "calibration.json"):
            calibrate.passed(self.p, "m", self.cases)
        with self.assertRaisesRegex(ValueError, "calibration.json"):
            calibrate.save(self.p, "m", self.ok(), self.cases)


class CalibrateCommand(unittest.TestCase):
    def setUp(self):
        state = Path(tempfile.mkdtemp())
        env = mock.patch.dict(os.environ, {f"XDG_{k}_HOME": str(state / k)
                                           for k in ("CONFIG", "CACHE", "STATE", "DATA")})
        env.start()
        self.addCleanup(env.stop)
        self.p = config.paths()
        self.p.config.mkdir(parents=True, exist_ok=True)
        self.p.credentials.write_text("sk-or-v1-test")
        os.chmod(self.p.credentials, 0o600)

    def run_cli(self, *argv, gw=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            if gw is not None:
                stack.enter_context(mock.patch.object(cli, "_calibration_gateway", return_value=gw))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_all_right_prints_one_line_per_judgment_and_exits_zero(self):
        gw = FakeGW({"approve-and-land": "pass", "forge-cleanup-fix": "pass", "gate-command": "fail"})  # each case's own spec id marks its reply
        code, out, err = self.run_cli("models", "calibrate", "vendor/model", gw=gw)
        self.assertEqual(err, "")
        lines = out.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0],
                         "vendor/model | approve-land | want pass got pass | RIGHT | $0.0025 | 0s")
        self.assertTrue(lines[2].startswith(
            "vendor/model | gate-attempt-1 | want fail got fail | RIGHT | $0.0025 | 0s | defect fail "), lines[2])
        self.assertEqual(lines[3], "vendor/model: 3/3 right, $0.0075, 0s -> may review")
        self.assertEqual(len(gw.prompts), 3)
        self.assertIn("You are the verifier", gw.prompts[0])
        entry = json.loads((self.p.cache / "calibration.json").read_text(encoding="utf-8"))["vendor/model"]
        self.assertEqual((entry["right"], entry["total"], entry["secs"]), (3, 3, 0))
        self.assertEqual(entry["fingerprint"], calibrate.fingerprint(calibrate.load_cases()))

    def test_one_wrong_judgment_exits_one(self):
        gw = FakeGW({"approve-and-land": "pass", "forge-cleanup-fix": "pass", "gate-command": "pass"})  # the buggy change judged pass
        code, out, _ = self.run_cli("models", "calibrate", "vendor/model", gw=gw)
        self.assertEqual(code, 1)
        self.assertIn("vendor/model | gate-attempt-1 | want fail got pass | WRONG | $0.0025 | 0s", out)
        self.assertIn("vendor/model: 2/3 right, $0.0075, 0s -> may not review", out)

    def test_the_note_is_at_most_100_chars(self):
        code, out, _ = self.run_cli("models", "calibrate", "vendor/model", gw=FakeGW({"approve-and-land": "fail"}))
        self.assertEqual(code, 1)
        note = [l for l in out.splitlines() if "approve-land" in l][0].split(" | ")[-1]
        self.assertEqual(note, "defect fail " + "x" * 88)  # the blocking item, cut to 100

    def test_repeat_and_several_models(self):
        gw = FakeGW({"approve-and-land": "pass", "forge-cleanup-fix": "pass", "gate-command": "fail"})
        code, out, _ = self.run_cli("models", "calibrate", "a/m", "b/m", "--repeat", "2", gw=gw)
        self.assertEqual(code, 0)
        self.assertEqual(len([l for l in out.splitlines() if " | " in l]), 12)  # 3 cases x 2 repeats x 2 models
        self.assertEqual([l for l in out.splitlines() if l.startswith(("a/m", "b/m")) and l.endswith("review")],
                         ["a/m: 6/6 right, $0.0150, 0s -> may review", "b/m: 6/6 right, $0.0150, 0s -> may review"])
        self.assertEqual(sorted(json.loads((self.p.cache / "calibration.json").read_text(encoding="utf-8"))),
                         ["a/m", "b/m"])

    def test_no_model_named_is_an_error(self):
        code, out, err = self.run_cli("models", "calibrate", gw=FakeGW({}))
        self.assertEqual(code, 2)
        self.assertIn("usage: aios models calibrate", err)

    def test_a_missing_key_is_an_error(self):
        os.remove(self.p.credentials)
        code, out, err = self.run_cli("models", "calibrate", "vendor/model")
        self.assertEqual(code, 2)
        self.assertIn("credentials", err)


class GatewayForCalibration(unittest.TestCase):
    def setUp(self):
        self.p = temp_paths()
        self.p.config.mkdir(parents=True, exist_ok=True)
        self.p.credentials.write_text("sk-or-v1-test")
        os.chmod(self.p.credentials, 0o600)

    def test_privacy_comes_from_the_project_when_inside_one(self):
        root = Path(tempfile.mkdtemp())
        (root / ".aios").mkdir()
        (root / ".aios" / "project.toml").write_text(PROJECT, encoding="utf-8")
        for where, want in ((root, {"data_collection": "deny", "zdr": True}), (Path(tempfile.mkdtemp()), None)):
            with cwd(where), mock.patch.object(gateway, "Gateway", return_value="gw") as g:
                self.assertEqual(cli._calibration_gateway(self.p), "gw")
                self.assertEqual(g.call_args.args, ("sk-or-v1-test",))
                self.assertEqual(g.call_args.kwargs["privacy"], want)


if __name__ == "__main__":
    unittest.main()
