"""The model policy and the live OpenRouter catalog: sync, candidates, and the roster diff (ADR-0034).

Routing picks from the whole live catalog (ADR-0034 s3): the cache joins every model with the ones this account may
use, plus their scores, prices and capabilities, and `candidates` ranks them by expected cost. The roster and its
diff are only read by `aios models` now; a later task deletes them.

Sections:
  1. Roster      aios/roster.toml -> approved entries (ADR-0031; `aios models` only until the cleanup task)
  2. Cache       the gateway -> every model joined with the usable ones, one JSON file per day
  3. Policy      aios/models.toml + the project's [models] -> levels, blocks, families
  4. Candidates  the cache + a role and a level -> candidates, cheapest expected cost first
  5. Diff        the roster + the live catalog -> drift and gaps, and who is eligible now
"""
from __future__ import annotations

import datetime as dt
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .config import ConfigError, Paths
from .gateway import GatewayError

TIERS = ("T1", "T2", "T3")
ROLES = ("implement", "verify")
DEFAULT_ROSTER = Path(__file__).with_name("roster.toml")
LEVELS = ("junior", "mid", "senior")
ROLE_NEEDS = {"implementer": "tools", "adversarial_tester": "tools",
              "reviewer": "structured_outputs", "security_reviewer": "structured_outputs"}
ROLE_TOKENS = {"implementer": (300_000, 15_000), "adversarial_tester": (200_000, 10_000),
               "reviewer": (15_000, 5_000), "security_reviewer": (15_000, 5_000)}  # (input, output) per task
DEFAULT_POLICY = Path(__file__).with_name("models.toml")


# --- 1. Roster ---------------------------------------------------------------------------
# From: aios/roster.toml (contract: roster.schema.md)
# To:   Entry tuples for the router, `aios models` and the diff
@dataclass(frozen=True)
class Entry:
    id: str
    tier: str
    canonical_slug: str
    family: str
    roles: tuple[str, ...] = ROLES
    since: str = ""
    note: str = ""

    @property
    def vendor(self) -> str:
        return self.id.split("/", 1)[0]


def load_roster(path: Path = DEFAULT_ROSTER) -> tuple[Entry, ...]:
    w = str(path)
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"{w}: {e}") from e
    if set(doc) - {"roster_version", "model"} or doc.get("roster_version") != 1:
        raise ConfigError(f"{w}: expected roster_version = 1 and [[model]] tables only")
    entries = []
    for i, m in enumerate(doc.get("model", [])):
        where = f"{w} model[{i}]"
        if unknown := set(m) - {"id", "tier", "canonical_slug", "family", "roles", "since", "note"}:
            raise ConfigError(f"{where}: unknown key(s): {', '.join(sorted(unknown))}")
        mid = m.get("id", "")
        if not isinstance(mid, str) or "/" not in mid or mid.startswith("~") or ":" in mid:
            raise ConfigError(f"{where}: 'id' must be an exact 'vendor/model' id (no '~' aliases, no ':variants')")
        if m.get("tier") not in TIERS:
            raise ConfigError(f"{where}: 'tier' must be one of {', '.join(TIERS)}")
        if not isinstance(m.get("canonical_slug"), str) or not m["canonical_slug"]:
            raise ConfigError(f"{where}: 'canonical_slug' is required (it detects silent model drift)")
        roles = tuple(m.get("roles", ROLES))
        if not roles or set(roles) - set(ROLES):
            raise ConfigError(f"{where}: 'roles' must be a non-empty subset of {', '.join(ROLES)}")
        entries.append(Entry(mid, m["tier"], m["canonical_slug"], m.get("family") or mid.split("/", 1)[0], roles,
                             str(m.get("since", "")), str(m.get("note", ""))))
    if len({e.id for e in entries}) != len(entries):
        raise ConfigError(f"{w}: duplicate model ids")
    return tuple(entries)


# --- 2. Cache ----------------------------------------------------------------------------
# From: gateway.models() joined with gateway.models(user=True)
# To:   one models-<day>.json in the cache dir, read back by the router, the CLI and `candidates`
def cache_file(p: Paths, day: dt.date | None = None) -> Path:
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
    pr = model.get("pricing") or {}
    return float(pr.get("prompt") or 0) * 1e6, float(pr.get("completion") or 0) * 1e6


# --- 3. Policy ---------------------------------------------------------------------------
# From: aios/models.toml plus the project's [models] table (contract: models.schema.md)
# To:   one Policy: the level thresholds, the measured blocks, and the family groupings
@dataclass(frozen=True)
class Policy:
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


# --- 4. Candidates -----------------------------------------------------------------------
# From: the joined cache, the policy, and the role's capability and token needs
# To:   Candidate rows for one role at one level (None: any score), cheapest expected cost first
@dataclass(frozen=True)
class Candidate:
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


# --- 5. Diff -----------------------------------------------------------------------------
# From: the roster and the live catalog
# To:   what changed (drift, gaps, expiry, new models) and the entries eligible for a role now
@dataclass
class Diff:
    suspended: list[tuple[Entry, str]] = field(default_factory=list)  # canonical slug moved: silent drift
    missing: list[Entry] = field(default_factory=list)                 # gone from the live catalog
    expiring: list[tuple[Entry, str]] = field(default_factory=list)
    new: list[dict] = field(default_factory=list)                      # from roster vendors, not yet in the roster


def diff(roster: tuple[Entry, ...], live: list[dict]) -> Diff:
    by_id = {m["id"]: m for m in live}
    d = Diff()
    for e in roster:
        m = by_id.get(e.id)
        if m is None:
            d.missing.append(e)
            continue
        if m.get("canonical_slug") != e.canonical_slug:
            d.suspended.append((e, str(m.get("canonical_slug"))))
        if m.get("expiration_date"):
            d.expiring.append((e, str(m["expiration_date"])))
    known, vendors = {e.id for e in roster}, {e.vendor for e in roster}
    newest = max((dt.date.fromisoformat(e.since) for e in roster if e.since), default=dt.date.min)
    cutoff = dt.datetime.combine(newest, dt.time()).timestamp() - 90 * 86400
    d.new = sorted((m for m in live if m["id"].split("/", 1)[0] in vendors and m["id"] not in known
                    and ":" not in m["id"] and not m["id"].startswith("~") and m.get("created", 0) >= cutoff),
                   key=lambda m: -m.get("created", 0))
    return d


def eligible(roster: tuple[Entry, ...], live: list[dict], *, role: str, tier: str | None = None,
             exclude_families: tuple[str, ...] = (), deny_vendors: tuple[str, ...] = (), max_tier: str = "T3"
             ) -> list[Entry]:
    """Roster entries usable now for `role`, cheapest first. Drifted or missing models are never eligible."""
    d = diff(roster, live)
    blocked = {e.id for e, _ in d.suspended} | {e.id for e in d.missing}
    by_id = {m["id"]: m for m in live}
    ok = [e for e in roster if role in e.roles and e.id not in blocked and e.family not in exclude_families
          and e.vendor not in deny_vendors and TIERS.index(e.tier) <= TIERS.index(max_tier)
          and (tier is None or e.tier == tier)]
    return sorted(ok, key=lambda e: sum(price_per_m(by_id[e.id])))
