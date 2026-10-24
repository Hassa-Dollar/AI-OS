"""Reviewer calibration: a model may fill the reviewer role only after it judges known changes right (ADR-0034 s6).

The cases live in `aios/calibration/<case>/` and their right answer is known, so this measures the very call the
gate makes in production (`gate.verify`) and caches the outcome per model on this machine.

Sections:
  1. Cases        aios/calibration/<case>/ -> Case objects, sorted by name; a broken case fails loud
  2. Fingerprint  the verifier prompt + every case -> one sha256 (it invalidates every old result)
  3. Run          gate.verify per case, repeat times each -> Judgments (an error is wrong; never stops early)
  4. Cache        one model's Judgments -> <cache>/calibration.json, other models' entries kept
  5. Verdict      the cache + today + the current fingerprint -> may this model review
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from . import gate, gateway

CASES_DIR = Path(__file__).with_name("calibration")
CACHE_NAME = "calibration.json"


# --- 1. Cases ---------------------------------------------------------------------------
# From: aios/calibration/<case>/{spec.md, change.diff, case.toml}
# To:   Case objects, sorted by name, for run(), fingerprint() and the cache
@dataclass(frozen=True)
class Case:
    """One calibration case: id, expected verdict, spec text, diff text and (command, exit, tail) checks."""
    id: str
    expected: str
    spec_text: str
    diff_text: str
    checks: list[tuple[str, int, str]]


@dataclass(frozen=True)
class Judgment:
    """One judged case: the expected and got verdicts, whether they match, cost, seconds and a note."""
    case: str
    expected: str
    got: str
    right: bool
    usd: float
    secs: int
    note: str  # the first blocking item, or the error text


def _case(directory: Path) -> Case:
    """Read one case folder; a missing file or a bad value raises ValueError naming the case."""
    try:
        doc = tomllib.loads((directory / "case.toml").read_text(encoding="utf-8"))
        spec, diff = ((directory / n).read_text(encoding="utf-8") for n in ("spec.md", "change.diff"))
        checks = [(str(c["command"]), int(c["exit"]), str(c.get("tail") or "")) for c in doc.get("checks") or []]
        if doc.get("expected") not in ("pass", "fail"):
            raise ValueError(f"'expected' must be 'pass' or 'fail', got {doc.get('expected')!r}")
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as e:
        raise ValueError(f"{directory.name}: {e}") from e
    return Case(directory.name, doc["expected"], spec, diff, checks)


def load_cases(directory: Path = CASES_DIR) -> list[Case]:
    """Every case folder in `directory`, sorted by name; raises ValueError naming a broken case."""
    return [_case(d) for d in sorted(directory.iterdir()) if d.is_dir()]


# --- 2. Fingerprint ---------------------------------------------------------------------
# From: aios/prompts/verifier.md (the prompt production uses) and every case's files
# To:   one sha256 hex digest, stored with each model's result in the cache
def fingerprint(cases: list[Case]) -> str:
    """A sha256 over the verifier prompt text and every case's id, expected verdict, spec, diff and checks."""
    blob = gate.VERIFIER_PROMPT.read_text(encoding="utf-8") + "\0".join(json.dumps(asdict(c)) for c in cases)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --- 3. Run -----------------------------------------------------------------------------
# From: the model to calibrate, the cases and the clock
# To:   one Judgment per gate.verify call, for the CLI and the cache
def run(gw, model: str, cases: list[Case], *, repeat: int = 1, clock=time.monotonic) -> list[Judgment]:
    """Judge every case `repeat` times with the production reviewer call; an error is a wrong judgment."""
    if repeat < 1:
        raise ValueError(f"repeat must be at least 1, got {repeat}")
    out = []
    for c in cases:
        for _ in range(repeat):
            t0, got, usd, note = clock(), "error", 0.0, ""
            try:
                v = gate.verify(gw, model, c.spec_text, c.diff_text, c.checks)
                got, usd, note = v["verdict"], float(v.get("usd") or 0.0), next(iter(v["blocking"]), "")
            except (ValueError, gateway.GatewayError) as e:
                note = str(e)
            out.append(Judgment(c.id, c.expected, got, got == c.expected, usd, int(clock() - t0), note))
    return out


# --- 4. Cache ---------------------------------------------------------------------------
# From: one model's Judgments and the cases they judged
# To:   <cache>/calibration.json, one entry per model, every other model's entry kept
def _load(p) -> dict:
    """The cached results keyed by model id; {} when there is none yet, a malformed file fails loud."""
    f = p.cache / CACHE_NAME
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise ValueError(f"{f}: {e}") from e
    return data


def save(p, model: str, judgments: list[Judgment], cases: list[Case], *, today: dt.date | None = None) -> None:
    """Write or update `model`'s entry in `<cache>/calibration.json`, keeping every other model's entry."""
    data = _load(p)
    data[model] = {"date": (today or dt.date.today()).isoformat(), "fingerprint": fingerprint(cases),
                   "right": sum(j.right for j in judgments), "total": len(judgments),
                   "usd": round(sum(j.usd for j in judgments), 6), "secs": sum(j.secs for j in judgments)}
    p.cache.mkdir(parents=True, exist_ok=True)
    (p.cache / CACHE_NAME).write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


# --- 5. Verdict -------------------------------------------------------------------------
# From: the cache, today's date and the current cases (or the shipped ones)
# To:   one bool: this model may fill the reviewer role now
def passed(p, model: str, cases: list[Case] | None = None, *, max_age_days: int = 30,
           today: dt.date | None = None) -> bool:
    """True only when `model` judged every case right, at most `max_age_days` ago, under the current prompt."""
    e = _load(p).get(model)
    if not isinstance(e, dict) or not e.get("total") or e.get("right") != e.get("total"):
        return False
    try:
        age = (today or dt.date.today()) - dt.date.fromisoformat(str(e.get("date") or ""))
        return age.days <= max_age_days and e.get("fingerprint") == fingerprint(cases or load_cases())
    except ValueError:
        return False
