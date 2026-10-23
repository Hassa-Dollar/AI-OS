"""The second opinion: a fail counts only when another review confirms it, and the token budget comes from money.

Reviewers fail good code on speculation, so a first `fail` buys one more review from the cheapest calibrated
reviewer of yet another family, and the change fails only when both reviews say `fail`. Each call's `max_tokens`
is what the task's remaining money can pay for at that model's output price, up to the model's own maximum.

Sections:
  1. Tokens     remaining money + a model's output price -> max_tokens for one review call
  2. Confirmer  the live catalog + the calibration cache -> the model that re-reviews a first fail
  3. Review     one or two gate.verify calls -> the verdict the gate records
"""
from __future__ import annotations

from . import calibrate, catalog, gate

MIN_TOKENS = 4096


# --- 1. Tokens ---------------------------------------------------------------------------
# From: the live catalog, the model and the task's remaining money
# To:   max_tokens for one review call, for review() and gate.run_gate
def max_tokens_for(model: str, live: list[dict], usd_left: float) -> int:
    """The tokens the remaining money buys at `model`'s output price, capped by the model, never below MIN_TOKENS."""
    m = next((c for c in live if c["id"] == model), None)
    price = float((m.get("pricing") or {}).get("completion") or 0.0) if m else 0.0
    if price <= 0:
        return gate.VERIFIER_MAX_TOKENS
    n = int(usd_left / price)
    cap = (m.get("top_provider") or {}).get("max_completion_tokens")
    if cap is not None:
        n = min(n, int(cap))
    return max(n, MIN_TOKENS)


# --- 2. Confirmer ------------------------------------------------------------------------
# From: the live catalog, the policy and the calibration cache
# To:   the model that reviews a first fail, for review() and gate.run_gate
def pick_confirmer(p, live: list[dict], policy, *, first: str, exclude_families: tuple[str, ...]) -> str:
    """The cheapest calibrated reviewer outside `exclude_families` that is not `first`; `first` when none exists."""
    for c in catalog.candidates(live, role="reviewer", level=None, policy=policy,
                                exclude_families=exclude_families):
        if c.id != first and calibrate.passed(p, c.id):
            return c.id
    return first


# --- 3. Review ---------------------------------------------------------------------------
# From: the verifier prompt inputs, the gateway, the two models and their max_tokens
# To:   the verdict the gate records, carrying both reviews and who confirmed a fail
def _bare(v: dict) -> dict:
    """A review result without its own `reviews`, so it can be nested inside a verdict."""
    return {k: val for k, val in v.items() if k != "reviews"}


def _worst(a: str, b: str) -> str:
    """The higher of two risks, ranked by gate.RISKS."""
    return gate.RISKS[max(gate.RISKS.index(a), gate.RISKS.index(b))]


def review(gw, model: str, spec_text: str, diff_text: str, checks, *, confirmer: str, max_tokens) -> dict:
    """Reviews the change: a first fail buys one more review, and only two fails fail it."""
    v1 = gate.verify(gw, model, spec_text, diff_text, checks, max_tokens=max_tokens(model))
    if v1["verdict"] != "fail":
        return {**_bare(v1), "reviews": [_bare(v1)]}
    v2 = gate.verify(gw, confirmer, spec_text, diff_text, checks, max_tokens=max_tokens(confirmer))
    reviews = [_bare(v1), _bare(v2)]
    usd = v1["usd"] + v2["usd"]
    if v2["verdict"] != "fail":
        return {"verdict": v2["verdict"], "risk": v2["risk"], "blocking": list(v2["blocking"]),
                "verifier": v2["verifier"], "usd": usd, "reviews": reviews,
                "summary": v2["summary"] + " (A first review failed this change; a second review did not confirm it.)"}
    return {"verdict": "fail", "risk": _worst(v1["risk"], v2["risk"]),
            "blocking": list(v1["blocking"]) + [b for b in v2["blocking"] if b not in v1["blocking"]],
            "summary": v1["summary"], "verifier": model, "confirmed_by": confirmer, "usd": usd, "reviews": reviews}
