import contextlib
import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path

from aios import catalog, cli, config

NOW = dt.datetime(2026, 10, 21).timestamp()


def live_from(roster, **changes):
    """A live catalog matching `roster`, with per-id overrides."""
    out = [{"id": e.id, "canonical_slug": e.canonical_slug, "created": NOW - 86400 * 200,
            "pricing": {"prompt": str(1e-6 * (i + 1)), "completion": str(2e-6 * (i + 1))}}
           for i, e in enumerate(roster)]
    for m in out:
        m.update(changes.get(m["id"], {}))
    return [m for m in out if not m.get("_drop")]


def roster_file(text):
    f = Path(tempfile.mkdtemp()) / "roster.toml"
    f.write_text("roster_version = 1\n" + text)
    return f


ENTRY = '[[model]]\nid = "a/x"\ntier = "T2"\ncanonical_slug = "a/x-1"\n'


class Roster(unittest.TestCase):
    def test_shipped_roster_is_valid_and_p8_solvable(self):
        roster = catalog.load_roster()
        self.assertGreaterEqual(len(roster), 6)
        verifier_families = {e.family for e in roster if e.tier == "T2" and "verify" in e.roles}
        self.assertGreaterEqual(len(verifier_families), 2, "P8 needs two T2 verifier families")
        for e in roster:
            self.assertTrue(e.canonical_slug.startswith(e.vendor + "/"), e.id)

    def test_defaults(self):
        (e,) = catalog.load_roster(roster_file(ENTRY))
        self.assertEqual((e.family, e.roles, e.vendor), ("a", ("implement", "verify"), "a"))
        (e,) = catalog.load_roster(roster_file(ENTRY + 'family = "lineage"\nroles = ["verify"]\n'))
        self.assertEqual((e.family, e.roles), ("lineage", ("verify",)))

    def test_rejects(self):
        for bad, needle in [(ENTRY.replace('"a/x"', '"~a/x"'), "alias"), (ENTRY.replace('"a/x"', '"a/x:free"'), "alias"),
                            (ENTRY.replace('"T2"', '"T9"'), "tier"), (ENTRY.replace('canonical_slug = "a/x-1"\n', ""), "canonical_slug"),
                            (ENTRY + 'price = 1\n', "unknown"), (ENTRY + 'roles = ["lead"]\n', "roles"),
                            (ENTRY + ENTRY, "duplicate")]:
            with self.assertRaisesRegex(config.ConfigError, needle):
                catalog.load_roster(roster_file(bad))
        with self.assertRaisesRegex(config.ConfigError, "roster_version"):
            f = roster_file(ENTRY)
            f.write_text(ENTRY)
            catalog.load_roster(f)


class Diff(unittest.TestCase):
    roster = catalog.load_roster()

    def test_clean(self):
        d = catalog.diff(self.roster, live_from(self.roster))
        self.assertEqual((d.suspended, d.missing, d.expiring, d.new), ([], [], [], []))

    def test_drift_missing_expiring_and_new(self):
        a, b, c = self.roster[0], self.roster[1], self.roster[2]
        live = live_from(self.roster, **{a.id: {"canonical_slug": a.canonical_slug + "-v2"}, b.id: {"_drop": True},
                                         c.id: {"expiration_date": "2026-12-01"}})
        live += [{"id": f"{a.vendor}/brand-new", "created": NOW, "canonical_slug": "x"},
                 {"id": f"{a.vendor}/brand-new:free", "created": NOW}, {"id": f"~{a.vendor}/latest", "created": NOW},
                 {"id": f"{a.vendor}/ancient", "created": NOW - 86400 * 400}, {"id": "other/new", "created": NOW}]
        d = catalog.diff(self.roster, live)
        self.assertEqual([e.id for e, _ in d.suspended], [a.id])
        self.assertEqual([e.id for e in d.missing], [b.id])
        self.assertEqual(d.expiring, [(c, "2026-12-01")])
        self.assertEqual([m["id"] for m in d.new], [f"{a.vendor}/brand-new"])

    def test_eligible(self):
        live = live_from(self.roster)
        t2 = catalog.eligible(self.roster, live, role="verify", tier="T2")
        self.assertTrue(t2 and all(e.tier == "T2" for e in t2))
        prices = [sum(catalog.price_per_m(next(m for m in live if m["id"] == e.id))) for e in t2]
        self.assertEqual(prices, sorted(prices))
        fam = t2[0].family
        self.assertNotIn(fam, {e.family for e in catalog.eligible(self.roster, live, role="verify", tier="T2",
                                                                     exclude_families=(fam,))})
        self.assertTrue(all(e.tier != "T3" for e in catalog.eligible(self.roster, live, role="verify", max_tier="T2")))
        drifted = live_from(self.roster, **{t2[0].id: {"canonical_slug": "moved"}})
        self.assertNotIn(t2[0].id, [e.id for e in catalog.eligible(self.roster, drifted, role="verify")])
        self.assertNotIn(t2[0].vendor, {e.vendor for e in catalog.eligible(self.roster, live, role="verify",
                                                                           deny_vendors=(t2[0].vendor,))})
        self.assertTrue(all("implement" in e.roles for e in catalog.eligible(self.roster, live, role="implement")))


class Cache(unittest.TestCase):
    def test_sync_and_latest(self):
        p = config.paths({"HOME": tempfile.mkdtemp()})
        self.assertIsNone(catalog.latest(p))

        class FakeGW:
            def models(self):
                return [{"id": "a/x"}]

        self.assertEqual(catalog.sync(FakeGW(), p), [{"id": "a/x"}])
        self.assertEqual(catalog.latest(p), [{"id": "a/x"}])


class ModelsCommand(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_list_and_diff_from_cache(self):
        p = config.paths()  # tests/__init__.py points XDG at a throwaway dir
        for f in p.cache.glob("models-*.json"):
            f.unlink()
        code, _, err = self.run_cli("models", "list")
        self.assertEqual(code, 2)
        self.assertIn("aios models sync", err)
        roster = catalog.load_roster()
        p.cache.mkdir(parents=True, exist_ok=True)
        live = live_from(roster, **{roster[0].id: {"canonical_slug": "moved"}})
        catalog.cache_file(p).write_text(json.dumps(live))
        code, out, _ = self.run_cli("models", "list")
        self.assertEqual(code, 1)
        self.assertIn("SUSPENDED", out)
        code, out, _ = self.run_cli("models", "diff")
        self.assertIn(f"SUSPENDED {roster[0].id}", out)


if __name__ == "__main__":
    unittest.main()
