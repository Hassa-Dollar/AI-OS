"""The roster (approved models) and the live OpenRouter catalog: sync, diff, eligibility (ADR-0031).

Routing never looks beyond the roster. The live catalog only tells us prices, and what changed: new models from
roster vendors, silently re-pointed slugs (suspend), and models that are expiring or gone.
"""
from __future__ import annotations

import datetime as dt
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .config import ConfigError, Paths

TIERS = ("T1", "T2", "T3")
ROLES = ("implement", "verify")
DEFAULT_ROSTER = Path(__file__).with_name("roster.toml")


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


def cache_file(p: Paths, day: dt.date | None = None) -> Path:
    return p.cache / f"models-{(day or dt.date.today()).isoformat()}.json"


def sync(gateway, p: Paths) -> list[dict]:
    models = gateway.models()
    p.cache.mkdir(parents=True, exist_ok=True)
    cache_file(p).write_text(json.dumps(models), encoding="utf-8")
    return models


def latest(p: Paths) -> list[dict] | None:
    files = sorted(p.cache.glob("models-*.json"))
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def price_per_m(model: dict) -> tuple[float, float]:
    pr = model.get("pricing") or {}
    return float(pr.get("prompt") or 0) * 1e6, float(pr.get("completion") or 0) * 1e6


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
