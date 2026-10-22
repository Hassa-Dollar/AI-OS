import json
import unittest
from types import SimpleNamespace

from aios import catalog, router
from tests.helpers import clef_answers, fake_http, live_from

ROSTER = catalog.load_roster()
LIVE = live_from(ROSTER)
TIER = {e.id: e.tier for e in ROSTER}


def spec(**kw):
    base = dict(id="T-1", title="Add a CSV export to the report page", kind=None, blast_radius="low",
                human_required=False, irreversible=False, contracts=(), files_allowed=("src/report.py",),
                deps_preapproved=(), pin_model=None, pin_reason=None,
                sections={"goal": "Export reports as CSV.", "acceptance criteria": "`pytest -q` passes"})
    return SimpleNamespace(**(base | kw))


ans = clef_answers


def decide(s=None, a=None, **kw):
    return router.decide(s or spec(), a or ans(), roster=ROSTER, live=LIVE, **kw)


class DecisionTable(unittest.TestCase):
    def test_routine_feature(self):
        d = decide()
        self.assertEqual((d.action, d.gate, d.tier), ("dispatch", "AUTO", "T1"))
        self.assertEqual(TIER[d.author], "T1")
        self.assertEqual(TIER[d.verifier], "T2")
        self.assertNotEqual(d.author_family, d.verifier_family)
        json.dumps(d.record())

    def test_security(self):
        d = decide(spec(blast_radius="medium"), ans("security_auth", security_sensitive=0.95))
        self.assertEqual((d.gate, d.tier, TIER[d.verifier]), ("HUMAN", "T2", "T3"))
        d = decide(spec(blast_radius="low"), ans("security_auth", security_sensitive=0.95))
        self.assertEqual((d.gate, TIER[d.verifier]), ("AUTO", "T3"))

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

    def test_hard_or_broad_tasks_go_to_t2(self):
        self.assertEqual(decide(a=ans(cx=4)).tier, "T2")
        self.assertEqual(decide(a=ans(ctx=3)).tier, "T2")

    def test_low_confidence_bumps_but_frontier_needs_opt_in(self):
        self.assertEqual(decide(a=ans(conf=0.4)).tier, "T2")
        self.assertEqual(decide(a=ans("security_auth", conf=0.4)).tier, "T2")
        self.assertEqual(decide(a=ans("security_auth", conf=0.4), frontier_auto=True).tier, "T3")

    def test_spec_kind_overrides_classifier(self):
        d = decide(spec(kind="docs"), ans("security_auth", conf=0.3))
        self.assertEqual((d.task_class, d.confidence, d.tier), ("docs", 1.0, "T1"))

    def test_limits(self):
        d = decide(max_tier="T1")
        self.assertEqual(d.action, "refuse")
        self.assertIn("P8", d.reasons[-1])
        first = decide().author.split("/")[0]
        self.assertNotEqual(decide(deny_vendors=(first,)).author.split("/")[0], first)

    def test_state_keeps_acceptance_criteria_whole(self):
        acs = "\n".join(f"- criterion {i}: `make test` passes" for i in range(60))
        s = spec(sections={"goal": "g" * 9000, "context": "c" * 9000, "acceptance criteria": acs})
        state = router.state_of(s)
        self.assertLessEqual(len(state.encode()), 8192 + 64)
        self.assertEqual(json.loads(state)["acceptance_criteria"], acs)


class Heuristic(unittest.TestCase):
    def test_shapes_and_signals(self):
        a = router.heuristic(spec(title="Add password reset via email token"))
        self.assertEqual(a["task_class"]["choice"], "security_auth")
        self.assertGreater(a["security_sensitive"]["noul"], 0.5)
        self.assertEqual(set(a), set(router.QUESTIONS))
        self.assertEqual(router.heuristic(spec(title="Update the README")).get("task_class")["choice"], "docs")
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
