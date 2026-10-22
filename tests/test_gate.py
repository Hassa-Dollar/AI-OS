"""Unit tests for aios.gate: the deterministic gate checks (changes, scope, deps, flags, tiers, run_checks)."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from aios import config, gate
from aios import spec as specs
from tests import helpers


def git_repo(files=None):
    return helpers.git_repo(files)


def commit_all(wt: Path, msg: str = "c") -> None:
    subprocess.run(["git", "add", "-A"], cwd=wt, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", msg], cwd=wt, check=True, capture_output=True)


def write(wt: Path, rel: str, text: str) -> None:
    p = wt / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


SPEC = """+++
id = "T1"
title = "demo"
files_allowed = ["src/", "README.md"]
deps_preapproved = ["numpy"]
contracts = ["architecture/contracts/spec.schema.md"]
blast_radius = "low"
+++

## Goal
x

## Acceptance criteria
`true`
"""


class GateTests(unittest.TestCase):
    def setUp(self):
        self.wt = git_repo({"src/a.py": "one\n", "package.json": json.dumps({"dependencies": {"a": "1"}})})
        self.base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.wt, capture_output=True,
                                   text=True, check=True).stdout.strip()
        self.s = specs.parse_spec(SPEC)
        self.p = config.paths({"HOME": tempfile.mkdtemp()})

    # --- 1. changes ----------------------------------------------------------
    def test_changes_files_cache_and_pyc_excluded(self):
        write(self.wt, "src/b.py", "print('b')\n")
        write(self.wt, "__pycache__/junk.pyc", "junk")
        write(self.wt, "node_modules/pkg/index.js", "js")
        write(self.wt, "src/__pycache__/x.pyc", "x")
        write(self.wt, "loose.pyc", "loose")
        write(self.wt, "src/__pycache__/deep/mod.pyc", "mod")
        commit_all(self.wt)
        c = gate.changes(self.wt, self.base)
        self.assertNotIn("__pycache__/junk.pyc", c.files)
        self.assertNotIn("node_modules/pkg/index.js", c.files)
        self.assertNotIn("src/__pycache__/x.pyc", c.files)
        self.assertNotIn("src/__pycache__/deep/mod.pyc", c.files)
        self.assertNotIn("loose.pyc", c.files)
        self.assertIn("src/b.py", c.files)

    def test_changes_authored_lines_excludes_lockfiles_and_binary(self):
        write(self.wt, "src/a.py", "one\ntwo\nthree\nfour\n")
        write(self.wt, "package-lock.json", '{"deps": {}}\n')
        write(self.wt, "bin.dat", "\x00\x01\x02\x03")
        commit_all(self.wt)
        subprocess.run(["git", "add", "bin.dat"], cwd=self.wt, check=True, capture_output=True)
        c = gate.changes(self.wt, self.base)
        self.assertEqual(("bin.dat", "package-lock.json", "src/a.py"), c.files)
        self.assertEqual(3, c.authored_lines)

    # --- 2. out_of_scope ----------------------------------------------------
    def test_out_of_scope_directory_grants_and_own_record(self):
        files = ("src/a.py", "src/deep/b.py", "README.md", "other.py", ".aios/records/T1.json")
        got = gate.out_of_scope(self.s, "T1", files)
        self.assertEqual(["other.py"], got)

    def test_out_of_scope_allows_own_record_even_outside_grants(self):
        self.assertEqual([], gate.out_of_scope(self.s, "T1", (".aios/records/T1.json",)))
        self.assertNotEqual([], gate.out_of_scope(self.s, "T2", (".aios/records/T1.json",)))

    # --- 3. added_dependencies ---------------------------------------------
    def test_added_deps_package_json_new_key(self):
        write(self.wt, "package.json", json.dumps({"dependencies": {"a": "1", "b": "2"},
                                                   "devDependencies": {"c": "3"},
                                                   "peerDependencies": {"d": "4"},
                                                   "optionalDependencies": {"e": "5"}}))
        commit_all(self.wt)
        self.assertEqual(["b", "c", "d", "e"], gate.added_dependencies(self.wt, self.base, ("package.json",)))

    def test_added_deps_pyproject_toml(self):
        write(self.wt, "pyproject.toml",
              '[project]\ndependencies = ["requests>=2.0", "flask; python_version>=3.8"]\n'
              '[project.optional-dependencies]\ntest = ["pytest [extra]>=1.0", "mock"]\n')
        commit_all(self.wt)
        self.assertEqual(["flask", "mock", "pytest", "requests"],
                         gate.added_dependencies(self.wt, self.base, ("pyproject.toml",)))

    def test_added_deps_requirements_txt(self):
        write(self.wt, "requirements.txt", "numpy>=1.0\npandas==1.2\n# comment\n\nscipy\n")
        commit_all(self.wt)
        self.assertEqual(["numpy", "pandas", "scipy"], gate.added_dependencies(self.wt, self.base, ("requirements.txt",)))

    def test_added_deps_manifest_new_in_diff(self):
        write(self.wt, "requirements.txt", "numpy>=1.0\nscipy\n")
        commit_all(self.wt)
        self.assertEqual(["numpy", "scipy"],
                         gate.added_dependencies(self.wt, self.base, ("requirements.txt",)))

    def test_added_deps_case_insensitive(self):
        repo = git_repo({"requirements.txt": "numpy>=1.0\n"})
        b = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
        write(repo, "requirements.txt", "NumPy>=1.0\n")  # same name, different case: not an addition
        commit_all(repo)
        self.assertEqual([], gate.added_dependencies(repo, b, ("requirements.txt",)))
        write(repo, "requirements.txt", "NumPy>=1.0\nPandas==1.2\n")
        commit_all(repo)
        self.assertEqual(["pandas"], gate.added_dependencies(repo, b, ("requirements.txt",)))

    def test_added_deps_removed_not_counted(self):
        repo = git_repo({"requirements.txt": "numpy>=1.0\n"})
        b = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
        write(repo, "requirements.txt", "pandas==1.2\n")  # numpy removed, pandas added
        commit_all(repo)
        self.assertEqual(["pandas"], gate.added_dependencies(repo, b, ("requirements.txt",)))

    # --- 4. flags ----------------------------------------------------------
    def test_flags_dependency_change_unapproved(self):
        self.assertEqual([("dependency-change", "LEAD")],
                         gate.flags(self.s, ("src/a.py",), 10, ["zod"]))

    def test_flags_dependency_change_preapproved_no_flag(self):
        self.assertEqual([], gate.flags(self.s, ("src/a.py",), 10, ["numpy"]))

    def test_flags_touches_contract(self):
        self.assertEqual([("touches-contract", "LEAD")],
                         gate.flags(self.s, ("src/a.py", "architecture/contracts/spec.schema.md"), 10, []))
        self.assertEqual([("touches-contract", "LEAD")],
                         gate.flags(self.s, ("architecture/contracts/project.schema.md",), 10, []))

    def test_flags_sensitive_path(self):
        self.assertEqual([("sensitive-path", "LEAD")],
                         gate.flags(self.s, ("src/a.py",), 10, [], sensitive_paths=("src/",)))
        self.assertEqual([("sensitive-path", "LEAD")],
                         gate.flags(self.s, ("id_rsa",), 10, [], sensitive_paths=("id_rsa",)))

    def test_flags_large_change(self):
        files = tuple(f"f{i}.py" for i in range(13))
        self.assertEqual([("large-change", "OPERATOR")], gate.flags(self.s, files, 0, []))
        self.assertEqual([("large-change", "OPERATOR")], gate.flags(self.s, ("src/a.py",), 351, []))

    def test_flags_verifier_risk_high(self):
        self.assertEqual([("verifier-risk-high", "LEAD")],
                         gate.flags(self.s, ("src/a.py",), 0, [], verifier_risk="high"))
        self.assertEqual([], gate.flags(self.s, ("src/a.py",), 0, [], verifier_risk="low"))

    def test_flags_order_and_dedup(self):
        files = tuple(f"f{i}.py" for i in range(13)) + ("architecture/contracts/x.md", "other/secret")
        got = gate.flags(self.s, files, 400, ["zod"], sensitive_paths=("other/",), verifier_risk="high")
        self.assertEqual([("dependency-change", "LEAD"), ("touches-contract", "LEAD"),
                          ("sensitive-path", "LEAD"), ("large-change", "OPERATOR"),
                          ("verifier-risk-high", "LEAD")], got)

    # --- 5. tier ----------------------------------------------------------
    def test_tier_ordering(self):
        self.assertEqual("AUTO", gate.tier("AUTO", []))
        self.assertEqual("HUMAN", gate.tier("AUTO", [("x", "HUMAN")]))
        self.assertEqual("LEAD", gate.tier("LEAD", [("x", "OPERATOR")]))
        self.assertEqual("HUMAN", gate.tier("OPERATOR", [("x", "LEAD"), ("y", "HUMAN")]))
        self.assertEqual("LEAD", gate.tier("AUTO", [("x", "LEAD"), ("y", "OPERATOR")]))

    # --- 6. run_checks ----------------------------------------------------
    def test_run_checks_fake_runner_argument_shape(self):
        comp = config.Component("c", "", "p", None, ("true", "false"))
        seen = []
        calls = {"n": 0}

        def fake_runner(cmd, **kw):
            seen.append((cmd, kw))
            calls["n"] += 1
            return subprocess.CompletedProcess(cmd, 0, "out", "err")

        r = gate.run_checks(self.p, self.wt, comp, runner=fake_runner)
        self.assertEqual(2, len(r))
        cmd, kw = seen[0]
        self.assertEqual("bwrap", cmd[0])
        self.assertIn("--bind", cmd)
        self.assertIn(str(self.wt), cmd)
        self.assertIn("--chdir", cmd)
        self.assertIn("bash", cmd)
        self.assertIn("-c", cmd)
        self.assertEqual(kw["timeout"], 1800)
        self.assertFalse(kw["env"].get("network"))
        self.assertEqual(("true", 0, "outerr"), r[0])

    def test_run_checks_continues_past_failure(self):
        comp = config.Component("c", "", "p", None, ("exit 1", "true"))

        def fake_runner(cmd, **kw):
            if "exit 1" in cmd[-1]:
                return subprocess.CompletedProcess(cmd, 1, "", "boom")
            return subprocess.CompletedProcess(cmd, 0, "ok", "")

        r = gate.run_checks(self.p, self.wt, comp, runner=fake_runner)
        self.assertEqual(2, len(r))
        self.assertEqual(1, r[0][1])
        self.assertEqual(0, r[1][1])

    def test_run_checks_truncates_output(self):
        comp = config.Component("c", "", "p", None, ("true",))
        gate.run_checks(self.p, self.wt, comp, runner=lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "x" * 3000, ""))
        # Truncation is checked in the result; re-run capturing it
        r = gate.run_checks(self.p, self.wt, comp, runner=lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "x" * 3000, ""))
        self.assertEqual(2000, len(r[0][2]))

    def test_run_checks_none_raises(self):
        comp = config.Component("c", "", "p", None, None)
        with self.assertRaises(ValueError):
            gate.run_checks(self.p, self.wt, comp, runner=lambda *a, **k: None)


if __name__ == "__main__":
    unittest.main()
