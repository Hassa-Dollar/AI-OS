import os
import tempfile
import unittest

from aios.spec import (
    BLAST,
    KINDS,
    Spec,
    SpecError,
    load_spec,
    overlaps,
    parse_spec,
    path_allowed,
)


def make_spec(
    id_="AI-1",
    title="t",
    files_allowed=("aios/spec.py",),
    **kw,
):
    fields = {
        "deps_preapproved": (),
        "contracts": (),
        "blast_radius": "low",
        "depends_on": (),
        "human_required": False,
        "irreversible": False,
        "budget_usd": None,
        "kind": None,
        "pin_model": None,
        "pin_reason": None,
        "body": "",
        "sections": {},
    }
    fields.update(kw)
    return Spec(id=id_, title=title, files_allowed=tuple(files_allowed), **fields)


def spec_text(
    front,
    body="# Goal\n\ndo it\n\n## Acceptance criteria\n\nok\n",
    fence="+++",
):
    return f"{fence}\n{front}\n{fence}\n{body}"


BASE_FRONT = 'id = "AI-1"\ntitle = "t"\nfiles_allowed = ["aios/spec.py"]'


def assert_err(self, text, frag, source="src.md"):
    with self.assertRaises(SpecError) as cm:
        parse_spec(text, source=source)
    self.assertIn(source, str(cm.exception))
    if frag is not None:
        self.assertIn(frag, str(cm.exception))


class TestFences(unittest.TestCase):
    def test_valid(self):
        s = parse_spec(spec_text(BASE_FRONT))
        self.assertEqual(s.id, "AI-1")
        self.assertEqual(s.title, "t")
        self.assertEqual(s.files_allowed, ("aios/spec.py",))

    def test_bom_allowed(self):
        parse_spec("﻿" + spec_text(BASE_FRONT))

    def test_missing_opening_fence(self):
        assert_err(self, "id = 1\n+++\n# Goal\n", "+++")

    def test_missing_closing_fence(self):
        assert_err(self, f"+++\n{BASE_FRONT}\n", "closing")

    def test_toml_error_chained(self):
        with self.assertRaises(SpecError) as cm:
            parse_spec(spec_text("id = ="))
        self.assertIsInstance(cm.exception.__cause__, Exception)


class TestKeys(unittest.TestCase):
    def test_unknown_key(self):
        assert_err(self, spec_text(BASE_FRONT + '\nfoo = 1'), "foo")

    def test_missing_required(self):
        for key in ("id", "title", "files_allowed"):
            front = "\n".join(
                ln for ln in BASE_FRONT.splitlines() if not ln.startswith(key)
            )
            with self.assertRaises(SpecError):
                parse_spec(spec_text(front))

    def test_bad_id(self):
        for id_ in ("", "-x", "a b", "a" * 65, 1):
            with self.assertRaises(SpecError):
                parse_spec(spec_text(f'id = {id_!r}\ntitle = "t"\nfiles_allowed = ["a"]'))
        s = parse_spec(spec_text('id = "a.b-1"\ntitle = "t"\nfiles_allowed = ["a"]'))
        self.assertEqual(s.branch, "aios/a.b-1")

    def test_blank_title(self):
        assert_err(self, spec_text('id = "a"\ntitle = "   "\nfiles_allowed = ["a"]'), "title")

    def test_empty_files_allowed(self):
        assert_err(self, spec_text('id = "a"\ntitle = "t"\nfiles_allowed = []'), "files_allowed")


class TestOptionalKeys(unittest.TestCase):
    def test_full(self):
        front = "\n".join([
            BASE_FRONT,
            'deps_preapproved = ["x"]',
            'contracts = ["c"]',
            'depends_on = ["AI-0"]',
            "human_required = true",
            "irreversible = false",
            "budget_usd = 0.75",
            'kind = "feature"',
            'blast_radius = "medium"',
            "[pin]",
            'model = "m"',
            'reason = "r"',
        ])
        s = parse_spec(spec_text(front))
        self.assertEqual(
            (s.deps_preapproved, s.contracts, s.depends_on,
             s.human_required, s.irreversible),
            (("x",), ("c",), ("AI-0",), True, False),
        )
        self.assertEqual(s.budget_usd, 0.75)
        self.assertEqual(s.kind, "feature")
        self.assertEqual(s.blast_radius, "medium")
        self.assertEqual((s.pin_model, s.pin_reason), ("m", "r"))

    def test_int_budget(self):
        s = parse_spec(spec_text(BASE_FRONT + "\nbudget_usd = 2"))
        self.assertEqual(s.budget_usd, 2.0)
        self.assertIsInstance(s.budget_usd, float)

    def test_bad_budget(self):
        for v in ("0", "true", "-1", '"0.5"', "0"):
            with self.assertRaises(SpecError):
                parse_spec(spec_text(BASE_FRONT + f"\nbudget_usd = {v}"))
        with self.assertRaises(SpecError):
            parse_spec(spec_text(BASE_FRONT + "\nbudget_usd = true"))

    def test_bad_bools(self):
        for k in ("human_required", "irreversible"):
            assert_err(self, spec_text(BASE_FRONT + f"\n{k} = 0"), k)
            assert_err(self, spec_text(BASE_FRONT + f'\n{k} = "true"'), k)

    def test_bad_str_lists(self):
        for k in ("deps_preapproved", "contracts", "depends_on"):
            assert_err(self, spec_text(BASE_FRONT + f"\n{k} = 1"), k)
            assert_err(self, spec_text(BASE_FRONT + f"\n{k} = [1]"), k)

    def test_bad_kind(self):
        assert_err(self, spec_text(BASE_FRONT + '\nkind = "nope"'), "kind")
        for k in KINDS:
            parse_spec(spec_text(BASE_FRONT + f'\nkind = "{k}"'))

    def test_bad_blast(self):
        assert_err(self, spec_text(BASE_FRONT + '\nblast_radius = "nope"'), "blast_radius")
        self.assertEqual(BLAST, ("low", "medium", "high"))

    def test_bad_pin(self):
        assert_err(self, spec_text(BASE_FRONT + '\npin = "x"'), "pin")
        assert_err(self, spec_text(BASE_FRONT + '\n[pin]\nmodel = "m"'), "pin")
        assert_err(
            self,
            spec_text(BASE_FRONT + '\n[pin]\nmodel = "m"\nreason = " "\n'),
            "pin",
        )
        assert_err(
            self,
            spec_text(BASE_FRONT + '\n[pin]\nmodel = "m"\nreason = "r"\nx = 1\n'),
            "pin",
        )


class TestFilesAllowed(unittest.TestCase):
    def test_bad_entries(self):
        bad = ["", "/abs", "a\\b", "a/../b", ".", "./a", "a/./b", "a//b", "//", ".."]
        for e in bad:
            esc = e.replace("\\", "\\\\").replace('"', '\\"')
            with self.assertRaises(SpecError):
                parse_spec(spec_text(f'id = "a"\ntitle = "t"\nfiles_allowed = ["{esc}"]'))

    def test_dup(self):
        assert_err(
            self,
            spec_text('id = "a"\ntitle = "t"\nfiles_allowed = ["a", "a"]'),
            "duplicate",
        )

    def test_dir_grant_kept(self):
        s = parse_spec(spec_text('id = "a"\ntitle = "t"\nfiles_allowed = ["src/"]'))
        self.assertEqual(s.files_allowed, ("src/",))


class TestSections(unittest.TestCase):
    def test_sections(self):
        s = parse_spec(spec_text(
            BASE_FRONT,
            body="intro\n\n# Goal\n\ndo\n\n## Acceptance criteria\n\nok\n"
                 "\n### Other  Head \n\nz\n",
        ))
        self.assertEqual(s.sections["goal"], "do")
        self.assertEqual(s.sections["acceptance criteria"], "ok")
        self.assertEqual(s.sections["other  head"], "z")

    def test_heading_keys_lowered_stripped(self):
        s = parse_spec(spec_text(BASE_FRONT, body="#  Goal \nbody\n\n# Acceptance criteria\nok"))
        self.assertEqual(s.sections["goal"], "body")

    def test_deeper_heading_is_text(self):
        s = parse_spec(spec_text(BASE_FRONT, body="# Goal\n#### Deep\ntext\n\n# Acceptance criteria\nok"))
        self.assertEqual(s.sections["goal"], "#### Deep\ntext")
        self.assertIn("#### Deep", s.body)

    def test_no_space_not_heading(self):
        s = parse_spec(spec_text(BASE_FRONT, body="# Goal\n#Goal\ng\n\n# Acceptance criteria\na\n"))
        self.assertNotIn("goal:", s.sections)
        self.assertIn("#Goal", s.sections["goal"])

    def test_body_leading_newlines(self):
        s = parse_spec("+++\n%s\n+++\n\n\n# Goal\n\ng\n# Acceptance criteria\n\na\n" % BASE_FRONT)
        self.assertTrue(s.body.startswith("# Goal"))

    def test_missing_sections(self):
        with self.assertRaises(SpecError):
            parse_spec("+++\n%s\n+++\n# Goal\nonly goal\n" % BASE_FRONT)
        with self.assertRaises(SpecError):
            parse_spec("+++\n%s\n+++\n# Acceptance criteria\nonly ac\n" % BASE_FRONT)


class TestLoad(unittest.TestCase):
    def test_load_spec(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(spec_text(BASE_FRONT))
            s = load_spec(p)
            self.assertEqual(s.id, "AI-1")

    def test_load_error_names_source(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write("no fence\n")
            with self.assertRaises(SpecError) as cm:
                load_spec(p)
            self.assertIn(p, str(cm.exception))


class TestPathAllowed(unittest.TestCase):
    def test_file_grant(self):
        s = make_spec(files_allowed=("aios/spec.py",))
        self.assertTrue(path_allowed(s, "aios/spec.py"))
        self.assertFalse(path_allowed(s, "aios/other.py"))

    def test_dir_grant(self):
        s = make_spec(files_allowed=("src/",))
        for p, want in [
            ("src/a.py", True), ("src/x/y", True),
            ("src", False), ("srcx/a", False), ("other/a", False),
        ]:
            self.assertEqual(path_allowed(s, p), want, p)

    def test_invalid_paths(self):
        s = make_spec()
        for p in ("", "/abs", "a\\b", "a/../b", ".", "./a", "a//b", ".."):
            self.assertFalse(path_allowed(s, p), p)


class TestOverlaps(unittest.TestCase):
    def test_disjoint(self):
        a = make_spec(id_="A", files_allowed=("a.py",))
        b = make_spec(id_="B", files_allowed=("b.py",))
        self.assertEqual(overlaps(a, b), [])

    def test_equal(self):
        a = make_spec(id_="A", files_allowed=("a.py",))
        b = make_spec(id_="B", files_allowed=("a.py",))
        self.assertEqual(overlaps(a, b), ["a.py <-> a.py"])

    def test_dir_covers(self):
        a = make_spec(id_="A", files_allowed=("src/",))
        b = make_spec(id_="B", files_allowed=("src/x.py",))
        self.assertEqual(overlaps(a, b), ["src/ <-> src/x.py"])
        self.assertEqual(overlaps(b, a), ["src/x.py <-> src/"])

    def test_dedup_sorted(self):
        a = make_spec(id_="A", files_allowed=("src/", "b.py", "a.py"))
        b = make_spec(id_="B", files_allowed=("src/z.py", "b.py", "src/"))
        self.assertEqual(overlaps(a, b),
                         sorted({"src/ <-> src/z.py", "b.py <-> b.py", "src/ <-> src/"}))


class TestSpecDefaults(unittest.TestCase):
    def test_defaults(self):
        s = parse_spec(spec_text(BASE_FRONT))
        self.assertEqual(
            (s.deps_preapproved, s.contracts, s.blast_radius, s.depends_on,
             s.human_required, s.irreversible, s.budget_usd, s.kind,
             s.pin_model, s.pin_reason),
            ((), (), "low", (), False, False, None, None, None, None),
        )

    def test_frozen(self):
        s = parse_spec(spec_text(BASE_FRONT))
        with self.assertRaises(Exception):
            s.id = "x"


if __name__ == "__main__":
    unittest.main()