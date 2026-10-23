"""Tests for `aios review`: the token budget from money, the confirmer, and the two-review verdict."""
import unittest
from unittest import mock

from aios import gate, review

LIVE = [{"id": "a/a1", "pricing": {"completion": "0.000002"}, "top_provider": {"max_completion_tokens": 8192}},
        {"id": "a/a2", "pricing": {"completion": "0.000004"}, "top_provider": {"max_completion_tokens": None}},
        {"id": "b/b1", "pricing": {"completion": "0"}, "top_provider": {"max_completion_tokens": 8192}},
        {"id": "c/c1", "pricing": {"completion": "0.000001"}}]

FIRST = "a/a1"
CONFIRMER = "b/b1"


class Cand:
    """A stand-in for one catalog.Candidate, with just the id review uses."""

    def __init__(self, id: str):  # noqa: A002
        self.id = id


class FakeGW:
    """A gateway whose chat() answers with the canned verdicts in order, remembering every call."""

    def __init__(self, verdicts):
        self.calls = []
        self.verdicts = list(verdicts)

    def chat(self, model, messages, schema=None, max_tokens=None):
        self.calls.append({"model": model, "max_tokens": max_tokens})
        v = dict(self.verdicts.pop(0))
        v["verifier"] = model
        return {"json": v, "usd": 0.0123}


def fail(blocking=("bug",), risk="medium", summary="it is broken"):
    """A canned failing verdict."""
    return {"verdict": "fail", "risk": risk, "blocking": list(blocking), "summary": summary}


def ok(summary="all clear"):
    """A canned passing verdict."""
    return {"verdict": "pass", "risk": "low", "blocking": [], "summary": summary}


def confirmer_of(cands, calibrated):
    """patch catalog.candidates and calibrate.passed, then return what pick_confirmer chose."""
    with mock.patch.object(review.catalog, "candidates", return_value=[Cand(c) for c in cands]) as cands_m, \
            mock.patch.object(review.calibrate, "passed", side_effect=lambda p, m: m in calibrated):
        got = review.pick_confirmer(None, LIVE, None, first=FIRST, exclude_families=("x",))
    cands_m.assert_called_once_with(LIVE, role="reviewer", level=None, policy=None, exclude_families=("x",))
    return got


class MaxTokens(unittest.TestCase):
    def test_money_bound_and_capped_by_the_model(self):
        self.assertEqual(review.max_tokens_for(FIRST, LIVE, 0.012), 6000)
        self.assertEqual(review.max_tokens_for(FIRST, LIVE, 0.02), 8192)

    def test_floored_and_uncapped_when_the_model_has_no_maximum(self):
        self.assertEqual(review.max_tokens_for(FIRST, LIVE, 0.0001), review.MIN_TOKENS)
        self.assertEqual(review.max_tokens_for("a/a2", LIVE, 1000.0), 250_000_000)

    def test_unknown_model_or_zero_price_falls_back_to_the_fixed_cap(self):
        self.assertEqual(review.max_tokens_for("nope/none", LIVE, 1000.0), gate.VERIFIER_MAX_TOKENS)
        self.assertEqual(review.max_tokens_for("b/b1", LIVE, 1000.0), gate.VERIFIER_MAX_TOKENS)
        self.assertEqual(review.max_tokens_for(FIRST, [], 1000.0), gate.VERIFIER_MAX_TOKENS)


class PickConfirmer(unittest.TestCase):
    def test_cheapest_calibrated_reviewer_of_another_family(self):
        self.assertEqual(confirmer_of(["a/a1", "b/b1"], {"b/b1"}), "b/b1")

    def test_skips_an_uncalibrated_model_and_falls_back_to_first(self):
        self.assertEqual(confirmer_of(["a/a1", "b/b1"], {}), FIRST)
        self.assertEqual(confirmer_of(["a/a1", "b/b1"], {"a/a1"}), FIRST)

    def test_calibrated_but_priced_out_of_the_first_candidates_family(self):
        self.assertEqual(confirmer_of(["b/b1", "a/a1"], {"b/b1"}), "b/b1")


class Review(unittest.TestCase):
    def run_review(self, verdicts):
        gw = FakeGW(verdicts)
        out = review.review(gw, FIRST, "SPEC", "DIFF", [], confirmer=CONFIRMER,
                            max_tokens=lambda m: 1234 if m == FIRST else 4096)
        return out, gw

    def test_a_pass_makes_one_call(self):
        out, gw = self.run_review([ok()])
        self.assertEqual(out["verdict"], "pass")
        self.assertEqual(len(gw.calls), 1)
        self.assertEqual(gw.calls[0]["max_tokens"], 1234)
        self.assertEqual(out["reviews"], [{**ok(), "verifier": FIRST, "usd": 0.0123}])

    def test_two_fails_confirm_a_fail_with_merged_blocking_and_both_reviews(self):
        out, gw = self.run_review([fail(("bug",), risk="medium", summary="first says no"),
                                   fail(("late", "bug"), risk="high", summary="second says no")])
        self.assertEqual(out["verdict"], "fail")
        self.assertEqual(out["risk"], "high")
        self.assertEqual(out["blocking"], ["bug", "late"])
        self.assertEqual(out["summary"], "first says no")
        self.assertEqual(out["verifier"], FIRST)
        self.assertEqual(out["confirmed_by"], CONFIRMER)
        self.assertEqual(out["usd"], 0.0246)
        self.assertEqual([r["verdict"] for r in out["reviews"]], ["fail", "fail"])
        self.assertEqual([c["model"] for c in gw.calls], [FIRST, CONFIRMER])
        self.assertEqual([c["max_tokens"] for c in gw.calls], [1234, 4096])

    def test_a_pass_from_the_second_review_overrides_the_first(self):
        out, gw = self.run_review([fail(("bug",), summary="first says no"), ok(summary="second is sure")])
        self.assertEqual(out["verdict"], "pass")
        self.assertEqual(out["risk"], "low")
        self.assertEqual(out["blocking"], [])
        self.assertEqual(out["verifier"], CONFIRMER)
        self.assertNotIn("confirmed_by", out)
        self.assertEqual(out["usd"], 0.0246)
        self.assertEqual(out["summary"], "second is sure (A first review failed this change; "
                                          "a second review did not confirm it.)")
        self.assertEqual([r["verdict"] for r in out["reviews"]], ["fail", "pass"])

    def test_needs_decision_from_the_second_review_wins(self):
        out, _ = self.run_review([fail(), {"verdict": "needs_decision", "risk": "high",
                                           "blocking": ["ask"], "summary": "not sure"}])
        self.assertEqual(out["verdict"], "needs_decision")
        self.assertEqual(out["risk"], "high")
        self.assertEqual(out["blocking"], ["ask"])
        self.assertEqual(out["usd"], 0.0246)


if __name__ == "__main__":
    unittest.main()
