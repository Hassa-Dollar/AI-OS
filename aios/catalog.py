"""The model policy and the live OpenRouter catalog: sync, cache and candidates (ADR-0034).

Routing picks from the whole live catalog (ADR-0034 s3): the cache joins every model with the ones this account may
use, plus their scores, prices and capabilities, and `candidates` ranks them by expected cost. There is no fixed
list of allowed models anywhere in aios (ADR-0034); the policy only holds levels, blocks and families.

Sections:
  1. Cache       the gateway -> every model joined with the usable ones, one JSON file per day
  2. Policy      aios/models.toml + the project's [models] -> levels, blocks, families
  3. Candidates  the cache + a role and a level -> candidates, cheapest expected cost first
"""
from __future__ import annotations

import datetime as dt
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .config import ConfigError, Paths
from .gateway import GatewayError

LEVELS = ("junior", "mid", "senior")
ROLE_NEEDS = {"implementer": "tools", "adversarial_tester": "tools",
              "reviewer": "structured_outputs", "security_reviewer": "structured_outputs"}
ROLE_TOKENS = {"implementer": (300_000, 15_000), "adversarial_tester": (200_000, 10_000),
               "reviewer": (15_000, 5_000), "security_reviewer": (15_000, 5_000)}  # (input, output) per task
DEFAULT_POLICY = Path(__file__).with_name("models.toml")


# --- 1. Cache ----------------------------------------------------------------------------
# From: gateway.models() joined with gateway.models(user=True)
# To:   one models-<day>.json in the cache dir, read back by the router, the CLI and `candidates`
def cache_file(p: Paths, day: dt.date | None = None) -> Path:
    """The cache path for `day` (today by default): <cache>/models-<day>.json."""
    return p.cache / f"models-{(day or dt.date.today()).isoformat()}.json"


def sync(gateway, p: Paths) -> list[dict]:
    """Fetch the catalog, mark which models this account may use, write the cache; return the joined list."""
    usable = {m["id"] for m in gateway.models(user=True)}
    models = [dict(m, usable=m["id"] in usable) for m in gateway.models()]
    p.cache.mkdir(parents=True, exist_ok=True)
    cache_file(p).write_text(json.dumps(models), encoding="utf-8")
    return models


def latest(p: Paths, *, gateway=None, max_age_h: float = 24, out=print) -> list[dict] | None:
    """The newest cache, refreshed through `gateway` when older than `max_age_h`; None when there is no cache."""
    files = sorted(p.cache.glob("models-*.json"))
    if not files:
        return None
    if gateway is not None and dt.datetime.now().timestamp() - files[-1].stat().st_mtime > max_age_h * 3600:
        try:
            sync(gateway, p)
            files = sorted(p.cache.glob("models-*.json"))
        except GatewayError as e:
            out(f"warning: the catalog is {max_age_h:.0f}h old and the refresh failed ({e}); using {files[-1].name}")
    return json.loads(files[-1].read_text(encoding="utf-8"))


def price_per_m(model: dict) -> tuple[float, float]:
    """One catalog model -> its (input, output) USD price per million tokens."""
    pr = model.get("pricing") or {}
    return float(pr.get("prompt") or 0) * 1e6, float(pr.get("completion") or 0) * 1e6


# --- 2. Policy ---------------------------------------------------------------------------
# From: aios/models.toml plus the project's [models] table (contract: models.schema.md)
# To:   one Policy: the level thresholds, the measured blocks, and the family groupings
@dataclass(frozen=True)
class Policy:
    """One policy: the level score floors, the (model id, roles, reason) blocks and the id -> family map."""
    levels: dict[str, float]
    blocks: tuple[tuple[str, frozenset[str], str], ...]   # (model id, roles, reason)
    families: dict[str, str]                               # model id -> family


def _policy(doc: dict, where: str, *, versioned: bool = False
            ) -> tuple[dict[str, float], list[tuple[str, frozenset[str], str]], dict[str, str]]:
    """Validate one policy document (contract: models.schema.md); return its levels, blocks and families."""
    if unknown := set(doc) - {"models_version", "levels", "block", "family"}:
        raise ConfigError(f"{where}: unknown key(s): {', '.join(sorted(unknown))}")
    if doc.get("models_version", 0 if versioned else 1) != 1:
        raise ConfigError(f"{where}: expected models_version = 1")
    t = doc.get("levels") or {}
    if not isinstance(t, dict) or set(t) - set(LEVELS) or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in t.values()):
        raise ConfigError(f"{where} [levels]: numbers keyed by {', '.join(LEVELS)}")
    blocks = []
    for i, b in enumerate(doc.get("block", [])):
        w = f"{where} block[{i}]"
        roles = b.get("roles") or [] if isinstance(b, dict) else []
        if (not isinstance(b, dict) or set(b) - {"model", "roles", "reason", "review_by"}
                or not isinstance(b.get("model"), str) or not b["model"] or not isinstance(roles, list)
                or not roles or set(roles) - set(ROLE_NEEDS)):
            raise ConfigError(f"{w}: needs a 'vendor/model' id, 'roles' from {', '.join(ROLE_NEEDS)}, "
                              "and no other keys")
        blocks.append((b["model"], frozenset(roles), str(b.get("reason", ""))))
    families: dict[str, str] = {}
    for i, f in enumerate(doc.get("family", [])):
        w = f"{where} family[{i}]"
        name, ids = (f.get("family") or "", f.get("models") or []) if isinstance(f, dict) else ("", [])
        if (not isinstance(f, dict) or set(f) - {"family", "models", "reason"} or not isinstance(name, str)
                or not name or not isinstance(ids, list) or not all(isinstance(m, str) and m for m in ids)):
            raise ConfigError(f"{w}: needs a 'family' name, a non-empty 'models' list, and no other keys")
        families |= {m: name for m in ids}
    return {k: float(v) for k, v in t.items()}, blocks, families


def load_policy(path: Path = DEFAULT_POLICY, project: dict | None = None) -> Policy:
    """Read aios/models.toml and merge the project's [models] into it, validating both against the contract."""
    w = str(path)
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"{w}: {e}") from e
    levels, blocks, families = _policy(doc, w, versioned=True)
    if project:
        plevels, pblocks, pfams = _policy(project, "project [models]")
        levels, blocks = {**levels, **plevels}, blocks + pblocks
        families |= pfams  # the project's grouping is the more specific one
    got = [levels[k] for k in LEVELS if k in levels]
    if any(a >= b for a, b in zip(got, got[1:])):
        raise ConfigError(f"{w} [levels]: must increase from junior to mid to senior")
    return Policy(levels, tuple(blocks), families)


def family(model_id: str, policy: Policy) -> str:
    """The [[family]] grouping covering the id, else the vendor prefix of the id."""
    return policy.families.get(model_id) or model_id.split("/", 1)[0]


# --- 3. Candidates -----------------------------------------------------------------------
# From: the joined cache, the policy, and the role's capability and token needs
# To:   Candidate rows for one role at one level (None: any score), cheapest expected cost first
@dataclass(frozen=True)
class Candidate:
    """One model that can fill a role: id, family, scores, prices, limits and its expected task cost."""
    id: str
    family: str
    score: float
    coding: float | None
    agentic: float | None
    usd_in: float    # per million input tokens
    usd_out: float   # per million output tokens
    context: int
    max_out: int | None
    est_usd: float   # expected cost of one task in this role


def _num(v) -> float | None:
    """float(v), or None when v is None (the benchmark indexes may be null)."""
    return None if v is None else float(v)


def _expiring(model: dict, today: dt.date) -> bool:
    """True when the model expires within 14 days of `today` (an unreadable date never blocks one)."""
    raw = str(model.get("expiration_date") or "")
    try:
        return (dt.date.fromisoformat(raw[:10]) - today).days <= 14
    except ValueError:
        return False


def candidates(live: list[dict], *, role: str, level: str | None, policy: Policy, exclude_families=(),
               context_need: int = 0, today: dt.date | None = None) -> list[Candidate]:
    """Models that can fill `role` at `level` (None: no minimum), cheapest expected cost first."""
    # A level of None drops the minimum but never the score: an unscored model is no candidate (ADR-0034 s3).
    if role not in ROLE_NEEDS:
        raise ConfigError(f"unknown role '{role}': one of {', '.join(ROLE_NEEDS)}")
    if level is not None and level not in policy.levels:
        raise ConfigError(f"unknown level '{level}': one of {', '.join(LEVELS)}")
    floor, need, (tin, tout) = policy.levels.get(level, float("-inf")), ROLE_NEEDS[role], ROLE_TOKENS[role]
    blocked = {mid for mid, roles, _ in policy.blocks if role in roles}
    fams, today, out = set(exclude_families), today or dt.date.today(), []
    for m in live:
        aa = (m.get("benchmarks") or {}).get("artificial_analysis") or {}
        score = aa.get("intelligence_index")
        usd_in, usd_out = price_per_m(m)
        if (not m.get("usable") or score is None or float(score) < floor or (usd_in <= 0 and usd_out <= 0)
                or m["id"].startswith("~") or ":" in m["id"] or need not in (m.get("supported_parameters") or [])
                or (m.get("context_length") or 0) < context_need or m["id"] in blocked
                or family(m["id"], policy) in fams or _expiring(m, today)):
            continue
        mx = (m.get("top_provider") or {}).get("max_completion_tokens")
        out.append(Candidate(m["id"], family(m["id"], policy), float(score), _num(aa.get("coding_index")),
                             _num(aa.get("agentic_index")), usd_in, usd_out, int(m.get("context_length") or 0),
                             None if mx is None else int(mx), usd_in * tin / 1e6 + usd_out * tout / 1e6))
    return sorted(out, key=lambda c: (c.est_usd, -c.score, c.id))
