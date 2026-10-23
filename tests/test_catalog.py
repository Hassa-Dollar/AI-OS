import contextlib
import datetime as dt
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aios import catalog, cli, config, gateway
from tests.helpers import NOW, fake_http, live_from

def roster_file(text):
    f = Path(tempfile.mkdtemp()) / "roster.toml"
    f.write_text("roster_version = 1\n" + text)
    return f


ENTRY = '[[model]]\nid = "a/x"\ntier = "T2"\ncanonical_slug = "a/x-1"\n'

LEVELS = "[levels]\njunior = 40\nmid = 45\nsenior = 52\n"


def policy_file(text: str) -> Path:
    f = Path(tempfile.mkdtemp()) / "models.toml"
    f.write_text(text if "models_version" in text else "models_version = 1\n" + text)
    return f


def policy(text: str = LEVELS, project: dict | None = None) -> catalog.Policy:
    return catalog.load_policy(policy_file(text), project)


def model(mid: str, *, score: float | None = 50.0, coding: float | None = 60.0, agentic: float | None = 55.0,
          pin="0.000001", pout="0.000002", context=200_000, params=("tools", "structured_outputs"),
          usable=True, expires=None, **extra) -> dict:
    """One joined catalog entry in the shape OpenRouter serves and `catalog.sync` stores."""
    m = {"id": mid, "usable": usable, "context_length": context, "supported_parameters": list(params),
         "pricing": {"prompt": pin, "completion": pout}, "top_provider": {"max_completion_tokens": 64_000},
         "expiration_date": expires}
    if score is not None:
        m["benchmarks"] = {"artificial_analysis": {"intelligence_index": score, "coding_index": coding,
                                                   "agentic_index": agentic}}
    m.update(extra)
    return m


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


class FakeGW:
    """A gateway stub that records which endpoint `sync` used, and can pretend the network is down."""

    def __init__(self, every=(), user=(), error=False):
        self.every, self.user, self.error, self.calls = list(every), list(user), error, []

    def models(self, *, user=False):
        self.calls.append("user" if user else "all")
        if self.error:
            raise gateway.GatewayError(None, "offline")
        return list(self.user if user else self.every)


class Join(unittest.TestCase):
    def test_gateway_models_user_hits_the_user_endpoint(self):
        log = []
        routes = {"/models": (200, {"data": []}), "/models/user": (200, {"data": [{"id": "a/x"}]})}
        with fake_http(routes, log) as base:
            g = gateway.Gateway("sk-or-v1-t", base=base, backoff=0)
            self.assertEqual((g.models(user=True), g.models()), ([{"id": "a/x"}], []))
        self.assertEqual([(m, p) for m, p, _ in log], [("GET", "/models/user"), ("GET", "/models")])

    def test_sync_joins_the_catalog_with_the_usable_models(self):
        p = config.paths({"HOME": tempfile.mkdtemp()})
        routes = {"/models": (200, {"data": [{"id": "a/x"}, {"id": "b/y"}]}),
                  "/models/user": (200, {"data": [{"id": "a/x"}]})}
        with fake_http(routes) as base:
            live = catalog.sync(gateway.Gateway("sk-or-v1-t", base=base, backoff=0), p)
        self.assertEqual([(m["id"], m["usable"]) for m in live], [("a/x", True), ("b/y", False)])
        self.assertEqual(catalog.latest(p), live)

    def test_no_cache_returns_none_even_with_a_gateway(self):
        p = config.paths({"HOME": tempfile.mkdtemp()})
        gw = FakeGW([{"id": "a/x"}], [{"id": "a/x"}])
        self.assertIsNone(catalog.latest(p, gateway=gw))
        self.assertEqual(gw.calls, [])


class Freshness(unittest.TestCase):
    def setUp(self):
        self.p = config.paths({"HOME": tempfile.mkdtemp()})
        self.gw = FakeGW([{"id": "new/x"}], [{"id": "new/x"}])

    def cache(self, models, *, age_h: float = 0.0) -> Path:
        self.p.cache.mkdir(parents=True, exist_ok=True)
        f = catalog.cache_file(self.p)
        f.write_text(json.dumps(models), encoding="utf-8")
        if age_h:
            when = dt.datetime.now().timestamp() - age_h * 3600
            os.utime(f, (when, when))
        return f

    def test_a_fresh_cache_is_not_refreshed(self):
        self.cache([{"id": "old/x"}])
        self.assertEqual(catalog.latest(self.p, gateway=self.gw), [{"id": "old/x"}])
        self.assertEqual(self.gw.calls, [])

    def test_a_stale_cache_is_refreshed(self):
        self.cache([{"id": "old/x"}], age_h=25)
        self.assertEqual(catalog.latest(self.p, gateway=self.gw), [{"id": "new/x", "usable": True}])
        self.assertEqual(len(self.gw.calls), 2)

    def test_max_age_h_zero_forces_a_refresh(self):
        self.cache([{"id": "old/x"}])
        self.assertEqual([m["id"] for m in catalog.latest(self.p, gateway=self.gw, max_age_h=0)], ["new/x"])

    def test_offline_keeps_the_old_cache_and_warns_once(self):
        self.cache([{"id": "old/x"}], age_h=25)
        gw, buf = FakeGW(error=True), io.StringIO()
        self.assertEqual(catalog.latest(self.p, gateway=gw, out=buf.write), [{"id": "old/x"}])
        self.assertEqual(len(gw.calls), 1)
        self.assertIn("warning", buf.getvalue())


class Candidates(unittest.TestCase):
    def setUp(self):
        self.pol = policy()
        self.live = [model("cheap/a", pin="0.000001", pout="0.000002"),
                     model("cheap/b", pin="0.000002", pout="0.000004"),
                     model("cheap/c", pin="0.000004", pout="0.000008")]

    def pick(self, live=None, role="implementer", level="junior", **kw):
        live = self.live if live is None else live
        return [c.id for c in catalog.candidates(live, role=role, level=level, **{"policy": self.pol, **kw})]

    def test_usable_score_and_price(self):
        self.assertEqual(self.pick(), ["cheap/a", "cheap/b", "cheap/c"])
        self.assertEqual(self.pick([model("cheap/a", usable=False), *self.live[1:]]), ["cheap/b", "cheap/c"])
        self.assertEqual(self.pick([model("cheap/a", score=39.9)]), [])
        self.assertEqual(self.pick([model("cheap/a", score=40)]), ["cheap/a"])
        self.assertEqual(self.pick([model("cheap/a", score=None)]), [])
        self.assertEqual(self.pick(level="senior"), [])
        self.assertEqual(self.pick([model("cheap/a", pin="0", pout="0")]), [])
        self.assertEqual(self.pick([model("cheap/a", pin="0")]), ["cheap/a"])
        self.assertEqual(self.pick([model("cheap/a", pout="0")]), ["cheap/a"])

    def test_aliases_variants_and_expiry(self):
        self.assertEqual(self.pick([model("~cheap/a"), model("cheap/b:free"), model("cheap/c")]), ["cheap/c"])
        today = dt.date(2026, 10, 22)
        soon = (today + dt.timedelta(days=13)).isoformat()
        far = (today + dt.timedelta(days=15)).isoformat()
        live = [model("cheap/a", expires=soon), model("cheap/b", expires=far), model("cheap/c", expires="2026-10-01")]
        self.assertEqual(self.pick(live, today=today), ["cheap/b"])

    def test_capability_context_block_and_family(self):
        self.assertEqual(self.pick([model("cheap/a", params=("tools",))]), ["cheap/a"])
        self.assertEqual(self.pick([model("cheap/a", params=("tools",))], role="reviewer"), [])
        self.assertEqual(self.pick([model("cheap/a", params=("structured_outputs",))], role="reviewer"), ["cheap/a"])
        self.assertEqual(self.pick(context_need=100_000), ["cheap/a", "cheap/b", "cheap/c"])
        self.assertEqual(self.pick(context_need=200_001), [])
        blocked = policy(LEVELS + '[[block]]\nmodel = "cheap/a"\nroles = ["implementer"]\nreason = "measured"\n')
        self.assertEqual(self.pick(policy=blocked), ["cheap/b", "cheap/c"])
        self.assertEqual(self.pick(policy=blocked, role="reviewer"), ["cheap/a", "cheap/b", "cheap/c"])
        self.assertEqual(self.pick(exclude_families=("cheap",)), [])
        grouped = policy(LEVELS + '[[family]]\nfamily = "lineage"\nmodels = ["cheap/a", "cheap/b"]\n'
                                  'reason = "a fine-tune"\n')
        self.assertEqual(self.pick(policy=grouped, exclude_families=("lineage",)), ["cheap/c"])
        self.assertEqual([c.family for c in catalog.candidates(self.live, role="implementer", level="junior",
                                                               policy=grouped)], ["lineage", "lineage", "cheap"])

    def test_order_and_estimated_cost(self):
        est = {c.id: round(c.est_usd, 6) for c in catalog.candidates(self.live, role="implementer", level="junior",
                                                                    policy=self.pol)}
        self.assertEqual(est, {"cheap/a": 0.33, "cheap/b": 0.66, "cheap/c": 1.32})  # 300K in / 15K out
        self.assertEqual(self.pick(), ["cheap/a", "cheap/b", "cheap/c"])
        tie = [model("cheap/z", pin="0.000001", pout="0.000002", score=51),
               model("cheap/a", pin="0.000001", pout="0.000002", score=51),
               model("cheap/m", pin="0.000001", pout="0.000002", score=49)]
        self.assertEqual(self.pick(tie), ["cheap/a", "cheap/z", "cheap/m"])
        reviewer = [model("cheap/a", pin="0.000001", pout="0.000002")]
        self.assertEqual(round(catalog.candidates(reviewer, role="reviewer", level="junior",
                                                 policy=self.pol)[0].est_usd, 6), 0.025)  # 15K in / 5K out
        self.assertEqual(self.pick([model("cheap/a", context=1_000_000, params=("tools",))],
                                   context_need=500_000), ["cheap/a"])

    def test_candidate_fields_and_unknown_role_or_level(self):
        (c,) = catalog.candidates([model("cheap/a", context=400_000, score=41.5, coding=None, agentic=None,
                                         top_provider={})], role="implementer", level="junior",
                                  policy=self.pol)
        self.assertEqual((c.id, c.family, c.score, c.coding, c.agentic, c.context, c.max_out),
                         ("cheap/a", "cheap", 41.5, None, None, 400_000, None))
        with self.assertRaisesRegex(config.ConfigError, "role"):
            catalog.candidates([], role="lead", level="junior", policy=self.pol)
        with self.assertRaisesRegex(config.ConfigError, "level"):
            catalog.candidates([], role="implementer", level="T2", policy=self.pol)


class Policy(unittest.TestCase):
    def test_shipped_policy_loads(self):
        p = catalog.load_policy()
        self.assertEqual(p.levels, {"junior": 40.0, "mid": 45.0, "senior": 52.0})
        self.assertEqual((p.blocks, p.families), ((), {}))

    def test_blocks_and_families(self):
        text = (LEVELS + '[[block]]\nmodel = "a/x"\nroles = ["reviewer", "security_reviewer"]\n'
                'reason = "measured"\nreview_by = "2026-12-31"\n'
                '[[family]]\nfamily = "lineage"\nmodels = ["a/x", "b/y"]\nreason = "a fine-tune"\n')
        p = policy(text)
        self.assertEqual(p.blocks, (("a/x", frozenset(["reviewer", "security_reviewer"]), "measured"),))
        self.assertEqual(p.families, {"a/x": "lineage", "b/y": "lineage"})
        self.assertEqual((catalog.family("a/x", p), catalog.family("b/y", p), catalog.family("c/z", p)),
                         ("lineage", "lineage", "c"))
        self.assertEqual(catalog.family("~a/x", p), "~a")

    def test_rejects(self):
        for bad, needle in [('junk = 1\n', "unknown"), (LEVELS + '[[block]]\nmodel = "a/x"\nroles = ["lead"]\n'
                                                        'reason = "x"\n', "roles"),
                            (LEVELS + '[[block]]\nroles = ["reviewer"]\nreason = "x"\n', "model"),
                            ("[levels]\njunior = 45\nmid = 45\nsenior = 52\n", "increase"),
                            ("[levels]\njunior = 40\nmid = 45\nsenior = 30\n", "increase"),
                            ('[levels]\njunior = "40"\n', "levels"),
                            ("models_version = 2\n" + LEVELS, "models_version")]:
            with self.assertRaisesRegex(config.ConfigError, needle):
                catalog.load_policy(policy_file(bad))
        with self.assertRaisesRegex(config.ConfigError, "models_version"):
            catalog.load_policy(policy_file("[levels]\njunior = 40\nmid = 45\nsenior = 52\n"), {"models_version": 2})

    def test_project_merge(self):
        project = {"levels": {"junior": 30, "mid": 35, "senior": 40},
                   "block": [{"model": "b/y", "roles": ["implementer"], "reason": "measured"}],
                   "family": [{"family": "lineage", "models": ["a/x", "b/y"], "reason": "a fine-tune"}]}
        p = policy(LEVELS + '[[block]]\nmodel = "a/x"\nroles = ["reviewer"]\nreason = "measured"\n', project)
        self.assertEqual(p.levels, {"junior": 30.0, "mid": 35.0, "senior": 40.0})
        self.assertEqual([b[0] for b in p.blocks], ["a/x", "b/y"])
        self.assertEqual(p.families, {"a/x": "lineage", "b/y": "lineage"})
        with self.assertRaisesRegex(config.ConfigError, "unknown"):
            catalog.load_policy(policy_file(LEVELS), {"junk": 1})


class ModelsCommand(unittest.TestCase):
    def setUp(self):
        state = Path(tempfile.mkdtemp())
        env = mock.patch.dict(os.environ, {f"XDG_{k}_HOME": str(state / k)
                                           for k in ("CONFIG", "CACHE", "STATE", "DATA")})
        env.start()
        self.addCleanup(env.stop)
        self.p = config.paths()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def cache(self, models, *, age_h: float = 0.0):
        self.p.cache.mkdir(parents=True, exist_ok=True)
        f = catalog.cache_file(self.p)
        f.write_text(json.dumps(models), encoding="utf-8")
        if age_h:
            when = dt.datetime.now().timestamp() - age_h * 3600
            os.utime(f, (when, when))
        return f

    def test_list_prints_candidates_per_role_and_level_and_credits_the_scores(self):
        self.p.cache.mkdir(parents=True, exist_ok=True)
        live = live_from(catalog.load_roster()) + [model(f"cheap/{n}", pin=f"0.00000{i}", pout="0.000002")
                                                   for i, n in enumerate("abcd", start=1)]
        catalog.cache_file(self.p).write_text(json.dumps(live))
        roles = ("implementer", "adversarial_tester", "reviewer", "security_reviewer")
        for argv in (("models",), ("models", "list")):
            code, out, _ = self.run_cli(*argv)
            self.assertEqual(code, 0, out)
            self.assertEqual([l.split(":")[0] for l in out.splitlines() if l.startswith(roles)],
                             [f"{r} {v}" for r in roles for v in ("junior", "mid", "senior")])
            self.assertIn("implementer junior: cheap/a (score 50.0, $1.00/$2.00 per M, ~$0.33 per task) | "
                          "cheap/b (score 50.0, $2.00/$2.00 per M, ~$0.63 per task) | "
                          "cheap/c (score 50.0, $3.00/$2.00 per M, ~$0.93 per task)", out)
            self.assertNotIn("cheap/d", out)  # only the three cheapest are shown
            self.assertIn("Quality scores: Artificial Analysis (artificialanalysis.ai), via OpenRouter.", out)

    def test_list_and_diff_from_cache(self):
        code, _, err = self.run_cli("models", "list")
        self.assertEqual(code, 2)
        self.assertIn("aios models sync", err)
        roster = catalog.load_roster()
        self.p.cache.mkdir(parents=True, exist_ok=True)
        live = live_from(roster, **{roster[0].id: {"canonical_slug": "moved"}})
        catalog.cache_file(self.p).write_text(json.dumps(live))
        code, out, _ = self.run_cli("models", "list")
        self.assertEqual(code, 1)
        self.assertIn("SUSPENDED", out)
        self.assertIn("Quality scores: Artificial Analysis", out)
        code, out, _ = self.run_cli("models", "diff")
        self.assertIn(f"SUSPENDED {roster[0].id}", out)

    def test_sync_writes_the_joined_cache(self):
        self.p.config.mkdir(parents=True, exist_ok=True)
        self.p.credentials.write_text("sk-or-v1-test")
        os.chmod(self.p.credentials, 0o600)
        routes = {"/models": (200, {"data": [model("a/x")]}), "/models/user": (200, {"data": [{"id": "a/x"}]})}
        with fake_http(routes) as base, mock.patch.dict(os.environ, {"AIOS_OPENROUTER_URL": base}):
            code, out, _ = self.run_cli("models", "sync")
        self.assertEqual(code, 1)  # the roster models are missing from this one-model catalog
        self.assertIn("synced 1 models", out)
        self.assertEqual([(m["id"], m["usable"]) for m in catalog.latest(self.p)], [("a/x", True)])

    def test_a_stale_cache_is_refreshed_only_when_there_is_a_key(self):
        self.cache([model("old/x", usable=False)], age_h=25)
        self.run_cli("models", "list")  # no key stored: no refresh, and the cache is used as it is
        self.assertEqual([m["id"] for m in catalog.latest(self.p)], ["old/x"])
        self.p.config.mkdir(parents=True, exist_ok=True)
        self.p.credentials.write_text("sk-or-v1-test")
        os.chmod(self.p.credentials, 0o600)
        routes = {"/models": (200, {"data": [model("a/x")]}), "/models/user": (200, {"data": [{"id": "a/x"}]})}
        with fake_http(routes) as base, mock.patch.dict(os.environ, {"AIOS_OPENROUTER_URL": base}):
            code, out, _ = self.run_cli("models", "list")
        self.assertIn("implementer junior: a/x", out)
        self.assertEqual([(m["id"], m["usable"]) for m in catalog.latest(self.p)], [("a/x", True)])


if __name__ == "__main__":
    unittest.main()
