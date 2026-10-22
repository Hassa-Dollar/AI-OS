"""Routing (ADR-0031). A local decision model (Clef) classifies the task; a deterministic table decides.

The decision is made once per task, recorded, and re-read by the gate (lesson #4: one resolver). If Ollama is
unavailable, a keyword heuristic produces answers of the same shape, and the record says so (P11).
"""
from __future__ import annotations

import dataclasses
import json
import re
import urllib.error
import urllib.request

from . import catalog

TIERS = catalog.TIERS
CLASSES = {  # conservative options first: Clef breaks ties toward the earlier option
    "security_auth": "authentication, sessions, secrets, crypto, payments, billing, signed webhooks",
    "data_migration": "database schema or data migrations",
    "contract_change": "changes a public API, interface or data contract",
    "hardware": "firmware, device drivers, flashing, hardware interfaces",
    "research": "investigation or a decision memo, no code",
    "infra_ci": "build tooling, CI, scaffolding, project setup",
    "feature_backend": "new server-side or library behavior",
    "feature_frontend": "new UI behavior",
    "bugfix": "fixing incorrect behavior",
    "refactor": "restructuring without behavior change",
    "tests": "only tests",
    "docs": "only documentation",
}
SEC_HUMAN, IRR_HUMAN, HW_HUMAN, CONTRACT_LEAD = 0.8, 0.5, 0.5, 0.6  # calibrated on eval/router (ADR-0031)
BORDERLINE = {"security_sensitive": (0.4, SEC_HUMAN), "irreversible": (0.3, 0.7), "needs_hardware": (0.3, 0.7)}
_VAGUE = re.compile(r"^(it )?(should )?(works?( well| fine| properly| correctly)?|make it (nice|better|good|clean)|"
                    r"looks? (good|nice|better)|as expected|be (good|nice|better|fast))\W*$", re.I)
_CHECKABLE = re.compile(r"`[^`]+`|\b\d{3}\b|\b(returns?|pass(es)?|fails?|exits?|status|equals?|rejects?|writes?)\b"
                        r"|==|->|→", re.I)
CLASS_FLOOR = {"security_auth": "T2", "data_migration": "T2", "contract_change": "T2", "hardware": "T2", "research": "T2"}
KIND_TO_CLASS = {"security": "security_auth", "migration": "data_migration", "infra": "infra_ci",
                 "feature": "feature_backend", "bugfix": "bugfix", "refactor": "refactor", "tests": "tests",
                 "docs": "docs", "research": "research"}
QUESTIONS = {
    "task_class": {"type": "choice", "instructions": "What kind of software task is this?", "criteria": CLASSES},
    "acs_executable": {"type": "score", "instructions": "Can the acceptance criteria be checked by running something?",
                       "criteria": ["not at all", "partly", "mostly", "fully"]},
    "complexity": {"type": "score", "instructions": "How hard is this task for a competent engineer?",
                   "criteria": ["trivial", "simple", "moderate", "hard", "very hard"]},
    "context_breadth": {"type": "score", "instructions": "How much of the codebase must be understood?",
                        "criteria": ["one file", "a few files", "a module", "many modules"]},
    "ambiguity": {"type": "noul", "instructions": "Is the task ambiguous enough that two engineers would build different things?"},
    "contract_change_needed": {"type": "noul", "instructions": "Does the task require changing a public API, schema or interface contract?"},
    "security_sensitive": {"type": "noul", "instructions": "Does the task touch authentication, sessions, secrets, payments, billing or personal data?"},
    "irreversible": {"type": "noul", "instructions": "Could a mistake cause irreversible harm: data loss, money movement, a broken public API, bricked hardware?"},
    "needs_vision": {"type": "noul", "instructions": "Does the task require looking at images, screenshots or designs?"},
    "needs_hardware": {"type": "noul", "instructions": "Does verifying the task require physical hardware?"},
}
_CLASS_KW = [("security_auth", r"\b(auth\w*|login|signup|sign-up|session|password|secret|token|crypto|payment|billing|stripe|"
                                r"webhook|e-?mails?\b|personal data|pii\b|purchase history)"),
             ("data_migration", r"\bmigrat\w*|schema change"), ("contract_change", r"\b(contract|public api|breaking change)"),
             ("hardware", r"\b(firmware|bootloader|gpio|i2c|spi|uart|mcu)\b"), ("research", r"\b(research|memo|investigate)\b"),
             ("docs", r"\b(readme|docs?|documentation|runbook)\b"), ("tests", r"\b(tests?|coverage|e2e)\b"),
             ("feature_frontend", r"\b(ui|page|component|react|css|frontend)\b"), ("infra_ci", r"\b(ci|scaffold\w*|tooling|build)\b"),
             ("bugfix", r"\b(fix|bug|broken|crash)"), ("refactor", r"\brefactor")]


class RouterError(RuntimeError):
    """The classifier could not be reached or answered badly."""


@dataclasses.dataclass
class Decision:
    action: str  # "dispatch" | "refuse"
    gate: str  # AUTO | LEAD | HUMAN (OPERATOR is added later by the gate's size checks)
    tier: str
    task_class: str
    author: str | None
    author_family: str | None
    verifier: str | None
    verifier_family: str | None
    router: str
    confidence: float
    reasons: list[str]
    answers: dict

    def record(self) -> dict:
        return dataclasses.asdict(self)


def state_of(spec, limit: int = 8192) -> str:
    """The classifier's view of a task. Acceptance criteria are never truncated; other prose is shortened to fit."""
    s = spec.sections
    head = {"id": spec.id, "title": spec.title, "kind": spec.kind, "files_allowed": list(spec.files_allowed),
            "deps_preapproved": list(spec.deps_preapproved), "contracts": list(spec.contracts),
            "acceptance_criteria": s.get("acceptance criteria", "")}
    rest = {k: s.get(k, "") for k in ("goal", "context", "out of scope")}
    while len((text := json.dumps(head | rest)).encode()) > limit and any(len(v) > 40 for v in rest.values()):
        k = max(rest, key=lambda k: len(rest[k]))
        rest[k] = rest[k][: len(rest[k]) // 2] + "..."
    return text


def ask_clef(state: str, model: str, host: str, timeout: int = 60) -> dict:
    body = json.dumps({"model": model, "state": state, "questions": QUESTIONS, "keep_alive": "10m"}).encode()
    req = urllib.request.Request(f"{host}/v1/systemone", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            answers = json.load(r)["answers"]
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        e.close()
        raise RouterError(f"{model}: HTTP {e.code} {detail}") from None
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
        raise RouterError(f"{model}: {e}") from None
    if set(answers) != set(QUESTIONS):
        raise RouterError(f"{model}: answered {sorted(answers)}, expected {sorted(QUESTIONS)}")
    return answers


def _score(level: int, n: int) -> dict:
    return {"score": float(level), "probabilities": {str(i): float(i == level) for i in range(n)}, "confidence": 0.5}


def heuristic(spec) -> dict:
    """Keyword fallback in Clef's answer shape, so one decision table serves both paths."""
    text = " ".join([spec.title, *spec.sections.values()]).lower()
    lines = acceptance_lines(spec)
    executable = any(_CHECKABLE.search(line) for line in lines)
    cls = next((c for c, pat in _CLASS_KW if re.search(pat, text)), "feature_backend")

    def noul(pattern: str) -> dict:
        return {"noul": 0.9 if re.search(pattern, text) else 0.05}

    n = len(spec.files_allowed)
    return {"task_class": {"choice": cls, "confidence": 0.5, "probabilities": {cls: 1.0}},
            "acs_executable": _score(3 if executable else 1, 4), "complexity": _score(min(4, 1 + n // 4), 5),
            "context_breadth": _score(min(3, n // 3), 4), "ambiguity": {"noul": 0.1 if executable else 0.5},
            "contract_change_needed": noul(r"\b(contract|public api|breaking change)"),
            "security_sensitive": noul(_CLASS_KW[0][1]),
            "irreversible": noul(r"\b(migrat\w*|drop table|delete data|bootloader|fuses?|ota)\b|production data"),
            "needs_vision": noul(r"\b(screenshot|mockup|figma)"),
            "needs_hardware": noul(r"\b(firmware|flashing|gpio|i2c|uart|bootloader|on-device)\b")}


def classify(spec, *, host: str, model: str = "clef-flash", escalation_model: str | None = "clef",
             threshold: float = 0.6) -> tuple[dict, str]:
    """Clef cascade: flash answers; the 27B gives a second opinion only when a gate-deciding signal is borderline.
    (Low class confidence raises the tier in `decide`; it never needs the slow model.) Heuristic if Ollama is down."""
    state = state_of(spec)
    try:
        answers, used = ask_clef(state, model, host), model
    except RouterError:
        return heuristic(spec), "heuristic"
    decisive = answers["security_sensitive"]["noul"] >= SEC_HUMAN or any(
        answers[k]["noul"] >= BORDERLINE[k][1] for k in ("irreversible", "needs_hardware"))
    borderline = not decisive and any(lo <= answers[k]["noul"] < hi for k, (lo, hi) in BORDERLINE.items())
    if escalation_model and borderline:  # class confidence only moves the tier (decide); the 27B guards the gate
        try:
            second = ask_clef(state, escalation_model, host, timeout=300)
        except RouterError:
            return answers, used  # flash's answer stands
        for k in ("security_sensitive", "irreversible", "needs_hardware", "contract_change_needed"):
            second[k] = {"noul": max(answers[k]["noul"], second[k]["noul"])}  # a second opinion only adds caution
        answers, used = second, escalation_model
    return answers, used


def acceptance_lines(spec) -> list[str]:
    raw = spec.sections.get("acceptance criteria", "")
    return [ln.strip(" \t-*0123456789.)[]x") for ln in raw.splitlines() if ln.strip(" \t-*")]


def spec_gaps(spec, task_class: str, needs_hardware: bool) -> list[str]:
    """P10: whether acceptance criteria can be checked is a property of the text, so code decides it, not a model.
    Hardware, docs and research work may have human-judged criteria; vague ones are never accepted."""
    lines = acceptance_lines(spec)
    if not lines or all(_VAGUE.match(line) for line in lines):
        return ["acceptance criteria are missing or vague"]
    if not any(_CHECKABLE.search(line) for line in lines) and not (needs_hardware or task_class in ("docs", "research")):
        return ["acceptance criteria are not executable"]
    return []


def _at_least(answer: dict, level: int) -> float:
    return sum(p for k, p in (answer.get("probabilities") or {}).items() if int(k) >= level)


def _up(tier: str, to: str) -> str:
    return max(tier, to, key=TIERS.index)


def _pick(roster, live, role, tier, max_tier, deny_vendors, exclude_families=()):
    for t in TIERS[TIERS.index(tier): TIERS.index(max_tier) + 1]:
        if got := catalog.eligible(roster, live, role=role, tier=t, exclude_families=exclude_families,
                                   deny_vendors=deny_vendors, max_tier=max_tier):
            return got[0]
    return None


def decide(spec, answers: dict, *, roster, live, router: str = "clef-flash", max_tier: str = "T3",
           frontier_auto: bool = False, deny_vendors: tuple[str, ...] = (), min_tier: str = "T1",
           confidence_floor: float = 0.6) -> Decision:
    """The ADR-0031 decision table: P1 (route by leverage) made executable."""
    a = answers
    cls = KIND_TO_CLASS.get(spec.kind or "") or a["task_class"]["choice"]
    conf = 1.0 if spec.kind else float(a["task_class"].get("confidence", 0))
    out = Decision("refuse", "LEAD", "T1", cls, None, None, None, None, router, conf, [], a)
    human = [r for r, hit in [("spec says human_required", spec.human_required),
                              ("spec says irreversible", spec.irreversible),
                              ("security-sensitive, blast radius >= medium",
                               a["security_sensitive"]["noul"] > SEC_HUMAN and spec.blast_radius != "low"),
                              ("possibly irreversible", a["irreversible"]["noul"] > IRR_HUMAN),
                              ("needs hardware to verify", a["needs_hardware"]["noul"] > HW_HUMAN)] if hit]
    gaps = spec_gaps(spec, cls, a["needs_hardware"]["noul"] > HW_HUMAN) + \
        (["the task is ambiguous"] if a["ambiguity"]["noul"] > 0.9 else [])
    if gaps:
        out.reasons = [f"spec gap: {g}" for g in gaps]
        return out
    lead = [r for r, hit in [("blast radius high", spec.blast_radius == "high"),
                             ("contract change", a["contract_change_needed"]["noul"] > CONTRACT_LEAD or cls == "contract_change"),
                             (f"model pinned: {spec.pin_reason}", bool(spec.pin_model))] if hit]
    if router == "heuristic":
        lead.append("degraded routing (classifier unavailable): Lead reviews")  # P11: less intelligence, more oversight
    out.gate = "HUMAN" if human else "LEAD" if lead else "AUTO"
    out.reasons = human + lead
    tier = _up(CLASS_FLOOR.get(cls, "T1"), min_tier)
    for reason, hit in [("hard task", _at_least(a["complexity"], 3) > 0.5),
                        ("broad context", _at_least(a["context_breadth"], 3) > 0.5)]:
        if hit:
            tier = _up(tier, "T2")
            out.reasons.append(reason)
    if conf < confidence_floor:
        bumped = TIERS[min(TIERS.index(tier) + 1, 2)]
        tier = min(bumped, "T3" if frontier_auto else _up(tier, "T2"), key=TIERS.index)
        out.reasons.append(f"low classifier confidence ({conf:.2f})")
    out.tier = min(tier, max_tier, key=TIERS.index)
    author = _pick(roster, live, "implement", out.tier, max_tier, deny_vendors)
    if author is None:
        out.reasons.append(f"no eligible implementer at {out.tier}..{max_tier}")
        return out
    vtier = _up(out.tier, "T3" if (human or a["security_sensitive"]["noul"] > SEC_HUMAN) else "T2")
    verifier = _pick(roster, live, "verify", min(vtier, max_tier, key=TIERS.index), max_tier, deny_vendors,
                     exclude_families=(author.family,))
    if verifier is None:
        out.reasons.append(f"P8: no verifier outside family '{author.family}' within {max_tier}")
        return out
    out.action, out.author, out.author_family = "dispatch", author.id, author.family
    out.verifier, out.verifier_family = verifier.id, verifier.family
    return out
