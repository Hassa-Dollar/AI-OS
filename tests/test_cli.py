import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aios import catalog, cli, config, git
from tests.helpers import clef_answers, cwd, fake_http, git_repo


def run(*argv):
    code, _, err = run_out(*argv)
    return code, err


def run_out(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


SPEC = """+++
id = "T-1"
title = "Add a CSV export"
files_allowed = ["src/report.py"]
+++
# Goal
Export reports as CSV.
## Acceptance criteria
- `pytest -q` passes
"""

# A spec with a descriptive id, named after it (the route command does not check names; spec does).
NAMED = """+++
id = "export-reports"
title = "Add a CSV export"
files_allowed = ["src/report.py"]
+++
# Goal
Export reports as CSV.
## Acceptance criteria
- `pytest -q` passes
"""


def write(text: str, name: str = "task") -> Path:
    f = Path(tempfile.mkdtemp()) / f"{name}.md"
    f.write_text(text)
    return f


def model(mid, *, score, pin, pout):
    """One scored catalog entry in the shape `catalog.sync` caches (a fake live catalog, not the roster)."""
    return {"id": mid, "usable": True, "context_length": 200_000,
            "supported_parameters": ["tools", "structured_outputs"],
            "pricing": {"prompt": pin, "completion": pout},
            "benchmarks": {"artificial_analysis": {"intelligence_index": score}}}


# At least two families for workers (acme, echo) and reviewers (watch, bolt, dune), so a cross-family reviewer exists.
LIVE = [model("acme/econ", score=41.0, pin="0.0000002", pout="0.0000004"),
        model("watch/cheap", score=36.0, pin="0.0000001", pout="0.0000002"),
        model("echo/mid", score=46.0, pin="0.0000003", pout="0.0000006"),
        model("watch/ok", score=44.0, pin="0.0000004", pout="0.0000008"),
        model("cortex/front", score=60.0, pin="0.0000005", pout="0.000001"),
        model("bolt/standard", score=46.0, pin="0.000001", pout="0.000002"),
        model("dune/senior", score=55.0, pin="0.000002", pout="0.000004")]


class Init(unittest.TestCase):
    def test_node_repo(self):
        pkg = json.dumps({"scripts": {"lint": "eslint .", "test": "vitest run", "dev": "x"}})
        root = git_repo({"package.json": pkg}, remote="https://github.com/acme/app.git")
        with cwd(root):
            self.assertEqual(run("init")[0], 0)
        p = config.load_project(root)
        self.assertEqual((p.name, p.forge, p.default_branch), (root.name, "github", "main"))
        self.assertEqual(p.components[0].profile, "node")
        self.assertEqual(p.components[0].checks, ("npm run -s lint", "npm run -s test"))
        self.assertTrue((root / ".aios" / "tasks" / ".gitkeep").exists())
        with cwd(root):
            code, err = run("init")
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)

    def test_requires_a_check_when_undetectable(self):
        root = git_repo()
        with cwd(root):
            code, err = run("init")
            self.assertEqual(code, 2)
            self.assertIn("--check", err)
            self.assertEqual(run("init", "--check", "make test", "--name", "fw")[0], 0)
        p = config.load_project(root)
        self.assertEqual((p.name, p.forge, p.components[0].profile, p.components[0].checks),
                         ("fw", "local", "generic", ("make test",)))

    def test_outside_git_repo(self):
        import tempfile
        with cwd(tempfile.mkdtemp()):
            code, err = run("init", "--check", "x")
        self.assertEqual(code, 2)
        self.assertIn("git", err)


class SpecAndRoute(unittest.TestCase):
    def test_spec_validates_and_reports_overlaps(self):
        a = write(NAMED, "export-reports")
        b = write(NAMED.replace('"export-reports"', '"import-reports"'), "import-reports")
        self.assertEqual(run_out("spec", str(a))[0], 0)
        code, out, _ = run_out("spec", str(a), str(b))
        self.assertEqual(code, 2)
        self.assertIn("OVERLAP export-reports / import-reports: src/report.py <-> src/report.py", out)
        code, out, _ = run_out("spec", str(write(NAMED.replace('id = "export-reports"\n', ""),
                                                 "export-reports")))
        self.assertEqual(code, 2)
        self.assertIn("FAIL", out)

    def test_spec_rejects_a_coded_name(self):
        f = write(SPEC, "task")
        code, out, _ = run_out("spec", str(f))
        self.assertEqual(code, 2)
        self.assertIn(f"FAIL    {f}: 'T-1' is not a descriptive name", out)
        self.assertIn("2 to 6 lowercase words joined by hyphens", out)

    def test_spec_rejects_a_file_name_that_differs_from_the_id(self):
        f = write(NAMED, "wrong-name")
        code, out, _ = run_out("spec", str(f))
        self.assertEqual(code, 2)
        self.assertIn("the file is named wrong-name.md but the id is export-reports;", out)
        self.assertIn("name the file export-reports.md", out)

    def test_names_skips_the_overlap_report(self):
        a = write(NAMED, "export-reports")
        b = write(NAMED.replace('"export-reports"', '"import-reports"'), "import-reports")
        code, out, _ = run_out("spec", str(a), str(b), "--names")
        self.assertEqual(code, 0)
        self.assertNotIn("OVERLAP", out)
        code, out, _ = run_out("spec", str(write(SPEC, "task")), "--names")
        self.assertEqual(code, 2)
        self.assertIn("is not a descriptive name", out)

    def route(self, *argv, answers=None):
        p = config.paths()
        p.cache.mkdir(parents=True, exist_ok=True)
        catalog.cache_file(p).write_text(json.dumps(LIVE))
        with fake_http({"POST /v1/systemone": (200, {"answers": answers or clef_answers()})}) as host, \
                mock.patch.dict(os.environ, {"OLLAMA_HOST": host}), \
                mock.patch("aios.calibrate.passed", return_value=True):
            return run_out("route", *argv)

    def test_route_dispatch_refuse_and_json(self):
        code, out, _ = self.route(str(write(SPEC)))
        self.assertEqual(code, 0, out)
        self.assertIn("DISPATCH  gate AUTO  level junior", out)
        self.assertIn("  implementer acme/econ [acme]", out)
        self.assertIn("  reviewer    watch/cheap [watch]", out)
        code, out, _ = self.route(str(write(SPEC.replace("- `pytest -q` passes", "- make it nice"))))
        self.assertEqual(code, 3)
        self.assertIn("vague", out)
        code, out, _ = self.route(str(write(SPEC)), "--json", answers=clef_answers(security_sensitive=0.95))
        record = json.loads(out)
        self.assertEqual((record["action"], record["router"]), ("dispatch", "clef-flash"))
        self.assertNotEqual(record["author_family"], record["verifier_family"])


class Git(unittest.TestCase):
    def test_helpers(self):
        root = git_repo(remote="git@example.invalid:x.git")
        self.assertEqual(git.toplevel(root / ".git" / ".."), root.resolve())
        self.assertEqual(len(git.root_commit(root)), 40)
        self.assertEqual(git.default_branch(root), "main")
        self.assertEqual(git.remote_url(root), "git@example.invalid:x.git")
        self.assertIsNone(git.remote_url(root, "nope"))
        with self.assertRaises(git.GitError):
            git.git(["show", "no-such-ref"], root)


if __name__ == "__main__":
    unittest.main()
