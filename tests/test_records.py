import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aios.records import RECORD_SCHEMA, build, load_runs, read, write


class TestRecords(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.runs_dir = self.temp_dir / "runs"
        self.runs_dir.mkdir()
        self.worktree = self.temp_dir / "repo"
        self.worktree.mkdir()
        self.decision = {"action": "dispatch", "gate": "LEAD", "tier": "T2", "task_class": "feature_backend",
                         "author": "deepseek/deepseek-v4-pro", "author_family": "deepseek",
                         "verifier": "moonshotai/kimi-k2.7-code", "verifier_family": "moonshotai",
                         "router": "clef", "confidence": 0.9, "reasons": ["r1"], "answers": {"q": "a"}}
        self.roles = {"implementer": {"model": "xiaomi/mimo-v2.6-pro", "family": "xiaomi", "level": "mid",
                                      "score": 46.3, "usd_per_m": [0.435, 0.87], "est_usd": 0.14,
                                      "why": "cheapest of 23 candidates at mid"},
                      "reviewer": {"model": "anthropic/claude-sonnet-5.5", "family": "anthropic", "level": "senior",
                                   "score": 56, "usd_per_m": [2.0, 10.0], "est_usd": 0.08,
                                   "why": "cheapest calibrated reviewer at senior"}}
        self.new_decision = {**self.decision, "level": "mid", "roles": self.roles}
        del self.new_decision["tier"]
        self.attempt = {"exit": "submitted", "model": "deepseek/deepseek-v4-pro", "steps": 10, "usd": 0.05,
                        "secs": 30, "summary": "ok", "harness": "mini-swe-agent 1.0"}

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def add_run(self, name, decision, attempt):
        (self.runs_dir / name).mkdir()
        with open(self.runs_dir / name / "attempt.json", "w", encoding="utf-8") as f:
            json.dump({"decision": decision, "attempt": attempt}, f)

    # --- load_runs ---

    def test_load_runs_missing_dir(self):
        self.assertEqual(load_runs(self.temp_dir / "missing"), [])

    def test_load_runs_skips_subdirs_without_attempt(self):
        self.add_run("20261022T001000", self.decision, self.attempt)
        (self.runs_dir / "20261022T002000").mkdir()  # empty subdirectory: skipped
        self.add_run("20261022T003000", {"action": "refuse"}, {"exit": "escalated", "usd": 0.1})
        runs = load_runs(self.runs_dir)
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0]["decision"]["router"], "clef")
        self.assertEqual(runs[1]["attempt"]["exit"], "escalated")

    def test_load_runs_order_is_oldest_first(self):
        self.add_run("20261022T001500", self.decision, {"usd": 0.1})
        self.add_run("20261022T011500", self.decision, {"usd": 0.2})
        runs = load_runs(self.runs_dir)
        self.assertEqual([r["attempt"]["usd"] for r in runs], [0.1, 0.2])

    def test_load_runs_empty_dir(self):
        self.assertEqual(load_runs(self.runs_dir), [])

    def test_load_runs_corrupt_propagates(self):
        self.add_run("20261022T001500", self.decision, self.attempt)
        (self.runs_dir / "20261022T020000").mkdir()
        with open(self.runs_dir / "20261022T020000" / "attempt.json", "w", encoding="utf-8") as f:
            f.write("{not valid json")
        with self.assertRaises(json.JSONDecodeError):
            load_runs(self.runs_dir)

    # --- build ---

    def test_build_empty_runs(self):
        record = build("SH-1", [], spec_blob="b", tool_version="aios 2.0.0-dev")
        self.assertEqual(record["record_schema"], RECORD_SCHEMA)
        self.assertIsNone(record["routing"])
        self.assertEqual(record["attempts"], [])
        self.assertEqual(record["usd_total"], 0.0)
        self.assertEqual(record["gate"], "AUTO")

    def test_build_routing_from_first_run(self):
        self.add_run("20261022T001000", self.decision, self.attempt)
        self.add_run("20261022T002000", {**self.decision, "router": "heuristic", "tier": "T1"}, self.attempt)
        record = build("SH-1", load_runs(self.runs_dir), spec_blob="b", tool_version="v", roster_version="roster")
        # Routing is decided once: the later run never changes it.
        self.assertEqual(record["routing"], {
            "router": "clef", "answers": {"q": "a"}, "level": "T2", "roles": {},
            "author": {"model": "deepseek/deepseek-v4-pro", "family": "deepseek"},
            "verifier": {"model": "moonshotai/kimi-k2.7-code", "family": "moonshotai"},
            "gate": "LEAD", "reasons": ["r1"], "policy_version": 1, "roster_version": "roster"})

    def test_build_attempts_and_verdict_on_last_only(self):
        self.add_run("20261022T001000", self.decision, self.attempt)
        self.add_run("20261022T002000", self.decision, self.attempt)
        verdict = {"verdict": "pass", "risk": "low", "usd": 0.001}
        record = build("SH-1", load_runs(self.runs_dir), spec_blob="b", tool_version="v", verdict=verdict,
                       flags=("multi-component",), gate="OPERATOR", approval={"by": "lead"}, summary="s",
                       lessons=("l1",))
        self.assertEqual([a["n"] for a in record["attempts"]], [1, 2])
        self.assertNotIn("verdict", record["attempts"][0])
        self.assertEqual(record["attempts"][1]["verdict"], verdict)
        self.assertEqual(record["flags"], ["multi-component"])
        self.assertEqual(record["gate"], "OPERATOR")
        self.assertEqual(record["approval"], {"by": "lead"})
        self.assertEqual(record["summary"], "s")
        self.assertEqual(record["lessons"], ["l1"])

    def test_build_usd_total_includes_verdict(self):
        self.add_run("20261022T001000", self.decision, self.attempt)
        record = build("SH-1", load_runs(self.runs_dir), spec_blob="b", tool_version="v",
                       verdict={"verdict": "pass", "usd": 0.0004})
        self.assertEqual(record["usd_total"], round(0.05 + 0.0004, 6))

    def test_build_usd_total_without_verdict(self):
        self.add_run("20261022T001000", self.decision, self.attempt)
        self.add_run("20261022T002000", self.decision, {**self.attempt, "usd": 0.025})
        record = build("SH-1", load_runs(self.runs_dir), spec_blob="b", tool_version="v")
        self.assertEqual(record["usd_total"], 0.075)

    # --- build: record_schema 2 routing ---

    def test_record_schema_is_2(self):
        self.add_run("20261022T001000", self.new_decision, self.attempt)
        self.assertEqual(RECORD_SCHEMA, 2)
        self.assertEqual(build("SH-1", load_runs(self.runs_dir), spec_blob="b", tool_version="v")["record_schema"], 2)

    def test_build_routing_records_level_and_roles(self):
        self.add_run("20261022T001000", self.new_decision, self.attempt)
        routing = build("SH-1", load_runs(self.runs_dir), spec_blob="b", tool_version="v",
                        roster_version="roster")["routing"]
        self.assertEqual(routing["level"], "mid")
        self.assertEqual(routing["roles"], self.roles)
        self.assertNotIn("tier", routing)
        # The other routing keys survive the schema bump.
        self.assertEqual(routing["router"], "clef")
        self.assertEqual(routing["answers"], {"q": "a"})
        self.assertEqual(routing["author"], {"model": "deepseek/deepseek-v4-pro", "family": "deepseek"})
        self.assertEqual(routing["verifier"], {"model": "moonshotai/kimi-k2.7-code", "family": "moonshotai"})
        self.assertEqual((routing["gate"], routing["reasons"]), ("LEAD", ["r1"]))
        self.assertEqual((routing["policy_version"], routing["roster_version"]), (1, "roster"))

    def test_build_routing_from_old_decision_maps_tier_to_level(self):
        self.add_run("20261022T001000", self.decision, self.attempt)
        routing = build("SH-1", load_runs(self.runs_dir), spec_blob="b", tool_version="v")["routing"]
        self.assertEqual(routing["level"], "T2")
        self.assertEqual(routing["roles"], {})
        self.assertNotIn("tier", routing)

    def test_build_routing_without_level_or_tier(self):
        decision = {k: v for k, v in self.decision.items() if k != "tier"}
        self.add_run("20261022T001000", decision, self.attempt)
        self.assertIsNone(build("SH-1", load_runs(self.runs_dir), spec_blob="b", tool_version="v")["routing"]["level"])

    def test_build_does_not_mutate_the_runs(self):
        decision, attempt = self.new_decision, dict(self.attempt)
        runs = [{"decision": decision, "attempt": attempt}]
        before = json.dumps(runs)
        record = build("SH-1", runs, spec_blob="b", tool_version="v")
        self.assertEqual(json.dumps(runs), before)
        self.assertEqual(record["routing"]["roles"], self.roles)

    # --- read: no migration ---

    def test_read_returns_an_older_record_unchanged(self):
        old = {"record_schema": 1, "task": "SH-6", "routing": {"router": "clef", "tier": "T2"}}
        (self.worktree / ".aios" / "records").mkdir(parents=True)
        with open(self.worktree / ".aios" / "records" / "SH-6.json", "w", encoding="utf-8") as f:
            json.dump(old, f)
        self.assertEqual(read(self.worktree, "SH-6"), old)

    # --- write ---

    def test_write_redacts_and_returns_path(self):
        record = build("SH-1", [], spec_blob="b", tool_version="v",
                       summary="worked in /home/alice/proj and /tmp/scratch/file.txt")
        with patch("aios.records.getpass.getuser", return_value="alice"):
            path = write(self.worktree, record)
        self.assertEqual(path, self.worktree / ".aios" / "records" / "SH-1.json")
        self.assertEqual(read(self.worktree, "SH-1")["summary"], "worked in <path> and <path>")

    def test_write_redacts_username(self):
        record = {"task": "SH-2", "spec_blob": "b", "tool_version": "v", "summary": "by username here"}
        with patch("aios.records.getpass.getuser", return_value="username"):
            path = write(self.worktree, record)
        self.assertEqual(read(self.worktree, "SH-2")["summary"], "by <user> here")

    def test_write_keeps_short_usernames(self):
        record = {"task": "SH-3", "spec_blob": "b", "tool_version": "v", "summary": "by username here"}
        with patch("aios.records.getpass.getuser", return_value="ab"):
            write(self.worktree, record)
        self.assertEqual(read(self.worktree, "SH-3")["summary"], "by username here")

    def test_write_does_not_mutate_input(self):
        record = {"task": "SH-4", "spec_blob": "b", "tool_version": "v",
                  "summary": "/home/username/proj", "flags": [], "lessons": []}
        original = json.dumps(record)
        with patch("aios.records.getpass.getuser", return_value="username"):
            write(self.worktree, record)
        self.assertEqual(json.dumps(record), original)

    def test_write_creates_missing_dir(self):
        record = {"task": "SH-5", "spec_blob": "b", "tool_version": "v", "summary": ""}
        (self.worktree / ".aios").mkdir()
        with patch("aios.records.getpass.getuser", return_value="user"):
            path = write(self.worktree, record)
        self.assertTrue(path.is_file())
        with open(path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), json.dumps(record, indent=1, sort_keys=True) + "\n")

    def test_write_round_trips_nested_values(self):
        verdict = {"verdict": "fail", "risk": "medium", "blocking": ["/var/log/app.log by username"]}
        self.add_run("20261022T001000", self.decision, self.attempt)
        record = build("SH-1", load_runs(self.runs_dir), spec_blob="b", tool_version="v", verdict=verdict,
                       summary="/root/tmp/x by username")
        with patch("aios.records.getpass.getuser", return_value="username"):
            write(self.worktree, record)
        saved = read(self.worktree, "SH-1")
        self.assertEqual(saved["attempts"][0]["verdict"]["blocking"], ["<path> by <user>"])
        self.assertEqual(saved["routing"]["author"], {"model": "deepseek/deepseek-v4-pro", "family": "deepseek"})
        self.assertEqual(saved["summary"], "<path> by <user>")

    # --- read ---

    def test_read_returns_none_when_absent(self):
        self.assertIsNone(read(self.worktree, "SH-9"))

    def test_read_corrupt_record_raises(self):
        (self.worktree / ".aios" / "records").mkdir(parents=True)
        with open(self.worktree / ".aios" / "records" / "SH-1.json", "w", encoding="utf-8") as f:
            f.write("{bad json")
        with self.assertRaises(json.JSONDecodeError):
            read(self.worktree, "SH-1")


if __name__ == "__main__":
    unittest.main()
