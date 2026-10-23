"""Tests for the router: the gate, the level, and the two roles filled from the live catalog (ADR-0034)."""
import json
import unittest
from types import SimpleNamespace

from aios import catalog, router
from tests.helpers import clef_answers, fake_http

LEVELS = {"junior": 40.0, "mid": 45.0, "senior": 52.0}
POLICY = catalog.Policy(LEVELS, (), {})
ONE_FAMILY = catalog.Policy(LEVELS, (), {"watch/cheap": "acme"})  # P8: watch/cheap counts as acme


def model(mid, *, score=50.0, pin, pout, usable=True, context=200_000, params=("tools", "structured_outputs")):
    """One joined catalog entry in the shape `catalog.sync` caches (the cache shape, not the roster)."""
    return {"id": mid, "usable": usable, "context_length": context, "supported_parameters": list(params),
            "pricing": {"prompt": pin, "completion": pout},
            "benchmarks": {"artificial_analysis": {"intelligence_index": score}}}


def per_m(pin, pout):
    """The per-million prices a model's `pricing` strings turn into, as `catalog.price_per_m` reads them."""
    return [float(pin) * 1e6, float(pout) * 1e6]


# `acme/econ` is the cheapest junior; `echo/mid` the cheapest mid; `cortex/front` (frontier) the cheapest senior.
# `watch/cheap` scores 36, below every level, so it can only ever be a reviewer. The list is deliberately not in
# price order: `catalog.candidates` does the ranking.
LIVE = [model("acme/econ", score=41.0, pin="0.0000002", pout="0.0000004"),
        model("watch/cheap", score=36.0, pin="0.0000001", pout="0.0000002"),
        model("echo/mid", score=46.0, pin="0.0000003", pout="0.0000006"),
        model("watch/ok", score=44.0, pin="0.0000004", pout="0.0000008"),
        model("cortex/front", score=60.0, pin="0.0000005", pout="0.000001"),
        model("bolt/standard", score=46.0, pin="0.000001", pout="0.000002"),
        model("dune/senior", score=55.0, pin="0.000002", pout="0.000004")]


def spec(**kw):
    base = dict(id="T-1", title="Add a CSV export to the report page", kind=None, blast_radius="low",
                human_required=False, irreversible=False, contracts=(), files_allowed=("src/report.py",),
                deps_preapproved=(), pin_model=None, pin_reason=None,
                sections={"goal": "Export reports as CSV.", "acceptance criteria": "`pytest -q` passes"})
    return SimpleNamespace(**(base | kw))


ans = clef_answers


def decide(s=None, a=None, live=LIVE, policy=POLICY, **kw):
    return router.decide(s or spec(), a or ans(), live=live, policy=policy, **kw)


class DecisionTable(unittest.TestCase):
    def test_routine_feature(self):
        d = decide()
        self.assertEqual((d.action, d.gate, d.level), ("dispatch", "AUTO", "junior"))
        self.assertEqual((d.author, d.author_family), ("acme/econ", "acme"))
        self.assertNotEqual(d.author_family, d.verifier_family)
        self.assertEqual(json.loads(json.dumps(d.record()))["level"], "junior")

    def test_security(self):
        d = decide(spec(blast_radius="medium"), ans("security_auth", security_sensitive=0.95))
        self.assertEqual((d.gate, d.level), ("HUMAN", "senior"))
        d = decide(spec(blast_radius="low"), ans("security_auth", security_sensitive=0.95))
        self.assertEqual((d.gate, d.level), ("AUTO", "senior"))

    def test_spec_flags_and_answers_raise_the_gate(self):
        self.assertEqual(decide(spec(human_required=True)).gate, "HUMAN")
        self.assertEqual(decide(spec(irreversible=True)).gate, "HUMAN")
        self.assertEqual(decide(a=ans(irreversible=0.8)).gate, "HUMAN")
        self.assertEqual(decide(spec(blast_radius="medium"), ans(security_sensitive=0.7)).gate, "AUTO")
        self.assertEqual(decide(a=ans(needs_hardware=0.8)).gate, "HUMAN")
        self.assertEqual(decide(spec(blast_radius="high")).gate, "LEAD")
        self.assertEqual(decide(spec(pin_model="x/y", pin_reason="needs vision")).gate, "LEAD")
        self.assertEqual(decide(a=ans(contract_change_needed=0.9)).gate, "LEAD")

    def test_spec_gaps_refuse_deterministically(self):
        vague = spec(sections={"goal": "g", "acceptance criteria": "- it should work well\n- make it nice"})
        d = decide(vague)
        self.assertEqual((d.action, d.author), ("refuse", None))
        self.assertIn("vague", d.reasons[0])
        prose = spec(sections={"goal": "g", "acceptance criteria": "- the export feels intuitive"})
        self.assertIn("not executable", decide(prose).reasons[0])
        self.assertEqual(decide(prose, ans("docs")).action, "dispatch")  # docs are reviewed, not executed
        self.assertEqual(decide(prose, ans(needs_hardware=0.9)).gate, "HUMAN")  # verified on the bench by a person
        self.assertEqual(decide(a=ans(acs=0)).action, "dispatch")  # the classifier's opinion is advisory
        self.assertIn("ambiguous", decide(a=ans(ambiguity=0.95)).reasons[0])

    def test_spec_kind_overrides_classifier(self):
        d = decide(spec(kind="docs"), ans("security_auth", conf=0.3))
        self.assertEqual((d.task_class, d.confidence, d.level), ("docs", 1.0, "junior"))


class Level(unittest.TestCase):
    def test_class_floor(self):
        for cls in ("security_auth", "data_migration", "contract_change", "hardware", "research"):
            self.assertEqual(decide(a=ans(cls)).level, "mid", cls)  # these classes need judgement
        self.assertEqual(decide(a=ans("security_auth", cx=4)).level, "mid")  # hard alone does not make it senior

    def test_hard_or_broad_needs_mid(self):
        self.assertEqual(decide(a=ans(cx=4)).level, "mid")
        self.assertEqual(decide(a=ans(ctx=3)).level, "mid")
        self.assertEqual(decide(a=ans(cx=4)).reasons, ["hard task"])
        self.assertEqual(decide(a=ans(ctx=3)).reasons, ["broad context"])

    def test_hard_and_broad_needs_senior(self):
        d = decide(a=ans(cx=4, ctx=3))
        self.assertEqual((d.level, d.reasons), ("senior", ["hard task", "broad context"]))

    def test_security_sensitive_needs_senior_even_when_the_gate_stays_auto(self):
        d = decide(a=ans(security_sensitive=0.9))
        self.assertEqual((d.gate, d.level, d.reasons), ("AUTO", "senior", ["security-sensitive task"]))
        self.assertEqual(decide(a=ans(security_sensitive=0.7)).level, "junior")  # below SEC_HUMAN

    def test_the_human_gate_needs_senior(self):
        d = decide(spec(irreversible=True))
        self.assertEqual((d.gate, d.level), ("HUMAN", "senior"))

    def test_low_confidence_raises_one_level(self):
        self.assertEqual(decide(a=ans(conf=0.4)).level, "mid")
        self.assertEqual(decide(a=ans(cx=4, conf=0.4)).level, "senior")
        self.assertEqual(decide(a=ans(cx=4, ctx=3, conf=0.4)).level, "senior")  # senior is the ceiling
        self.assertIn("low classifier confidence", decide(a=ans(conf=0.4)).reasons[-1])


class Roles(unittest.TestCase):
    def test_the_cheapest_candidate_wins_at_each_level(self):
        self.assertEqual(decide().author, "acme/econ")  # junior: 6 candidates at 40+, the cheapest of them
        self.assertEqual(decide(a=ans(cx=4)).author, "echo/mid")  # mid: 4 candidates at 45+
        d = decide(a=ans(cx=4, ctx=3))
        self.assertEqual((d.author, d.roles["implementer"]["why"]),
                         ("cortex/front", "cheapest of 2 candidates at senior"))  # a frontier model, when cheapest

    def test_denied_vendors_are_skipped(self):
        self.assertEqual(decide(deny_vendors=("acme",)).author, "echo/mid")
        d = decide(deny_vendors=("acme", "echo"))
        self.assertEqual((d.author, d.verifier), ("watch/ok", "cortex/front"))  # denied vendors never review

    def test_the_reviewer_is_outside_the_implementers_family(self):
        d = decide(policy=ONE_FAMILY)  # watch/cheap is grouped with acme, so it may not review acme's work
        self.assertEqual((d.author, d.verifier), ("acme/econ", "echo/mid"))

    def test_the_reviewer_must_be_calibrated(self):
        d = decide(reviewer_ok=lambda m: m != "watch/cheap")
        self.assertEqual(d.verifier, "echo/mid")  # the next cheapest calibrated reviewer
        self.assertEqual(decide(reviewer_ok=lambda m: m in ("watch/cheap", "echo/mid")).verifier, "watch/cheap")

    def test_a_senior_task_needs_a_senior_reviewer(self):
        self.assertEqual(decide(a=ans(cx=4, ctx=3)).verifier, "dune/senior")  # watch/cheap scores 36: too junior
        self.assertEqual(decide(a=ans(cx=4)).verifier, "watch/cheap")  # a mid task may still use it

    def test_a_cheap_low_scoring_calibrated_reviewer_wins_a_junior_task(self):
        d = decide()
        self.assertEqual((d.verifier, d.verifier_family), ("watch/cheap", "watch"))
        self.assertEqual(d.roles["reviewer"]["score"], 36.0)

    def test_roles_record_the_choice(self):
        d = decide()
        self.assertEqual(d.roles, {
            "implementer": {"model": "acme/econ", "family": "acme", "level": "junior", "score": 41.0,
                            "usd_per_m": per_m("0.0000002", "0.0000004"), "est_usd": 0.066,
                            "why": "cheapest of 6 candidates at junior"},
            "reviewer": {"model": "watch/cheap", "family": "watch", "level": "any", "score": 36.0,
                         "usd_per_m": per_m("0.0000001", "0.0000002"), "est_usd": 0.0025,
                         "why": "cheapest calibrated reviewer of 6"}})
        self.assertEqual(json.loads(json.dumps(d.record()))["roles"], d.roles)

    def test_the_reviewers_level_is_any_unless_the_task_is_senior(self):
        d = decide()
        self.assertEqual((d.level, d.roles["reviewer"]["level"]), ("junior", "any"))
        self.assertEqual(d.roles["implementer"]["level"], "junior")  # the implementer keeps the task's level
        d = decide(a=ans(cx=4, ctx=3))
        self.assertEqual((d.level, d.roles["reviewer"]["level"]), ("senior", "senior"))
        self.assertEqual(d.roles["implementer"]["level"], "senior")

    def test_refuses_without_an_implementer(self):
        d = decide(live=[])
        self.assertEqual((d.action, d.gate, d.author), ("refuse", "AUTO", None))
        self.assertEqual(d.reasons[-1], "no implementer candidate at junior")
        d = decide(deny_vendors=tuple(m["id"].split("/")[0] for m in LIVE))
        self.assertEqual(d.reasons[-1], "no implementer candidate at junior")

    def test_refuses_without_a_calibrated_reviewer(self):
        d = decide(reviewer_ok=lambda m: False)
        self.assertEqual((d.action, d.author), ("refuse", None))
        self.assertEqual(d.reasons[-1], "no calibrated reviewer outside family 'acme': "
                                         "run 'aios models calibrate watch/cheap echo/mid watch/ok'")

    def test_refuses_when_only_the_implementers_family_can_review(self):
        live = [LIVE[0], model("acme/frontier", score=70.0, pin="0.000002", pout="0.000004")]
        d = decide(live=live)  # every reviewer candidate is in acme, the implementer's family
        self.assertEqual(d.action, "refuse")
        self.assertIn("no calibrated reviewer outside family 'acme'", d.reasons[-1])


class Heuristic(unittest.TestCase):
    def test_shapes_and_signals(self):
        a = router.heuristic(spec(title="Add password reset via email token"))
        self.assertEqual(a["task_class"]["choice"], "security_auth")
        self.assertGreater(a["security_sensitive"]["noul"], 0.5)
        self.assertEqual(set(a), set(router.QUESTIONS))
        self.assertEqual(router.heuristic(spec(title="Update the README"))["task_class"]["choice"], "docs")
        vague = spec(sections={"goal": "make it nicer", "acceptance criteria": "looks good"})
        self.assertEqual(decide(vague, router.heuristic(vague)).action, "refuse")
        d = decide(a=router.heuristic(spec()), router="heuristic")
        self.assertEqual((d.action, d.gate), ("dispatch", "LEAD"))  # degraded routing never auto-merges


class Classifier(unittest.TestCase):
    def test_cascade_only_on_borderline_safety_signals(self):
        log = []
        replies = [(200, {"answers": ans(conf=0.95, needs_hardware=0.45)}), (200, {"answers": ans(conf=0.95)})]
        with fake_http({"POST /v1/systemone": replies}, log) as host:
            a, used = router.classify(spec(), host=host)
        self.assertEqual((used, [r[2]["model"] for r in log]), ("clef", ["clef-flash", "clef"]))
        self.assertEqual(a["needs_hardware"]["noul"], 0.45)  # max of both opinions
        log.clear()
        with fake_http({"POST /v1/systemone": (200, {"answers": ans(conf=0.3)})}, log) as host:
            self.assertEqual(router.classify(spec(), host=host)[1], "clef-flash")
        self.assertEqual(len(log), 1)
        self.assertEqual(set(log[0][2]["questions"]), set(router.QUESTIONS))

    def test_borderline_signal_also_escalates(self):
        log = []
        replies = [(200, {"answers": ans(conf=0.95, security_sensitive=0.5)}),
                   (200, {"answers": ans(conf=0.95, security_sensitive=0.9)})]
        with fake_http({"POST /v1/systemone": replies}, log) as host:
            a, used = router.classify(spec(), host=host)
        self.assertEqual((used, a["security_sensitive"]["noul"]), ("clef", 0.9))
        replies = [(200, {"answers": ans(conf=0.9, irreversible=0.6)}), (200, {"answers": ans(conf=0.9, irreversible=0.1)})]
        with fake_http({"POST /v1/systemone": replies}) as host:
            a, used = router.classify(spec(), host=host)
        self.assertEqual((used, a["irreversible"]["noul"]), ("clef", 0.6))  # the 27B can't erase flash's caution
        log.clear()
        with fake_http({"POST /v1/systemone": (200, {"answers": ans(conf=0.95, security_sensitive=0.9)})}, log) as host:
            router.classify(spec(), host=host)
        self.assertEqual(len(log), 1)  # flash was decisive: no second opinion needed

    def test_falls_back_to_heuristic(self):
        self.assertEqual(router.classify(spec(), host="http://127.0.0.1:9")[1], "heuristic")
        with fake_http({"POST /v1/systemone": (200, {"answers": {"task_class": {}}})}) as host:
            self.assertEqual(router.classify(spec(), host=host)[1], "heuristic")
        with fake_http({"POST /v1/systemone": (500, {"error": "boom"})}) as host:
            self.assertEqual(router.classify(spec(), host=host)[1], "heuristic")


if __name__ == "__main__":
    unittest.main()
