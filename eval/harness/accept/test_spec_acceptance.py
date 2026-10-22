"""AI-1 hidden acceptance: aios/spec.py against the rules in tasks/AI-1.md."""
import ast
import sys
import tempfile
import unittest
from pathlib import Path

from aios.spec import BLAST, KINDS, SpecError, load_spec, overlaps, parse_spec, path_allowed

BODY = "\n# Goal\nDo it.\n\n## Acceptance criteria\n- works\n\n## Out of scope\nnothing\n"
MIN = 'id = "T-1"\ntitle = "x"\nfiles_allowed = ["src/a.py", "docs/"]'


def mk(front, body=BODY):
    return "+++\n" + front + "\n+++\n" + body


def spec(files, sid="T"):
    return parse_spec(mk(f'id="{sid}"\ntitle="x"\nfiles_allowed={files}'))


class Acceptance(unittest.TestCase):
    def bad(self, text, *needles, source="spec-x.md"):
        with self.assertRaises(SpecError) as cm:
            parse_spec(text, source=source)
        msg = str(cm.exception)
        self.assertIn(source, msg)
        for n in needles:
            self.assertIn(n.lower(), msg.lower())
        return cm.exception

    def test_minimal_defaults(self):
        s = parse_spec(mk(MIN))
        self.assertEqual((s.id, s.title, s.files_allowed), ("T-1", "x", ("src/a.py", "docs/")))
        self.assertEqual((s.deps_preapproved, s.contracts, s.depends_on), ((), (), ()))
        self.assertEqual(s.blast_radius, "low")
        self.assertFalse(s.human_required or s.irreversible)
        self.assertIsNone(s.budget_usd)
        self.assertIsNone(s.kind)
        self.assertIsNone(s.pin_model)
        self.assertEqual(s.branch, "aios/T-1")
        self.assertEqual(s.sections["goal"], "Do it.")
        self.assertEqual(s.sections["acceptance criteria"], "- works")
        self.assertTrue(s.body.startswith("# Goal"))

    def test_full(self):
        s = parse_spec(mk(MIN + '\ndeps_preapproved=["zod"]\ncontracts=["c.md"]\nblast_radius="high"\n'
                          'depends_on=["T-0"]\nhuman_required=true\nirreversible=true\nbudget_usd=2\n'
                          'kind="bugfix"\npin={model="m/x", reason="because"}'))
        self.assertEqual((s.deps_preapproved, s.contracts, s.depends_on), (("zod",), ("c.md",), ("T-0",)))
        self.assertEqual(s.blast_radius, "high")
        self.assertTrue(s.human_required and s.irreversible)
        self.assertEqual(s.budget_usd, 2.0)
        self.assertIsInstance(s.budget_usd, float)
        self.assertEqual(s.kind, "bugfix")
        self.assertEqual((s.pin_model, s.pin_reason), ("m/x", "because"))

    def test_frozen_and_bom(self):
        s = parse_spec("﻿" + mk(MIN))
        with self.assertRaises(Exception):
            s.id = "y"

    def test_fences(self):
        self.bad("id='x'\n" + BODY)
        self.bad("+++\n" + MIN + "\n" + BODY)
        self.bad(" +++\n" + MIN + "\n+++\n" + BODY)

    def test_toml_error_is_chained(self):
        self.assertIsNotNone(self.bad(mk('id = "T-1\ntitle="x"\nfiles_allowed=["a"]')).__cause__)

    def test_unknown_key(self):
        self.bad(mk(MIN + '\nowner_role="implementer"'), "owner_role")

    def test_required(self):
        self.bad(mk('title="x"\nfiles_allowed=["a"]'), "id")
        self.bad(mk('id="T"\nfiles_allowed=["a"]'), "title")
        self.bad(mk('id="T"\ntitle="  "\nfiles_allowed=["a"]'), "title")
        self.bad(mk('id="T"\ntitle="x"'), "files_allowed")
        self.bad(mk('id="T"\ntitle="x"\nfiles_allowed=[]'), "files_allowed")

    def test_id_pattern(self):
        for bad_id in ['"-x"', '"a b"', '"' + "a" * 65 + '"', "7"]:
            self.bad(mk(f'id={bad_id}\ntitle="x"\nfiles_allowed=["a"]'), "id")
        parse_spec(mk('id="a.B_c-1"\ntitle="x"\nfiles_allowed=["a"]'))

    def test_types(self):
        for extra, key in [('blast_radius="med"', "blast_radius"), ('kind="chore"', "kind"),
                           ('human_required="true"', "human_required"), ("irreversible=0", "irreversible"),
                           ("budget_usd=0", "budget_usd"), ("budget_usd=-1.5", "budget_usd"),
                           ("budget_usd=true", "budget_usd"), ('deps_preapproved="zod"', "deps_preapproved"),
                           ("contracts=[1]", "contracts"), ('depends_on="T-0"', "depends_on")]:
            self.bad(mk(MIN + "\n" + extra), key)
        self.bad(mk('id="T"\ntitle="x"\nfiles_allowed=["a", 2]'), "files_allowed")
        self.assertEqual(parse_spec(mk(MIN + "\nbudget_usd=0.25")).budget_usd, 0.25)

    def test_pin(self):
        for pin in ['"m/x"', '{model="m/x"}', '{model="m/x", reason=""}', '{model="m/x", reason="r", extra="y"}']:
            self.bad(mk(MIN + "\npin=" + pin), "pin")

    def test_files_allowed_entries(self):
        for entry in ['"/abs"', '"a\\\\b"', '"a/../b"', '"./a"', '"a//b"', '""', '"a/./b"', '".."']:
            self.bad(mk(f'id="T"\ntitle="x"\nfiles_allowed=[{entry}]'), "files_allowed")
        self.bad(mk('id="T"\ntitle="x"\nfiles_allowed=["a", "a"]'), "files_allowed")

    def test_sections(self):
        self.bad(mk(MIN, body="\n# Goal\nx\n"), "acceptance criteria")
        self.bad(mk(MIN, body="\n## Acceptance Criteria\nx\n"), "goal")
        s = parse_spec(mk(MIN, body="\n### GOAL\ng\n#### deep\nmore\n## Acceptance criteria\nac\n"))
        self.assertEqual(s.sections["goal"], "g\n#### deep\nmore")
        self.assertEqual(s.sections["acceptance criteria"], "ac")

    def test_path_allowed(self):
        s = spec('["src/", "README.md"]')
        for p in ["src/a.py", "src/x/y", "README.md"]:
            self.assertTrue(path_allowed(s, p), p)
        for p in ["src", "srcx/a", "README.md.bak", "/src/a.py", "src/../etc/passwd", "./src/a.py", "src//a", "", "src\\a"]:
            self.assertFalse(path_allowed(s, p), p)

    def test_overlaps(self):
        a = spec('["src/", "docs/a.md"]', "A")
        b = spec('["src/x/y.py", "docs/a.md", "lib/"]', "B")
        c = spec('["srcx/a", "lib/z"]', "C")
        d = spec('["src/x/"]', "D")
        self.assertEqual(overlaps(a, b), ["docs/a.md <-> docs/a.md", "src/ <-> src/x/y.py"])
        self.assertEqual(overlaps(a, c), [])
        self.assertEqual(overlaps(b, c), ["lib/ <-> lib/z"])
        self.assertEqual(overlaps(d, a), ["src/x/ <-> src/"])

    def test_load_spec(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "t.md")
            p.write_text(mk(MIN), encoding="utf-8")
            self.assertEqual(load_spec(p).id, "T-1")
            self.assertEqual(load_spec(str(p)).id, "T-1")
            p.write_text(mk('title="x"\nfiles_allowed=["a"]'), encoding="utf-8")
            with self.assertRaises(SpecError) as cm:
                load_spec(p)
            self.assertIn(str(p), str(cm.exception))

    def test_constants_and_stdlib_only(self):
        self.assertEqual(BLAST, ("low", "medium", "high"))
        self.assertEqual(KINDS, frozenset({"feature", "bugfix", "refactor", "tests", "docs", "research", "infra",
                                           "security", "migration"}))
        tree = ast.parse(Path(sys.modules["aios.spec"].__file__).read_text())
        mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and n.level == 0}
        self.assertTrue(mods <= set(sys.stdlib_module_names) | {"aios", "__future__"}, mods)


if __name__ == "__main__":
    unittest.main()
