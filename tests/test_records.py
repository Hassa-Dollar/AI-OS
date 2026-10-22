import json
import tempfile
import os
import shutil
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from aios.records import load_runs, build, write, read, RECORD_SCHEMA

class TestRecords(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.runs_dir = Path(self.temp_dir) / "runs"
        self.runs_dir.mkdir()
        self.repo_root = Path(self.temp_dir) / "repo"
        self.repo_root.mkdir()
        self.worktree_root = Path(self.temp_dir) / "worktree"
        self.worktree_root.mkdir()
        
        self.mock_username = "testuser"

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    # --- load_runs tests ---

    def test_load_runs_missing_dir(self):
        non_existent_dir = Path(self.temp_dir) / "nonexistent"
        self.assertEqual(load_runs(non_existent_dir), [])

    def test_load_runs_empty_dir(self):
        self.assertEqual(load_runs(self.runs_dir), [])

    def test_load_runs_success_and_ordering(self):
        run1_dir = self.runs_dir / "20261020T000000"
        run1_dir.mkdir()
        run1_path = run1_dir / "attempt.json"
        with open(run1_path, 'w') as f:
            json.dump({"decision": {"router": "R1", "tier": "T1"}, "attempt": {"usd": 0.1}}, f)

        run2_dir = self.runs_dir / "20261022T000000"
        run2_dir.mkdir()
        run2_path = run2_dir / "attempt.json"
        with open(run2_path, 'w') as f:
            json.dump({"decision": {"router": "R2", "tier": "T2"}, "attempt": {"usd": 0.2}}, f)

        (self.runs_dir / "no_attempt_dir").mkdir()

        runs = load_runs(self.runs_dir)
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0]["decision"]["router"], "R1")
        self.assertEqual(runs[1]["decision"]["router"], "R2")

    def test_load_runs_corrupt_files(self):
        run1_dir = self.runs_dir / "20261020T000000"
        run1_dir.mkdir()
        run1_path = run1_dir / "attempt.json"
        with open(run1_path, 'w') as f:
            f.write("{invalid json")
        
        run2_dir = self.runs_dir / "20261022T000000"
        run2_dir.mkdir()
        run2_path = run2_dir / "attempt.json"
        with open(run2_path, 'w') as f:
            json.dump({"decision": {"router": "R2", "tier": "T2"}, "attempt": {"usd": 0.2}}, f)

        runs = load_runs(self.runs_dir)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["decision"]["router"], "R2")

    # --- build tests ---

    def test_build_with_runs(self):
        runs = [
            {"decision": {"router": "R_FIRST", "answers": {}, "tier": "T1", "author": {"model": "M1", "family": "F1"}, "verifier": {"model": "V1", "family": "F2"}, "gate": "AUTO", "reasons": ["r1"]}, "attempt": {"usd": 0.01, "exit": "submitted"}},
            {"decision": {}, "attempt": {"usd": 0.02, "exit": "error"}}
        ]
        
        verdict = {"usd": 0.005, "verdict": "pass"}
        
        record = build(
            task_id="T1",
            runs=runs,
            spec_blob="blob123",
            tool_version="v1",
            verdict=verdict,
            flags=["f"],
            gate="FINAL_GATE",
            approval={"by": "A1"},
            summary="Sum",
            lessons=["L1"]
        )
        
        self.assertEqual(record["record_schema"], RECORD_SCHEMA)
        self.assertEqual(record["task"], "T1")
        self.assertEqual(record["routing"]["router"], "R_FIRST")
        self.assertEqual(record["routing"]["tier"], "T1")
        self.assertEqual(record["attempts"][0]["n"], 1)
        self.assertEqual(record["attempts"][1]["n"], 2)
        
        self.assertIn("verdict", record["attempts"][1])
        self.assertEqual(record["attempts"][1]["verdict"]["verdict"], "pass")
        
        self.assertAlmostEqual(record["usd_total"], 0.035, places=6)

        self.assertEqual(record["flags"], ["f"])
        self.assertEqual(record["gate"], "FINAL_GATE")
        self.assertEqual(record["summary"], "Sum")

    def test_build_no_runs(self):
        record = build(
            task_id="T2",
            runs=[],
            spec_blob="blob456",
            tool_version="v2",
            verdict=None,
            flags=[],
            gate="AUTO"
        )
        self.assertIsNone(record["routing"])
        self.assertEqual(record["attempts"], [])
        self.assertEqual(record["usd_total"], 0.0)

    # --- write tests ---

    @patch('aios.records.getpass.getuser', return_value="sensitive_user")
    def test_write_redaction_success(self, mock_getuser):
        input_record = {
            "task": "T3",
            "spec_blob": "abc",
            "tool_version": "v3",
            "routing": {
                "reasons": ["/home/sensitive_user/config.yaml used"],
            },
            "attempts": [{
                "model": "/tmp/scratch_dir/model.pth",
                "usd": 0.1
            }],
            "summary": "This log contains the user's path: /Users/sensitive_user/Documents/notes.txt. Authored by sensitive_user."
        }
        
        output_path = write(self.worktree_root, input_record)
        
        self.assertTrue(output_path.is_file())
        
        with open(output_path, 'r') as f:
            written_record = json.load(f)

        # The regex (home|Users|root|tmp|mnt|var)/[^\s"'\]\)]* consumes slashes,
        # so the entire path is replaced by <path>.
        self.assertEqual(written_record["routing"]["reasons"][0], "<path> used")
        self.assertEqual(written_record["attempts"][0]["model"], "<path>")
        self.assertIn("<user>", written_record["summary"])
        self.assertEqual(written_record["summary"], "This log contains the user's path: <path> Authored by <user>.")
        
        self.assertEqual(input_record["routing"]["reasons"][0], "/home/sensitive_user/config.yaml used")

    @patch('aios.records.getpass.getuser', return_value="short") # 5 characters, must be redacted
    def test_write_redaction_username_short(self, mock_getuser):
        input_record = {
            "task": "T4",
            "spec_blob": "abc",
            "tool_version": "v3",
            "summary": "Contains short user: short"
        }
        
        output_path = write(self.worktree_root, input_record)
        with open(output_path, 'r') as f:
            written_record = json.load(f)
            
        # Username "short" is 5 chars (>= 3), so it must be redacted to <user>
        self.assertEqual(written_record["summary"], "Contains <user> user: <user>")

    # --- read tests ---

    def test_read_success_and_failure(self):
        task_id = "T5"
        record = {"record_schema": RECORD_SCHEMA, "task": task_id}
        
        output_path = write(self.worktree_root, record)
        
        read_record = read(self.worktree_root, task_id)
        self.assertIsNotNone(read_record)
        self.assertEqual(read_record["task"], task_id)
        
        read_absent = read(self.worktree_root, "T_MISSING")
        self.assertIsNone(read_absent)

if __name__ == "__main__":
    unittest.main()
